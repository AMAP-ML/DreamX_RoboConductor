#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-DreamX-RoboConductor-NonCommercial
"""Scan exported text for credential formats and private references.

Findings contain relative filenames, categories, and line numbers.
"""
import ipaddress
import re
from urllib.parse import urlsplit

# Public documentation, licensing, schemas, and source-hosting sites required
# by the distribution. Do not add private deployment hosts or account names.
PUBLIC_HOSTS = frozenset({
    'apache.org', 'www.apache.org', 'docs.python.org', 'github.com', 'docs.github.com',
    'json-schema.org', 'www.w3.org', 'pillow.readthedocs.io', 'pymupdf.io',
    'ffmpeg.org', 'www.gnu.org',
})
PLACEHOLDERS = frozenset({
    '', 'none', 'null', 'undefined', 'example', 'placeholder', 'redacted',
    'changeme', 'change_me', 'replace_me', 'your_api_key', 'your_token',
    'your_password',
})
PATTERNS = (
    ('experiment-record-id', re.compile(r'\bpiper-eval-\d{8}-\d{6}-[0-9a-f]+\b')),
    ('private-key', re.compile(r'-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----')),
    ('credential-format', re.compile(
        r'(?<![\w-])(?:'
        r'(?:AKIA|ASIA)[A-Z0-9]{16}|'
        r'LTAI[A-Za-z0-9]{12,30}|dl_live_[A-Za-z0-9_-]{20,}|'
        r'gh[opusr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{20,}|'
        r'glpat-[A-Za-z0-9_-]{20,}|'
        r'sk-(?:(?:proj|svcacct)-)?[A-Za-z0-9_-]{20,}|'
        r'xox[baprs]-[A-Za-z0-9-]{16,}|'
        r'AIza[A-Za-z0-9_-]{35}|'
        r'eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}'
        r')(?![\w-])')),
    ('personal-path', re.compile(
        r'(?<![\w])(?:/(?:Users|home)/[^/\s"\'<>]+(?:/|\b)|'
        r'/root(?:/|(?=[\s"\'<>]|$))|'
        r'[A-Za-z]:\\+(?:Users|Documents and Settings)\\+[^\\\s"\'<>]+|'
        r'~/(?:[^\s"\'<>]+))', re.I)),
    ('bearer-credential', re.compile(r'\bBearer\s+[A-Za-z0-9._~+/-]{16,}={0,2}\b', re.I)),
)
CREDENTIAL_ASSIGNMENT = re.compile(
    r'(?<![\w-])["\']?'
    r'(?:api[_-]?(?:key|secret)|access[_-]?token|auth[_-]?token|refresh[_-]?token|'
    r'client[_-]?secret|(?:secret|private)[_-]?key|authorization|password|passwd|secret|token)'
    r'["\']?\s*[:=]\s*'
    r'(?:"(?P<double>[^"\n]*)"|\'(?P<single>[^\'\n]*)\'|'
    r'(?P<bare>[^\s,;\}\]\)<>]+))', re.I)
EMAIL = re.compile(r'\b[A-Za-z0-9.!#$%&*+/=?^_`{|}~-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)\b')
URL = re.compile(r'(?i)(?:\b(?:https?|wss?|ssh|git|ftp)://|(?<![:\w])//(?=[a-z0-9.-]+[.:]))[^\s"\'<>`]+')


def reserved_host(host):
    host = host.lower().rstrip('.')
    if host in {'localhost', 'example', 'test', 'invalid', 'example.com', 'example.org', 'example.net'}:
        return True
    if host.endswith(('.localhost', '.example', '.test', '.invalid', '.example.com', '.example.org', '.example.net')):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def allowed_host(host):
    host = host.lower().rstrip('.')
    return reserved_host(host) or host in PUBLIC_HOSTS or host.endswith('.github.io')


def scan_public_text(entries):
    """Return safe candidate records without copying matched values into output."""
    findings = set()
    for filename, data in sorted(entries.items()):
        try:
            content = data.decode('utf-8') if isinstance(data, bytes) else data
        except UnicodeDecodeError:
            findings.add((filename, 'non-text-content', 1))
            continue
        for line_number, line in enumerate(content.replace(r'\/', '/').splitlines(), 1):
            for kind, pattern in PATTERNS:
                if pattern.search(line):
                    findings.add((filename, kind, line_number))
            for match in CREDENTIAL_ASSIGNMENT.finditer(line):
                value = next(value for value in match.groupdict().values() if value is not None)
                if value.lower() not in PLACEHOLDERS:
                    findings.add((filename, 'credential-assignment', line_number))
            for match in EMAIL.finditer(line):
                if not reserved_host(match.group(1)):
                    findings.add((filename, 'email-address', line_number))
            for match in URL.finditer(line):
                try:
                    parsed = urlsplit(match.group().rstrip(').,;'))
                    if parsed.username is not None or parsed.password is not None:
                        findings.add((filename, 'url-credentials', line_number))
                    if not parsed.hostname or not allowed_host(parsed.hostname):
                        findings.add((filename, 'unapproved-url-host', line_number))
                except ValueError:
                    findings.add((filename, 'unapproved-url-host', line_number))
    return [{'file': filename, 'type': kind, 'line': line}
            for filename, kind, line in sorted(findings)]


def require_public_text(entries):
    findings = scan_public_text(entries)
    if findings:
        report = '\n'.join(f"{item['file']}:{item['line']}: {item['type']}" for item in findings)
        raise ValueError('Public release privacy scan failed:\n' + report)
