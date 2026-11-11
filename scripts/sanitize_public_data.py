#!/usr/bin/env python3
"""Sanitize public snapshots in place and refresh their dependent hashes.

Run with --check to detect changes without writing. Media is never read, copied,
or rewritten. The source snapshots must already be trusted JSON/known JSONP.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote

from public_data_sanitizer import sanitize_public_data


ROOT = Path(__file__).resolve().parents[1]


def read_data(path: Path):
    raw = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(raw), raw, None
    match = re.fullmatch(r"(window\.registerEpisode\(|window\.EVALUATION_CATALOG\s*=\s*)(.*?)(\);|;)\s*", raw, re.S)
    if not match:
        raise ValueError(f"Unsupported public JSONP wrapper: {path.name}")
    return json.loads(match[2]), raw, (match[1], match[3])


def serialize(value, original: str, wrapper) -> str:
    if wrapper:
        payload = (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
                   .replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
        return wrapper[0] + payload + wrapper[1] + "\n"
    indentation = re.search(r"\n( +)\S", original)
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      indent=len(indentation[1]) if indentation else 1) + "\n"


def replay_link(episode: dict, prefix: str = "") -> str:
    return prefix + "#/platforms/{}/tasks/{}/episodes/{}".format(
        *(quote(str(episode[key]), safe="") for key in ("backend", "task", "id")))


def sanitize_tree(root: Path, *, check: bool = False) -> dict:
    files = sorted(set([*root.glob("scripts/*.json"), *root.glob("scripts/cache/*.json"),
                       *root.glob("scripts/cache/*.js"), *root.glob("dist/data/*.json"),
                       *root.glob("dist/archive/episodes/**/data.js"), root / "dist/archive/catalog.js"]))
    episode_sources = {path.parent.name: path for path in files if path.name == "data.js"}
    pending = {}
    changes = Counter()

    def stage(path, value, original, wrapper):
        content = serialize(value, original, wrapper)
        if content != original:
            pending[path] = content.encode("utf-8")

    for path in files:
        if not path.is_file():
            continue
        value, raw, wrapper = read_data(path)
        link = replay_link(value) if isinstance(value, dict) and all(key in value for key in ("backend", "task", "id", "steps")) else None
        # Viewer references are known archive assets, so keep useful relative URLs.
        if path.name == "simulation-summary.json":
            example = value.get("exampleEpisode") or {}
            viewer = example.get("existingVisualizer")
            if isinstance(viewer, dict) and example.get("id"):
                episode = {"backend": value["platform"], "task": example["task"], "id": example["id"]}
                viewer["page"] = replay_link(episode, "archive/index.html")
                episode_source = episode_sources[example["id"]].relative_to(root / "dist").as_posix()
                viewer["data"] = episode_source
                thumbnail = re.search(r"/frames/([^/?#]+)$", viewer.get("thumbnail", ""))
                if thumbnail:
                    viewer["thumbnail"] = str(Path(episode_source).parent / "frames" / thumbnail[1])
        clean = sanitize_public_data(value, replay_url=link)
        if clean != value or path.name == "simulation-summary.json":
            stage(path, clean, raw, wrapper)
            if path in pending:
                changes["sanitizedFiles"] += 1
                if path.name == "data.js" and path.parent.name in episode_sources:
                    changes["sanitizedEpisodes"] += 1

    def digest(path):
        return hashlib.sha256(pending[path] if path in pending else path.read_bytes()).hexdigest()

    proof_path = root / "scripts/cache/evaluation-provenance.json"
    if proof_path.exists():
        proof, raw, wrapper = read_data(proof_path)
        proof = sanitize_public_data(proof)
        for entry in proof:
            source = episode_sources[entry["id"]]
            if not source.is_file():
                raise ValueError(f"Missing episode for provenance: {entry['id']}")
            content = (pending[source] if source in pending else source.read_bytes()).decode()
            detail = json.loads(content[content.index("(") + 1:content.rfind(")")])
            entry["dataSha256"] = digest(source)
            entry["manualSha256"] = detail["manual"]["sha256"]
        stage(proof_path, proof, raw, wrapper)

    manifest_path = root / "scripts/cache/cache-manifest.json"
    if manifest_path.exists():
        manifest, raw, wrapper = read_data(manifest_path)
        manifest = sanitize_public_data(manifest)
        manifest["sha256"] = {name: digest(manifest_path.parent / name) for name in manifest["sha256"]}
        stage(manifest_path, manifest, raw, wrapper)
        page_path = root / "dist/data/page-data.json"
        if page_path.exists():
            page, raw, wrapper = read_data(page_path)
            page = sanitize_public_data(page)
            page["provenance"]["cacheManifestSha256"] = digest(manifest_path)
            stage(page_path, page, raw, wrapper)

    if not check:
        for path, content in pending.items():
            path.write_bytes(content)
    return {"checkedFiles": len(files), **changes, "changedFiles": len(pending), "checkOnly": check}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = sanitize_tree(args.root.resolve(), check=args.check)
    print(json.dumps(result, sort_keys=True))
    return int(args.check and result["changedFiles"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
