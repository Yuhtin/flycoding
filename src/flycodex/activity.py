"""Bounded, identity-bound public telemetry for future pilot windows.

The recorder deliberately has no event bus or filesystem browsing API.  A
pilot opens one named window, appends measured bins, and closes that window.
Every write is a complete JSON replacement, so readers never parse a partial
document.  Oversized windows become explicitly unavailable instead of being
silently truncated.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Mapping

from .neural.activity import ACTIVITY_SCHEMA_VERSION, copy_bin


PUBLIC_ACTIVITY_SCHEMA_VERSION = 1
MAX_ACTIVITY_BYTES = 8 * 1024 * 1024


def _safe_json(value):
    if isinstance(value, dict):
        return {str(key): _safe_json(item) for key, item in list(value.items())[:64]}
    if isinstance(value, (list, tuple)):
        # Measured sparse arrays are never truncated: indices/counts must stay
        # pairwise complete. The finite document bound below turns an
        # oversized window into an explicit unavailable result.
        return [_safe_json(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)[:4096]


class ActivityRecorder:
    """Write one bounded latest-window document and immutable per-window copies."""

    def __init__(self, public_dir: Path, *, run: str, attempt: str, turn: int,
                 phase: str, neuron_order_sha256: str | None):
        raw_public = Path(public_dir).expanduser()
        if raw_public.is_symlink():
            raise OSError("activity public directory must not be a symlink")
        self.public_dir = raw_public.resolve()
        self.public_dir.mkdir(parents=True, exist_ok=True)
        self.run = str(run)
        self.attempt = str(attempt)
        self.turn = int(turn)
        self.phase = str(phase)
        self.neuron_order_sha256 = neuron_order_sha256
        self._window = None
        self._window_id = None
        self._sequence = 0

    def _identity(self):
        return {
            "run": self.run,
            "attempt": self.attempt,
            "turn": self.turn,
            "phase": self.phase,
            "window_id": self._window_id,
            "neuron_order_sha256": self.neuron_order_sha256,
            "activity_schema_version": ACTIVITY_SCHEMA_VERSION,
        }

    def _document(self):
        status = self._window.get("status", "running") if self._window else "unavailable"
        return {
            "schema_version": PUBLIC_ACTIVITY_SCHEMA_VERSION,
            "available": self._window is not None and status != "error",
            "status": status,
            **self._identity(),
            "window": copy.deepcopy(self._window) if self._window else None,
        }

    def _write(self, *, immutable=False):
        document = _safe_json(self._document())
        encoded = (json.dumps(document, separators=(",", ":"), allow_nan=False) + "\n").encode()
        if len(encoded) > MAX_ACTIVITY_BYTES:
            if self._window is not None and self._window.get("status") != "error":
                self._window = {
                    "window_id": self._window_id,
                    "run": self.run,
                    "attempt": self.attempt,
                    "turn": self.turn,
                    "phase": self.phase,
                    "status": "error",
                    "error": "activity window exceeds bounded public size",
                    "events": [],
                }
            document = _safe_json(self._document())
            encoded = (json.dumps(document, separators=(",", ":"), allow_nan=False) + "\n").encode()
        if len(encoded) > MAX_ACTIVITY_BYTES:
            raise ValueError("activity document exceeds bounded public size")
        target = self.public_dir / "activity.json"
        if target.is_symlink():
            raise OSError("activity target must not be a symlink")
        if immutable:
            directory = self.public_dir / "activity"
            directory.mkdir(exist_ok=True)
            target = directory / f"{self._window_id}.json"
            if target.exists() or target.is_symlink():
                raise FileExistsError(f"activity window already exists: {self._window_id}")
        partial = target.with_suffix(target.suffix + ".partial")
        if partial.is_symlink():
            raise OSError("activity temporary target must not be a symlink")
        fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                fd = None
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(partial, target)
        finally:
            if fd is not None:
                os.close(fd)

    def start(self, *, window: str, window_ms: int):
        if self._window is not None and self._window.get("status") == "running":
            raise RuntimeError("activity window already running")
        self._window_id = str(window)
        self._sequence = 1
        self._window = {
            "window_id": self._window_id,
            "run": self.run,
            "attempt": self.attempt,
            "turn": self.turn,
            "phase": self.phase,
            "window_ms": int(window_ms),
            "status": "running",
            "events": [{"seq": 1, "type": "start", "window_ms": int(window_ms)}],
        }
        self._write()

    def bin(self, value: Mapping):
        if self._window is None or self._window.get("status") != "running":
            if self._window is not None and self._window.get("status") == "error":
                return
            raise RuntimeError("activity window is not running")
        measured = copy_bin(value)
        self._sequence += 1
        self._window["events"].append({"seq": self._sequence, **measured})
        self._write()

    def end(self, *, choice=None, feedback=None, error=None):
        if self._window is None or self._window.get("status") != "running":
            if self._window is not None and self._window.get("status") == "error":
                return
            raise RuntimeError("activity window is not running")
        self._sequence += 1
        event = {"seq": self._sequence, "type": "end"}
        if choice is not None:
            event["choice"] = _safe_json(choice)
        if feedback is not None:
            event["feedback"] = _safe_json(feedback)
        if error is not None:
            event["error"] = str(error)[:4096]
        self._window["events"].append(event)
        self._window["status"] = "error" if error is not None else "complete"
        self._write(immutable=True)
        self._write()


class ActivityReader:
    """Read only the explicitly named public activity artifact."""

    def __init__(self, public_dir: Path):
        self.public_dir = Path(public_dir).expanduser()

    def read(self, after: int | None = None) -> dict:
        if self.public_dir.is_symlink():
            return {"available": False, "reason": "symlink"}
        self.public_dir = self.public_dir.resolve()
        target = self.public_dir / "activity.json"
        if target.is_symlink() or not target.is_file():
            if (target.with_suffix(target.suffix + ".partial")).exists():
                return {"available": False, "reason": "incomplete"}
            return {"available": False, "reason": "missing"}
        try:
            if target.stat().st_size > MAX_ACTIVITY_BYTES:
                return {"available": False, "reason": "too_large"}
            document = json.loads(target.read_text())
            if not isinstance(document, dict) or document.get("schema_version") != PUBLIC_ACTIVITY_SCHEMA_VERSION:
                return {"available": False, "reason": "invalid"}
            if after is not None:
                if isinstance(after, bool) or not isinstance(after, int) or after < 0:
                    raise ValueError("after must be a nonnegative integer")
                document = copy.deepcopy(document)
                window = document.get("window")
                if isinstance(window, dict):
                    window["events"] = [event for event in window.get("events", []) if event.get("seq", 0) > after]
            return document
        except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
            return {"available": False, "reason": "incomplete"}


def read_activity(public_dir: Path, after: int | None = None) -> dict:
    return ActivityReader(public_dir).read(after=after)
