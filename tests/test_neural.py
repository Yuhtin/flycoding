import numpy as np
import pytest

from flycodex.neural import decode_counts, decode_rates
from flycodex.neural.rule import advance


def test_decode_rates_assigns_fix_at_the_positive_exact_threshold():
    assert decode_rates(left_hz=0, right_hz=2, gate_spikes=1)["action"] == "fix"


def test_decode_rates_assigns_test_at_the_negative_exact_threshold():
    assert decode_rates(left_hz=2, right_hz=0, gate_spikes=1)["action"] == "test"


def test_decode_rates_reports_an_inactive_gate_before_direction():
    result = decode_rates(left_hz=0, right_hz=20, gate_spikes=0)

    assert result["action"] == "investigate"
    assert result["reason"] == "gate_inactive"


def test_decode_counts_rejects_a_missing_annotated_gate():
    with pytest.raises(ValueError, match="Missing annotated BCI gate"):
        decode_counts(
            np.array([0, 2], dtype=np.int32),
            left=np.array([0], dtype=np.int32),
            right=np.array([1], dtype=np.int32),
            gate=np.array([], dtype=np.int32),
            seconds=1.0,
        )


def test_candidate_rule_freeze_preserves_efficacy_during_passive_decay():
    y_kc = np.array([0.0])
    y_dan = np.array([0.0])
    efficacy_state = np.array([0.0])
    efficacy = np.array([0.4])
    advance(
        y_kc,
        y_dan,
        efficacy_state,
        efficacy,
        kc_hz=np.array([0.0]),
        dan_hz=np.array([0.0]),
        gain=np.array([[1.0]]),
        dt_seconds=0.01,
        eta=0.001,
        learning=False,
        frozen=True,
    )

    assert efficacy.tolist() == [0.4]
    assert efficacy_state.tolist() == [0.0]
