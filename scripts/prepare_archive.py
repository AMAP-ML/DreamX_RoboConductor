#!/usr/bin/env python3
"""Apply prepared Piper image copies and validate the complete static archive."""
import argparse
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'dist/archive'


def catalog_data():
    return json.loads((ARCHIVE / 'catalog.js').read_text().split('=', 1)[1].strip().rstrip(';'))


def episode_data(path):
    raw = path.read_text()
    return raw[:raw.index('(') + 1], json.loads(raw[raw.index('(') + 1:raw.rfind(')')])


def rewrite(value, replacements):
    if isinstance(value, str):
        return replacements.get(value, value)
    if isinstance(value, list):
        return [rewrite(v, replacements) for v in value]
    if isinstance(value, dict):
        return {k: rewrite(v, replacements) for k, v in value.items()}
    return value


def references(value):
    if isinstance(value, str):
        if value.startswith('episodes/') and re.search(r'\.(?:png|jpe?g|webp|mp4|webm|js)$', value, re.I):
            yield value
    elif isinstance(value, list):
        for v in value:
            yield from references(v)
    elif isinstance(value, dict):
        for v in value.values():
            yield from references(v)


def write_category_indexes(catalog):
    for backend, kind, title in (
        ('robotwin', 'simulation', 'Simulation evaluation records'),
        ('piper', 'real-world', 'Real-world Piper evaluation records'),
    ):
        directory = ARCHIVE / 'episodes' / kind
        groups = [task for platform in catalog['platforms'] for task in platform['tasks']
                  if task['backend'] == backend]
        tasks = []
        for task in sorted(groups, key=lambda item: item['name']):
            entries = []
            for episode in task['episodes']:
                record = (ARCHIVE / episode['data_file']).relative_to(directory)
                entries.append({'id': episode['id'], 'record': record.as_posix(),
                                'scene': episode.get('scene_id'), 'seed': episode.get('seed'),
                                'success': episode.get('success')})
            tasks.append({'task': task['name'], 'episodes': entries})
        count = sum(len(task['episodes']) for task in tasks)
        index = {'kind': kind, 'backend': backend, 'episode_count': count,
                 'task_count': len(tasks), 'tasks': tasks}
        (directory / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n')
        readme = [f'# {title}', '', f'{count} episodes across {len(tasks)} tasks.', '',
                  'Each task has its own directory. Each episode contains `data.js` and its corresponding `frames/`.', '',
                  '`steps[].narration` contains per-turn public commentary; `public_summary` contains the final response. Commands and execution feedback remain in each step.', '',
                  '| Task | Episodes |', '| --- | ---: |']
        readme.extend(f"| [{task['task']}]({task['task']}/) | {len(task['episodes'])} |" for task in tasks)
        (directory / 'README.md').write_text('\n'.join(readme) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--processed-root', type=Path)
    args = parser.parse_args()
    catalog = catalog_data()
    episodes = [e for p in catalog['platforms'] for t in p['tasks'] for e in t['episodes']]
    if args.processed_root:
        root = args.processed_root.resolve()
        cases = json.loads((root.parent / 'case-list.json').read_text())
        case_index = {(c['task'], int(c['case'].split('/')[2].split('_')[-1])): c for c in cases}
        replacements = {}
        for ep in episodes:
            if ep['backend'] != 'piper':
                continue
            case = case_index[(ep['task'], int(ep['scene_id']))]
            source = root / case['case'] / 'frames'
            images = sorted(source.glob('*.png'))
            if len(images) != case['image_count']:
                raise SystemExit('Prepared Piper frame count mismatch: ' + case['case'])
            relative_frames = Path(ep['data_file']).parent / 'frames'
            target = ARCHIVE / relative_frames
            target.mkdir(parents=True, exist_ok=True)
            if list(target.glob('*.jpg')):
                raise SystemExit('Original JPEGs found in Piper output: ' + ep['id'])
            for image in images:
                shutil.copy2(image, target / image.name)
                old = (relative_frames / image.with_suffix('.jpg').name).as_posix()
                replacements[old] = (relative_frames / image.name).as_posix()
            path = ARCHIVE / ep['data_file']
            prefix, data = episode_data(path)
            path.write_text(prefix + json.dumps(rewrite(data, replacements), ensure_ascii=False, separators=(',', ':')) + ');\n')
        catalog = rewrite(catalog, replacements)
        (ARCHIVE / 'catalog.js').write_text('window.EVALUATION_CATALOG = ' + json.dumps(catalog, ensure_ascii=False, separators=(',', ':')) + ';\n')
    refs = set(references(catalog))
    for ep in episodes:
        _, data = episode_data(ARCHIVE / ep['data_file'])
        refs.update(references(data))
    missing = [ref for ref in sorted(refs) if not (ARCHIVE / ref).is_file()]
    if missing:
        raise SystemExit('Missing archive files:\n' + '\n'.join(missing[:30]))
    write_category_indexes(catalog)
    files = [p for p in ARCHIVE.rglob('*') if p.is_file()]
    print(json.dumps({'episodes': len(episodes), 'platforms': len(catalog['platforms']), 'references': len(refs), 'files': len(files), 'bytes': sum(p.stat().st_size for p in files)}))


if __name__ == '__main__':
    main()
