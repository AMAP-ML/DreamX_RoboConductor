#!/usr/bin/env python3
"""Verify published metrics, public references, media bundles and page structure."""
import json
import hashlib
import os
import re
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from build_page_data import (confirmed_outcome, digest_bytes, digest_file, jsonp,
                             resolve_real_entry, resolve_remote, unique_index, verify_cache)

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'
DATA = json.loads((DIST / 'data' / 'page-data.json').read_text())
HTML = (DIST / 'index.html').read_text()
CATALOG = json.loads((DIST / 'archive' / 'catalog.js').read_text().split('=', 1)[1].strip().rstrip(';'))
ARCHIVE_EPISODES = unique_index([episode for platform in CATALOG['platforms']
                                 for task in platform['tasks'] for episode in task['episodes']],
                                lambda episode: episode['id'])
SITE = json.loads((DIST / 'data' / 'episodes.json').read_text())
CACHE = ROOT / 'scripts' / 'cache'
verify_cache(CACHE)
PROVENANCE = unique_index(json.loads((CACHE / 'evaluation-provenance.json').read_text()), lambda e: e['id'])
assert set(PROVENANCE) == set(ARCHIVE_EPISODES)
for archive_id, episode in ARCHIVE_EPISODES.items():
    proof = PROVENANCE[archive_id]
    source = DIST / 'archive' / episode['data_file']
    assert source.is_file()
    # Provenance pins the source viewer bytes. Public image-path rewrites can change
    # serialized data.js bytes, so verify identity/fields and actual manual text below.
    assert re.fullmatch(r'[0-9a-f]{64}', proof['dataSha256']), archive_id
    detail = jsonp(source)
    assert detail['id'] == archive_id and detail['task'] == episode['task'] == proof['task']
    for field in ('instruction', 'turns', 'model', 'reasoning_effort', 'evaluation'):
        assert detail.get(field) == episode.get(field), (archive_id, field)
    assert detail.get('model') == proof.get('model')
    assert detail.get('reasoning_effort') == proof.get('reasoningEffort')
    assert detail.get('evaluation') == proof.get('operatorEvaluation')
    assert detail['backend'] == episode['backend'] == proof['backend']
    manual = detail.get('manual') or {}
    assert isinstance(manual.get('text'), str) and manual['text'].strip(), archive_id
    assert digest_bytes(manual['text'].encode()) == manual.get('sha256') == proof.get('manualSha256'), archive_id

assert resolve_remote('https://example.test/showcase/', 'episodes/id/data.js') == 'https://example.test/showcase/episodes/id/data.js'
for unsafe in ('http://example.test/data.js', 'https://other.test/data.js', '//other.test/data.js',
               '/data.js', '../data.js', 'episodes/%2e%2e/data.js', 'episodes\\data.js',
               'data.js?query=1', 'data.js#fragment'):
    try:
        resolve_remote('https://example.test/showcase/', unsafe)
    except ValueError:
        pass
    else:
        raise AssertionError(f'unsafe viewer path accepted: {unsafe}')


def public_path(value):
    return isinstance(value, str) and value.startswith(('media/', 'downloads/', 'data/', 'assets/'))


def walk(value, paths):
    if isinstance(value, dict):
        for child in value.values():
            walk(child, paths)
    elif isinstance(value, list):
        for child in value:
            walk(child, paths)
    elif public_path(value):
        paths.add(value)


assert DATA['provenance']['archiveEpisodes'] == DATA['provenance']['episodesWithVerifiedTaskManuals'] == len(ARCHIVE_EPISODES)
assert DATA['provenance']['cacheManifestSha256'] == digest_file(CACHE / 'cache-manifest.json')
assert re.fullmatch(r'[0-9a-f]{64}', DATA['provenance']['cacheManifestSha256'])
sim = DATA['simulation']
assert (sim['taskCount'], sim['trials'], sim['successes'], sim['failures']) == (50, 500, 411, 89)
assert len(sim['tasks']) == 50 and all(t['trials'] == len(t['outcomes']) == 10 for t in sim['tasks'])
assert sum(t['successes'] for t in sim['tasks']) == 411
assert sim['perfectTasks'] == sum(t['successes'] == 10 for t in sim['tasks']) == 23
assert sum(len(t['outcomes']) for t in sim['tasks']) == 500
assert sum(o['success'] for t in sim['tasks'] for o in t['outcomes']) == 411
assert len(sim['featured']) == 6
assert len(ARCHIVE_EPISODES) == 500 + len(SITE['episodes'])
for task in sim['tasks']:
    for outcome in task['outcomes']:
        episode = ARCHIVE_EPISODES[outcome['id']]
        assert episode['backend'] == 'robotwin' and episode['task'] == task['id']
        assert (DIST / 'archive' / episode['data_file']).is_file()

