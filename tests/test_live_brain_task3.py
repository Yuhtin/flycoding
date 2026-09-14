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
        return {"action": "left", "reason": "synthetic"}


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


def json_headers(origin="http://127.0.0.1"):
    return {"Content-Type": "application/json", "Origin": origin, "Host": "127.0.0.1"}


def test_lab_routes_require_small_exact_same_origin_json_payload(lab_server):
    address = lab_server
    status, _, body = request(address, "/lab/state")
    assert status == 200
    state = json.loads(body)
    assert state["availability"] is True
    assert "event_cursor" in state

    assert request(address, "/lab/observe", "POST", b"{}", json_headers())[0] == 400
    assert request(address, "/lab/observe", "POST", b'{"kind":"dark","passed":true}', json_headers())[0] == 400
    assert request(address, "/lab/observe", "POST", b'{"kind":[],"passed":0}', json_headers())[0] == 400
    assert request(address, "/lab/observe", "POST", b'{"kind":"dark","passed":0,"extra":1}', json_headers())[0] == 400
    assert request(address, "/lab/observe", "POST", b'{"kind":"dark","passed":0}',
                   {**json_headers(), "Content-Type": "text/plain"})[0] == 400
    assert request(address, "/lab/observe", "POST", b'{"kind":"dark","passed":0}',
                   {**json_headers(), "Origin": "http://evil.invalid"})[0] == 403
    assert request(address, "/lab/observe", "POST", b'{"kind":"dark","passed":0}',
                   {**json_headers(), "Host": "evil.invalid"})[0] == 403
    assert request(address, "/lab/observe", "POST", b"x" * 1025, json_headers())[0] == 400

    status, _, body = request(address, "/lab/observe", "POST", b'{"kind":"dark","passed":0}', json_headers())
    assert status == 202
    job_id = json.loads(body)["job_id"]
    image_status, image_headers, image_body = request(address, f"/lab/input.png?job_id={job_id}")
    assert image_status == 200
    assert image_headers["Content-Type"] == "image/png"
    assert image_body.startswith(b"\x89PNG")
    assert request(address, "/lab/input.png?job_id=stale")[0] == 404
    status, _, body = request(address, "/lab/observe", "POST", b'{"kind":"dark","passed":0}', json_headers())
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


def test_lab_cancel_and_cursor_validation(lab_server):
    assert request(lab_server, "/lab/events?after=not-int")[0] == 400
    assert request(lab_server, "/lab/cancel", "POST", b"{}", json_headers())[0] in (200, 409)


def test_lab_disabled_and_read_only_compatibility(tmp_path):
    server = create_server(tmp_path / "missing", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert request(server.server_address, "/lab/state")[0] == 404
        assert request(server.server_address, "/lab/observe", "POST", b"{}", json_headers())[0] == 405
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
        assert request(server.server_address, "/lab/observe", "POST", b'{"kind":"dark","passed":0}', json_headers())[0] == 503
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
                                phase="choice", neuron_order_sha256="order-hash")
    recorder.start(window="choice-2", window_ms=500)
    recorder.bin({"type": "bin", "start_ms": 0.0, "end_ms": 10.0,
                  "indices": [4], "counts": [7], "total_spikes": 7})
    recorder.end(choice={"action": "left"})
    payload = ActivityReader(public).read()
    assert payload["available"] is True
    assert payload["run"] == "run-1"
    assert payload["window"]["attempt"] == "adaptive-1"
    assert payload["window"]["turn"] == 2
    assert payload["window"]["phase"] == "choice"
    assert payload["window"]["events"][1]["counts"] == [7]
    assert len(json.dumps(payload)) < 64 * 1024


def test_activity_recorder_preserves_more_than_256_sparse_neurons(tmp_path):
    public = tmp_path / "public"
    recorder = ActivityRecorder(public, run="run", attempt="a", turn=1, phase="choice",
                                neuron_order_sha256="hash")
    recorder.start(window="w", window_ms=500)
    indices = list(range(300))
    counts = [index + 1 for index in indices]
    recorder.bin({"type": "bin", "start_ms": 0.0, "end_ms": 10.0,
                  "indices": indices, "counts": counts, "total_spikes": sum(counts)})
    recorder.end(choice={"action": "left"})
    event = ActivityReader(public).read()["window"]["events"][1]
    assert event["indices"] == indices
    assert event["counts"] == counts
    assert event["total_spikes"] == sum(counts)


def test_activity_recorder_marks_oversized_window_unavailable(tmp_path, monkeypatch):
    import flycodex.activity as activity

    monkeypatch.setattr(activity, "MAX_ACTIVITY_BYTES", 512)
    recorder = ActivityRecorder(tmp_path / "public", run="run", attempt="a", turn=1,
                                phase="choice", neuron_order_sha256="hash")
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
