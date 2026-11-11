# SPDX-License-Identifier: LicenseRef-DreamX-RoboConductor-NonCommercial
"""Offline integrity, fixture, local-reference, and HTTP tests for the release."""
import functools
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import re
import threading
import unittest
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ('href', 'src', 'poster') and value and not value.startswith(('#', 'data:')):
                self.paths.append(value)


class ReleaseTests(unittest.TestCase):
    def test_manifest_and_distribution_boundaries(self):
        manifest = json.loads((ROOT / 'RELEASE_MANIFEST.json').read_text())
        self.assertEqual(manifest['distribution'], 'synthetic-code-demo')
        self.assertIs(manifest['includesOriginalExperimentData'], False)
        listed = {entry['path'] for entry in manifest['files']}
        self.assertEqual(len(listed), len(manifest['files']))
        actual = {path.relative_to(ROOT).as_posix() for path in ROOT.rglob('*')
                  if path.is_file() and not {'.git', '__pycache__', '.run'}.intersection(path.relative_to(ROOT).parts)}
        self.assertEqual(actual, listed | {'RELEASE_MANIFEST.json'})
        required = {'LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md', 'DEPENDENCIES.md',
                    'README.md', 'serve.py', '.gitignore', 'DATA_CONTRACTS.md',
                    'dist/index.html', 'dist/assets/demo.js', 'dist/assets/demo.css',
                    'dist/data/demo.json', 'tests/test_release.py',
                    'src/showcase/dist/index.html', 'src/showcase/dist/assets/app.js',
                    'src/showcase/dist/archive/app.js', 'src/showcase/dist/archive/frames.js'}
        self.assertTrue(required <= listed)
        forbidden_parts = {'.git', '.aoneci', '.run', 'cache', 'operator-records', 'rawlogs', 'vendor', 'media', 'downloads'}
        for entry in manifest['files']:
            path = ROOT / entry['path']
            self.assertFalse(path.is_symlink(), entry['path'])
            self.assertFalse(forbidden_parts.intersection(Path(entry['path']).parts), entry['path'])
            self.assertNotIn(path.suffix.lower(), {'.mp4', '.jpg', '.jpeg', '.png', '.gif', '.webp', '.woff', '.woff2', '.ttf', '.zip'})
            data = path.read_bytes()
            self.assertEqual(len(data), entry['bytes'], entry['path'])
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry['sha256'], entry['path'])
        self.assertIn('Non-Commercial Research and Personal Use License', (ROOT / 'LICENSE').read_text())
        self.assertIn('Commercial use is not permitted', (ROOT / 'LICENSE').read_text())
        self.assertIn('does not revoke', (ROOT / 'LICENSE').read_text())

    def test_synthetic_fixtures(self):
        fixture = json.loads((ROOT / 'dist/data/demo.json').read_text())
        self.assertIs(fixture['synthetic'], True)
        self.assertEqual(len(fixture['episodes']), 3)
        ids = set()
        for episode in fixture['episodes']:
            self.assertIs(episode['synthetic'], True)
            self.assertNotIn(episode['id'], ids)
            ids.add(episode['id'])
            self.assertIn(episode['category'], ('arrangement', 'inspection'))
            self.assertTrue(episode['steps'])
            for key in ('id', 'title', 'summary', 'outcome'):
                self.assertIsInstance(episode[key], str)
            for step in episode['steps']:
                self.assertEqual(set(step), {'title', 'detail'})
                self.assertTrue(all(isinstance(value, str) for value in step.values()))
        for relative in ('fixtures/archive-catalog.example.json', 'fixtures/archive-episode.example.json',
                         'src/showcase/dist/data/page-data.json'):
            self.assertIs(json.loads((ROOT / relative).read_text())['synthetic'], True)
        for path in (ROOT / 'schemas').glob('*.json'):
            self.assertIsInstance(json.loads(path.read_text()), dict)

    def test_demo_has_only_resolvable_local_references(self):
        parser = References()
        parser.feed((ROOT / 'dist/index.html').read_text())
        for reference in parser.paths:
            parsed = urlsplit(reference)
            self.assertFalse(parsed.scheme or parsed.netloc, reference)
            self.assertTrue((ROOT / 'dist' / parsed.path).is_file(), reference)
        script = (ROOT / 'dist/assets/demo.js').read_text()
        self.assertIn("fetch('data/demo.json'", script)
        self.assertNotIn('innerHTML', script)
        self.assertNotRegex(script, r'https?://')
        source_html = (ROOT / 'src/showcase/dist/index.html').read_text()
        self.assertIn('Showcase source: configure data/page-data.json', source_html)
        self.assertNotRegex(source_html, r'(?i)(?:piper-eval-|episodes/[a-f0-9]{20}|\d{8}-\d{6})')
        self.assertNotRegex(source_html, r'>\d+(?:\.\d+)?%<')
        source_css = (ROOT / 'src/showcase/dist/assets/app.css').read_text()
        self.assertNotRegex(source_css, r'\.result-bar \.(?:simulation|real)-fill\{width:[1-9]')


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('release_server', ROOT / 'serve.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.server = module.Server(('127.0.0.1', 0), functools.partial(module.Handler, directory=str(ROOT / 'dist')))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def test_demo_assets_and_health(self):
        for path in ('/', '/assets/demo.css', '/assets/demo.js', '/data/demo.json', '/healthz'):
            with urlopen(self.base + path, timeout=3) as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(response.read())
                self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        with urlopen(Request(self.base + '/', method='HEAD'), timeout=3) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b'')

    def test_ranges(self):
        original = (ROOT / 'dist/assets/demo.js').read_bytes()
        with urlopen(Request(self.base + '/assets/demo.js', headers={'Range': 'bytes=0-15'}), timeout=3) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.read(), original[:16])
            self.assertEqual(response.headers['Content-Range'], f'bytes 0-15/{len(original)}')
        with self.assertRaises(HTTPError) as caught:
            urlopen(Request(self.base + '/assets/demo.js', headers={'Range': 'bytes=999999999-'}), timeout=3)
        self.assertEqual(caught.exception.code, 416)

    def test_private_and_missing_paths(self):
        for path in ('/.git/config', '/%2e%2e/LICENSE', '/README.md', '/missing-file'):
            with self.assertRaises(HTTPError) as caught:
                urlopen(self.base + path, timeout=3)
            self.assertEqual(caught.exception.code, 404, path)


if __name__ == '__main__':
    unittest.main()
