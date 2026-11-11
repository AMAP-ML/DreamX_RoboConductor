#!/usr/bin/env python3
"""Export evaluation records to a portable, dependency-free HTML viewer."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import quote, unquote, urlsplit

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from public_data_sanitizer import sanitize_public_data
from visualizer.data import PLATFORMS, build_replay, infer_backend, load_events, public_messages, read_jsonl
from visualizer.usage import load_usage


ROOT = Path(__file__).resolve().parent
MARKER = ".visualizer.json"
MEDIA_TYPES = {".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image",
               ".mp4": "video", ".mov": "video", ".m4v": "video", ".webm": "video", ".mkv": "video"}
MEDIA_LINK = re.compile(r"(!?)\[([^\]]*)\]\(\s*(<[^>]+>|[^)\n]+)\s*\)")


def _json(value) -> str:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            .replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _source(path: Path, root: Path) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file() or path.is_symlink():
        raise ValueError("source file escapes the input directory or is a symbolic link")
    return resolved


def _target(path: Path, root: Path) -> Path:
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError("output must not contain redirected files or directories")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _copy(source: Path, target: Path, source_root: Path, output: Path) -> str:
    source = _source(source, source_root)
    target = _target(target, output)
    if not target.is_file() or (target.stat().st_size, target.stat().st_mtime_ns) != (
            source.stat().st_size, source.stat().st_mtime_ns):
        shutil.copy2(source, target)
    return quote(target.relative_to(output).as_posix(), safe="/")


def _summary(entries: list[dict]) -> dict:
    scored = [entry for entry in entries if entry["counted"] and type(entry["success"]) is bool]
    wins = sum(entry["success"] for entry in scored)
    unscored = sum(not entry["counted"] and type(entry["success"]) is bool for entry in entries)
    operator = [entry for entry in entries if entry.get("result_source") == "operator"]
    operator_wins = sum(entry["success"] for entry in operator)
    return {"episodes": len(entries), "counted": len(scored), "successes": wins,
            "failures": len(scored) - wins, "unscored": unscored,
            "unknown": len(entries) - len(scored) - unscored,
            "success_rate": wins / len(scored) if scored else None,
            "operator_confirmed": len(operator), "operator_successes": operator_wins,
            "operator_failures": len(operator) - operator_wins,
            "operator_success_rate": operator_wins / len(operator) if operator else None}


def _manual(run: Path, target: Path, source_root: Path, output: Path, warnings: list[str]) -> dict:
    directory = run / "task_manual"
    result = {"text": "", "media": [], "sha256": None, "mode": None}
    try:
        result["text"] = _source(directory / "MANUAL.md", source_root).read_text(encoding="utf-8")
        result["sha256"] = hashlib.sha256(result["text"].encode()).hexdigest()
    except (OSError, ValueError) as exc:
        warnings.append(f"Task manual unavailable: {exc}")
        return result
    try:
        manifest = json.loads(_source(directory / "manifest.json", source_root).read_text(encoding="utf-8"))
        # Never export input_context, generation_context, source, or the original manifest.
        result["mode"] = manifest.get("mode")
        if manifest.get("used_sha256") not in {None, result["sha256"]}:
            warnings.append("Archived manual text does not match its recorded hash.")
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        warnings.append(f"Manual provenance unavailable: {exc}")
    seen = set()
    for image_marker, label, raw in MEDIA_LINK.findall(result["text"]):
        raw = raw.strip()
        raw = raw[1:-1] if raw.startswith("<") and raw.endswith(">") else re.sub(r'\s+["\'].*["\']$', "", raw)
        parsed = urlsplit(raw)
        relative = Path(unquote(parsed.path))
        kind = MEDIA_TYPES.get(relative.suffix.lower())
        if not image_marker and kind is None:
            continue
        try:
            if parsed.scheme or parsed.netloc or parsed.query or relative.is_absolute() or kind is None:
                raise ValueError("only local image/video references are allowed")
            path = _source(directory / relative, directory.resolve())
            normalized = path.relative_to(directory.resolve())
            if normalized in seen:
                continue
            url = _copy(path, target / "manual" / normalized, source_root, output)
            result["media"].append({"label": label or path.name, "url": url, "kind": kind})
            seen.add(normalized)
        except (OSError, ValueError) as exc:
            warnings.append(f"Manual media skipped ({raw}): {exc}")
    return result


def _episode(record_path: Path | None, run: Path, source_root: Path, output: Path) -> tuple[dict, list[str]]:
    warnings = []
    record = {}
    if record_path is not None:
        try:
            record = json.loads(_source(record_path, source_root).read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                raise ValueError("archive record is not an object")
        except (OSError, ValueError) as exc:
            warnings.append(f"Archive record invalid: {exc}")
            record = {}
    try:
        _source(run / "events.jsonl", source_root)
        replay = build_replay(run, load_events(run))
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        warnings.append(f"Episode trace unavailable: {exc}")
        replay = {"steps": []}
    summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
    attempt = record.get("attempt") if isinstance(record.get("attempt"), dict) else {}
    backend = record.get("backend") or summary.get("backend") or replay.get("backend") or infer_backend(run)
    platform_name, platform_kind = PLATFORMS.get(backend, (str(backend), "simulation"))
    success_available = summary.get("success_available", replay.get("success_available", platform_kind != "physical")) is True
    if (type(summary.get("success")) is bool and type(replay.get("success")) is bool
            and summary["success"] != replay["success"]):
        warnings.append("Archived official result and trace disagree; the archived score is preserved.")
    relative = run.relative_to(source_root).as_posix()
    identity = hashlib.sha256(relative.encode()).hexdigest()[:20]
    task_name = summary.get("task") or replay.get("task") or attempt.get("task") or "unknown"
    if not isinstance(task_name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", task_name):
        raise ValueError("Task names must be safe directory components")
    group = "real-world" if platform_kind == "physical" else "simulation"
    relative_output = Path("episodes") / group / task_name / identity
    destination = output / relative_output
    success = summary.get("success") if record_path is not None else replay.get("success")
    evaluation = record.get("evaluation")
    operator_confirmed = (platform_kind == "physical" and isinstance(evaluation, dict)
                          and evaluation.get("source") == "operator" and evaluation.get("status") == "confirmed"
                          and type(evaluation.get("success")) is bool)
    if operator_confirmed:
        evaluation = {key: evaluation[key] for key in ("source", "status", "success", "confirmed_at") if key in evaluation}
        success = evaluation["success"]
    else:
        evaluation = None
        if not success_available:
            success = None
    counted = (platform_kind == "simulation" and success_available and summary.get("counted") is True
               and summary.get("closed") is True and type(success) is bool)
    if type(success) is not bool:
        success = None
    entry = {
        "id": identity, "run_id": summary.get("run_id") or replay.get("run_id") or run.name,
        "backend": backend, "platform_name": platform_name, "platform_kind": platform_kind,
        "success_available": success_available,
        "result_source": "operator" if operator_confirmed else "official" if success_available and type(success) is bool else "unavailable",
        "evaluation": evaluation,
        "task": summary.get("task") or replay.get("task") or attempt.get("task") or "unknown",
        "task_config": summary.get("task_config") or replay.get("task_config") or attempt.get("task_config"),
        "seed": summary.get("seed", replay.get("seed")),
        "scene_id": summary.get("scene_id") or attempt.get("scene_id") or replay.get("scene_id"),
        "execution_mode": summary.get("execution_mode") or replay.get("execution_mode"),
        "episode_index": summary.get("episode_index", attempt.get("episode_index")),
        "episode_count": summary.get("episode_count", attempt.get("episode_count")),
        "success": success, "counted": counted, "archive_status": record.get("status", "unarchived"),
        "turns": summary.get("turns", replay.get("turns", 0)),
        "command_steps": summary.get("command_steps", replay.get("command_steps", 0)),
        "done_reason": summary.get("done_reason", replay.get("done_reason")),
        "instruction": replay.get("instruction", ""),
        "model": summary.get("codex_model") or attempt.get("model") or "unknown",
        "reasoning_effort": summary.get("reasoning_effort") or attempt.get("reasoning_effort"),
        "data_file": (relative_output / "data.js").as_posix(), "thumbnail": None,
    }
    if record_path is not None and (record.get("status") != "complete" or record.get("error") or record.get("missing")):
        warnings.append("Archive is incomplete; official counted results are preserved, not reclassified.")
    steps = replay["steps"]
    for step in steps:
        images = {}
        for camera, path in step["images"].items():
            try:
                images[camera] = _copy(run / path, destination / path, source_root, output)
            except (OSError, ValueError) as exc:
                warnings.append(f"Frame skipped: {exc}")
        step["images"] = images
    camera_names = replay.get("camera_names") or record.get("camera_names") or []
    if not steps or any(not step["images"] or not set(camera_names) <= step["images"].keys() for step in steps):
        warnings.append("Some camera observations are missing; no intermediate frames are reconstructed.")
    entry["camera_names"] = list(dict.fromkeys([*camera_names, *(camera for step in steps for camera in step["images"])]))
    entry["thumbnail"] = next((step["images"].get("head_camera") or next(iter(step["images"].values()), None)
                               for step in steps if step["images"]), None)
    public_summary = ""
    try:
        path = _source(run / "codex" / "events.jsonl", source_root)
        replay_url = f"#/platforms/{quote(backend, safe='')}/tasks/{quote(entry['task'], safe='')}/episodes/{identity}"
        narration, public_summary = public_messages(path, replay_url=replay_url)
        for step in steps:
            step["narration"] = narration.get(step["turn"], [])
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        warnings.append(f"Public agent commentary unavailable: {exc}")
    usage_paths = []
    for name in ("events.jsonl", "session.jsonl"):
        try:
            usage_paths.append(_source(run / "codex" / name, source_root))
        except FileNotFoundError:
            usage_paths.append(None)
        except (OSError, ValueError) as exc:
            warnings.append(f"Token usage source skipped ({name}): {exc}")
            usage_paths.append(None)
    usage, token_usage = load_usage(record.get("usage"), *usage_paths, warnings)
    detail = {**entry, "steps": steps, "public_summary": public_summary,
              "manual": _manual(run, destination, source_root, output, warnings),
              "usage": usage, "token_usage": token_usage, "warnings": warnings}
    detail = sanitize_public_data(detail)
    entry = {key: detail[key] for key in entry}
    warnings = detail["warnings"]
    _target(output / entry["data_file"], output).write_text(
        f"window.registerEpisode({_json(detail)});\n", encoding="utf-8")
    return entry, warnings


def build_site(records_dir: Path, output_dir: Path) -> dict:
    source = Path(records_dir).expanduser().resolve(strict=True)
    raw_output = Path(output_dir).expanduser().absolute()
    if raw_output.is_symlink():
        raise ValueError("output directory must not be a symbolic link")
    output = raw_output.resolve()
    if not source.is_dir():
        raise ValueError("input must be an evaluation-record directory")
    if source.is_relative_to(output) or output.is_relative_to(source):
        raise ValueError("input and output directories must not overlap")
    if output.exists() and any(output.iterdir()) and not (output / MARKER).is_file():
        raise ValueError("output is not owned by this visualizer; choose an empty directory")
    runs = {path.parent: path for path in sorted(source.rglob("record.json"))}
    for path in sorted(source.rglob("events.jsonl")):
        if path.parent in runs or any(part in {"codex", "manual_generation", "task_manual"}
                                      for part in path.relative_to(source).parts[:-1]):
            continue
        try:
            if path.parent == source or any(event.get("event") in {"start_episode", "execute_turn", "finish_episode"}
                                            for event in read_jsonl(_source(path, source))):
                runs[path.parent] = None
        except (OSError, ValueError):
            continue
    if not runs:
        raise ValueError("no record.json archives or single-episode trace found")
    output.mkdir(parents=True, exist_ok=True)
    _target(output / MARKER, output).write_text(_json({"format": 1}) + "\n", encoding="utf-8")
    tasks = {}
    warnings = []
    for run, path in sorted(runs.items()):
        entry, problems = _episode(path, run, source, output)
        tasks.setdefault((entry["backend"], entry["task"]), []).append(entry)
        warnings.extend(f"{entry['run_id']}: {problem}" for problem in problems)
    entries = [entry for group in tasks.values() for entry in group]
    duplicate = Counter((entry["backend"], entry["task"], entry["task_config"], entry["seed"], entry["scene_id"]) for entry in entries)
    if any(count > 1 for count in duplicate.values()):
        warnings.append("Repeated task/config/seed records are shown separately; no attempts were silently merged.")
    ordered = []
    for (backend, task), items in sorted(tasks.items()):
        items.sort(key=lambda item: (str(item["task_config"] or ""),
                                   item["episode_index"] if type(item["episode_index"]) is int else -1,
                                   str(item["seed"] or ""), item["run_id"]))
        ordered.append({"id": f"{backend}/{task}", "name": task, "backend": backend,
                        "platform_name": items[0]["platform_name"], "summary": _summary(items), "episodes": items})
    platforms = []
    for backend in sorted({entry["backend"] for entry in entries}, key=lambda name: (name != "robotwin", name)):
        groups = [task for task in ordered if task["backend"] == backend]
        name, kind = PLATFORMS.get(backend, (str(backend), "simulation"))
        platforms.append({"id": backend, "name": name, "kind": kind,
                          "summary": {"tasks": len(groups), **_summary([entry for group in groups for entry in group["episodes"]])},
                          "tasks": groups})
    catalog = {"generated_at": datetime.now(timezone.utc).isoformat(), "source_name": "evaluation_records",
               "summary": {"platforms": len(platforms), "tasks": len(ordered), **_summary(entries)},
               "platforms": platforms, "tasks": ordered, "warnings": warnings}
    catalog = sanitize_public_data(catalog)
    for name in ("index.html", "app.js", "frames.js", "style.css"):
        shutil.copyfile(ROOT / "assets" / name, _target(output / name, output))
    _target(output / "catalog.js", output).write_text(
        f"window.EVALUATION_CATALOG = {_json(catalog)};\n", encoding="utf-8")
    return catalog


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records_dir", type=Path, help="evaluation_records, one platform directory, or one archived/raw episode")
    parser.add_argument("--output", type=Path, default=ROOT / "site", help="output directory (default: visualizer/site)")
    args = parser.parse_args(argv)
    try:
        catalog = build_site(args.records_dir, args.output)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Cannot build viewer: {exc}\n")
    counts = catalog["summary"]
    print(f"{counts['tasks']} tasks; {counts['successes']}/{counts['counted']} successful counted episodes")
    print(args.output.expanduser().resolve() / "index.html")
    if catalog["warnings"]:
        print(f"{len(catalog['warnings'])} warning(s); see the viewer for details", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
