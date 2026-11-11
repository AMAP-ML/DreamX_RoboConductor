# SPDX-License-Identifier: LicenseRef-DreamX-RoboConductor-NonCommercial
"""Privacy-gate regression checks; all injected values below are synthetic."""
from pathlib import Path
import tempfile
import unittest

import build_public_release as release
from release_privacy import require_public_text, scan_public_text


class PrivacyTests(unittest.TestCase):
    def test_current_release_passes_without_writing_artifacts(self):
        entries = release.release_entries()
        self.assertFalse(scan_public_text(entries))

    def test_candidates_report_locations_without_values(self):
        cases = (
            ('-----BEGIN PRIVATE KEY-----', 'private-key'),
            ('-----BEGIN PGP PRIVATE KEY BLOCK-----', 'private-key'),
            ('sk-' + 'x' * 32, 'credential-format'),
            ('LTAI' + 'x' * 20, 'credential-format'),
            ('dl_live_' + 'x' * 32, 'credential-format'),
            ('piper-eval-' + '20000101-000000-abcdef', 'experiment-record-id'),
            ('const apiKey = "synthetic-test-credential";', 'credential-assignment'),
            ('api_key=synthetic123', 'credential-assignment'),
            ('"Authorization": "Basic synthetic-placeholder-value"', 'credential-assignment'),
            ('/Users/synthetic-person/project', 'personal-path'),
            ('C:\\Users\\synthetic-person\\project', 'personal-path'),
            ('synthetic.person@private.invalid-domain.org', 'email-address'),
            ('https://private-service.invalid-domain.org/a', 'unapproved-url-host'),
            ('https://synthetic:synthetic-test-password@example.test/a', 'url-credentials'),
        )
        for value, expected_kind in cases:
            with self.subTest(kind=expected_kind):
                findings = scan_public_text({'allowed.js': ('// fixture\n' + value).encode()})
                self.assertIn({'file': 'allowed.js', 'type': expected_kind, 'line': 2}, findings)
                with self.assertRaises(ValueError) as caught:
                    require_public_text({'allowed.js': ('// fixture\n' + value).encode()})
                self.assertNotIn(value, str(caught.exception))
                self.assertIn('allowed.js:2:', str(caught.exception))

    def test_reserved_examples_license_urls_and_placeholders(self):
        text = '\n'.join((
            'http://www.apache.org/licenses/LICENSE-2.0',
            'https://docs.python.org/3/license.html',
            'https://github.com/example/project',
            'https://synthetic-project.github.io/docs/',
            'http://127.0.0.1:8098 http://localhost:8098 https://example.test/',
            'reader@example.org reader@local.example reader@site.test',
            '/.git/config /%2e%2e/LICENSE',
            'password = "none"; token = null; api_key = "";',
        ))
        self.assertFalse(scan_public_text({'examples.txt': text.encode()}))

    def test_secret_in_allowlisted_javascript_blocks_export(self):
        # Copy only current allowlisted sources into a disposable checkout.
        # This never edits the actual repository or creates a public artifact.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'checkout'
            for source_name, _ in release.FILE_ALLOWLIST:
                target = root / source_name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((release.ROOT / source_name).read_bytes())
            script = root / 'dist/assets/app.js'
            script.write_bytes(script.read_bytes() + b'\nconst api_key = "synthetic-release-test-credential";\n')
            output = Path(directory) / 'export'
            with self.assertRaises(ValueError) as caught:
                release.build_release(output, root=root)
            self.assertIn('src/showcase/dist/assets/app.js:', str(caught.exception))
            self.assertIn('credential-assignment', str(caught.exception))
            self.assertNotIn('synthetic-release-test-credential', str(caught.exception))
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
