"""Task 3 contracts: lab HTTP, archive assets, and future activity telemetry."""

from __future__ import annotations

import http.client
import json
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from flycodex.activity import ActivityReader, ActivityRecorder
from flycodex.lab import LabBusyError
from flycodex.web import create_server


def request(address, path, method="GET", body=None, headers=None):
    connection = http.client.HTTPConnection(*address, timeout=3)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


class FakePolicy:
    def __init__(self, data_dir, learning=False, on_activity=None):
        self.on_activity = on_activity

    def reset(self, keep_memory=False):
        return None

    def choose(self, frame):
        if self.on_activity:
            for start in (0.0, 10.0):
                self.on_activity({"type": "bin", "start_ms": start, "end_ms": start + 10,
                                  "indices": [3], "counts": [2], "total_spikes": 2})
        return {"action": "fix", "reason": "synthetic"}


@pytest.fixture
def lab_server(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    np.savez(data / "graph.npz", ids=np.arange(4, dtype=np.uint64))
    server = create_server(tmp_path / "run", data_dir=tmp_path / "data", lab=True,
                           policy_factory=FakePolicy, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def json_headers(address, origin_host="127.0.0.1", host="127.0.0.1"):
    port = address[1]
    authority = f"{host}:{port}"
    return {"Content-Type": "application/json", "Origin": f"http://{origin_host}:{port}", "Host": authority}


def test_lab_routes_require_small_exact_same_origin_json_payload(lab_server):
    address = lab_server
    status, _, body = request(address, "/lab/state")
    assert status == 200
    state = json.loads(body)
    assert state["availability"] is True
    assert "event_cursor" in state

    assert request(address, "/lab/observe", "POST", b"{}", json_headers(address))[0] == 400
    assert request(address, "/lab/observe", "POST", b'{"kind":"dark","passed":true}', json_headers(address))[0] == 400
    assert request(address, "/lab/observe", "POST", b'{"kind":[],"passed":0}', json_headers(address))[0] == 400
    assert request(address, "/lab/observe", "POST", b'{"kind":"dark","passed":0,"extra":1}', json_headers(address))[0] == 400
    assert request(address, "/lab/observe", "POST", b'{"kind":"dark","passed":0}',
                   {**json_headers(address), "Content-Type": "text/plain"})[0] == 400
    assert request(address, "/lab/observe", "POST", b'{"kind":"dark","passed":0}',
                   {**json_headers(address), "Origin": f"http://evil.invalid:{address[1]}"})[0] == 403
    assert request(address, "/lab/observe", "POST", b'{"kind":"dark","passed":0}',
                   {**json_headers(address), "Host": f"evil.invalid:{address[1]}"})[0] == 403
    assert request(address, "/lab/observe", "POST", b'{"kind":"dark","passed":0}',
                   {**json_headers(address), "Origin": f"http://localhost:{address[1]}"})[0] == 403
    assert request(address, "/lab/observe", "POST", b'{"kind":"dark","passed":0}',
                   {**json_headers(address), "Origin": "http://127.0.0.1"})[0] == 403
    assert request(address, "/lab/observe", "POST", b'{"kind":"dark","passed":0}',
                   {**json_headers(address), "Host": "127.0.0.1:" + "9" * 5000})[0] == 403
    assert request(address, "/lab/observe", "POST", b"x" * 1025, json_headers(address))[0] == 400

    status, _, body = request(address, "/lab/observe", "POST", b'{"kind":"dark","passed":0}', json_headers(address))
    assert status == 202
    job_id = json.loads(body)["job_id"]
    image_status, image_headers, image_body = request(address, f"/lab/input.png?job_id={job_id}")
    assert image_status == 200
    assert image_headers["Content-Type"] == "image/png"
    assert image_body.startswith(b"\x89PNG")
    assert request(address, "/lab/input.png?job_id=stale")[0] == 404
    status, _, body = request(address, "/lab/observe", "POST", b'{"kind":"dark","passed":0}', json_headers(address))
    assert status in (202, 409)
    if status == 202:
        job_id = json.loads(body)["job_id"]
    while True:
        state = json.loads(request(address, "/lab/state")[2])
        if state["status"] in {"completed", "error", "cancelled"}:
            break
        time.sleep(0.01)
    assert state["job_id"] == job_id
    events = json.loads(request(address, "/lab/events?after=0")[2])
    assert events["events"]
    assert {event["job_id"] for event in events["events"]} == {job_id}
    assert all(isinstance(event["recorded_at_ms"], int) for event in events["events"])


def test_lab_cancel_and_cursor_validation(lab_server):
    assert request(lab_server, "/lab/events?after=not-int")[0] == 400
    assert request(lab_server, "/lab/events?after=" + "9" * 5000)[0] == 400
    assert request(lab_server, "/lab/cancel", "POST", b"{}", json_headers(lab_server))[0] in (200, 409)


def test_lab_disabled_and_read_only_compatibility(tmp_path):
    server = create_server(tmp_path / "missing", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert request(server.server_address, "/lab/state")[0] == 404
        assert request(server.server_address, "/lab/observe", "POST", b"{}", json_headers(server.server_address))[0] == 405
        assert request(server.server_address, "/archive/snapshot.json")[0] == 200
        assert request(server.server_address, "/brain/manifest.json")[0] == 200
        assert request(server.server_address, "/brain/positions.bin")[0] == 200
        assert request(server.server_address, "/brain/indices.bin")[0] == 200
        assert request(server.server_address, "/brain/neurons.json")[0] == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_lab_reports_missing_data_without_fabricating_activity(tmp_path):
    server = create_server(tmp_path / "run", data_dir=tmp_path / "missing", lab=True, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = request(server.server_address, "/lab/state")
        assert status == 503
        state = json.loads(body)
        assert state["availability"] is False
        assert "unavailable" in state["error"]
        assert request(server.server_address, "/lab/observe", "POST", b'{"kind":"dark","passed":0}', json_headers(server.server_address))[0] == 503
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_demo_preserves_snapshot_and_archive_is_allowlisted(tmp_path):
    server = create_server(tmp_path / "absent", demo=True, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        snapshot = request(server.server_address, "/snapshot.json")[2]
        archive = request(server.server_address, "/archive/snapshot.json")
        assert archive[0] == 200
        assert archive[1]["Content-Type"].startswith("application/json")
        assert archive[2] == snapshot
        assert request(server.server_address, "/archive/images/../snapshot.json")[0] == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_activity_recorder_identity_rotation_and_reader_bounds(tmp_path):
    public = tmp_path / "public"
    public.mkdir()
    recorder = ActivityRecorder(public, run="run-1", attempt="adaptive-1", turn=2,
                                phase="choice", neuron_order_sha256="a" * 64)
    recorder.start(window="choice-2", window_ms=500)
    recorder.bin({"type": "bin", "start_ms": 0.0, "end_ms": 10.0,
                  "indices": [4], "counts": [7], "total_spikes": 7})
    recorder.end(choice={"action": "fix"})
    payload = ActivityReader(public).read()
    assert payload["available"] is True
    assert payload["run"] == "run-1"
    assert payload["window"]["attempt"] == "adaptive-1"
    assert payload["window"]["turn"] == 2
    assert payload["window"]["phase"] == "choice"
    assert payload["window"]["events"][1]["counts"] == [7]
    assert isinstance(payload["window"]["events"][1]["recorded_at_ms"], int)
    assert len(json.dumps(payload)) < 64 * 1024


def test_activity_recorder_preserves_more_than_256_sparse_neurons(tmp_path):
    public = tmp_path / "public"
    recorder = ActivityRecorder(public, run="run", attempt="a", turn=1, phase="choice",
                                neuron_order_sha256="a" * 64)
    recorder.start(window="w", window_ms=500)
    indices = list(range(300))
    counts = [index + 1 for index in indices]
    recorder.bin({"type": "bin", "start_ms": 0.0, "end_ms": 10.0,
                  "indices": indices, "counts": counts, "total_spikes": sum(counts)})
    recorder.end(choice={"action": "fix"})
    event = ActivityReader(public).read()["window"]["events"][1]
    assert event["indices"] == indices
    assert event["counts"] == counts
    assert event["total_spikes"] == sum(counts)


def test_lab_event_deque_rollover_resets_lagged_cursor(tmp_path):
    from flycodex.lab import LabService

    service = LabService(tmp_path / "missing")
    for index in range(300):
        service._append("job", "synthetic", index=index)
    page = service.events(after=1)
    assert page["oldest_seq"] == 45
    assert page["reset"] is True
    assert page["events"][0]["seq"] == 45
    assert page["latest_seq"] == 300


def test_activity_recorder_marks_oversized_window_unavailable(tmp_path, monkeypatch):
    import flycodex.activity as activity

    monkeypatch.setattr(activity, "MAX_ACTIVITY_BYTES", 512)
    recorder = ActivityRecorder(tmp_path / "public", run="run", attempt="a", turn=1,
                                phase="choice", neuron_order_sha256="a" * 64)
    recorder.start(window="w", window_ms=500)
    recorder.bin({"type": "bin", "start_ms": 0.0, "end_ms": 10.0,
                  "indices": list(range(300)), "counts": [1] * 300, "total_spikes": 300})
    payload = ActivityReader(tmp_path / "public").read()
    assert payload["available"] is False
    assert payload["status"] == "error"


def test_activity_reader_rejects_symlink_and_incomplete_write(tmp_path):
    public = tmp_path / "public"
    public.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text('{"available":true}')
    (public / "activity.json").symlink_to(outside)
    assert ActivityReader(public).read()["available"] is False
    (public / "activity.json").unlink()
    (public / "activity.json.partial").write_text('{"available":true')
    result = ActivityReader(public).read()
    assert result["available"] is False
    assert result["reason"] == "incomplete"


def test_activity_reader_turns_recursion_error_into_unavailable(tmp_path, monkeypatch):
    public = tmp_path / "public"
    public.mkdir()
    (public / "activity.json").write_text("{}")
    monkeypatch.setattr(json, "loads", lambda value: (_ for _ in ()).throw(RecursionError("deep")))
    result = ActivityReader(public).read()
    assert result == {"available": False, "reason": "incomplete"}


@pytest.mark.parametrize("document", [
    {"schema_version": 1, "available": True},
    {"schema_version": 1, "available": True, "status": "complete", "events": [{"seq": 1}]},
    {"schema_version": 1, "activity_schema_version": 1, "available": True,
     "status": "complete", "run": "r", "attempt": "a", "turn": 1,
     "phase": "choice", "window_id": "w", "neuron_order_sha256": "a" * 64,
     "window": {"events": [{"seq": 1, "type": "bin", "indices": [1], "counts": [1]}]}},
])
def test_activity_reader_rejects_malformed_shape_with_or_without_cursor(tmp_path, document):
    public = tmp_path / "public"
    public.mkdir()
    (public / "activity.json").write_text(json.dumps(document))
    reader = ActivityReader(public)
    assert reader.read()["available"] is False
    assert reader.read(after=1)["available"] is False


def test_activity_reader_rejects_impossible_state_machine_and_hash(tmp_path):
    start = {"seq": 1, "type": "start", "window_ms": 500}
    measured = {"seq": 2, "type": "bin", "start_ms": 500.0, "end_ms": 510.0,
                "indices": [1], "counts": [2], "total_spikes": 2}
    end = {"seq": 3, "type": "end", "choice": {"action": "fix"}}

    def document(events, *, status="complete", available=True, order="a" * 64, window_ms=500):
        return {
            "schema_version": 1, "available": available, "status": status,
            "run": "r", "attempt": "a", "turn": 1, "phase": "choice", "window_id": "w",
            "neuron_order_sha256": order, "activity_schema_version": 1,
            "window": {"window_id": "w", "run": "r", "attempt": "a", "turn": 1,
                        "phase": "choice", "window_ms": window_ms, "status": status, "events": events},
        }

    invalid = [
        document([start, measured, end], status="running", available=True),
        document([measured], status="running", available=True),
        document([start, {**measured, "end_ms": 501.0}, end]),
        document([start, measured, end], order="order-hash"),
        document([start, measured, end], window_ms=200),
        document([1], status="running", available=True),
    ]
    wrong_feedback = document([start, measured, end])
    wrong_feedback["phase"] = "feedback"
    wrong_feedback["window"]["phase"] = "feedback"
    invalid.append(wrong_feedback)
    public = tmp_path / "public"
    public.mkdir()
    for value in invalid:
        (public / "activity.json").write_text(json.dumps(value))
        reader = ActivityReader(public)
        assert reader.read()["available"] is False
        assert reader.read(after=1)["available"] is False


def test_synthetic_pilot_policy_is_not_forced_to_accept_activity(tmp_path):
    from flycodex.pilot import Pilot

    seen = []

    class LegacyPolicy:
        def __init__(self, data_dir, learning=False):
            seen.append("constructed")

    # Construction is enough to assert the callback boundary without spending a run.
    pilot = Pilot(tmp_path / "run", tmp_path / "data", model="synthetic", evidence="synthetic",
                  policy_factory=LegacyPolicy)
    assert pilot.policy_factory is LegacyPolicy
    assert seen == []
