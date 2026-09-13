"""Streaming subprocess boundary for serial Codex turns."""

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import threading
import time
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
        self._state_changed = threading.Condition(self._state_lock)
        self._termination_lock = threading.Lock()
        self._active = False
        self._owner_thread: int | None = None
        self._process: subprocess.Popen[str] | None = None
        self._process_group: int | None = None
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
    def _group_exists(process_group: int) -> bool:
        try:
            os.killpg(process_group, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            # Darwin can report EPERM for a group whose last process is being
            # reaped. It is no longer a group this runner can signal.
            return False
        return True

    def _terminate(self, process: subprocess.Popen[str], process_group: int) -> None:
        """Terminate the whole group, even when its direct child has exited."""
        with self._termination_lock:
            if self._group_exists(process_group):
                try:
                    os.killpg(process_group, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
                grace_deadline = time.monotonic() + 0.1
                while self._group_exists(process_group) and time.monotonic() < grace_deadline:
                    time.sleep(0.01)
            if self._group_exists(process_group):
                try:
                    os.killpg(process_group, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                process.wait(timeout=0.5)
            gone_deadline = time.monotonic() + 0.5
            while self._group_exists(process_group) and time.monotonic() < gone_deadline:
                time.sleep(0.01)

    @staticmethod
    def _close_pipe(stream) -> None:
        try:
            os.close(stream.fileno())
        except (OSError, ValueError):
            pass

    def cancel(self) -> None:
        """Cancel startup or terminate the active group, then await cleanup."""
        caller = threading.get_ident()
        with self._state_changed:
            if not self._active:
                return
            self._cancel_requested = True
            self._state_changed.notify_all()
            owns_run = caller == self._owner_thread
            while not owns_run and self._active and self._process is None:
                self._state_changed.wait()
            process = self._process
            process_group = self._process_group
        if process is not None and process_group is not None:
            self._terminate(process, process_group)
        if owns_run:
            return
        with self._state_changed:
            while self._active:
                self._state_changed.wait()

    @staticmethod
    def _parse_event(line: str, stream_name: str) -> dict[str, Any] | None:
        line = line.rstrip("\r\n")
        if not line:
            return None
        try:
            event = json.loads(line)
            if not isinstance(event, dict) or "type" not in event:
                raise ValueError("not a Codex event object")
            return event
        except (json.JSONDecodeError, ValueError):
            return {"type": "diagnostic", "stream": stream_name, "message": line}

    def _release_active(self) -> None:
        with self._state_changed:
            self._process = None
            self._process_group = None
            self._active = False
            self._owner_thread = None
            self._state_changed.notify_all()

    def _claim_active(self) -> float:
        with self._state_changed:
            if self._active:
                raise RuntimeError("a Codex turn is already active")
            self._active = True
            self._owner_thread = threading.get_ident()
            self._process = None
            self._process_group = None
            self._cancel_requested = False
        return time.monotonic() + self.timeout

    def _publish_process(self, process: subprocess.Popen[str]) -> bool:
        with self._state_changed:
            self._process = process
            self._process_group = process.pid
            cancelled = self._cancel_requested
            self._state_changed.notify_all()
            return cancelled

    def _submit_prompt(self, process: subprocess.Popen[str], prompt: str) -> bool:
        """Serialize the cancellation check with the first prompt write."""
        with self._state_changed:
            if self._cancel_requested:
                try:
                    process.stdin.close()
                except BrokenPipeError:
                    pass
                return False
            try:
                process.stdin.write(prompt)
                process.stdin.close()
            except BrokenPipeError:
                pass
            return True

    def run(
        self,
        prompt: str,
        session_id: str | None,
        on_event: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        """Submit exactly one prompt, streaming and durably recording events."""
        if not self.workspace.is_dir():
            raise ValueError(f"workspace does not exist: {self.workspace}")
        deadline = self._claim_active()
        process: subprocess.Popen[str] | None = None
        event_file = None
        started_readers: list[threading.Thread] = []
        try:
            full_prompt = (
                prompt
                if session_id is not None
                else f"{INITIAL_CONTEXT}\nSelected instruction:\n{prompt}"
            )
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
            cancelled_before_submit = self._publish_process(process)

            reported_session = session_id
            usage: dict[str, Any] = {}
            turn_completed = False
            turn_error: str | None = None
            callback_error: Exception | None = None
            timed_out = False
            event_queue: queue.Queue[object] = queue.Queue()
            stream_finished = object()
            self.events_path.parent.mkdir(parents=True, exist_ok=True)
            event_file = self.events_path.open("a")

            def emit(event: dict[str, Any]) -> None:
                nonlocal reported_session, usage, turn_completed, turn_error, callback_error
                event_file.write(json.dumps(event, sort_keys=True) + "\n")
                event_file.flush()
                os.fsync(event_file.fileno())
                event_type = event.get("type")
                if event_type == "thread.started" and isinstance(
                    event.get("thread_id"), str
                ):
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
                try:
                    for line in stream:
                        event = self._parse_event(line, stream_name)
                        if event is not None:
                            event_queue.put(event)
                except (OSError, ValueError):
                    pass
                finally:
                    event_queue.put(stream_finished)

            readers = [
                threading.Thread(
                    target=read_stream, args=(process.stdout, "stdout"), daemon=True
                ),
                threading.Thread(
                    target=read_stream, args=(process.stderr, "stderr"), daemon=True
                ),
            ]
            for reader in readers:
                reader.start()
                started_readers.append(reader)

            cleanup_deadline: float | None = None
            open_streams = 2
            submitted = self._submit_prompt(process, full_prompt)
            if cancelled_before_submit or not submitted:
                self._terminate(process, process.pid)
                cleanup_deadline = time.monotonic() + 0.5
            while open_streams or process.poll() is None:
                with self._state_changed:
                    cancelled = self._cancel_requested
                now = time.monotonic()
                if cancelled and cleanup_deadline is None:
                    self._terminate(process, process.pid)
                    cleanup_deadline = time.monotonic() + 0.5
                elif process.poll() is not None and cleanup_deadline is None:
                    process.wait()
                    if self._group_exists(process.pid):
                        self._terminate(process, process.pid)
                    cleanup_deadline = time.monotonic() + 0.5
                elif now >= deadline and cleanup_deadline is None:
                    timed_out = True
                    self._terminate(process, process.pid)
                    cleanup_deadline = time.monotonic() + 0.5
                if cleanup_deadline is not None and now >= cleanup_deadline:
                    self._close_pipe(process.stdout)
                    self._close_pipe(process.stderr)
                    break
                wait_for = 0.02
                if cleanup_deadline is None:
                    wait_for = max(0.001, min(wait_for, deadline - now))
                try:
                    item = event_queue.get(timeout=wait_for)
                except queue.Empty:
                    continue
                if item is stream_finished:
                    open_streams -= 1
                else:
                    emit(item)
            for reader in started_readers:
                reader.join(timeout=0.2)
            while True:
                try:
                    item = event_queue.get_nowait()
                except queue.Empty:
                    break
                if item is not stream_finished:
                    emit(item)
            if process.poll() is None or self._group_exists(process.pid):
                self._terminate(process, process.pid)
            return_code = process.wait()
            with self._state_changed:
                cancelled = self._cancel_requested
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
        finally:
            try:
                if process is not None:
                    try:
                        if process.stdin is not None and not process.stdin.closed:
                            process.stdin.close()
                    except (BrokenPipeError, OSError):
                        pass
                    if process.poll() is None or self._group_exists(process.pid):
                        self._terminate(process, process.pid)
                    for reader, stream in zip(
                        started_readers, (process.stdout, process.stderr)
                    ):
                        if reader.is_alive():
                            self._close_pipe(stream)
                    for reader in started_readers:
                        reader.join(timeout=0.2)
            finally:
                try:
                    if event_file is not None:
                        event_file.close()
                finally:
                    self._release_active()
