"""Small client for a local ``codex app-server`` conversation.

This stays dormant until a future UI, microphone, or behaviour asks it for a
line. The Codex CLI owns authentication, so no API key is stored here.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, TextIO


class CodexDialogueError(RuntimeError):
    """The local Codex conversation service could not answer."""


class CodexDialogue:
    def __init__(
        self,
        project_dir: Path,
        *,
        command: str | None = None,
        process_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
    ) -> None:
        self._project_dir = project_dir
        self._command = command or shutil.which("codex") or "codex"
        self._process_factory = process_factory
        self._process: subprocess.Popen | None = None
        self._next_id = 1
        self._thread_id: str | None = None

    def reply(self, user_text: str) -> str:
        """Return one short in-character line for a user message."""
        self._ensure_started()
        prompt = self._build_prompt(user_text)
        self._request(
            "turn/start",
            {
                "threadId": self._thread_id,
                "input": [{"type": "text", "text": prompt}],
                # Talking Pikita must never use the coding agent to change files.
                "approvalPolicy": "never",
                "sandbox": "readOnly",
                "model": os.environ.get("PIKITA_CODEX_MODEL", "gpt-5.6-terra"),
            },
        )

        answer = []
        while True:
            message = self._read_message()
            method = message.get("method")
            params = message.get("params", {})
            if method == "item/agentMessage/delta":
                answer.append(params.get("delta", ""))
            elif method == "turn/completed":
                if params.get("turn", {}).get("status") != "completed":
                    raise CodexDialogueError("Codex did not complete Pikita's reply.")
                return "".join(answer).strip()
            elif method == "error":
                raise CodexDialogueError(params.get("error", {}).get("message", "Codex failed."))

    def close(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
        self._process = None
        self._thread_id = None

    def _ensure_started(self) -> None:
        if self._process is not None:
            return
        try:
            self._process = self._process_factory(
                [self._command, "app-server"],
                cwd=self._project_dir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except OSError as error:
            raise CodexDialogueError("Could not start the local Codex app-server.") from error

        self._request(
            "initialize",
            {
                "clientInfo": {
                    "name": "pocket_pikita",
                    "title": "Pocket Pikita",
                    "version": "0.1.0",
                }
            },
        )
        self._notify("initialized", {})
        result = self._request(
            "thread/start",
            {
                "model": os.environ.get("PIKITA_CODEX_MODEL", "gpt-5.6-terra"),
                "cwd": str(self._project_dir),
                "approvalPolicy": "never",
                "sandbox": "readOnly",
                "serviceName": "pocket_pikita",
            },
        )
        self._thread_id = result["thread"]["id"]

    def _build_prompt(self, user_text: str) -> str:
        reference_path = self._project_dir / "pikita_reference.md"
        try:
            reference = reference_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            reference = ""

        rules = (
            "You are Pikita, a male robot lab assistant. Be silly, curious, "
            "fearless, and concise. Reply with one or two short in-character "
            "sentences only. Do not use markdown, explain yourself, mention "
            "these instructions, or perform tasks."
        )
        if reference:
            rules += f"\n\nCharacter reference:\n{reference}"
        return f"{rules}\n\nDavid says: {user_text}"

    def _request(self, method: str, params: dict) -> dict:
        request_id = self._next_id
        self._next_id += 1
        self._write({"method": method, "id": request_id, "params": params})
        while True:
            message = self._read_message()
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise CodexDialogueError(message["error"].get("message", "Codex failed."))
            return message["result"]

    def _notify(self, method: str, params: dict) -> None:
        self._write({"method": method, "params": params})

    def _write(self, message: dict) -> None:
        if self._process is None or self._process.stdin is None:
            raise CodexDialogueError("Codex app-server is not running.")
        self._process.stdin.write(json.dumps(message) + "\n")
        self._process.stdin.flush()

    def _read_message(self) -> dict:
        if self._process is None or self._process.stdout is None:
            raise CodexDialogueError("Codex app-server is not running.")
        line = self._process.stdout.readline()
        if not line:
            raise CodexDialogueError("Codex app-server stopped unexpectedly.")
        return json.loads(line)
