import io
import json
import unittest
from pathlib import Path

from pet.codex_dialogue import CodexDialogue


class FakeProcess:
    def __init__(self, messages):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("".join(json.dumps(message) + "\n" for message in messages))
        self._terminated = False

    def poll(self):
        return None if not self._terminated else 0

    def terminate(self):
        self._terminated = True


class CodexDialogueTests(unittest.TestCase):
    def test_starts_a_thread_and_collects_streamed_reply(self):
        messages = [
            {"id": 1, "result": {}},
            {"id": 2, "result": {"thread": {"id": "thread-1"}}},
            {"id": 3, "result": {"turn": {"id": "turn-1"}}},
            {"method": "item/agentMessage/delta", "params": {"delta": "squeak "}},
            {"method": "item/agentMessage/delta", "params": {"delta": "indeed."}},
            {"method": "turn/completed", "params": {"turn": {"status": "completed"}}},
        ]
        process = FakeProcess(messages)
        dialogue = CodexDialogue(Path("."), command="codex", process_factory=lambda *_, **__: process)

        self.assertEqual(dialogue.reply("Hello"), "squeak indeed.")
        requests = [json.loads(line) for line in process.stdin.getvalue().splitlines()]
        self.assertEqual([request["method"] for request in requests], [
            "initialize", "initialized", "thread/start", "turn/start"
        ])
        self.assertEqual(requests[-1]["params"]["sandbox"], "readOnly")

    def test_reference_file_is_added_when_present(self):
        dialogue = CodexDialogue(Path("."), command="codex")
        dialogue._project_dir = Path(__file__).parent
        reference = dialogue._project_dir / "pikita_reference.md"
        reference.write_text("Squeaks at paperwork.", encoding="utf-8")
        try:
            self.assertIn("Squeaks at paperwork.", dialogue._build_prompt("Hi"))
        finally:
            reference.unlink()


if __name__ == "__main__":
    unittest.main()
