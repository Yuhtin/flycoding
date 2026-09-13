"""Streaming subprocess boundary for serial Codex turns."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import threading
from typing import Callable, Any


PROMPTS = {
    "investigate": "Analise a falha e explique a provável causa, sem editar.",
    "fix": "Corrija a função de desconto, preservando os testes.",
    "test": "Execute os testes e relate o resultado.",
}

INITIAL_CONTEXT = """\
This dedicated arithmetic benchmark and its edit scope are already approved.
Act on the selected instruction directly, without a design interview, skills,
subagents, or unrelated repository work. Only edit `discount.py`; preserve
`test_discount.py`, `AGENTS.md`, and every file outside this workspace. The
task supports only the documented pure integer-arithmetic function. Follow the
workspace instructions when running commands.
"""


def _event_error(value: Any) -> str:
    if isinstance(value, dict):
        if isinstance(value.get("message"), str):
            return value["message"]
        return json.dumps(value, sort_keys=True)
    return str(value)


class CodexRunner:
    """Run at most one Codex subprocess and stream its JSONL event boundary."""

    def __init__(
        self,
        workspace: Path,
        model: str | None = None,
        timeout: float = 300,
        executable: str = "codex",
    ):
        self.workspace = Path(workspace).resolve()
        self.model = model
        self.timeout = timeout
        self.executable = executable
        self.events_path = self.workspace.parent / "codex-events.jsonl"
        self._state_lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._cancel_requested = False

    def _arguments(self, session_id: str | None) -> list[str]:
        arguments = [
            self.executable,
            "-a",
            "never",
            "exec",
            "--sandbox",
            "workspace-write",
            "--ignore-user-config",
            "--json",
            "--color",
            "never",
            "-C",
            str(self.workspace),
        ]
        if self.model is not None:
            arguments.extend(["--model", self.model])
        if session_id is not None:
            arguments.extend(["resume", session_id])
        arguments.append("-")
        return arguments

    @staticmethod
    def _environment() -> dict[str, str]:
        environment = os.environ.copy()
        # A turn resumes only through the explicit CLI session argument. Parent
        # controller identity must never implicitly select a conversation.
        environment.pop("CODEX_SESSION_ID", None)
        environment.pop("CODEX_THREAD_ID", None)
        return environment

    @staticmethod
    def _terminate(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            process.wait()
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            process.wait()
            return
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()

    def cancel(self) -> None:
        """Terminate the active process group and wait until it is reaped."""
        with self._state_lock:
            self._cancel_requested = True
            process = self._process
        if process is not None:
            self._terminate(process)

    def run(
        self,
        prompt: str,
        session_id: str | None,
        on_event: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        """Submit exactly one prompt, streaming and durably recording events."""
        if not self.workspace.is_dir():
            raise ValueError(f"workspace does not exist: {self.workspace}")
        with self._state_lock:
            if self._process is not None:
                raise RuntimeError("a Codex turn is already active")
            self._cancel_requested = False

        full_prompt = prompt if session_id is not None else f"{INITIAL_CONTEXT}\nSelected instruction:\n{prompt}"
        try:
            process = subprocess.Popen(
                self._arguments(session_id),
                cwd=self.workspace,
                env=self._environment(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
        except OSError as exc:
            return {
                "session_id": session_id,
                "status": "failed",
                "usage": {},
                "error": f"could not start Codex: {exc}",
            }
        with self._state_lock:
            self._process = process

        events: list[dict[str, Any]] = []
        event_lock = threading.Lock()
        reported_session = session_id
        usage: dict[str, Any] = {}
        turn_completed = False
        turn_error: str | None = None
        callback_error: Exception | None = None
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        event_file = self.events_path.open("a")

        def emit(event: dict[str, Any]) -> None:
            nonlocal reported_session, usage, turn_completed, turn_error, callback_error
            with event_lock:
                events.append(event)
                event_file.write(json.dumps(event, sort_keys=True) + "\n")
                event_file.flush()
                os.fsync(event_file.fileno())
                event_type = event.get("type")
                if event_type == "thread.started" and isinstance(event.get("thread_id"), str):
                    reported_session = event["thread_id"]
                elif event_type == "turn.completed":
                    turn_completed = True
                    if isinstance(event.get("usage"), dict):
                        usage = event["usage"]
                elif event_type in {"turn.failed", "error"}:
                    turn_error = _event_error(event.get("error", event))
                try:
                    on_event(event)
                except Exception as exc:
                    callback_error = exc

        def read_stream(stream, stream_name: str) -> None:
            for line in stream:
                line = line.rstrip("\r\n")
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if not isinstance(event, dict) or "type" not in event:
                        raise ValueError("not a Codex event object")
                except (json.JSONDecodeError, ValueError):
                    event = {"type": "diagnostic", "stream": stream_name, "message": line}
                emit(event)

        stdout_thread = threading.Thread(
            target=read_stream, args=(process.stdout, "stdout"), daemon=True
        )
        stderr_thread = threading.Thread(
            target=read_stream, args=(process.stderr, "stderr"), daemon=True
        )
        stdout_thread.start()
        stderr_thread.start()
        try:
            try:
                process.stdin.write(full_prompt)
                process.stdin.close()
            except BrokenPipeError:
                pass
            timed_out = False
            try:
                return_code = process.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                self._terminate(process)
                return_code = process.returncode
            stdout_thread.join()
            stderr_thread.join()
        finally:
            event_file.close()
            with self._state_lock:
                cancelled = self._cancel_requested
                self._process = None

        if callback_error is not None and turn_error is None:
            turn_error = f"event callback failed: {callback_error}"
        if cancelled:
            status = "cancelled"
            error = "Codex turn was cancelled"
        elif timed_out:
            status = "timed_out"
            error = f"Codex turn exceeded {self.timeout} seconds"
        elif return_code != 0 or turn_error is not None:
            status = "failed"
            error = turn_error or f"Codex exited with status {return_code}"
        elif not turn_completed:
            status = "failed"
            error = "Codex exited without a turn.completed event"
        elif session_id is None and reported_session is None:
            status = "failed"
            error = "Codex did not report a session ID"
        else:
            status = "completed"
            error = None
        return {
            "session_id": reported_session,
            "status": status,
            "usage": usage,
            "error": error,
        }
