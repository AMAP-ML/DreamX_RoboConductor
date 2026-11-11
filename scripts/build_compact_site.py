#!/usr/bin/env python3
"""Build a self-contained, size-limited Pages copy from the prepared site."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

from PIL import Image
from prepare_archive import episode_data, references, rewrite
from prepare_pages import write_zip

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {'.html', '.js', '.json', '.css', '.svg', '.md'}
ASSET_PATH = re.compile(r'(?:archive/)?episodes/[\w./-]+\.(?:png|jpe?g|webp)|media/[\w./-]+\.mp4')


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def refresh_archive_metadata(source, target):
    proof = json.loads((ROOT / 'scripts/paper-method-provenance.json').read_text())
    for item in proof['behaviorFrames']:
        destination = target / item['source']
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / item['source'], destination)
    archive = target / 'archive'
    index_path = archive / 'translations/en/index.json'
    index = json.loads(index_path.read_text())
    for entry in index['entries']:
        entry['sourceSha256'] = sha256(archive / entry['source'])
        translation_path = archive / entry['translation']
        translation = json.loads(translation_path.read_text())
        translation['sourceSha256'] = entry['sourceSha256']
        translation_path.write_text(json.dumps(translation, ensure_ascii=False,
                                               separators=(',', ':')) + '\n')
        entry['sha256'] = sha256(translation_path)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1) + '\n')


def build(args):
    source = ROOT / 'dist'
    target = args.output.resolve()
    if source in target.parents or target in source.parents or source == target:
        raise ValueError('Output must be separate from the source tree')
    if target.exists() and any(target.iterdir()):
        raise ValueError('Output directory must be empty')
    target.mkdir(parents=True, exist_ok=True)
    source_files = sorted(path for path in source.rglob('*') if path.is_file())
    proofs = json.loads((ROOT / 'scripts/paper-method-provenance.json').read_text())
    proof_paths = {source / item['source'] for item in proofs['behaviorFrames']}
    frames = [path for path in (source / 'archive/episodes').rglob('*')
              if path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}
              and path not in proof_paths]
    assets = json.loads((source / 'data/web-media.json').read_text())['assets']
    videos = [(name, entry['src']) for name, entry in assets.items() if name.endswith('.mp4')]
    replacements = {}
    for path in frames:
        relative = path.relative_to(source).as_posix()
        converted = path.relative_to(source).with_suffix('.webp').as_posix()
        replacements[relative] = converted
        replacements[relative.removeprefix('archive/')] = converted.removeprefix('archive/')
    for name, playback in videos:
        replacements[playback] = name
    aliases = json.loads((source / 'data/media-aliases.json').read_text())['aliases']
    for alias, entry in aliases.items():
        if alias.endswith('.mp4'):
            replacements[alias] = entry['source']

    skipped = set(frames)
    skipped.update(source / name for name, _ in videos)
    skipped.update(source / name for name in replacements if name.endswith('.mp4'))
    for path in source_files:
        relative = path.relative_to(source)
        if path in skipped or relative.parts[0] == 'downloads':
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)

    def encode_frame(path):
        relative = path.relative_to(source)
        destination = target / relative.with_suffix('.webp')
        destination.parent.mkdir(parents=True, exist_ok=True)
        simulation = relative.parts[2] == 'simulation'
        quality = args.sim_quality if simulation else args.real_quality
        with Image.open(path) as image:
            size = image.size
            if path.suffix.lower() == '.webp':
                shutil.copy2(path, destination)
            else:
                image.convert('RGB').save(destination, 'WEBP', quality=quality, method=4)
        with Image.open(destination) as converted:
            converted.load()
            if converted.size != size:
                raise ValueError('Image dimensions changed')
        return ('simulation' if simulation else 'real-world', path.stat().st_size,
                destination.stat().st_size)

    totals = Counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for index, (kind, before, after) in enumerate(pool.map(encode_frame, frames), 1):
            totals[kind + '_frames'] += 1
            totals[kind + '_source_bytes'] += before
            totals[kind + '_bytes'] += after
            if index % 2000 == 0 or index == len(frames):
                print(f'Images {index}/{len(frames)}', flush=True)

    def encode_video(item):
        name, playback = item
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        command = [str(args.ffmpeg), '-hide_banner', '-loglevel', 'error', '-y',
                   '-i', str(source / playback), '-map', '0:v:0', '-an', '-c:v', 'libx264',
                   '-preset', 'medium', '-crf', str(args.video_crf), '-threads', '2',
                   '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(destination)]
        subprocess.run(command, check=True, capture_output=True)
        subprocess.run([str(args.ffmpeg), '-v', 'error', '-i', str(destination),
                        '-map', '0:v:0', '-f', 'null', '-'], check=True, capture_output=True)
        return name, destination.stat().st_size, sha256(destination)

    with ThreadPoolExecutor(max_workers=3) as pool:
        for index, (name, size, digest) in enumerate(pool.map(encode_video, videos), 1):
            assets[name].update(src=name, sourceBytes=size, bytes=size, sourceSha256=digest)
            if index % 8 == 0 or index == len(videos):
                print(f'Videos {index}/{len(videos)}', flush=True)

    for path in target.rglob('*'):
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            text = path.read_text()
            updated = ASSET_PATH.sub(lambda match: replacements.get(match[0], match[0]), text)
            if updated != text:
                path.write_text(updated)
    (target / 'data/media-aliases.json').write_text('{"aliases":{}}\n')
    (target / 'data/web-media.json').write_text(json.dumps({'assets': assets}, indent=1) + '\n')
    page_path = target / 'data/page-data.json'
    page = json.loads(page_path.read_text())
    page['media'] = assets
    page_path.write_text(json.dumps(page, ensure_ascii=False, indent=1) + '\n')

    site = json.loads((target / 'data/episodes.json').read_text())
    featured = json.loads((target / 'data/simulation-featured.json').read_text())
    for key, episodes in [('videoZip', site['episodes']), ('simulationZip', featured)]:
        entries = [(Path(item['video']).name, target / item['video']) for item in episodes]
        write_zip(target / site['site'][key], entries, zipfile.ZIP_STORED)
    code_zip = site['site']['sourceZip']
    shutil.copy2(source / code_zip, target / code_zip)
    (target / '.nojekyll').touch()
    refresh_archive_metadata(source, target)

    catalog_path = target / 'archive/catalog.js'
    catalog = json.loads(catalog_path.read_text().split('=', 1)[1].strip().rstrip(';'))
    episodes = [episode for platform in catalog['platforms'] for task in platform['tasks']
                for episode in task['episodes']]
    image_references = set(references(catalog))
    for item in episodes:
        _, original = episode_data(source / 'archive' / item['data_file'])
        _, converted = episode_data(target / 'archive' / item['data_file'])
        if rewrite(original, replacements) != converted:
            raise ValueError('Episode content changed beyond media paths')
        image_references.update(references(converted))
    missing = [name for name in image_references if not (target / 'archive' / name).is_file()]
    for path in target.rglob('*'):
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            for name in ASSET_PATH.findall(path.read_text()):
                base = target if name.startswith(('archive/', 'media/')) else target / 'archive'
                if not (base / name).is_file():
                    missing.append(name)
    if missing:
        raise ValueError(f'Missing media references: {len(set(missing))}')
    for name, entry in assets.items():
        if not (target / name).is_file() or not (target / entry['src']).is_file():
            raise ValueError('Missing playback asset')
        if (target / entry['src']).stat().st_size != entry['bytes']:
            raise ValueError('Playback asset metadata mismatch')
    for key in ('videoZip', 'simulationZip'):
        with zipfile.ZipFile(target / site['site'][key]) as archive:
            if archive.testzip() is not None:
                raise ValueError('Download archive CRC mismatch')
            for name in archive.namelist():
                if archive.read(name) != (target / 'media' / name).read_bytes():
                    raise ValueError('Download video differs from playback')
    output_files = [path for path in target.rglob('*') if path.is_file()]
    size = sum(path.stat().st_size for path in output_files)
    if size > args.max_bytes:
        raise ValueError(f'Site exceeds size budget: {size} > {args.max_bytes}')
    largest = max(path.stat().st_size for path in output_files)
    if largest > 100 * 1024 * 1024:
        raise ValueError('An output file exceeds the ordinary GitHub file limit')
    source_page = json.loads((source / 'data/page-data.json').read_text())
    for section in ('simulation', 'real'):
        if page[section] != rewrite(source_page[section], replacements):
            raise ValueError('Evaluation results changed')
    summary = dict(totals, source_bytes=sum(p.stat().st_size for p in source_files),
                   site_bytes=size, largest_file_bytes=largest, files=len(output_files),
                   episodes=len(episodes), simulation_episodes=500, real_episodes=50,
                   videos=len(videos), image_dimensions_preserved=True,
                   sim_quality=args.sim_quality, real_quality=args.real_quality,
                   video_crf=args.video_crf, missing_references=0)
    (target.parent / 'compression-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--ffmpeg', required=True, type=Path)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--sim-quality', type=int, default=75)
    parser.add_argument('--real-quality', type=int, default=90)
    parser.add_argument('--video-crf', type=int, default=29)
    parser.add_argument('--max-bytes', type=int, default=900_000_000)
    build(parser.parse_args())


if __name__ == '__main__':
    main()
