"""Synthetic privacy-boundary tests: never use actual private data as fixtures."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from public_data_sanitizer import (LOCAL_PATH, PRIVATE_REFERENCE, PRIVATE_VALUE,
                                   sanitize_public_data, sanitize_public_text)

sys.path.insert(0, str(Path(__file__).parent / "vendor"))
from visualizer.data import public_messages
from visualizer.build import _episode


class PublicDataSanitizerTests(unittest.TestCase):
    def test_local_links_become_replay_links(self):
        text = "Succeeded. [record](/Users/example/records/run-001)"
        clean = sanitize_public_text(text, replay_url="#/platforms/demo/tasks/pick/episodes/001")
        self.assertEqual(clean, "Succeeded. [record](#/platforms/demo/tasks/pick/episodes/001)")
        self.assertEqual(sanitize_public_text(clean), clean)

    def test_paths_and_private_network_references(self):
        samples = ["/home/example/project/run", "C:\\Users\\example\\run",
                   "~/records/run", "\\\\server\\share\\record",
                   "file:///Users/example/run", "https://console.internal/records/1",
                   "http://192.0.2.10:8000/", "https://[2001:db8::1]/",
                   "//console.example.test/private", "192.0.2.10:8000", "2001:db8::1",
                   "example@example.test"]
        for sample in samples:
            with self.subTest(sample=sample):
                clean = sanitize_public_text(sample)
                self.assertIn(clean, (LOCAL_PATH, PRIVATE_REFERENCE))
                self.assertEqual(sanitize_public_text(clean), clean)

    def test_public_host_opt_in_and_credentials(self):
        text = "https://docs.example.test/guide"
        self.assertEqual(sanitize_public_text(text, allowed_url_hosts=["docs.example.test"]), text)
        self.assertEqual(sanitize_public_text("https://user:pass@docs.example.test/guide",
                                            allowed_url_hosts=["docs.example.test"]), PRIVATE_REFERENCE)
        clean = sanitize_public_text("api_key=synthetic-secret")
        self.assertEqual(clean, "api_key=" + PRIVATE_VALUE)
        self.assertEqual(sanitize_public_text(clean), clean)

    def test_records_and_actions_remain_intact(self):
        value = {"id": "episode-001", "success": True, "turns": 4,
                 "commands": [{"pose": [0.1, -0.2, 0.3], "steps": 10}],
                 "recording_dir": "/Users/example/records/run-001",
                 "manual": {"text": "Close the gripper.", "sha256": "unchanged"}}
        clean = sanitize_public_data(value)
        self.assertNotIn("recording_dir", clean)
        self.assertEqual(clean, {key: item for key, item in value.items() if key != "recording_dir"})
        self.assertIn("recording_dir", value)

    def test_sensitive_manual_hash_updates(self):
        clean = sanitize_public_data({"text": "Saved in /home/example/records", "sha256": "old"})
        self.assertEqual(clean["sha256"], hashlib.sha256(clean["text"].encode()).hexdigest())

    def test_generic_and_quoted_paths(self):
        self.assertEqual(sanitize_public_text("/custom-volume/example/project"), LOCAL_PATH)
        self.assertEqual(sanitize_public_text('Saved "/Users/Example User/my project".'),
                         'Saved "' + LOCAL_PATH + '".')
        route = "#/platforms/demo/tasks/pick/episodes/001"
        self.assertEqual(sanitize_public_text(route), route)

    def test_episode_export_has_no_local_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory).resolve() / "source"
            run = source / "robotwin" / "pick" / "run-001"
            (run / "codex").mkdir(parents=True)
            (run / "task_manual").mkdir()
            manual = "Close the gripper."
            (run / "task_manual/MANUAL.md").write_text(manual)
            (run / "task_manual/manifest.json").write_text(json.dumps({"mode": "auto"}))
            commands = [{"command": "move", "position": [0.1, 0.2, -0.3]}]
            events = [{"event": "start_episode", "index": 0,
                       "request": {"task": "pick"}, "response": {"backend": "robotwin", "turn": 0}},
                      {"event": "execute_turn", "index": 1, "request": {"commands": commands},
                       "response": {"turn": 1, "success": True, "done": True}}]
            (run / "events.jsonl").write_text("\n".join(json.dumps(event) for event in events))
            public = {"type": "item.completed", "item": {"type": "agent_message",
                      "text": "Succeeded. [record](/Users/example/records/run-001)"}}
            (run / "codex/events.jsonl").write_text(json.dumps(public))
            output = Path(directory).resolve() / "public"
            entry, _ = _episode(None, run, source, output)
            raw = (output / entry["data_file"]).read_text()
            detail = json.loads(raw[raw.index("(") + 1:raw.rfind(")")])
            self.assertNotIn(str(source), raw)
            self.assertNotIn("/Users/example", raw)
            self.assertEqual(detail["steps"][1]["commands"], commands)
            self.assertEqual(detail["manual"]["text"], manual)
            self.assertIn("#/platforms/robotwin/tasks/pick/episodes/", detail["public_summary"])

    def test_new_public_messages_are_sanitized_before_export(self):
        events = [
            {"type": "item.completed", "item": {"type": "agent_message", "text": "Saved /home/example/run"}},
            {"type": "item.completed", "item": {"type": "mcp_tool_call", "tool": "execute_turn",
                                                 "result": {"structured_content": {"turn": 1}}}},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "[record](/home/example/run)"}},
            {"type": "item.completed", "item": {"type": "reasoning", "text": "Never export this"}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text("\n".join(json.dumps(event) for event in events))
            turns, summary = public_messages(path, replay_url="#/episode/001")
        self.assertEqual(turns, {1: ["Saved " + LOCAL_PATH]})
        self.assertEqual(summary, "[record](#/episode/001)")


if __name__ == "__main__":
    unittest.main()
