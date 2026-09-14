import hashlib
import importlib.util
import json
import time
import threading

import numpy as np
import pytest

from flycodex.lab import LabBusyError, LabService
from flycodex.neural import NeuralPolicy
from flycodex.neural.activity import neuron_order_sha256
from flycodex.neural.runtime import FullGraphRuntime


@pytest.fixture
def brain_exporter():
    path = __import__("pathlib").Path(__file__).parents[1] / "tools/export_brain.py"
    spec = importlib.util.spec_from_file_location("export_brain", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tiny_runtime():
    runtime = object.__new__(FullGraphRuntime)
    runtime.uv = np.array([[0.0, 0.0]], dtype=np.float32)
    runtime.r8_uv = np.empty((0, 2), dtype=np.float32)
    runtime.r8_channel = np.empty(0, dtype=np.int32)
    runtime.r8 = np.empty(0, dtype=np.int32)
    runtime.retina = np.array([0], dtype=np.int32)
    runtime.lamina = np.empty(0, dtype=np.int32)
    runtime.sugar = np.empty(0, dtype=np.int32)
    runtime.luminance = np.zeros(1, dtype=np.float32)
    runtime.r8_light = np.empty(0, dtype=np.float32)
    runtime.n = 3
    runtime.ptr = np.zeros(4, dtype=np.int64)
    runtime.post = np.empty(0, dtype=np.int32)
    runtime.weight = np.empty(0, dtype=np.float32)
    runtime.v = np.zeros(3, dtype=np.float32)
    runtime.g = np.zeros(3, dtype=np.float32)
    runtime.refractory = np.zeros(3, dtype=np.int16)
    runtime.drive = np.zeros(3, dtype=np.float32)
    runtime.previous_drive = np.zeros(3, dtype=np.float32)
    runtime.queue = np.zeros((19, 3), dtype=np.int32)
    runtime.queue_count = np.zeros(19, dtype=np.int32)
    runtime.clock = np.zeros(1, dtype=np.int64)
    runtime.counts = np.zeros(3, dtype=np.int32)
    runtime.active = np.zeros(3, dtype=np.int32)
    runtime.flags = np.zeros(3, dtype=np.uint8)
    runtime.nactive = np.zeros(1, dtype=np.int32)
    runtime.last = np.zeros(3, dtype=np.int64)
    runtime.kc_mask = np.zeros(3, dtype=np.uint8)
    runtime.dan_index = np.full(3, -1, dtype=np.int8)
    runtime.eligibility = np.zeros(3, dtype=np.float64)
    runtime.eligibility_last = np.zeros(3, dtype=np.int64)
    runtime.plastic_edges = np.empty(0, dtype=np.int64)
    runtime.plastic_pre = np.empty(0, dtype=np.int32)
    runtime.baseline_plastic = np.empty(0, dtype=np.float32)
    runtime.gain = np.empty((0, 0), dtype=np.float32)
    runtime.modulation = np.zeros(3, dtype=np.float32)
    runtime.modulation_last = np.zeros(3, dtype=np.int64)
    runtime.modulation_mask = np.zeros(3, dtype=np.uint8)
    runtime.rest = np.zeros(3, dtype=np.float32)
    runtime.adaptation = np.zeros(3, dtype=np.float32)
    runtime.rate_kc = np.empty(0)
    runtime.rate_dan = np.empty(0)
    runtime.memory_u = np.empty(0)
    runtime.memory_w = np.empty(0)
    runtime.learning = False

    def advance(*_args):
        runtime.counts[:] = [1, 0, 2]
        runtime.clock[0] += 100

    runtime.advance = advance
    return runtime


def test_runtime_activity_callback_is_a_copy_and_sums_to_window_output():
    runtime = _tiny_runtime()
    received = []

    def mutate(bin_snapshot):
        received.append(bin_snapshot)
        bin_snapshot["counts"][0] = 999

    aggregate, _ = runtime.window(np.zeros((1, 1, 3), dtype=np.uint8), 20, on_bin=mutate)

    assert aggregate.tolist() == [2, 0, 4]
    assert [item["total_spikes"] for item in received] == [3, 3]
    assert received[0]["indices"] == [0, 2]
    assert received[0]["counts"] == [999, 2]
    assert received[0]["start_ms"] == 0.0
    assert received[1]["end_ms"] == 20.0


def test_neural_policy_forwards_optional_activity_callback_without_changing_trace():
    observed = []
    policy = object.__new__(NeuralPolicy)
    policy.on_activity = observed.append
    brain = type("Brain", (), {})()
    brain.window = lambda rgb, duration_ms, stimulation=None, on_bin=None: (
        on_bin({"type": "bin", "start_ms": 0.0, "end_ms": 10.0, "indices": [0], "counts": [2], "total_spikes": 2}),
        (np.array([2], dtype=np.int32), 0.0),
    )[1]
    policy._brain = lambda: brain

    raw = policy._raw_window(np.zeros((1, 1, 3), dtype=np.uint8), 10)

    assert observed[0]["total_spikes"] == 2
    assert raw["counts"].tolist() == [2]


class _FakePolicy:
    init_started = threading.Event()
    allow_init = threading.Event()

    def __init__(self, data_dir, learning=False, on_activity=None):
        self.on_activity = on_activity
        type(self).init_started.set()
        type(self).allow_init.wait(2)

    def reset(self, keep_memory=False):
        assert keep_memory is False

    def choose(self, rgb):
        self.on_activity({"type": "bin", "start_ms": 0.0, "end_ms": 10.0, "indices": [4], "counts": [3], "total_spikes": 3})
        return {"action": "fix", "reason": "fixture", "total_spikes": 3}


def _wait_for(service, status):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if service.state()["status"] == status:
            return service.state()
        time.sleep(0.005)
    raise AssertionError(f"service did not reach {status}: {service.state()}")


def test_lab_rejects_concurrent_job_and_cancel_before_first_bin(tmp_path):
    _FakePolicy.init_started.clear()
    _FakePolicy.allow_init.clear()
    service = LabService(tmp_path, policy_factory=_FakePolicy)
    try:
        job_id = service.observe({"kind": "dark", "passed": 0})
        assert isinstance(job_id, str)
        assert _FakePolicy.init_started.wait(1)
        with pytest.raises(LabBusyError):
            service.observe({"kind": "light", "passed": 1})
        assert service.cancel() is True
        _FakePolicy.allow_init.set()
        state = _wait_for(service, "cancelled")
        assert state["job_id"] == job_id
        assert service.events(after=0)["events"][-1]["type"] == "cancelled"
        assert not any(event["type"] == "bin" for event in service.events(after=0)["events"])
    finally:
        _FakePolicy.allow_init.set()
        service.close()


class _ImmediatePolicy:
    def __init__(self, data_dir, learning=False, on_activity=None):
        self.on_activity = on_activity

    def reset(self, keep_memory=False):
        pass

    def choose(self, rgb):
        self.on_activity({"type": "bin", "start_ms": 0.0, "end_ms": 10.0, "indices": [2], "counts": [1], "total_spikes": 1})
        return {"action": "test", "reason": "fixture", "total_spikes": 1}


class _HugeChoicePolicy(_ImmediatePolicy):
    def choose(self, rgb):
        return {"action": "test", "diagnostic": "x" * 10000}


def test_lab_events_are_bounded_and_include_identity_metadata(tmp_path):
    service = LabService(tmp_path, policy_factory=_ImmediatePolicy)
    try:
        job_id = service.observe({"kind": "task", "passed": 5})
        state = _wait_for(service, "completed")
        page = service.events(after=0)
        assert state["job_id"] == job_id
        assert [event["type"] for event in page["events"]] == ["started", "bin", "choice", "completed"]
        assert all(event["job_id"] == job_id for event in page["events"])
        assert all("neuron_order_sha256" in event for event in page["events"])
        assert page["latest_seq"] == 4
        assert page["reset"] is False
    finally:
        service.close()


def test_lab_choice_serialization_is_bounded(tmp_path):
    service = LabService(tmp_path, policy_factory=_HugeChoicePolicy)
    try:
        service.observe({"kind": "dark", "passed": 0})
        state = _wait_for(service, "completed")
        assert len(state["choice"]["diagnostic"]) <= 4096
    finally:
        service.close()


def test_lab_task_frame_is_the_existing_rendered_task_state():
    from flycodex.panel import render_panel

    expected = np.asarray(render_panel(3, 5), dtype=np.uint8)
    actual = LabService._frame({"kind": "task", "passed": 3})

    assert actual.shape == (180, 320, 3)
    assert actual.dtype == np.uint8
    assert np.array_equal(actual, expected)
    assert hashlib.sha256(actual.tobytes()).hexdigest() == hashlib.sha256(expected.tobytes()).hexdigest()


def test_neuron_order_hash_uses_canonical_little_endian_ids(tmp_path):
    from flycodex.neural.activity import neuron_order_sha256

    ids = np.array([1, 2, 3], dtype=np.int64)
    assert neuron_order_sha256(ids) == hashlib.sha256(np.array([1, 2, 3], dtype="<u8").tobytes()).hexdigest()


def test_brain_export_retains_positions_and_binds_packaged_files(tmp_path, brain_exporter):
    import pandas as pd
    import pyarrow.feather as feather

    data = tmp_path / "data"
    data.mkdir()
    graph = {
        "ids": np.array([10, 20, 30], dtype=np.int64),
        "superclass": np.array(["brain", "optic", "vnc"]),
    }
    np.savez(data / "graph.npz", **graph)
    feather.write_feather(pd.DataFrame({
        "bodyId": [10, 20, 30],
        "somaLocation": [np.array([1, 2, 3]), None, np.array([4, 5, 6])],
        "type": ["A", "B", "C"],
        "class": ["x", None, "z"],
    }), data / "annotations.feather")
    feather.write_feather(pd.DataFrame({"source_id": [10, 20, 30]}), data / "normalized-neurons.feather")
    out = tmp_path / "out"

    manifest = brain_exporter.export_brain(data, out)

    assert manifest["total_neurons"] == 3
    assert manifest["positioned_neurons"] == 2
    assert manifest["missing_neurons"] == 1
    assert manifest["neuron_order_sha256"] == neuron_order_sha256(graph["ids"])
    assert np.fromfile(out / "positions.bin", dtype="<f4").tolist() == [1, 2, 3, 4, 5, 6]
    assert np.fromfile(out / "indices.bin", dtype="<u4").tolist() == [0, 2]
    neurons = json.loads((out / "neurons.json").read_text())
    assert neurons == [
        {"id": 10, "type": "A", "class": "x", "superclass": "brain"},
        {"id": 20, "type": "B", "class": "", "superclass": "optic"},
        {"id": 30, "type": "C", "class": "z", "superclass": "vnc"},
    ]
    stored = json.loads((out / "manifest.json").read_text())
    assert stored["files"]["positions.bin"]["sha256"] == hashlib.sha256((out / "positions.bin").read_bytes()).hexdigest()
