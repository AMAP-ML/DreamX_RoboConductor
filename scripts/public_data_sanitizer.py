"""Remove private references and credentials from exported JSON and text.

Exports use relative links or explicitly configured public hosts.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
from collections.abc import Iterable
from urllib.parse import unquote, urlsplit


LOCAL_PATH = "[local path removed]"
PRIVATE_REFERENCE = "[private reference removed]"
PRIVATE_VALUE = "[private value removed]"
_PATH_ROOTS = r"Users|home|root|tmp|private|var|data|mnt|Volumes|opt|srv|workspace|workspaces"
_PATH = re.compile(
    rf"(?<![\w:/#])(?:/(?:{_PATH_ROOTS})(?:/[^\s\"'`<>\[\]()，。；]+)?"
    r"|/[^/\s\"'`<>\[\]()，。；]+/[^\s\"'`<>\[\]()，。；]+"
    r"|[A-Za-z]:[\\/][^\s\"'`<>\[\]()，。；]+|~[/\\][^\s\"'`<>\[\]()，。；]+"
    r"|\\\\[^\s\"'`<>\[\]()，。；]+)"
)
_QUOTED_PATH = re.compile(r"([\"'`])([^\n]*?)\1")
_URL = re.compile(r"(?i)(?:\b(?:https?|ftp|ssh|file):|(?<![\w:]))//[^\s\"'`<>()，。；]+")
_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?(?![\w.])")
_IPV6 = re.compile(r"(?<![\w:])(?:[0-9a-fA-F]{0,4}:){2,}[0-9a-fA-F:]{0,39}(?:%[\w.-]+)?(?![\w:])")
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])")
_INTERNAL_HOST = re.compile(r"(?i)\b(?:[a-z0-9-]+\.)+(?:internal|intranet|corp|local|lan)\b")
_MARKDOWN_LINK = re.compile(r"(!?)\[([^\]\n]*)\]\(\s*(<[^>\n]+>|[^)\n]+)\s*\)")
_PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z ]*PRIVATE KEY)-----.*?-----END (?:[A-Z ]*PRIVATE KEY)-----", re.S)
_CREDENTIAL = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|authorization)"
    r"(\s*[:=]\s*)(?!\[private value removed\])(?:Bearer\s+)?[^\s,;\"'`<>]+"
)
_OMIT_KEYS = {"recording_dir", "recording_directory", "password", "api_key", "apikey",
              "access_token", "refresh_token", "client_secret", "private_key", "authorization", "cookie"}


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value.split("%", 1)[0])
        return True
    except ValueError:
        return False


def _private_url(value: str, allowed_hosts: frozenset[str]) -> bool:
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError:
        return True
    return (parsed.scheme not in {"https", "http"} or not host
            or bool(parsed.username or parsed.password) or _is_ip(host)
            or host not in allowed_hosts)


def _local_reference(value: str) -> bool:
    decoded = unquote(value.strip().strip("<>"))
    return decoded.lower().startswith("file://") or bool(_PATH.search(decoded))


def sanitize_public_text(text: str, *, replay_url: str | None = None,
                         allowed_url_hosts: Iterable[str] = ()) -> str:
    """Remove private references without changing surrounding public narration.

    A replay_url must be relative. Only local Markdown link destinations are
    replaced with it; plain filesystem paths become a neutral placeholder.
    """
    allowed = frozenset(host.lower().rstrip(".") for host in allowed_url_hosts)
    if replay_url and (urlsplit(replay_url).scheme or urlsplit(replay_url).netloc
                       or replay_url.startswith("/")):
        raise ValueError("Public replay URL must be relative")

    def link(match: re.Match) -> str:
        marker, label, target = match.groups()
        raw = target.strip().strip("<>")
        if _local_reference(raw):
            return f"[{label}]({replay_url})" if replay_url else f"{label} ({LOCAL_PATH})"
        if re.match(r"(?i)^(?:(?:https?|ftp|ssh):)?//", raw) and _private_url(raw, allowed):
            return f"{label} ({PRIVATE_REFERENCE})"
        return match.group(0)

    text = _PRIVATE_KEY.sub(PRIVATE_VALUE, text)
    text = _MARKDOWN_LINK.sub(link, text)
    text = _URL.sub(lambda match: PRIVATE_REFERENCE if _private_url(match.group(0), allowed) else match.group(0), text)
    text = _QUOTED_PATH.sub(lambda match: match[1] + LOCAL_PATH + match[1]
                            if _PATH.match(match[2]) else match[0], text)
    text = _PATH.sub(LOCAL_PATH, text)
    text = _IPV4.sub(lambda match: PRIVATE_REFERENCE if _is_ip(match.group(0).split(":", 1)[0]) else match.group(0), text)
    text = _IPV6.sub(lambda match: PRIVATE_REFERENCE if _is_ip(match.group(0)) else match.group(0), text)
    text = _EMAIL.sub(PRIVATE_REFERENCE, text)
    text = _INTERNAL_HOST.sub(PRIVATE_REFERENCE, text)
    return _CREDENTIAL.sub(lambda match: match[1] + match[2] + PRIVATE_VALUE, text)


def sanitize_public_data(value, *, replay_url: str | None = None,
                         allowed_url_hosts: Iterable[str] = ()):
    """Return a clean copy of a JSON-compatible value; never mutate the input.

    Identity, metrics and action values are preserved. A manual hash is updated
    only when sanitizing its text actually changes that text.
    """
    allowed = tuple(allowed_url_hosts)
    options = {"replay_url": replay_url, "allowed_url_hosts": allowed}
    if isinstance(value, str):
        return sanitize_public_text(value, **options)
    if isinstance(value, list):
        return [sanitize_public_data(item, **options) for item in value]
    if isinstance(value, dict):
        clean = {key: sanitize_public_data(item, **options) for key, item in value.items()
                 if re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower() not in _OMIT_KEYS}
        if (isinstance(value.get("text"), str) and "sha256" in value
                and clean.get("text") != value["text"]):
            clean["sha256"] = hashlib.sha256(clean["text"].encode()).hexdigest()
        return clean
    return value
