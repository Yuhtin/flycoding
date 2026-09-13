import numpy as np
import pytest

from flycodex.neural import NeuralPolicy, decode_counts, decode_rates
from flycodex.neural.policy import STATE_FIELDS
import flycodex.neural.policy as policy_module
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


def test_feedback_reports_a_window_trace_without_a_policy_decision():
    policy = object.__new__(NeuralPolicy)
    policy._brain = lambda: type("Brain", (), {"gate": np.array([], dtype=np.int32), "reward": np.array([1]), "aversive": np.array([2]), "cell_ids": {}, "clock": np.array([0]), "dt": 0.1, "memory": lambda self: {}})()
    policy._raw_window = lambda rgb, duration_ms, stimulation: {"counts": np.array([0], dtype=np.int32), "compute_seconds": 0.0, "window_ms": duration_ms, "brain": policy._brain()}

    result = policy.feedback(np.zeros((1, 1, 3), dtype=np.uint8), 0)

    assert "action" not in result
    assert "reason" not in result
    assert result["window_ms"] == 200
    assert result["stimulus_ms"] == 0


def test_restore_rejects_a_checkpoint_missing_runtime_state(tmp_path):
    policy = object.__new__(NeuralPolicy)
    brain = type("Brain", (), {"ids": np.array([1], dtype=np.int64), "ptr": np.array([0, 0], dtype=np.int64), "build": {"source_sha256": "source"}})()
    policy.learning = False
    policy._brain = lambda: brain
    checkpoint = tmp_path / "missing-state.npz"
    np.savez(checkpoint, metadata='{"model": "flycodex-full-graph-v1", "learning": false, "graph_ids_sha256": "' + __import__("hashlib").sha256(brain.ids.tobytes()).hexdigest() + '", "graph_ptr_sha256": "' + __import__("hashlib").sha256(brain.ptr.tobytes()).hexdigest() + '", "kernel": {"source_sha256": "source"}}')

    with pytest.raises(ValueError, match="(?i)checkpoint state"):
        policy.restore(checkpoint)


def test_restore_validates_every_array_before_mutating_runtime_state(tmp_path):
    policy = object.__new__(NeuralPolicy)
    brain = type("Brain", (), {})()
    for name in STATE_FIELDS:
        setattr(brain, name, np.array([3.0 if name == "weight" else 0.0], dtype=np.float64))
    brain.ids = np.array([1], dtype=np.int64)
    brain.ptr = np.array([0, 0], dtype=np.int64)
    brain.post = np.array([], dtype=np.int32)
    brain.plastic_edges = np.array([], dtype=np.int64)
    brain.build = {"source_sha256": "source"}
    brain.configuration_signature = lambda: {}
    policy.learning = False
    policy._brain = lambda: brain
    checkpoint = tmp_path / "nonfinite-state.npz"
    stored = {name: getattr(brain, name).copy() for name in STATE_FIELDS}
    stored["memory_w"][:] = np.nan
    np.savez(checkpoint, metadata=__import__("json").dumps(policy._checkpoint_metadata(brain)), **stored)

    with pytest.raises(ValueError, match="Nonfinite checkpoint state"):
        policy.restore(checkpoint)

    assert brain.weight.tolist() == [3.0]


def test_source_verification_does_not_reserve_compile_space_when_nothing_is_missing(tmp_path, monkeypatch):
    source = tmp_path / "edges.feather"
    source.write_bytes(b"x")
    locked = {"edges.feather": {"bytes": 1, "sha256": __import__("hashlib").sha256(b"x").hexdigest()}}
    monkeypatch.setattr(policy_module, "_locks", lambda: locked)
    monkeypatch.setattr(policy_module.shutil, "disk_usage", lambda path: type("Usage", (), {"free": 0})())

    assert policy_module._obtain_sources(tmp_path)["edges.feather"]["verified"] is True
