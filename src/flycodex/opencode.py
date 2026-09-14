"""Streaming boundary for the pinned OpenCode JSONL runner."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .codex import CodexRunner, _event_error


DEFAULT_MODEL = "opencode/muse-spark-1.3-contributor-free"


class OpenCodeRunner(CodexRunner):
    """Run one explicit OpenCode turn with conservative completion evidence."""

    def __init__(
        self,
        workspace: Path,
        model: str = DEFAULT_MODEL,
        timeout: float = 300,
        executable: str = "opencode",
        title: str = "flycodex-task",
    ):
        super().__init__(workspace, model=model, timeout=timeout, executable=executable)
        self.title = title
        self.events_path = self.workspace.parent / "opencode-events.jsonl"
        # Keep runner-owned configuration beside the task workspace. The
        # workspace itself is an evaluator-owned checkout and must stay clean.
        self._config_root = self.workspace.parent / ".flycodex-opencode"

    @property
    def _runner_name(self) -> str:
        return "OpenCode"

    def _arguments(self, session_id: str | None) -> list[str]:
        arguments = [
            self.executable,
            "run",
            "--pure",
            "--format",
            "json",
            "--model",
            self.model,
            "--title",
            self.title,
            "--dir",
            str(self.workspace),
        ]
        if session_id is not None:
            arguments.extend(["--session", session_id])
        return arguments

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        self._config_root.mkdir(parents=True, exist_ok=True)
        xdg_root = self._config_root / "xdg"
        config_dir = self._config_root / "config"
        xdg_root.mkdir(parents=True, exist_ok=True)
        config_dir.mkdir(parents=True, exist_ok=True)
        permissions = {
            "read": {
                "*": "deny",
                f"{self.workspace}/**": "allow",
            },
            "edit": {
                "*": "deny",
                str(self.workspace / "discount.py"): "allow",
            },
            "bash": {
                "*": "deny",
                "rtk proxy python -B -m unittest -v": "allow",
                "python -B -m unittest -v": "allow",
            },
            "external_directory": "deny",
            "task": "deny",
            "skill": "deny",
            "question": "deny",
            "webfetch": "deny",
            "websearch": "deny",
        }
        config = {
            "$schema": "https://opencode.ai/config.json",
            "model": self.model,
            "small_model": self.model,
            "share": "disabled",
            "mcp": {},
            "plugin": [],
            "lsp": False,
            "formatter": False,
            "permission": permissions,
        }
        for key in (
            "OPENCODE_CONFIG",
            "OPENCODE_CONFIG_DIR",
            "OPENCODE_CONFIG_CONTENT",
            "XDG_CONFIG_HOME",
        ):
            environment.pop(key, None)
        environment["XDG_CONFIG_HOME"] = str(xdg_root)
        environment["OPENCODE_CONFIG_DIR"] = str(config_dir)
        environment["OPENCODE_CONFIG_CONTENT"] = json.dumps(
            config, separators=(",", ":"), sort_keys=True
        )
        environment["OPENCODE_DISABLE_PROJECT_CONFIG"] = "1"
        environment["OPENCODE_DISABLE_EXTERNAL_SKILLS"] = "1"
        environment["OPENCODE_DISABLE_CLAUDE_CODE"] = "1"
        environment["OPENCODE_DISABLE_CLAUDE_CODE_PROMPT"] = "1"
        environment["OPENCODE_DISABLE_CLAUDE_CODE_SKILLS"] = "1"
        environment["OPENCODE_DISABLE_DEFAULT_PLUGINS"] = "1"
        environment["OPENCODE_DISABLE_TERMINAL_TITLE"] = "1"
        environment["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
        environment["OPENCODE_DISABLE_LSP_DOWNLOAD"] = "1"
        environment["OPENCODE_CLIENT"] = "flycodex"
        environment.pop("CODEX_SESSION_ID", None)
        environment.pop("CODEX_THREAD_ID", None)
        return environment

    @staticmethod
    def _parse_event(line: str, stream_name: str) -> dict[str, Any] | None:
        line = line.rstrip("\r\n")
        if not line:
            return None
        try:
            event = json.loads(line)
            if not isinstance(event, dict) or "type" not in event:
                raise ValueError("not an OpenCode event object")
            return event
        except (json.JSONDecodeError, ValueError):
            return {
                "type": "diagnostic",
                "stream": stream_name,
                "message": line,
                "_malformed": True,
            }

    def _new_event_state(self, session_id: str | None) -> dict[str, Any]:
        return {
            "reported_session": session_id,
            "expected_session": session_id,
            "usage": {},
            "turn_error": None,
            "malformed_stdout": False,
            "session_mismatch": False,
            "last_step_reason": None,
        }

    def _normalize_event(
        self,
        event: dict[str, Any],
        stream_name: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        raw_type = event.get("type")
        session_id = event.get("sessionID")
        if (
            isinstance(session_id, str)
            and session_id
            and state["expected_session"] is not None
            and session_id != state["expected_session"]
        ):
            state["session_mismatch"] = True
        if isinstance(session_id, str) and session_id:
            state["reported_session"] = session_id
        if event.get("_malformed"):
            if stream_name == "stdout":
                state["malformed_stdout"] = True
                state["turn_error"] = "OpenCode emitted malformed JSON on stdout"
            raw = {
                "type": "diagnostic",
                "stream": event.get("stream", stream_name),
                "message": event.get("message", ""),
            }
            raw_type = "diagnostic"
        else:
            raw = event
        if raw_type == "error":
            state["turn_error"] = _event_error(event.get("error", event))
        if raw_type == "step_finish":
            part = event.get("part")
            part = part if isinstance(part, dict) else {}
            reason = part.get("reason", event.get("reason"))
            state["last_step_reason"] = reason
            usage = part.get("usage", part.get("tokens"))
            if isinstance(usage, dict):
                state["usage"] = usage
        kinds = {
            "tool_use": "tool",
            "step_start": "step_start",
            "step_finish": "step_finish",
            "text": "text",
            "reasoning": "reasoning",
            "error": "error",
            "diagnostic": "diagnostic",
            "status": "status",
        }
        kind = kinds.get(raw_type, "status")
        return {
            "backend": "opencode",
            "source": "opencode.run.jsonl",
            "kind": kind,
            "session_id": state["reported_session"],
            "raw_type": raw_type,
            "raw": raw,
        }

    def _final_result(
        self,
        state: dict[str, Any],
        return_code: int,
        cancelled: bool,
        timed_out: bool,
        callback_error: Exception | None,
    ) -> dict[str, Any]:
        if callback_error is not None and state["turn_error"] is None:
            state["turn_error"] = f"event callback failed: {callback_error}"
        if cancelled:
            status = "cancelled"
            error = "OpenCode turn was cancelled"
        elif timed_out:
            status = "timed_out"
            error = f"OpenCode turn exceeded {self.timeout} seconds"
        elif return_code != 0 or state["turn_error"] is not None:
            status = "failed"
            error = state["turn_error"] or f"OpenCode exited with status {return_code}"
        elif state["malformed_stdout"]:
            status = "failed"
            error = "OpenCode emitted malformed JSON on stdout"
        elif state["session_mismatch"]:
            status = "failed"
            error = "OpenCode session ID did not match the explicit resume session"
        elif state["reported_session"] is None:
            status = "failed"
            error = "OpenCode did not report a session ID"
        elif state["last_step_reason"] != "stop":
            status = "failed"
            error = "OpenCode completion_evidence_missing: final step_finish reason=stop was not observed"
        else:
            status = "completed"
            error = None
        return {
            "session_id": state["reported_session"],
            "status": status,
            "usage": state["usage"],
            "error": error,
        }