real = DATA['real']
real_tasks = unique_index(real['tasks'], lambda task: task['id'])
site_tasks = unique_index(SITE['tasks'], lambda task: task['id'])
assert set(real_tasks) == set(site_tasks)
episodes = [e for task in real['tasks'] for e in task['episodes']]
real_by_id = unique_index(episodes, lambda e: e['id'])
site_by_id = unique_index(SITE['episodes'], lambda e: e['id'])
assert set(real_by_id) == set(site_by_id)
real_by_archive = unique_index(episodes, lambda e: e['archiveId'])
archive_real = {key: e for key, e in ARCHIVE_EPISODES.items() if e['backend'] == 'piper'}
assert set(real_by_archive) == set(archive_real)
canonical_cases = [e['canonicalCase'] for e in episodes if e.get('canonicalCase')]
assert len(canonical_cases) == len(set(canonical_cases))
assert real['trials'] == len(episodes) == SITE['site']['episodeCount']
assert real['taskCount'] == len(real_tasks) == SITE['site']['taskCount']
assert SITE['site']['realWorldAvailableTaskCount'] == len(real_tasks)
assert all(e['outcome'] in {'success', 'failure', 'unlabelled'} for e in episodes)
successes = sum(e['outcome'] == 'success' for e in episodes)
confirmed = sum(e['outcome'] in {'success', 'failure'} for e in episodes)
unknown = sum(e['outcome'] == 'unlabelled' for e in episodes)
assert real['successes'] == successes
assert real['confirmedTrials'] == confirmed and real['unknownTrials'] == unknown
assert confirmed + unknown == len(episodes)
assert sum(confirmed_outcome(e.get('evaluation')) == 'success' for e in archive_real.values()) == successes
assert sum(confirmed_outcome(e.get('evaluation')) != 'unlabelled' for e in archive_real.values()) == confirmed
assert sum(confirmed_outcome(e.get('evaluation')) == 'unlabelled' for e in archive_real.values()) == unknown
for task in real['tasks']:
    assert len(task['episodes']) == sum(e['task'] == task['id'] for e in SITE['episodes'])
    instructions = list(dict.fromkeys(e['instructionZh'] for e in task['episodes']))
    assert task['instructionVariants'] == instructions
    assert task['instructionZh'] == instructions[0]
    for item in task['episodes']:
        site_item = site_by_id[item['id']]
        episode = ARCHIVE_EPISODES[item['archiveId']]
        proof = PROVENANCE[item['archiveId']]
        assert resolve_real_entry(site_item, ARCHIVE_EPISODES)['id'] == item['archiveId']
        assert site_item['task'] == episode['task'] == task['id']
        assert episode['backend'] == 'piper'
        assert item['outcome'] == confirmed_outcome(episode.get('evaluation')) == confirmed_outcome(proof.get('operatorEvaluation'))
        assert site_item.get('outcome', 'unlabelled') == item['outcome']
        assert item['model'] == episode.get('model') == proof.get('model')
        assert item['reasoningEffort'] == episode.get('reasoning_effort') == proof.get('reasoningEffort')
        assert item['manualSha256'] == proof['manualSha256']
        assert item['turns'] == episode['turns']
        assert item['instructionZh'] == episode['instruction']
        assert item['video'] == site_item['video'] and item['poster'] == site_item['poster']
        if site_item.get('canonicalCase'):
            assert item['canonicalCase'] == site_item['canonicalCase']

walkthrough = DATA['walkthrough']
assert (walkthrough['id'], walkthrough['turns'], walkthrough['commandSteps']) == ('741b3424896812a02b42', 8, 9)
assert len(walkthrough['steps']) == 9 and walkthrough['steps'][-1]['success'] is True
raw_walkthrough = (ROOT / 'scripts/cache/episode-741b3424896812a02b42.js').read_text()
raw_walkthrough = json.loads(raw_walkthrough[raw_walkthrough.index('(') + 1:raw_walkthrough.rfind(')')])
for step, original in zip(walkthrough['steps'], raw_walkthrough['steps']):
    for field, source in [('narration', 'narration'), ('rawCommands', 'commands'),
                          ('rawResults', 'command_results'), ('robotState', 'robot_state'),
                          ('timestamp', 'time'), ('eventIndex', 'event_index'),
                          ('doneReason', 'done_reason')]:
        assert step[field] == original[source], (step['turn'], field)
