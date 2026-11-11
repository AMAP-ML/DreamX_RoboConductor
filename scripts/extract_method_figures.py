#!/usr/bin/env python3
"""Extract report diagrams and pair them with the site's prepared observation frames."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import fitz

ROOT = Path(__file__).resolve().parents[1]
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path)
    args = parser.parse_args()
    document = fitz.open(args.pdf)
    output = ROOT / 'dist/media/method'
    output.mkdir(parents=True, exist_ok=True)
    figures = []
    for name, page_number, rect in [
        ('system-overview.svg', 5, (79, 68, 533, 407)),
        ('test-lift-verification.png', 10, (70, 428, 306, 557)),
    ]:
        page = document[page_number - 1]
        if name.endswith('.png'):
            # Rasterize only the plot region: an SVG crop retains off-canvas source photos.
            page.get_pixmap(matrix=fitz.Matrix(4, 4), clip=fitz.Rect(*rect), alpha=False).save(output / name)
        else:
            original = page.cropbox
            page.set_cropbox(fitz.Rect(*rect))
            (output / name).write_text(page.get_svg_image(text_as_path=True))
            page.set_cropbox(original)
        figures.append({'asset': 'media/method/' + name, 'page': page_number, 'crop': rect,
                        'sha256': sha(output / name)})
    data = json.loads((ROOT / 'dist/data/page-data.json').read_text())
    episodes = {e['id']: e for task in data['real']['tasks'] for e in task['episodes']}
    selected = [
        ('pen', 'piper-eval-20261019-205241-f03708', [(49, 'right_camera'), (69, 'right_camera'), (103, 'head_camera')]),
        ('phone', 'piper-eval-20261022-133455-a8cbe1', [(55, 'head_camera'), (68, 'head_camera'), (96, 'head_camera')]),
    ]
    frames = []
    for label, record_id, choices in selected:
        archive_id = episodes[record_id]['archiveId']
        source = next((ROOT / 'dist/archive/episodes').rglob(f'{archive_id}/data.js'))
        raw = source.read_text()
        detail = json.loads(raw[raw.index('(') + 1:raw.rfind(')')])
        for turn, camera in choices:
            step = next(step for step in detail['steps'] if step['turn'] == turn)
            source = ROOT / 'dist/archive' / step['images'][camera]
            target = output / f'{label}-{turn}.png'
            shutil.copy2(source, target)
            frames.append({'asset': 'media/method/' + target.name, 'recordId': record_id,
                           'archiveId': archive_id, 'turn': turn, 'camera': camera,
                           'source': 'archive/' + step['images'][camera], 'sha256': sha(target)})
    provenance = {'reportTitle': 'RoboConductor: Specify the Task, Let the Coding Agent Control the Robot',
                  'reportVersion': '0.2', 'reportDate': '2026-10-25', 'pdfSha256': sha(args.pdf),
                  'methodPages': [1, 4, 5, 6, 7], 'diagramAssets': figures, 'behaviorFrames': frames,
                  'note': 'Figure 2 is presented using the corresponding prepared archive frames.'}
    (ROOT / 'scripts/paper-method-provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    print(json.dumps({'diagrams': len(figures), 'preparedFrames': len(frames)}))
if __name__ == '__main__': main()
