"""Neural policy interface and readout convention for the Flycodex pilot."""

from __future__ import annotations

import math

import numpy as np


def decode_rates(left_hz: float, right_hz: float, gate_spikes: int) -> dict:
    """Map fixed output rates to the pre-registered pilot instruction."""
    if not all(math.isfinite(value) and value >= 0 for value in (left_hz, right_hz)):
        raise ValueError("rates must be finite and nonnegative")
    if gate_spikes < 0:
        raise ValueError("gate spikes must be nonnegative")
    difference = float(right_hz - left_hz)
    if not gate_spikes:
        action, reason = "investigate", "gate_inactive"
    elif difference >= 2:
        action, reason = "fix", "right_threshold"
    elif difference <= -2:
        action, reason = "test", "left_threshold"
    else:
        action, reason = "investigate", "difference_below_threshold"
    return {
        "action": action,
        "reason": reason,
        "left_hz": float(left_hz),
        "right_hz": float(right_hz),
        "difference_hz": difference,
        "gate_spikes": int(gate_spikes),
    }


def decode_counts(
    counts: np.ndarray,
    *,
    left: np.ndarray,
    right: np.ndarray,
    gate: np.ndarray,
    seconds: float,
) -> dict:
    """Decode real spike counts after validating the annotated output groups."""
    if not len(left) or not len(right):
        raise ValueError("Missing annotated BCI directional outputs")
    if not len(gate):
        raise ValueError("Missing annotated BCI gate")
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("seconds must be positive")
    return decode_rates(
        float(np.mean(counts[left]) / seconds),
        float(np.mean(counts[right]) / seconds),
        int(counts[gate].sum()),
    )


from .policy import NeuralPolicy, prepare_data, probe  # noqa: E402

__all__ = ["NeuralPolicy", "decode_counts", "decode_rates", "prepare_data", "probe"]