assert sum(len(step['rawCommands']) for step in walkthrough['steps']) == 9
assert walkthrough['steps'][-1]['rawResults'][0]['target_reached'] is False
assert walkthrough['steps'][-1]['rawResults'][0]['position_error_cm'] == 13.363

paths = set(re.findall(r'(?:href|src)="([^"#]+)', HTML))
walk(DATA, paths)


def public_target(path):
    target = DIST / path.split('?', 1)[0].split('#', 1)[0]
    return target / 'index.html' if target.is_dir() else target


missing = sorted(path for path in paths if not re.match(r'^[a-z]+:', path) and not public_target(path).is_file())
assert not missing, missing
assert all(public_target(path).stat().st_size for path in paths if public_target(path).is_file())
web_media_path = DIST / 'data/web-media.json'
if web_media_path.exists():
    web_media = json.loads(web_media_path.read_text())['assets']
    assert DATA['media'] == web_media
    for source, entry in web_media.items():
        assert public_target(source).is_file()
        assert public_target(entry['src']).is_file()
        assert public_target(entry['src']).stat().st_size == entry['bytes']
        if source.endswith('.mp4'):
            assert digest_file(public_target(source)) == entry['sourceSha256']
            assert entry['bytes'] <= entry['sourceBytes']
        if 'thumbnail' in entry:
            assert public_target(entry['thumbnail']).is_file()
ids = re.findall(r'\bid="([^"]+)"', HTML)
assert len(ids) == len(set(ids))
assert 'id="resources"' not in HTML and 'href="#resources"' not in HTML
assert '<p class="kicker" id="method-title">Introduction</p>' in HTML
assert not re.search(r'<a\b[^>]*(?:\bdownload\b|href="downloads/)', HTML)
archive_html = (DIST / 'archive' / 'index.html').read_text()
archive_js = (DIST / 'archive' / 'app.js').read_text()
archive_ids = re.findall(r'\bid="([^"]+)"', archive_html)
assert len(archive_ids) == len(set(archive_ids))
assert set(re.findall(r"\$\('([^']+)'\)", archive_js)) <= set(archive_ids)
assert 'Reproduction status' not in HTML and 'not bundled with this snapshot' not in HTML
assert 'SHA256' not in archive_html + archive_js and 'Snapshot:' not in archive_js
assert 'color-scheme: light' in (DIST / 'archive' / 'style.css').read_text()
hero_links = re.search(r'<div class="hero-links">([\s\S]*?)</div>', HTML).group(1)
assert not re.search(r'<a\b', hero_links)
assert hero_links.count('aria-disabled="true"') == 2
assert 'arXiv' in hero_links and 'GitHub' in hero_links
assert hero_links.count('>Coming soon<') == 2
assert 'example.com' not in hero_links
assert all(name in HTML for name in ('hero-sim-video', 'hero-real-video', 'case-study'))
assert re.findall(r'data-hero-kind="([^"]+)"', HTML) == ['real-world'] * 4 + ['simulation'] * 4
fixed_videos = re.findall(r'<video\b[^>]*data-hero-kind="([^"]+)"[^>]*data-hero-episode="([^"]+)"[^>]*>', HTML)
assert len(fixed_videos) == 8
assert 'assets/hero-playlist.js' not in HTML
real_by_id = {item['id']: (task, item) for task in real['tasks'] for item in task['episodes']}
assert [real_by_id[record_id][0]['id'] for kind, record_id in fixed_videos if kind == 'real-world'] == ['put_pen', 'hang_cup', 'stack_three_bowls', 'empty_cup']
assert all(real_by_id[record_id][1]['outcome'] == 'success' for kind, record_id in fixed_videos if kind == 'real-world')
assert len({record_id for _, record_id in fixed_videos}) == 8
assert all(record_id in {item['id'] for item in sim['featured']} for kind, record_id in fixed_videos if kind == 'simulation')
primary = re.search(r'<button[^>]*class="result-card primary-result"[^>]*>([\s\S]*?)</button>', HTML).group(1)
assert 'Piper' in primary and 'data-bind="real.rate"' in primary
spotlight = HTML[HTML.index('class="result-spotlight"'):HTML.index('<details class="matrix-details"')]
assert spotlight.count('data-results-kind=') == 2 and 'result-context' not in spotlight
assert spotlight.count('aria-controls="results-matrix"') == 2
method_start = HTML.index('id="method"')
method = HTML[method_start:HTML.index('</section>', method_start)]
assert method_start < HTML.index('id="simulation"') < HTML.index('id="results"')
assert 'class="method-summary"' in method and '<figure' not in method and '<details' not in method
assert method.count('data-lang-only=') == 2 and '<strong>' in method
assert 'Forethought' not in method and 'mental rehearsal' not in method
assert 'behavior-study' not in HTML and 'Feedback changes the next action' not in HTML
comparison = json.loads((DIST / 'data/method-comparison.json').read_text())
ranking = sorted(comparison['entries'], key=lambda row: row['successRate'], reverse=True)
assert len(ranking) == len({row['id'] for row in ranking}) == 19
assert ranking[0]['id'] == 'roboconductor' and ranking[0]['successRate'] == 82.2
assert ranking[1]['id'] == 'go3-nano-preview' and ranking[1]['successRate'] == 81.48
assert ranking[1]['context'] == 'Full set' and ranking[1]['displayPrecision'] == 1
assert comparison['axis'] == [0, 100] and all(0 <= row['successRate'] <= 100 for row in ranking)
assert sorted(row['context'] for row in ranking if row['id'].startswith('robodawn')) == ['0-shot', '0-shot', '1-shot', '1-shot']
assert ranking[0]['context'] == '0-shot'
assert 'id="comparison"' in HTML and HTML.count('class="comparison-ours"') == 1
for asset in ('c2r-comparison.svg', 'c2r-comparison.png', 'c2r-comparison-mobile.svg', 'c2r-comparison-mobile.png'):
    assert (DIST / 'media/comparison' / asset).is_file()
