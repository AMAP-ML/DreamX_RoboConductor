#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-DreamX-RoboConductor-NonCommercial
"""Build the source download from FILE_ALLOWLIST and example fixtures."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from release_privacy import require_public_text

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = 'scripts/public-release-template'
ARCHIVE_ROOT = 'roboconductor-showcase'
STAMP = (2020, 1, 1, 0, 0, 0)

# Every source and destination is named individually. Never replace this with
# globbing, git ls-files, a recursive copy, or an exclusion-only policy.
FILE_ALLOWLIST = (
    ('serve.py', 'serve.py'),
    ('LICENSE', 'LICENSE'),
    ('NOTICE', 'NOTICE'),
    ('THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES.md'),
    ('DEPENDENCIES.md', 'DEPENDENCIES.md'),
    ('.gitignore', '.gitignore'),
    (f'{TEMPLATE}/README.md', 'README.md'),
    (f'{TEMPLATE}/GITHUB_MIGRATION.md', 'GITHUB_MIGRATION.md'),
    (f'{TEMPLATE}/dist/.nojekyll', 'dist/.nojekyll'),
    (f'{TEMPLATE}/dist/index.html', 'dist/index.html'),
    (f'{TEMPLATE}/dist/assets/demo.css', 'dist/assets/demo.css'),
    (f'{TEMPLATE}/dist/assets/demo.js', 'dist/assets/demo.js'),
    (f'{TEMPLATE}/dist/data/demo.json', 'dist/data/demo.json'),
    (f'{TEMPLATE}/tests/test_release.py', 'tests/test_release.py'),
    (f'{TEMPLATE}/DATA_CONTRACTS.md', 'DATA_CONTRACTS.md'),
    (f'{TEMPLATE}/fixtures/page-data.example.json', 'src/showcase/dist/data/page-data.json'),
    (f'{TEMPLATE}/fixtures/archive-catalog.example.json', 'fixtures/archive-catalog.example.json'),
    (f'{TEMPLATE}/fixtures/archive-episode.example.json', 'fixtures/archive-episode.example.json'),
    (f'{TEMPLATE}/schemas/demo.schema.json', 'schemas/demo.schema.json'),
    (f'{TEMPLATE}/schemas/page-data.schema.json', 'schemas/page-data.schema.json'),
    (f'{TEMPLATE}/schemas/archive.schema.json', 'schemas/archive.schema.json'),
    ('dist/index.html', 'src/showcase/dist/index.html'),
    ('dist/assets/app.js', 'src/showcase/dist/assets/app.js'),
    ('dist/assets/content-safety.js', 'src/showcase/dist/assets/content-safety.js'),
    ('dist/assets/episode-language.js', 'src/showcase/dist/assets/episode-language.js'),
    ('dist/assets/app.css', 'src/showcase/dist/assets/app.css'),
    ('dist/assets/walkthrough.css', 'src/showcase/dist/assets/walkthrough.css'),
    ('dist/assets/method-v2.css', 'src/showcase/dist/assets/method-v2.css'),
    ('dist/assets/comparison.css', 'src/showcase/dist/assets/comparison.css'),
    ('dist/assets/i18n.css', 'src/showcase/dist/assets/i18n.css'),
    ('dist/assets/i18n-common.js', 'src/showcase/dist/assets/i18n-common.js'),
    ('dist/assets/i18n.js', 'src/showcase/dist/assets/i18n.js'),
    ('dist/assets/i18n-home.js', 'src/showcase/dist/assets/i18n-home.js'),
    ('dist/assets/i18n-archive.js', 'src/showcase/dist/assets/i18n-archive.js'),
    ('dist/assets/video-player.js', 'src/showcase/dist/assets/video-player.js'),
    ('dist/assets/page-entry.js', 'src/showcase/dist/assets/page-entry.js'),
    ('dist/assets/hero-playlist.js', 'src/showcase/dist/assets/hero-playlist.js'),
    ('dist/assets/favicon.svg', 'src/showcase/dist/assets/favicon.svg'),
    ('dist/archive/index.html', 'src/showcase/dist/archive/index.html'),
    ('dist/archive/app.js', 'src/showcase/dist/archive/app.js'),
    ('dist/archive/frames.js', 'src/showcase/dist/archive/frames.js'),
    ('dist/archive/style.css', 'src/showcase/dist/archive/style.css'),
    ('scripts/test_i18n.cjs', 'src/showcase/scripts/test_i18n.cjs'),
    ('scripts/test_content_safety.cjs', 'src/showcase/scripts/test_content_safety.cjs'),
    ('scripts/test_episode_language.cjs', 'src/showcase/scripts/test_episode_language.cjs'),
    ('scripts/test_hero_playlist.cjs', 'src/showcase/scripts/test_hero_playlist.cjs'),
    ('scripts/test_video_player.cjs', 'src/showcase/scripts/test_video_player.cjs'),
)


def source_without_embedded_experiments(source_name, data):
    """Retain implementation while removing homepage-embedded research copy.

    These changes apply only to the exported source reference. They do not
    alter the internal site. Real JSON/media are never opened by the builder.
    """
    if source_name == 'dist/index.html':
        text = data.decode('utf-8')
        text = re.sub(r'<p data-lang-only="en">.*?</p>',
                      '<p data-lang-only="en">Add your project description here.</p>', text, flags=re.S)
        text = re.sub(r'<p data-lang-only="zh" hidden>.*?</p>',
                      '<p data-lang-only="zh" hidden>在此填写项目简介。</p>', text, flags=re.S)
        text = re.sub(r'<section class="behavior-study".*?</section>',
                      '<section class="behavior-study" aria-labelledby="behavior-title"><h3 id="behavior-title">Case studies</h3><p>Add a case study with its episode and media references.</p></section>', text, flags=re.S)
        text = re.sub(r'(<div class="case-meta"><p>).*?(</p>)',
                      r'\1Add an episode reference.\2', text, flags=re.S)
        text = re.sub(r'(<dl class="manual-task" id="manual-task">).*?(</dl>)',
                      r'\1<dt>Instruction</dt><dd>Add a task description.</dd>\2', text, flags=re.S)
        text = re.sub(r'<figcaption><b>Figure 2\.</b>.*?</figcaption>',
                      '<figcaption>Add an episode walkthrough.</figcaption>', text, flags=re.S)
        text = re.sub(r'<section class="(?:section )?comparison-section".*?</section>',
                      '<section class="section comparison-section" id="comparison"><h2>Method comparison</h2><p>Add comparison data and figures.</p></section>', text, flags=re.S)
        text = re.sub(r'(\b(?:src|poster|content))="media/[^"<>]+"', '', text)
        text = re.sub(r'href="(?:media|downloads)/[^"<>]+"', 'href="#top"', text)
        text = re.sub(r'href="https?://[^"<>]+"', 'href="#top"', text)
        text = re.sub(r'archive/#/platforms/[^"<>]+', 'archive/', text)
        text = re.sub(r'data-hero-episode="[^"]+"', 'data-hero-episode="example-episode"', text)
        # Numeric research captions and stale fallback metrics are placeholders;
        # HTML attribute values (layout, controls, SVG paths) stay unchanged.
        text = re.sub(r'>([^<>]*\d[^<>]*)<',
                      lambda match: '>' + re.sub(r'\d+(?:\.\d+)?', '…', match.group(1)) + '<', text)
        text = text.replace('<body>', '<body>\n<p class="noscript">Showcase source: configure data/page-data.json and media/ to run this layout.</p>')
        return text.encode('utf-8')
    if source_name == 'dist/assets/i18n-home.js':
        text = data.decode('utf-8')
        prefix, content = text.split('.push(', 1)
        translations = json.loads(content.rsplit(');', 1)[0])
        translations['strings'] = {
            key: value for key, value in translations['strings'].items()
            if not re.search(r'\d', key) and not any(term in key.lower() for term in (
                'after the pen slips', 'near a wrist constraint', 'historical episodes',
                'reacquires the shaft', 'portrait-placement', 'grasp region',
            ))
        }
        return (prefix + '.push(' + json.dumps(translations, ensure_ascii=False, indent=2) + ');\n').encode('utf-8')
    if source_name == 'dist/assets/app.css':
        text = data.decode('utf-8')
        text = re.sub(r'(\.result-bar \.(?:simulation|real)-fill\{width:)[\d.]+%', r'\g<1>0%', text)
        return text.encode('utf-8')
    if source_name == 'scripts/test_i18n.cjs':
        text = data.decode('utf-8')
        text = text.replace('50 tasks · 500 episodes · 411 / 500 Success', '2 tasks · 6 episodes · 3 / 6 Success')
        text = text.replace('/50.*500.*411.*500.*成功/', '/2.*6.*3.*6.*成功/')
        return text.encode('utf-8')
    return data


def release_entries(root=ROOT):
    """Return reviewed release bytes, failing closed for missing/symlink files."""
    root = Path(root).resolve()
    entries = {}
    for source_name, destination_name in FILE_ALLOWLIST:
        source = root / source_name
        current = root
        for component in Path(source_name).parts:
            current = current / component
            if current.is_symlink():
                raise ValueError(f'Release source must not be a symlink: {source_name}')
        if not source.is_file():
            raise ValueError(f'Missing required release file: {source_name}')
        source.resolve().relative_to(root)
        if destination_name in entries:
            raise ValueError(f'Duplicate release destination: {destination_name}')
        entries[destination_name] = source_without_embedded_experiments(source_name, source.read_bytes())

    fixture = json.loads(entries['dist/data/demo.json'])
    if fixture.get('synthetic') is not True or any(
        item.get('synthetic') is not True for item in fixture.get('episodes', [])
    ):
        raise ValueError('The public demo requires explicitly synthetic fixtures')
    manifest = {
        'formatVersion': 1,
        'distribution': 'synthetic-code-demo',
        'includesOriginalExperimentData': False,
        'files': [
            {'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            for name, data in sorted(entries.items())
        ],
    }
    entries['RELEASE_MANIFEST.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    require_public_text(entries)
    return entries


def write_release_zip(destination, entries):
    """Write deterministic ZIP bytes, with only the already validated entries."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.release-', suffix='.zip', delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(entries.items()):
                info = zipfile.ZipInfo(f'{ARCHIVE_ROOT}/{name}', STAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def build_release(destination, root=ROOT, zip_destination=None):
    """Create a fresh export directory outside the original checkout."""
    destination = Path(destination).absolute()
    root = Path(root).resolve()
    try:
        destination.resolve().relative_to(root)
    except ValueError:
        pass
    else:
        raise ValueError('Standalone release output must be outside the source checkout')
    if destination.exists() or destination.is_symlink():
        raise ValueError(f'Refusing to overwrite an existing release: {destination}')
    if zip_destination is not None:
        zip_destination = Path(zip_destination).absolute()
        try:
            zip_destination.resolve().relative_to(root)
        except ValueError:
            pass
        else:
            raise ValueError('Standalone release ZIP must be outside the source checkout')
        if zip_destination.exists() or zip_destination.is_symlink():
            raise ValueError(f'Refusing to overwrite an existing ZIP: {zip_destination}')
        if zip_destination == destination:
            raise ValueError('Release directory and ZIP must have different destinations')
    entries = release_entries(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.public-release-', dir=destination.parent))
    try:
        for name, data in entries.items():
            target = temporary / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    if zip_destination is not None:
        write_release_zip(zip_destination, entries)
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path,
                        help='New release directory outside this checkout')
    parser.add_argument('--zip', type=Path, dest='zip_destination',
                        help='Optional ZIP destination; defaults to OUTPUT.zip')
    args = parser.parse_args()
    zip_destination = args.zip_destination or args.output.with_name(args.output.name + '.zip')
    try:
        entries = build_release(args.output, zip_destination=zip_destination)
    except (ValueError, OSError) as error:
        parser.exit(1, f'Release build failed: {error}\n')
    print(f'Built {len(entries)} allowlisted files in {args.output}')
    print(f'ZIP: {zip_destination}')
    print('Source package ready.')


if __name__ == '__main__':
    main()
