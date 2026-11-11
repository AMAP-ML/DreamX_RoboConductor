#!/usr/bin/env python3
"""Build dist/data/page-data.json from verified evaluation snapshots.

Inputs are read-only: scripts/simulation-summary.json, scripts/operator-records.json,
dist/data/episodes.json, and hash-pinned evaluation-viewer snapshots in scripts/cache/.
Pass --refresh through HTTPS or a localhost SSH tunnel to rebuild the cache and verify
a task manual for every archived episode.
"""
import argparse
import hashlib
import json
import re
import statistics
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VIEWER = 'http://127.0.0.1:18080/'
WALKTHROUGH_ID = '741b3424896812a02b42'
CACHE_FILES = ('catalog.js', f'episode-{WALKTHROUGH_ID}.js', 'evaluation-provenance.json')
INSTRUCTIONS_EN = {
    'put_pen': 'Pick up the blue pen on the box and insert it into the pen holder on the right.',
    'put_phone': 'Pick up the phone on the box and place it on the phone stand on the right.',
    'discard_blackboard_eraser': 'Discard the blackboard eraser.',
    'empty_cup': 'Empty the cup.',
    'hang_cup': 'Hang the cup.',
    'place_gum_bottle': 'Place the gum bottle.',
    'stack_three_bowls': 'Stack three bowls.',
}
MANUAL_EN = {
    'note': 'English translation of the generated manual; the original is in Chinese.',
    'task': [
        ['Instruction', 'Lift the bottle with red screw cap from the table using the left arm.'],
        ['Task', "The target is a drink bottle with a red screw cap lying sideways near the front of the table. Use the left arm to pick it up and move it toward the robot's left side."],
        ['Success criteria', "The bottle must leave the table, rise into the air near the left gripper's initial height, and move outward to the robot's left, away from the center of the table. Lifting it slightly in place does not count."],
    ],
    'tips': [
        "Consider grasping from above on a straight, evenly wide section of the bottle, avoiding the tapered shoulder and the base. Close the gripper across the bottle's long axis to reduce slipping and pushing.",
        'Descend in small steps and use the cameras to confirm the chosen section sits between the finger pads before closing. If the view is occluded, adjust slightly or change the viewpoint first.',
        'After closing, lift slightly and check that the bottle moves with the gripper before raising it further and moving left, leaving clearance from the table and nearby objects.',
    ],
}


def parse_jsonp(raw):
    start = min(i for i in (raw.find('{'), raw.find('[')) if i >= 0)
    return json.loads(raw[start:max(raw.rfind('}'), raw.rfind(']')) + 1])


def jsonp(path):
    return parse_jsonp(path.read_text())


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def digest_file(path):
    return digest_bytes(path.read_bytes())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def resolve_remote(base, remote):
    if not isinstance(remote, str) or not remote:
        raise ValueError('Viewer path must be a non-empty relative URL')
    parsed = urllib.parse.urlsplit(remote)
    decoded = urllib.parse.unquote(parsed.path, errors='strict')
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or parsed.path.startswith('/'):
        raise ValueError(f'Viewer path must be relative: {remote!r}')
    if '\\' in decoded or '..' in decoded.split('/'):
        raise ValueError(f'Viewer path escapes the viewer base: {remote!r}')
    target = urllib.parse.urlsplit(urllib.parse.urljoin(base, parsed.path))
    origin = urllib.parse.urlsplit(base)
    if (target.scheme, target.hostname, target.port) != (origin.scheme, origin.hostname, origin.port):
        raise ValueError(f'Viewer path changes origin: {remote!r}')
    base_path = origin.path if origin.path.endswith('/') else origin.path + '/'
    if not target.path.startswith(base_path):
        raise ValueError(f'Viewer path leaves the viewer base: {remote!r}')
    return target.geturl()


def fetch(base, remote):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(resolve_remote(base, remote), timeout=60) as response:
        return response.read()


