"""Singleflight OpenCode service for the optional live typing player."""

from __future__ import annotations

import json
from pathlib import Path
import threading
import subprocess
import uuid
from typing import Any, Callable

from .opencode import DEFAULT_MODEL, OpenCodeRunner


TERMINAL_STATUSES = {"completed", "cancelled", "failed"}


class TypingBusyError(RuntimeError):
    """Raised when a different typing request is already active."""


class TypingClosedError(RuntimeError):
    """Raised when the typing service has been closed."""


class TypingValidationError(ValueError):
    """Raised for malformed typing input."""


class TypingOpenCodeRunner(OpenCodeRunner):
    """OpenCode runner whose edit permission is limited to its worktree."""

    def __init__(self, workspace: Path, model: str = DEFAULT_MODEL, **kwargs):
        super().__init__(workspace, model=model, **kwargs)
        self.events_path = self.workspace / ".flycodex" / "opencode-events.jsonl"

    @property
    def _initial_context(self) -> str:
        return (
            "This is an isolated coding workspace. Build the requested small app directly in this workspace. "
            "Keep all edits and commands inside the workspace, preserve useful existing files, and report "
            "the result plainly. Do not use subagents, external directories, plugins, or network tools."
        )

    def _environment(self) -> dict[str, str]:
        environment = super()._environment()
        config = json.loads(environment["OPENCODE_CONFIG_CONTENT"])
        # OpenCode may discover a Git worktree above --dir. Its edit requests
        # are relative to that root, so allow only this workspace's subtree.
        worktree = subprocess.run(
            ["git", "-C", str(self.workspace), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=False,
        )
        relative = "**"
        if worktree.returncode == 0:
            prefix = self.workspace.relative_to(Path(worktree.stdout.strip()).resolve())
            if str(prefix) != ".":
                relative = f"{prefix.as_posix()}/**"
        config["permission"]["edit"] = {
            "*": "deny", relative: "allow", f"{self.workspace}/**": "allow",
        }
        environment["OPENCODE_CONFIG_CONTENT"] = json.dumps(
            config, separators=(",", ":"), sort_keys=True
        )
        return environment


RunnerFactory = Callable[[Path, str], Any]


class TypingService:
    """Manage one live OpenCode request and expose a small polling state."""

    def __init__(
        self,
        workspace: Path,
        model: str = DEFAULT_MODEL,
        runner_factory: RunnerFactory | None = None,
    ):
        self.workspace = Path(workspace).expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.model = model or DEFAULT_MODEL
        self.runner_factory = runner_factory or (
            lambda path, selected_model: TypingOpenCodeRunner(path, model=selected_model)
        )
        self._lock = threading.RLock()
        self._closed = False
        self._runner = None
        self._thread: threading.Thread | None = None
        self._cancelled_jobs: set[str] = set()
        self._requests: dict[str, tuple[str, dict[str, Any]]] = {}
        self._state = self._new_state()

    def _new_state(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "status": "idle",
            "request_id": None,
            "job_id": None,
            "text": "",
            "prompt": "",
            "error": None,
            "model": self.model,
            "workspace": str(self.workspace),
        }

    def _snapshot_locked(self) -> dict[str, Any]:
        return dict(self._state)

    def state(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_locked()

    @staticmethod
    def _event_text(event: dict[str, Any]) -> tuple[str, bool]:
        if event.get("kind") != "text" and event.get("raw_type") != "text":
            return "", False
        raw = event.get("raw")
        if not isinstance(raw, dict):
            raw = event
        part = raw.get("part")
        if isinstance(part, dict):
            for key in ("text", "content"):
                value = part.get(key)
                if isinstance(value, str):
                    return value, bool(raw.get("delta") or part.get("delta"))
        for key in ("text", "content", "message"):
            value = raw.get(key)
            if isinstance(value, str):
                return value, bool(raw.get("delta"))
        content = raw.get("content")
        if isinstance(content, list):
            return "".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            ), bool(raw.get("delta"))
        return "", False

    def _on_event(self, job_id: str, event: dict[str, Any]) -> None:
        text, is_delta = self._event_text(event)
        with self._lock:
            if self._state.get("job_id") != job_id:
                return
            if self._state["status"] == "starting":
                self._state["status"] = "running"
            if text:
                if self._state["text"] and not is_delta and not self._state["text"].endswith("\n"):
                    self._state["text"] += "\n"
                self._state["text"] += text

    def _finish(self, job_id: str, result: dict[str, Any]) -> None:
        with self._lock:
            if self._state.get("job_id") != job_id:
                return
            cancelled = job_id in self._cancelled_jobs
            runner_status = result.get("status")
            if cancelled or runner_status == "cancelled":
                status = "cancelled"
                error = result.get("error") or "OpenCode turn was cancelled"
            elif runner_status == "completed":
                status = "completed"
                error = None
            else:
                status = "failed"
                error = result.get("error") or "OpenCode turn failed"
            self._state.update(status=status, error=error)
            self._requests[self._state["request_id"]] = (
                self._requests[self._state["request_id"]][0],
                self._snapshot_locked(),
            )
            self._runner = None
            self._thread = None
            self._cancelled_jobs.discard(job_id)

    def _run(self, job_id: str, prompt: str, request_id: str, runner: Any) -> None:
        try:
            result = runner.run(
                prompt,
                None,
                lambda event: self._on_event(job_id, event),
            )
            if not isinstance(result, dict):
                result = {"status": "failed", "error": "OpenCode returned invalid result"}
        except Exception as exc:  # runner boundary must become visible state
            result = {"status": "failed", "error": str(exc)}
        self._finish(job_id, result)

    def submit(self, prompt: str, request_id: str) -> dict[str, Any]:
        if not isinstance(prompt, str) or not prompt or len(prompt) > 1000:
            raise TypingValidationError("prompt must be a nonempty string of at most 1000 characters")
        if not isinstance(request_id, str) or not request_id or len(request_id) > 200:
            raise TypingValidationError("request_id must be a nonempty string of at most 200 characters")
        with self._lock:
            if self._closed:
                raise TypingClosedError("typing service is closed")
            previous = self._requests.get(request_id)
            if previous is not None:
                if previous[0] != prompt:
                    raise TypingValidationError("request_id was already used for a different prompt")
                if self._state.get("request_id") == request_id and self._state["status"] in {"starting", "running"}:
                    return self._snapshot_locked()
                return dict(previous[1])
            if self._state["status"] in {"starting", "running"}:
                raise TypingBusyError("another typing request is already running")
            job_id = uuid.uuid4().hex
            self._state.update(
                status="starting", request_id=request_id, job_id=job_id, text="", prompt=prompt, error=None
            )
            self._requests[request_id] = (prompt, self._snapshot_locked())
            try:
                runner = self.runner_factory(self.workspace, self.model)
            except Exception as exc:
                self._state.update(status="failed", error=str(exc))
                self._requests[request_id] = (prompt, self._snapshot_locked())
                return self._snapshot_locked()
            self._runner = runner
            self._thread = threading.Thread(
                target=self._run,
                args=(job_id, prompt, request_id, runner),
                name="flycoding-typing",
                daemon=True,
            )
            self._thread.start()
            return self._snapshot_locked()

    def cancel(self) -> dict[str, Any]:
        with self._lock:
            if self._closed:
                return self._snapshot_locked()
            runner = self._runner
            job_id = self._state.get("job_id")
            if self._state["status"] not in {"starting", "running"} or runner is None:
                return self._snapshot_locked()
            self._cancelled_jobs.add(job_id)
        try:
            runner.cancel()
        except Exception as exc:
            with self._lock:
                if self._state.get("job_id") == job_id:
                    # Keep the active slot until the worker actually exits.
                    self._state.update(error=str(exc))
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)
        with self._lock:
            return self._snapshot_locked()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            runner = self._runner
        if runner is not None:
            try:
                runner.cancel()
            except Exception:
                pass
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)
