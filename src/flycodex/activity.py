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
import math
import os
from pathlib import Path
import re
import time
from typing import Mapping

from .neural.activity import ACTIVITY_SCHEMA_VERSION, BIN_MS, copy_bin


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


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError):
        return False


def _valid_bin(event):
    if not isinstance(event, dict) or event.get("type") != "bin":
        return False
    required = {"seq", "type", "start_ms", "end_ms", "indices", "counts", "total_spikes"}
    if not required <= event.keys() or not _is_int(event["seq"]):
        return False
    if not _is_number(event["start_ms"]) or not _is_number(event["end_ms"]):
        return False
    if event["end_ms"] <= event["start_ms"] or not math.isclose(
        event["end_ms"] - event["start_ms"], BIN_MS, rel_tol=0.0, abs_tol=1e-6
    ):
        return False
    indices, counts = event["indices"], event["counts"]
    if not isinstance(indices, list) or not isinstance(counts, list) or len(indices) != len(counts):
        return False
    if any(not _is_int(index) or index < 0 for index in indices):
        return False
    if indices != sorted(set(indices)):
        return False
    if any(not _is_int(count) or count < 0 for count in counts):
        return False
    return _is_int(event["total_spikes"]) and event["total_spikes"] >= 0 and sum(counts) == event["total_spikes"]


def _valid_activity(document):
    if not isinstance(document, dict) or document.get("schema_version") != PUBLIC_ACTIVITY_SCHEMA_VERSION:
        return False
    if not _is_int(document.get("schema_version")) or not _is_int(document.get("activity_schema_version")):
        return False
    if document["activity_schema_version"] != ACTIVITY_SCHEMA_VERSION:
        return False
    if not isinstance(document.get("available"), bool):
        return False
    status = document.get("status")
    if status not in {"running", "complete", "error"}:
        return False
    if document["available"] != (status != "error"):
        return False
    identity = ("run", "attempt", "turn", "phase", "window_id", "neuron_order_sha256")
    if not isinstance(document.get("run"), str) or not document["run"]:
        return False
    if not isinstance(document.get("attempt"), str) or not document["attempt"]:
        return False
    if not _is_int(document.get("turn")) or document["turn"] < 1:
        return False
    if document.get("phase") not in {"choice", "feedback"}:
        return False
    if not isinstance(document.get("window_id"), str) or not document["window_id"]:
        return False
    if not isinstance(document.get("neuron_order_sha256"), str) or not re.fullmatch(
        r"[0-9a-f]{64}", document["neuron_order_sha256"]
    ):
        return False
    window = document.get("window")
    if not isinstance(window, dict):
        return False
    required = {"window_id", "run", "attempt", "turn", "phase", "window_ms", "status", "events"}
    if not required <= window.keys():
        return False
    if {key: window.get(key) for key in identity[:5]} != {key: document.get(key) for key in identity[:5]}:
        return False
    expected_window_ms = 500 if document["phase"] == "choice" else 200
    if (
        window.get("status") != status
        or not _is_int(window.get("window_ms"))
        or window["window_ms"] != expected_window_ms
    ):
        return False
    events = window.get("events")
    if not isinstance(events, list):
        return False
    if status != "error" and not events:
        return False
    if events and (not isinstance(events[0], dict) or events[0].get("type") != "start"):
        return False
    previous = 0
    expected_bin_start = None
    saw_bin = False
    for position, event in enumerate(events):
        if not isinstance(event, dict) or not _is_int(event.get("seq")) or event["seq"] <= previous:
            return False
        previous = event["seq"]
        event_type = event.get("type")
        if event_type == "start":
            if position != 0 or not _is_int(event.get("window_ms")) or event["window_ms"] != window["window_ms"]:
                return False
        elif event_type == "bin":
            if not _valid_bin(event):
                return False
            if expected_bin_start is None:
                expected_bin_start = event["start_ms"]
            if not math.isclose(event["start_ms"], expected_bin_start, rel_tol=0.0, abs_tol=1e-6):
                return False
            if event["end_ms"] > expected_bin_start + window["window_ms"] + 1e-6:
                return False
            expected_bin_start = float(event["end_ms"])
            saw_bin = True
        elif event_type == "end":
            if position != len(events) - 1:
                return False
            if status == "running":
                return False
            if any(key in event and not isinstance(event[key], dict) for key in ("choice", "feedback")):
                return False
        else:
            return False
    if status == "complete" and (not saw_bin or not events or events[-1].get("type") != "end"):
        return False
    return True


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
                    "window_ms": self._window.get("window_ms", 0),
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
        self._window["events"].append({"seq": self._sequence, "recorded_at_ms": int(time.time() * 1000), **measured})
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
            if not _valid_activity(document):
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