def refresh_cache(cache, base):
    parsed = urllib.parse.urlsplit(base)
    local = parsed.hostname in {'127.0.0.1', 'localhost', '::1'}
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and local):
        raise ValueError('Viewer refresh requires HTTPS or an SSH tunnel exposed on localhost')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Viewer base must not contain credentials, query, or fragment')
    base = base.rstrip('/') + '/'
    cache.mkdir(parents=True, exist_ok=True)
    catalog_bytes = fetch(base, 'catalog.js')
    catalog = parse_jsonp(catalog_bytes.decode())
    entries = [episode for task in catalog['tasks'] for episode in task['episodes']]

    def summarize(entry):
        raw = fetch(base, entry['data_file'])
        detail = parse_jsonp(raw.decode())
        assert detail['id'] == entry['id'] and detail.get('model') == entry.get('model')
        manual = detail.get('manual') or {}
        text = manual.get('text')
        if not isinstance(text, str) or not text.strip() or digest_bytes(text.encode()) != manual.get('sha256'):
            raise ValueError(f"Missing or invalid task manual for {entry['id']}")
        return {
            'id': entry['id'], 'dataSha256': digest_bytes(raw), 'backend': detail['backend'],
            'platformName': detail['platform_name'], 'task': detail['task'],
            'model': detail.get('model'), 'reasoningEffort': detail.get('reasoning_effort'),
            'taskConfig': detail.get('task_config'), 'resultSource': detail['result_source'],
            'archiveStatus': detail['archive_status'], 'manualSha256': manual['sha256'],
            'manualMode': manual.get('mode'), 'success': detail.get('success'),
            'operatorEvaluation': detail.get('evaluation'),
        }

    with ThreadPoolExecutor(max_workers=12) as pool:
        provenance = sorted(pool.map(summarize, entries), key=lambda item: item['id'])
    walkthrough_entry = next(entry for entry in entries if entry['id'] == WALKTHROUGH_ID)
    walkthrough = fetch(base, walkthrough_entry['data_file'])
    (cache / 'catalog.js').write_bytes(catalog_bytes)
    (cache / f'episode-{WALKTHROUGH_ID}.js').write_bytes(walkthrough)
    (cache / 'evaluation-provenance.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=1) + '\n')
    manifest = {name: digest_file(cache / name) for name in CACHE_FILES}
    (cache / 'cache-manifest.json').write_text(json.dumps({'transport': 'HTTPS or SSH-tunneled localhost', 'sha256': manifest}, indent=1) + '\n')


def verify_cache(cache):
    manifest = json.loads((cache / 'cache-manifest.json').read_text())['sha256']
    if set(manifest) != set(CACHE_FILES):
        raise ValueError('Cache manifest does not cover every required snapshot')
    for name, expected in manifest.items():
        actual = digest_file(cache / name)
        if actual != expected:
            raise ValueError(f'Cached snapshot hash mismatch: {name}')


def unique_index(rows, key):
    result = {}
    for row in rows:
        value = key(row)
        if value in result:
            raise ValueError(f'Duplicate episode identity: {value}')
        result[value] = row
    return result


def confirmed_outcome(evaluation):
    evaluation = evaluation or {}
    if evaluation.get('status') != 'confirmed' or not isinstance(evaluation.get('success'), bool):
        return 'unlabelled'
    if evaluation.get('source') != 'operator':
        raise ValueError('Confirmed real-world result must identify its operator source')
    return 'success' if evaluation['success'] is True else 'failure'


def operator_aliases(records):
    aliases = {}
    for record in records:
        for key in ('archiveId', 'record_id', 'canonicalCase', 'case'):
            value = record.get(key)
            if not value:
                continue
            for alias in (value, value.rstrip('/').split('/')[-1]):
                if alias in aliases and aliases[alias] is not record:
                    raise ValueError(f'Ambiguous operator identity: {alias}')
                aliases[alias] = record
    return aliases


def resolve_real_entry(ep, viewer):
    archive_id = ep.get('archiveId')
    if archive_id:
        entry = viewer[archive_id]
    else:
        canonical = ep.get('canonicalCase')
        candidates = [entry for entry in viewer.values() if entry.get('backend') == 'piper'
                      and (entry.get('record_id') == ep['id'] or entry['id'] == ep['id']
                           or (canonical and canonical in (entry.get('canonicalCase'), entry.get('case'), entry.get('record'))))]
        if not candidates and not canonical and ep['task'] in {'put_pen', 'put_phone'} and ep['id'].startswith('piper-eval-202610'):
            # Compatibility only for the original ten episodes, which predate archive IDs.
            legacy = ep['id'].split('-')[2]
            if legacy in {'20261019', '20261020', '20261022'}:
                scene = int(str(ep['scene']).split('_')[-1])
                candidates = [entry for entry in viewer.values() if entry.get('backend') == 'piper'
                              and entry['task'] == ep['task'] and int(entry['scene_id']) == scene]
        if len(candidates) != 1:
            raise ValueError(f"Expected one stable archive identity for {ep['id']}, found {len(candidates)}")
        entry = candidates[0]
    if entry.get('backend') != 'piper' or entry['task'] != ep['task']:
        raise ValueError(f"Archive identity/task mismatch for {ep['id']}")
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true', help='re-download and hash the viewer cache first')
    parser.add_argument('--viewer-base', default=DEFAULT_VIEWER,
                        help='HTTPS viewer URL or SSH-tunneled localhost URL used only with --refresh')
    args = parser.parse_args()
    cache = ROOT / 'scripts' / 'cache'
    if args.refresh:
        refresh_cache(cache, args.viewer_base)
    verify_cache(cache)

    summary = json.loads((ROOT / 'scripts' / 'simulation-summary.json').read_text())
    site = json.loads((ROOT / 'dist' / 'data' / 'episodes.json').read_text())
    operator = operator_aliases(json.loads((ROOT / 'scripts' / 'operator-records.json').read_text()))
    catalog = jsonp(cache / 'catalog.js')
    viewer = unique_index([e for t in catalog['tasks'] for e in t['episodes']], lambda e: e['id'])
    provenance = unique_index(json.loads((cache / 'evaluation-provenance.json').read_text()), lambda e: e['id'])
    if set(provenance) != set(viewer):
        raise ValueError('Per-episode provenance does not match the viewer catalog')

    records = summary['records']
    assert len(records) == summary['caseCount'] == 500
    names = {t['id']: t['name'] for t in site['simulation']['tasks']}
    tasks = {}
    for r in records:
        entry = viewer[r['id']]
        proof = provenance[r['id']]
        assert entry['model'] == proof['model'] == 'gpt-6-astra'
        assert entry['reasoning_effort'] == proof['reasoningEffort'] == 'xhigh'
        assert entry['task_config'] == proof['taskConfig'] == 'demo_randomized'
        assert entry['result_source'] == proof['resultSource'] == 'official'
        assert proof['backend'] == 'robotwin' and proof['archiveStatus'] == 'complete'
        assert proof['manualSha256'] and proof['success'] == (r['outcome'] == 'success')
        tasks.setdefault(r['task'], []).append({
            'seed': r['official']['seed'], 'success': r['outcome'] == 'success',
            'turns': r['official']['turns'], 'id': r['id']})
    task_rows = []
    for task_id, trials in sorted(tasks.items()):
        trials.sort(key=lambda t: t['seed'])
        assert len(trials) == 10
        task_rows.append({'id': task_id, 'name': names[task_id], 'trials': len(trials),
                          'successes': sum(t['success'] for t in trials),
                          'outcomes': [{'id': t['id'], 'seed': t['seed'], 'success': t['success'], 'turns': t['turns']}
                                       for t in trials]})
    successes = sum(t['successes'] for t in task_rows)
    assert successes == summary['success'] == 411
    turns_ok = [r['official']['turns'] for r in records if r['outcome'] == 'success']
    turns_bad = [r['official']['turns'] for r in records if r['outcome'] == 'failure']
    reasons = Counter(r['official'].get('done_reason') for r in records if r['outcome'] == 'failure')
    dates = sorted(r['record'].split('/')[4].split('-')[2] for r in records)
    seeds = [r['official']['seed'] for r in records]
    by_id = {r['id']: r for r in records}
    rates = {t['id']: t for t in task_rows}
    featured = []
    for f in site['simulation']['featured']:
        r = by_id[f['id']]
        assert r['outcome'] == 'success'
        featured.append({**f, 'seed': r['official']['seed'], 'turns': r['official']['turns'],
                         'taskSuccesses': rates[f['task']]['successes'], 'taskTrials': rates[f['task']]['trials']})

    real_tasks = []
    unique_index(site['episodes'], lambda e: e['id'])
    used_archive_ids = set()
    for task in site['tasks']:
        episodes, instructions = [], []
        for ep in (e for e in site['episodes'] if e['task'] == task['id']):
            entry = resolve_real_entry(ep, viewer)
            if entry['id'] in used_archive_ids:
                raise ValueError(f"Archive episode reused: {entry['id']}")
            used_archive_ids.add(entry['id'])
            proof = provenance[entry['id']]
            matches = [operator[key] for key in (ep.get('archiveId'), entry['id'], ep['id'], ep.get('canonicalCase')) if key in operator]
            if matches and any(record is not matches[0] for record in matches):
                raise ValueError(f"Conflicting operator identities: {ep['id']}")
            record = matches[0] if matches else {}
            evaluations = [record.get('evaluation'), entry.get('evaluation'), proof.get('operatorEvaluation')]
            available = [evaluation for evaluation in evaluations if evaluation is not None]
            outcomes = {confirmed_outcome(evaluation) for evaluation in available}
            if len(outcomes) > 1:
                raise ValueError(f"Conflicting operator results: {ep['id']}")
            outcome = next(iter(outcomes), 'unlabelled')
            assert ep.get('outcome', 'unlabelled') == outcome
            if record.get('summary', {}).get('turns') is not None:
                assert entry['turns'] == record['summary']['turns']
            assert entry.get('model') == proof.get('model')
            assert entry.get('reasoning_effort') == proof.get('reasoningEffort')
            assert proof['backend'] == 'piper' and proof['task'] == task['id']
            assert re.fullmatch(r'[0-9a-f]{64}', proof.get('manualSha256') or '')
            instruction = entry.get('instruction')
            if not isinstance(instruction, str) or not instruction.strip():
                raise ValueError(f"Missing real task instruction: {entry['id']}")
            if instruction not in instructions:
                instructions.append(instruction)
            duration = entry.get('execution_duration_seconds')
            episodes.append({'id': ep['id'], 'archiveId': entry['id'],
                             'canonicalCase': ep.get('canonicalCase', record.get('canonicalCase', record.get('case'))),
                             'scene': int(str(ep['scene']).split('_')[-1]), 'outcome': outcome,
                             'instructionZh': instruction,
                             'model': entry.get('model'), 'reasoningEffort': entry.get('reasoning_effort'),
                             'manualSha256': proof['manualSha256'],
                             'turns': entry['turns'], 'observations': ep['observations'],
                             'videoSeconds': ep['durationSeconds'],
                             'wallClockSeconds': round(duration) if duration is not None else None,
                             'video': ep['video'], 'poster': ep['poster'], 'recordedAt': ep['recordedAt']})
        if not episodes:
            raise ValueError(f"Task has no episodes: {task['id']}")
        # Preserve source order and each exact instruction; variants may change task requirements.
        instruction = instructions[0]
        instruction_en = task.get('instructionEn') or INSTRUCTIONS_EN.get(task['id'])
        if not instruction_en:
            raise ValueError(f"Missing English task instruction: {task['id']}")
        real_tasks.append({'id': task['id'], 'title': task['title'], 'instructionZh': instruction,
                           'instructionEn': instruction_en, 'instructionVariants': instructions, 'episodes': episodes})
    real_eps = [e for t in real_tasks for e in t['episodes']]
    assert len(real_eps) == len(site['episodes'])
    assert used_archive_ids == {e['id'] for e in viewer.values() if e.get('backend') == 'piper'}
    real_models = sorted({e['model'] for e in real_eps if e['model'] is not None})
    real_efforts = sorted({e['reasoningEffort'] for e in real_eps if e['reasoningEffort'] is not None})

    detail = jsonp(cache / f'episode-{WALKTHROUGH_ID}.js')
    assert detail['success'] is True and detail['result_source'] == 'official'
    assert provenance[WALKTHROUGH_ID]['manualSha256'] == detail['manual']['sha256']
    steps = []
    for s in detail['steps']:
        frame = Path(s['images']['head_camera']).name.split('_')[0]
        steps.append({'turn': s['turn'], 'event': s['event'],
                      'frames': {'head': f'media/walkthrough/{frame}_head_camera.jpg',
                                 'wrist': f'media/walkthrough/{frame}_left_camera.jpg'},
                      'commands': [{k: v for k, v in c.items() if k in ('op', 'arm', 'translation_cm', 'rotation_deg', 'frame', 'opening')}
                                   for c in s['commands']],
                      'results': [{k: c.get(k) for k in ('op', 'status', 'target_reached', 'position_error_cm') if k in c}
                                  for c in s['command_results']],
                      'narration': s['narration'],
                      'rawCommands': s['commands'], 'rawResults': s['command_results'],
                      'robotState': s['robot_state'], 'timestamp': s['time'],
                      'eventIndex': s['event_index'], 'doneReason': s['done_reason'],
                      'gripperOpening': s['robot_state'].get('left_gripper_opening'),
                      'success': s['success'], 'done': s['done']})
    for step in steps:
        assert (ROOT / 'dist' / step['frames']['head']).is_file() and (ROOT / 'dist' / step['frames']['wrist']).is_file()

    assert all(re.fullmatch(r'[0-9a-f]{64}', entry.get('manualSha256') or '') for entry in provenance.values())
    payload = {
        'updatedAt': site['site']['updatedAt'],
        'provenance': {'archiveEpisodes': len(provenance), 'episodesWithVerifiedTaskManuals': len(provenance),
                       'cacheManifestSha256': digest_file(cache / 'cache-manifest.json')},
        'simulation': {
            'platform': 'RoboTwin 2.0', 'taskConfig': 'demo_randomized', 'model': 'gpt-6-astra',
            'reasoningEffort': 'xhigh', 'turnBudget': max(r['official']['turns'] for r in records),
            'taskCount': len(task_rows), 'trials': len(records), 'successes': successes,
            'failures': len(records) - successes, 'perfectTasks': sum(t['successes'] == t['trials'] for t in task_rows),
            'turns': {'successMedian': statistics.median(turns_ok), 'failureMedian': statistics.median(turns_bad),
                      'turnLimitFailures': reasons.get('turn_limit', 0)},
            'seedRange': [min(seeds), max(seeds)],
            'dateRange': [f'{dates[0][:4]}-{dates[0][4:6]}-{dates[0][6:]}', f'{dates[-1][:4]}-{dates[-1][4:6]}-{dates[-1][6:]}'],
            'tasks': task_rows, 'featured': featured},
        'real': {
            'platform': 'Piper', 'model': real_models[0] if len(real_models) == 1 and all(e['model'] is not None for e in real_eps) else None,
            'reasoningEffort': real_efforts[0] if len(real_efforts) == 1 and all(e['reasoningEffort'] is not None for e in real_eps) else None,
            'models': real_models, 'reasoningEfforts': real_efforts, 'taskCount': len(real_tasks),
            'confirmedTrials': sum(e['outcome'] in {'success', 'failure'} for e in real_eps),
            'unknownTrials': sum(e['outcome'] == 'unlabelled' for e in real_eps),
            'plannedTaskCount': site['site']['realWorldTaskCount'], 'trials': len(real_eps),
            'successes': sum(e['outcome'] == 'success' for e in real_eps), 'tasks': real_tasks},
        'walkthrough': {
            'id': WALKTHROUGH_ID, 'task': detail['task'], 'name': names[detail['task']], 'seed': detail['seed'],
            'instruction': detail['instruction'], 'turns': detail['turns'], 'commandSteps': detail['command_steps'],
            'turnBudget': 40, 'executionSeconds': detail['execution_duration_seconds'],
            'manual': {**MANUAL_EN, 'sha256': detail['manual']['sha256'], 'original': detail['manual']['text']},
            'steps': steps},
    }
    web_media = ROOT / 'dist/data/web-media.json'
    if web_media.exists():
        payload['media'] = json.loads(web_media.read_text())['assets']
    out = ROOT / 'dist' / 'data' / 'page-data.json'
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({'simulation': f"{successes}/{len(records)}", 'perfectTasks': payload['simulation']['perfectTasks'],
                      'real': f"{payload['real']['successes']}/{len(real_eps)}", 'walkthroughSteps': len(steps)}))


if __name__ == '__main__':
    main()
