"""Read public episode traces, archived manuals and public agent messages only."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from public_data_sanitizer import sanitize_public_text


CAMERAS = ("head_camera", "left_camera", "right_camera")
PLATFORMS = {"robotwin": ("RoboTwin 2.0", "simulation"),
             "piper": ("Piper", "physical"), "robodojo": ("RoboDojo", "simulation")}


def infer_backend(run_dir: Path) -> str:
    return next((part for part in reversed(run_dir.parts) if part in PLATFORMS), "robotwin")


def _images(run_dir: Path, index: int) -> dict[str, str]:
    """Discover only saved camera images with simple, path-safe camera names."""
    images = {}
    for path in sorted((run_dir / "frames").glob(f"{index:04d}_*")):
        match = re.fullmatch(r"\d+_([A-Za-z][A-Za-z0-9_]{0,63})\.(?:jpg|jpeg|png|webp)", path.name)
        if match and path.is_file():
            images.setdefault(match[1], f"frames/{path.name}")
    return dict(sorted(images.items(), key=lambda item: (
        CAMERAS.index(item[0]) if item[0] in CAMERAS else len(CAMERAS), item[0])))


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError("expected an object")
            except ValueError as exc:
                raise ValueError(f"{path.name}, line {number}: {exc}") from exc
            yield event


def load_events(run_dir: Path) -> list[dict[str, Any]]:
    events = list(read_jsonl(Path(run_dir) / "events.jsonl"))
    if not events:
        raise ValueError("empty episode trace")
    return events


def build_replay(run_dir: Path, events: list[dict[str, Any]]) -> dict[str, Any]:
    """Normalize the old replay format, including zero-action and missing-frame runs."""
    first = next((event for event in events if event.get("event") == "start_episode"), {})
    request, response = first.get("request") or {}, first.get("response") or {}
    backend = response.get("backend") or ("piper" if response.get("success_available") is False else infer_backend(run_dir))
    steps = []
    for event in events:
        if event.get("event") not in {"start_episode", "execute_turn"}:
            continue
        index = event.get("index")
        if type(index) is not int or index < 0:
            continue
        observation = event.get("response") or {}
        step_request = event.get("request") or {}
        steps.append({
            "event_index": index, "event": event["event"], "time": event.get("time"),
            "turn": observation.get("turn", 0), "commands": step_request.get("commands") or [],
            "command_results": observation.get("command_results") or [],
            "robot_state": observation.get("robot_state") or {},
            "success": observation.get("success") if type(observation.get("success")) is bool else None,
            "done": observation.get("done") is True, "done_reason": observation.get("done_reason"),
            "images": _images(run_dir, index),
            "narration": [],
        })
    latest = next((event.get("response") or {} for event in reversed(events)
                   if event.get("event") == "execute_turn"), response)
    final = next((event.get("response") or {} for event in reversed(events)
                  if event.get("event") == "finish_episode"), latest)
    return {
        "backend": backend, "run_id": response.get("run_id") or run_dir.name,
        "task": response.get("task") or request.get("task") or "unknown",
        "instruction": response.get("instruction") or "",
        "seed": response.get("seed", request.get("seed")),
        "task_config": response.get("task_config", request.get("task_config")),
        "scene_id": response.get("scene_id", request.get("scene_id")),
        "execution_mode": final.get("execution_mode", response.get("execution_mode")),
        "success_available": final.get("success_available", response.get("success_available", backend != "piper")),
        "camera_names": list(response.get("camera_images") or {}) or list(dict.fromkeys(
            camera for step in steps for camera in step["images"])),
        "success": final.get("success"), "done_reason": final.get("done_reason"),
        "turns": final.get("turns", steps[-1]["turn"] if steps else 0),
        "command_steps": final.get("command_steps", sum(len(step["commands"]) for step in steps)),
        "steps": steps,
    }


def public_messages(path: Path, *, replay_url: str | None = None) -> tuple[dict[int, list[str]], str]:
    """Read CLI's public messages, never native session or reasoning events."""
    by_turn = defaultdict(list)
    pending = []
    last_turn = 0
    for event in read_jsonl(path):
        if event.get("type") != "item.completed":
            continue
        item = event.get("item") or {}
        if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
            pending.append(sanitize_public_text(item["text"], replay_url=replay_url))
        elif item.get("type") == "mcp_tool_call":
            result = item.get("result") or {}
            structured = result.get("structured_content") or result.get("structuredContent") or {}
            turn = structured.get("turn")
            if item.get("tool") in {"start_episode", "execute_turn"} and type(turn) is int:
                by_turn[turn].extend(pending)
                pending.clear()
                last_turn = turn
            elif item.get("tool") == "finish_episode":
                by_turn[last_turn].extend(pending)
                pending.clear()
    return dict(by_turn), "\n\n".join(pending)
