"""Small, identity-bound snapshots for optional neural activity observers."""

from __future__ import annotations

import hashlib
from typing import Mapping

import numpy as np


ACTIVITY_SCHEMA_VERSION = 1
BIN_MS = 10


def neuron_order_sha256(ids: np.ndarray) -> str:
    """Hash retained neuron IDs in a platform-independent canonical order."""
    values = np.asarray(ids, dtype="<u8")
    if values.ndim != 1:
        raise ValueError("retained neuron IDs must be one-dimensional")
    return hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()


def make_bin(start_ms: float, end_ms: float, counts: np.ndarray) -> dict:
    """Return a detached sparse 10 ms bin.

    The lists intentionally remain ordinary JSON-friendly lists: the snapshot is
    detached from runtime arrays, so an observer can annotate or mutate its copy
    without changing the simulator's numerical state.
    """
    values = np.asarray(counts)
    indices = np.flatnonzero(values).astype(np.int64, copy=False)
    sparse_counts = np.asarray(values[indices], dtype=np.int64)
    return {
        "type": "bin",
        "start_ms": float(start_ms),
        "end_ms": float(end_ms),
        "indices": [int(value) for value in indices],
        "counts": [int(value) for value in sparse_counts],
        "total_spikes": int(values.sum(dtype=np.int64)),
    }


def copy_bin(value: Mapping) -> dict:
    """Copy and validate a callback bin before handing it to a service."""
    if value.get("type") != "bin":
        raise ValueError("activity callback must provide a bin")
    indices = [int(index) for index in value.get("indices", ())]
    counts = [int(count) for count in value.get("counts", ())]
    if len(indices) != len(counts):
        raise ValueError("activity bin indices and counts must have equal lengths")
    return {
        "type": "bin",
        "start_ms": float(value["start_ms"]),
        "end_ms": float(value["end_ms"]),
        "indices": indices,
        "counts": counts,
        "total_spikes": int(value["total_spikes"]),
    }