paper_sources = json.loads((ROOT / 'scripts/paper-method-provenance.json').read_text())
for item in paper_sources['diagramAssets'] + paper_sources['behaviorFrames']:
    assert hashlib.sha256((DIST / item['asset']).read_bytes()).hexdigest() == item['sha256']
for item in paper_sources['behaviorFrames']:
    assert (DIST / item['asset']).read_bytes() == (DIST / item['source']).read_bytes()
assert '<details class="matrix-details" id="results-matrix" open>' in HTML and 'style=' not in HTML

with zipfile.ZipFile(DIST / 'downloads' / 'simulation-highlights.zip') as archive:
    assert len([name for name in archive.namelist() if name.endswith('.mp4')]) == 6
    assert archive.testzip() is None
assert SITE['site']['videoZip'] == 'downloads/piper-videos.zip'
with zipfile.ZipFile(DIST / 'downloads' / 'piper-videos.zip') as archive:
    videos = [name for name in archive.namelist() if name.endswith('.mp4')]
    assert len(videos) == len(set(videos)) == len(episodes)
    assert {Path(name).name for name in videos} == {Path(e['video']).name for e in episodes}
    for item in episodes:
        member = next(name for name in videos if Path(name).name == Path(item['video']).name)
        assert archive.read(member) == (DIST / item['video']).read_bytes(), item['id']
    assert archive.testzip() is None
from build_public_release import release_entries, ARCHIVE_ROOT
expected_source = release_entries(ROOT)
with zipfile.ZipFile(DIST / 'downloads' / 'piper-showcase-source.zip') as archive:
    names = set(archive.namelist())
    assert archive.testzip() is None
    assert names == {ARCHIVE_ROOT + '/' + path for path in expected_source}
    for relative, expected in expected_source.items():
        assert archive.read(ARCHIVE_ROOT + '/' + relative) == expected, relative
    assert all(not path.endswith(('.mp4', '.jpg', '.png', '.zip')) for path in names)
    assert ARCHIVE_ROOT + '/LICENSE' in names
    assert ARCHIVE_ROOT + '/NOTICE' in names
    assert not any('/.git/' in path or '/.aoneci/' in path or '/cache/' in path for path in names)

from verify_archive_english import verify as verify_english
assert verify_english()['episodes'] == len(ARCHIVE_EPISODES)

print(json.dumps({'publicFilesReferenced': len(paths), 'simulation': '411/500',
                  'perfectSimulationTasks': 23, 'realWorld': f'{successes}/{len(episodes)}',
                  'confirmedTrials': confirmed, 'unknownTrials': unknown,
                  'walkthroughSteps': 9, 'status': 'ok'}))
