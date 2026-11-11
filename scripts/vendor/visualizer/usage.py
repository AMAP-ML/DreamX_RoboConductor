"""Extract token counters only; never export native messages or reasoning."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from visualizer.data import read_jsonl


COUNTERS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
            "output_tokens", "reasoning_output_tokens")


def normalize_usage(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    counters = {key: value[key] for key in COUNTERS if key in value}
    if (not {"input_tokens", "output_tokens"} <= counters.keys()
            or any(type(count) is not int or count < 0 for count in counters.values())):
        return None
    if (counters.get("cached_input_tokens", 0) > counters["input_tokens"]
            or counters.get("reasoning_output_tokens", 0) > counters["output_tokens"]):
        return None
    # Cache hits and reasoning are subsets, not additional tokens to add again.
    counters["total_tokens"] = counters["input_tokens"] + counters["output_tokens"]
    return counters


def sum_usage(values: list[dict]) -> dict | None:
    if not values:
        return None
    # An absent optional breakdown remains unknown rather than becoming zero.
    keys = set.intersection(*(set(value) for value in values))
    return {key: sum(value[key] for value in values) for key in sorted(keys)}


def _timestamp(value: object) -> str | None:
    if isinstance(value, str):
        try:
            time = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if time.tzinfo is not None:
                return time.isoformat()
        except ValueError:
            pass
    return None


def load_usage(record_usage: object, public_path: Path | None, session_path: Path | None,
               warnings: list[str]) -> tuple[dict | None, dict]:
    """Prefer archived totals; native token_usage_record supplies per-model-call counts.

    A CLI turn can contain many model requests and robot actions. Do not split its
    total across robot turns or infer call-to-action attribution from timestamps.
    """
    total = normalize_usage(record_usage)
    source = "record" if total is not None else None
    if total is None and public_path is not None:
        try:
            values = [normalize_usage(event.get("usage")) for event in read_jsonl(public_path)
                      if event.get("type") == "turn.completed"]
            if values and all(value is not None for value in values):
                total = sum_usage(values)
                source = "public_events"
        except (OSError, ValueError, TypeError, AttributeError):
            warnings.append("Token total unavailable from the public event stream.")
    calls = []
    complete = None
    if session_path is not None:
        seen = set()
        try:
            for event in read_jsonl(session_path):
                if event.get("type") != "token_usage_record":
                    continue
                payload = event.get("payload") or {}
                usage = normalize_usage(payload.get("usage"))
                if usage is None:
                    complete = False
                    continue
                response_id = payload.get("response_id")
                if isinstance(response_id, str) and response_id:
                    if response_id in seen:
                        continue
                    seen.add(response_id)
                calls.append({"index": len(calls) + 1, "time": _timestamp(event.get("timestamp")),
                              "usage": usage})
        except (OSError, ValueError, TypeError, AttributeError):
            warnings.append("Per-call token details are incomplete or unreadable.")
            complete = False
    subtotal = sum_usage([call["usage"] for call in calls])
    if subtotal is not None:
        if total is None:
            if complete is not False:
                total, source = subtotal, "session"
        else:
            matches = all(subtotal.get(key) == count for key, count in total.items())
            complete = matches and complete is not False
            if not matches:
                warnings.append("Per-call token counts do not match the archived total; the total is preserved.")
    return total, {"source": source, "calls": calls, "complete": complete}
