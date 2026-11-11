#!/usr/bin/env python3
"""Validate the self-contained dist tree and reproducibly prepare Pages downloads.

Run from any directory: python3 scripts/prepare_pages.py
No network access or video processing is performed. MP4s must already be present.
"""
from pathlib import Path
import json
import re
import subprocess
import zipfile

from build_public_release import release_entries, write_release_zip

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'
STAMP = (2020, 1, 1, 0, 0, 0)


def local_path(reference):
    path = (DIST / reference.split('?', 1)[0].split('#', 1)[0]).resolve()
    try:
        path.relative_to(DIST.resolve())
    except ValueError:
        raise ValueError(f'Reference escapes dist: {reference}')
    return path


def write_zip(destination, entries, compression):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.zip.tmp')
    try:
        with zipfile.ZipFile(temporary, 'w', compression=compression) as archive:
            for name, source in sorted(entries):
                info = zipfile.ZipInfo(name, STAMP)
                info.compress_type = compression
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, source.read_bytes())
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def main():
    data = json.loads((DIST / 'data/episodes.json').read_text())
    featured = json.loads((DIST / 'data/simulation-featured.json').read_text())
    references = set()
    # Resolve local media/download references in all browser-facing text files.
    for path in DIST.rglob('*'):
        if path.is_file() and 'archive' not in path.relative_to(DIST).parts and path.suffix in {'.html', '.json', '.js', '.css'}:
            references.update(re.findall(r'''(?:media|downloads)/[^\s"'<>`\\)]+''', path.read_text()))
    generated = {
        data['site']['videoZip'], data['site']['simulationZip'], data['site']['sourceZip']
    }
    missing = sorted(ref for ref in references - generated if not local_path(ref).is_file())
    if missing:
        raise SystemExit('Missing local assets:\n' + '\n'.join(missing))
    for key, episodes in [('videoZip', data['episodes']), ('simulationZip', featured)]:
        entries = [(Path(item['video']).name, local_path(item['video'])) for item in episodes]
        if len({name for name, _ in entries}) != len(entries):
            raise SystemExit(f'Duplicate archive names for {key}')
        write_zip(local_path(data['site'][key]), entries, zipfile.ZIP_STORED)
    # The source download is a runnable synthetic code demo. The explicit
    # allowlist never reads internal datasets, media, tools, or Git history.
    write_release_zip(local_path(data['site']['sourceZip']), release_entries(ROOT))
    missing = sorted(ref for ref in references if not local_path(ref).is_file())
    if missing:
        raise SystemExit('Missing local assets:\n' + '\n'.join(missing))
    media = list((DIST / 'media').glob('*.mp4'))
    print(f'Validated {len(references)} local references; {len(media)} MP4s ({sum(p.stat().st_size for p in media):,} bytes).')
    for ref in sorted(generated):
        path = local_path(ref)
        print(f'{ref}: {path.stat().st_size:,} bytes')
    if (DIST / 'archive/catalog.js').exists():
        subprocess.run(['python3', str(ROOT / 'scripts/prepare_archive.py')], check=True)


if __name__ == '__main__':
    main()
