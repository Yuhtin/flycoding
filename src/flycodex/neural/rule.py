"""Candidate two-state efficacy rule adapted from Stonkfly revision 78ef3e0."""

import math

import numpy as np


PARAMETERS = {
    "trace_kc_seconds": 1.0,
    "trace_dan_seconds": 1.0,
    "memory_decay_seconds": 1800.0,
    "weight_filter_seconds": 0.05,
    "minimum_fraction": 0.1,
    "maximum_fraction": 2.0,
    "maximum_rate_bin_ms": 10.0,
    "source": "https://doi.org/10.1038/s41586-024-07819-w",
    "interpretation": "Candidate rate-rule adaptation; it is not validated learning.",
}


def advance(
    y_kc: np.ndarray,
    y_dan: np.ndarray,
    u: np.ndarray,
    w: np.ndarray,
    kc_hz: np.ndarray,
    dan_hz: np.ndarray,
    gain: np.ndarray,
    dt_seconds: float,
    eta: float,
    learning: bool = True,
    frozen: bool = False,
) -> None:
    """Advance traces and candidate efficacy deviations for one ≤10 ms bin.

    A frozen condition still observes spikes and updates measurement traces, but
    never changes either efficacy state.  This prevents passive decay from
    becoming an unlabelled source of adaptation.
    """
    if not math.isfinite(dt_seconds) or not 0 < dt_seconds <= 0.0100001:
        raise ValueError("Rate bins must be 0--10 ms")
    h = dt_seconds
    ak = math.exp(-h / PARAMETERS["trace_kc_seconds"])
    ad = math.exp(-h / PARAMETERS["trace_dan_seconds"])
    kmid = y_kc * math.sqrt(ak) + kc_hz * (1 - math.sqrt(ak))
    dmid = y_dan * math.sqrt(ad) + dan_hz * (1 - math.sqrt(ad))
    y_kc[:] = y_kc * ak + kc_hz * (1 - ak)
    y_dan[:] = y_dan * ad + dan_hz * (1 - ad)
    if frozen:
        return
    drive = (
        eta * (kc_hz * (gain.T @ dmid) - (gain.T @ dan_hz) * kmid)
        if learning
        else np.zeros_like(u)
    )
    memory_decay = math.exp(-h / PARAMETERS["memory_decay_seconds"])
    filter_decay = math.exp(-h / PARAMETERS["weight_filter_seconds"])
    coupling = PARAMETERS["memory_decay_seconds"] / (
        PARAMETERS["memory_decay_seconds"] - PARAMETERS["weight_filter_seconds"]
    ) * (memory_decay - filter_decay)
    old_u = u.copy()
    u[:] = old_u * memory_decay + drive * PARAMETERS["memory_decay_seconds"] * (-math.expm1(-h / PARAMETERS["memory_decay_seconds"]))
    w[:] = w * filter_decay + old_u * coupling + drive * PARAMETERS["memory_decay_seconds"] * (-math.expm1(-h / PARAMETERS["weight_filter_seconds"]) - coupling)
    np.clip(w, PARAMETERS["minimum_fraction"] - 1, PARAMETERS["maximum_fraction"] - 1, out=w)
