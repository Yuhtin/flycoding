"""Bounded, single-flight local neural observation service."""

from __future__ import annotations

import copy
import inspect
import threading
import time
import uuid
from collections import deque
from pathlib import Path

import numpy as np

from .panel import render_panel
from .neural import NeuralPolicy
from .neural.activity import ACTIVITY_SCHEMA_VERSION, copy_bin, neuron_order_sha256


class LabBusyError(RuntimeError):
    """Raised when an observation is submitted while another is active."""


class LabClosedError(RuntimeError):
    """Raised when work is submitted after the service has closed."""


class InvalidObservation(ValueError):
    """Raised for an observation outside the intentionally small lab contract."""


class _Cancelled(Exception):
    pass


def _json_value(value, *, depth=0):
    if depth > 3:
        return None
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _json_value(item, depth=depth + 1) for key, item in list(value.items())[:32]}
    if isinstance(value, (list, tuple)):
        return [_json_value(item, depth=depth + 1) for item in list(value)[:64]]
    if isinstance(value, str):
        return value[:4096]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:4096]


def _factory_accepts_activity(factory) -> bool:
    try:
        parameters = inspect.signature(factory).parameters.values()
    except (TypeError, ValueError):
        return True
    return any(parameter.kind == parameter.VAR_KEYWORD or parameter.name == "on_activity" for parameter in parameters)


class LabService:
    """Run one frozen 500 ms observation at a time and retain bounded events."""

    event_limit = 256

    def __init__(self, data_dir: Path, policy_factory=NeuralPolicy):
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.policy_factory = policy_factory
        self._lock = threading.RLock()
        self._events = deque(maxlen=self.event_limit)
        self._next_seq = 1
        self._thread = None
        self._cancel = None
        self._closed = False
        self._state = {
            "status": "idle",
            "job_id": None,
            "input": None,
            "choice": None,
            "error": None,
        }
        self.neuron_order_sha256 = self._read_order_hash()

    def _read_order_hash(self):
        graph = self.data_dir / "graph.npz"
        if not graph.exists():
            return None
        try:
            with np.load(graph, allow_pickle=False) as arrays:
                return neuron_order_sha256(arrays["ids"])
        except (OSError, KeyError, ValueError):
            return None

    @staticmethod
    def _validate_input(value):
        if not isinstance(value, dict) or set(value) != {"kind", "passed"}:
            raise InvalidObservation("observation must contain only kind and passed")
        if value["kind"] not in {"task", "dark", "light"}:
            raise InvalidObservation("kind must be task, dark, or light")
        passed = value["passed"]
        if isinstance(passed, bool) or not isinstance(passed, int) or not 0 <= passed <= 5:
            raise InvalidObservation("passed must be an integer from 0 to 5")
        return {"kind": value["kind"], "passed": passed}

    @staticmethod
    def _frame(observation):
        kind, passed = observation["kind"], observation["passed"]
        if kind == "dark":
            value = 0
        elif kind == "light":
            value = 255
        else:
            return np.asarray(render_panel(passed, 5), dtype=np.uint8)
        return np.full((180, 320, 3), value, dtype=np.uint8)

    def observe(self, value: dict) -> str:
        observation = self._validate_input(value)
        with self._lock:
            if self._closed:
                raise LabClosedError("lab service is closed")
            if self._thread is not None and self._thread.is_alive():
                raise LabBusyError("an observation is already running")
            job_id = uuid.uuid4().hex
            self._events.clear()
            self._state = {"status": "loading", "job_id": job_id, "input": observation, "choice": None, "error": None}
            self._cancel = threading.Event()
            self._thread = threading.Thread(target=self._run, args=(job_id, observation, self._cancel), daemon=True)
            self._thread.start()
            return job_id

    def _append(self, job_id, event_type, **payload):
        event = {
            "seq": self._next_seq,
            "job_id": job_id,
            "type": event_type,
            "recorded_at_ms": int(time.time() * 1000),
            "neuron_order_sha256": self.neuron_order_sha256,
            "activity_schema_version": ACTIVITY_SCHEMA_VERSION,
            **payload,
        }
        self._next_seq += 1
        self._events.append(event)
        return event

    def _callback(self, job_id, cancel):
        def on_bin(value):
            if cancel.is_set():
                raise _Cancelled
            snapshot = copy_bin(value)
            with self._lock:
                if cancel.is_set() or self._closed:
                    raise _Cancelled
                self._state["status"] = "running"
                self._append(job_id, "bin", **snapshot)

        return on_bin

    def _make_policy(self, callback):
        kwargs = {"learning": False}
        if _factory_accepts_activity(self.policy_factory):
            kwargs["on_activity"] = callback
        return self.policy_factory(self.data_dir, **kwargs)

    def _run(self, job_id, observation, cancel):
        try:
            with self._lock:
                self._append(job_id, "started", input=copy.deepcopy(observation))
            policy = self._make_policy(self._callback(job_id, cancel))
            if cancel.is_set():
                raise _Cancelled
            reset = getattr(policy, "reset", None)
            if reset is not None:
                reset(keep_memory=False)
            if cancel.is_set():
                raise _Cancelled
            choice = policy.choose(self._frame(observation))
            compact = _json_value(choice)
            with self._lock:
                if cancel.is_set():
                    raise _Cancelled
                self._state["choice"] = compact
                self._append(job_id, "choice", choice=compact)
                self._state["status"] = "completed"
                self._append(job_id, "completed")
        except _Cancelled:
            with self._lock:
                self._state.update({"status": "cancelled", "choice": None, "error": None})
                self._append(job_id, "cancelled")
        except Exception as error:  # worker errors are part of the public state contract
            with self._lock:
                error_text = _json_value(str(error))
                self._state.update({"status": "error", "choice": None, "error": error_text})
                self._append(job_id, "error", error=error_text)

    def cancel(self) -> bool:
        with self._lock:
            if self._thread is None or not self._thread.is_alive() or self._cancel is None:
                return False
            self._cancel.set()
            return True

    def state(self) -> dict:
        with self._lock:
            value = copy.deepcopy(self._state)
            value["neuron_order_sha256"] = self.neuron_order_sha256
            value["activity_schema_version"] = ACTIVITY_SCHEMA_VERSION
            value["oldest_seq"] = self._events[0]["seq"] if self._events else None
            value["latest_seq"] = self._events[-1]["seq"] if self._events else self._next_seq - 1
            return value

    def events(self, after: int = 0) -> dict:
        if isinstance(after, bool) or not isinstance(after, int) or after < 0:
            raise ValueError("after must be a nonnegative integer")
        with self._lock:
            oldest = self._events[0]["seq"] if self._events else self._next_seq
            latest = self._events[-1]["seq"] if self._events else self._next_seq - 1
            reset = bool(self._events and after < oldest - 1)
            return {
                "events": [copy.deepcopy(event) for event in self._events if event["seq"] > after],
                "oldest_seq": oldest,
                "latest_seq": latest,
                "reset": reset,
                "neuron_order_sha256": self.neuron_order_sha256,
                "activity_schema_version": ACTIVITY_SCHEMA_VERSION,
            }

    def close(self):
        with self._lock:
            self._closed = True
            if self._cancel is not None:
                self._cancel.set()
            thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)
