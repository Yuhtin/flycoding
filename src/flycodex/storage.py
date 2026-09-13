"""Crash-safe run state and the persisted Flycodex send budget."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import tempfile
from typing import Any
import uuid


GLOBAL_LIMIT = 30
ATTEMPT_LIMIT = 5
CONDITION_LIMIT = 10
ATTEMPT_ORDER = (
    "adaptive-1",
    "frozen-1",
    "random-1",
    "adaptive-2",
    "frozen-2",
    "random-2",
)
ATTEMPT_CONDITIONS = {
    "adaptive-1": "adaptive",
    "frozen-1": "frozen",
    "random-1": "random",
    "adaptive-2": "adaptive",
    "frozen-2": "frozen",
    "random-2": "random",
}


class StoreLocked(RuntimeError):
    """Another process already owns the run directory."""


class StoreCorrupt(RuntimeError):
    """Persisted state does not satisfy the fixed pilot contract."""


class BudgetExceeded(RuntimeError):
    """A persisted send limit has already been reached."""


def load_json(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise StoreCorrupt(f"cannot load JSON from {path}") from exc


def atomic_save_json(path: Path, value: Any) -> None:
    """Replace a JSON file atomically and fsync both the file and directory."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def _canonical_manifest(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": 1,
        "settings": deepcopy(settings),
        "limits": {
            "global": GLOBAL_LIMIT,
            "attempt": ATTEMPT_LIMIT,
            "condition": CONDITION_LIMIT,
        },
        "attempt_order": list(ATTEMPT_ORDER),
        "attempts": {
            attempt: {"condition": ATTEMPT_CONDITIONS[attempt]}
            for attempt in ATTEMPT_ORDER
        },
    }


def _validate_manifest(manifest: Any) -> None:
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise StoreCorrupt("unsupported manifest version")
    if manifest.get("limits") != _canonical_manifest({})["limits"]:
        raise StoreCorrupt("manifest limits differ from the fixed pilot limits")
    if manifest.get("attempt_order") != list(ATTEMPT_ORDER):
        raise StoreCorrupt("manifest attempt order differs from the fixed pilot allocation")
    if manifest.get("attempts") != _canonical_manifest({})["attempts"]:
        raise StoreCorrupt("manifest condition allocation differs from the fixed pilot allocation")
    if not isinstance(manifest.get("settings"), dict):
        raise StoreCorrupt("manifest settings must be an object")


def _validate_state(state: Any) -> None:
    if not isinstance(state, dict) or state.get("version") != 1:
        raise StoreCorrupt("unsupported state version")
    reservations = state.get("reservations")
    if not isinstance(reservations, dict):
        raise StoreCorrupt("state reservations must be an object")
    if len(reservations) > GLOBAL_LIMIT:
        raise StoreCorrupt("state exceeds the fixed global budget")
    attempt_counts = {attempt: 0 for attempt in ATTEMPT_ORDER}
    condition_counts = {condition: 0 for condition in set(ATTEMPT_CONDITIONS.values())}
    for send_id, reservation in reservations.items():
        if not isinstance(send_id, str) or not isinstance(reservation, dict):
            raise StoreCorrupt("invalid reservation entry")
        attempt = reservation.get("attempt")
        if attempt not in ATTEMPT_CONDITIONS:
            raise StoreCorrupt("reservation has an unknown attempt")
        if reservation.get("condition") != ATTEMPT_CONDITIONS[attempt]:
            raise StoreCorrupt("reservation condition conflicts with manifest allocation")
        if reservation.get("status") not in {"pending", "completed"}:
            raise StoreCorrupt("reservation has an invalid status")
        if reservation["status"] == "completed" and "result" not in reservation:
            raise StoreCorrupt("completed reservation has no result")
        if reservation["status"] == "pending" and "result" in reservation:
            raise StoreCorrupt("pending reservation unexpectedly has a result")
        attempt_counts[attempt] += 1
        condition_counts[ATTEMPT_CONDITIONS[attempt]] += 1
    if any(count > ATTEMPT_LIMIT for count in attempt_counts.values()):
        raise StoreCorrupt("state exceeds a fixed attempt budget")
    if any(count > CONDITION_LIMIT for count in condition_counts.values()):
        raise StoreCorrupt("state exceeds a fixed condition budget")


class RunStore:
    """Single-writer persistent storage for a single pilot run."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"
        self.state_path = self.root / "state.json"
        self.journal_path = self.root / "journal.jsonl"
        self._lock_handle = (self.root / ".writer.lock").open("a+")
        self._closed = False
        try:
            fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._lock_handle.close()
            self._closed = True
            raise StoreLocked(f"run store is already open: {self.root}") from exc
        try:
            manifest_exists = self.manifest_path.exists()
            state_exists = self.state_path.exists()
            if manifest_exists != state_exists:
                raise StoreCorrupt("manifest and state must either both exist or both be absent")
            self._manifest = load_json(self.manifest_path) if manifest_exists else None
            self._state = load_json(self.state_path) if state_exists else None
            if self._manifest is not None:
                _validate_manifest(self._manifest)
                _validate_state(self._state)
        except Exception:
            self.close()
            raise

    def __enter__(self) -> RunStore:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_UN)
        self._lock_handle.close()
        self._closed = True

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("run store is closed")

    def _append_event(self, event: dict[str, Any]) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **deepcopy(event),
        }
        with self.journal_path.open("a") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def initialize(self, settings: dict[str, Any]) -> None:
        """Set run settings before the first reservation and persist allocation."""
        self._require_open()
        if not isinstance(settings, dict):
            raise TypeError("settings must be a dictionary")
        if self._state is not None and self._state["reservations"]:
            raise ValueError("settings cannot change after the first reservation")
        manifest = _canonical_manifest(settings)
        state = self._state or {"version": 1, "reservations": {}}
        atomic_save_json(self.manifest_path, manifest)
        atomic_save_json(self.state_path, state)
        self._manifest = manifest
        self._state = state
        self._append_event({"event": "store_initialized", "settings": deepcopy(settings)})

    def _require_initialized(self) -> None:
        self._require_open()
        if self._manifest is None or self._state is None:
            raise RuntimeError("run store has not been initialized")

    def reserve(self, attempt: str) -> str:
        """Durably consume one send before a Codex submission begins."""
        self._require_initialized()
        if attempt not in self._manifest["attempts"]:
            raise ValueError(f"unknown attempt: {attempt}")
        reservations = self._state["reservations"]
        if len(reservations) >= GLOBAL_LIMIT:
            raise BudgetExceeded("global send budget exhausted")
        condition = self._manifest["attempts"][attempt]["condition"]
        condition_count = sum(
            entry["condition"] == condition for entry in reservations.values()
        )
        if condition_count >= CONDITION_LIMIT:
            raise BudgetExceeded(f"condition send budget exhausted: {condition}")
        attempt_count = sum(entry["attempt"] == attempt for entry in reservations.values())
        if attempt_count >= ATTEMPT_LIMIT:
            raise BudgetExceeded(f"attempt send budget exhausted: {attempt}")
        send_id = f"send-{uuid.uuid4().hex}"
        reservation = {
            "attempt": attempt,
            "condition": condition,
            "status": "pending",
        }
        reservations[send_id] = reservation
        atomic_save_json(self.state_path, self._state)
        self._append_event(
            {
                "event": "send_reserved",
                "send_id": send_id,
                "attempt": attempt,
                "condition": condition,
            }
        )
        return send_id

    def complete(self, send_id: str, result: dict[str, Any]) -> None:
        """Close an existing pending reservation exactly once."""
        self._require_initialized()
        if not isinstance(result, dict):
            raise TypeError("result must be a dictionary")
        stored_result = deepcopy(result)
        json.dumps(stored_result)
        reservation = self._state["reservations"].get(send_id)
        if reservation is None:
            raise ValueError(f"unknown reservation: {send_id}")
        if reservation["status"] != "pending":
            raise ValueError(f"reservation already completed: {send_id}")
        reservation["status"] = "completed"
        reservation["result"] = stored_result
        atomic_save_json(self.state_path, self._state)
        self._append_event(
            {
                "event": "send_completed",
                "send_id": send_id,
                "result": deepcopy(stored_result),
            }
        )

    def snapshot(self) -> dict[str, Any]:
        self._require_initialized()
        return deepcopy(self._state)
