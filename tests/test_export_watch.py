import hashlib
import json
import os
from pathlib import Path

import pytest

from tools.export_watch import export_watch


SOURCE_RUN = Path(os.environ["FLYCODEX_WATCH_SOURCE_RUN"]).expanduser() if os.environ.get("FLYCODEX_WATCH_SOURCE_RUN") else None
WATCH_ASSETS = Path(__file__).parents[1] / "src/flycodex/web/watch"


def _read_json(path):
    return json.loads(path.read_text())


def test_packaged_watch_assets_have_recorded_timeline_and_sanitized_events():
    run = _read_json(WATCH_ASSETS / "run.json")
    activity = _read_json(WATCH_ASSETS / "activity.json")

    assert run["version"] == 1
    assert run["backend"] == "opencode"
    assert run["decision"] == {
        "at_ms": run["phases"]["choice_end_ms"],
        "action": "fix",
        "text": "Fix the discount function while preserving the tests.",
    }
    assert run["result"] == {"at_ms": run["result"]["at_ms"], "passed": 5, "total": 5, "before": 1}
    assert run["phases"]["choice_end_ms"] < run["phases"]["execution_end_ms"] < run["phases"]["feedback_end_ms"]
    assert len([event for event in run["events"] if event["kind"] == "message"]) >= 2
    assert any("Fixing the discount function" in event["text"] for event in run["events"])
    assert any("rtk proxy python -B -m unittest -v" in event["text"] for event in run["events"])
    assert any("specific tool call" in event["text"] for event in run["events"] if event["kind"] == "error")
    assert activity["version"] == 1
    assert activity["neuron_order_sha256"] == run["provenance"]["neuron_order_sha256"]
    assert len(activity["bins"]) == 70
    assert [bin["phase"] for bin in activity["bins"]].count("choice") == 50
    assert [bin["phase"] for bin in activity["bins"]].count("feedback") == 20
    assert all("recorded_at_ms" not in bin for bin in activity["bins"])
    serialized = json.dumps({"run": run, "activity": activity})
    for secret in ("session_id", "sessionID", "send_id", "thread_id", "/Users/", "/private/"):
        assert secret not in serialized


def _synthetic_source(tmp_path):
    source = tmp_path / "source"
    public = source / "public" / "activity"
    public.mkdir(parents=True)
    order_hash = "a" * 64
    timestamp = "2026-01-01T00:00:00+00:00"
    turn_event = {"backend": "opencode", "kind": "text", "raw_type": "text", "raw": {"part": {"text": "Muse message"}}}
    snapshot = {"evidence": "genuine", "settings": {"backend": "opencode", "model": "opencode/muse-spark-1.3-contributor-free", "source_revision": "fixture-revision"}, "attempts": {"adaptive-1": {"baseline": {"passed": 1}, "workspace": "<workspace>", "turns": [{"choice": {"action": "fix"}, "prompt": "Fix the discount function while preserving the tests.", "evaluation": {"passed": 5, "total": 5}, "events": [turn_event]}]}}}
    (source / "public").mkdir(exist_ok=True)
    (source / "public/snapshot.json").write_text(json.dumps(snapshot))
    rows = []
    for name, offset in (("reserve_start", 500), ("turn_settled", 1000), ("feedback_start", 1100), ("turn_committed", 1300)):
        rows.append({"event": name, "timestamp": f"2026-01-01T00:00:00.{offset:03d}+00:00"})
    rows.append({"event": "execution_event", "timestamp": "2026-01-01T00:00:00.900+00:00", "payload": turn_event})
    (source / "journal.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    for name, phase, count, start in (("choice", "choice", 50, 0), ("feedback", "feedback", 20, 500)):
        events = [{"seq": 1, "type": "start", "window_ms": 500 if phase == "choice" else 200}]
        for index in range(count):
            events.append({"seq": index + 2, "type": "bin", "recorded_at_ms": 1000000 + start + index * 10, "start_ms": start + index * 10, "end_ms": start + (index + 1) * 10, "indices": [0], "counts": [1], "total_spikes": 1})
        events.append({"seq": count + 2, "type": "end"})
        document = {"neuron_order_sha256": order_hash, "phase": phase, "window": {"events": events}}
        (public / f"adaptive-1-1-{name}.json").write_text(json.dumps(document))
    return source


def test_export_watch_is_byte_reproducible_from_explicit_source(tmp_path):
    source = _synthetic_source(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    export_watch(source, first)
    export_watch(source, second)
    for name in ("run.json", "activity.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    assert hashlib.sha256((first / "activity.json").read_bytes()).hexdigest()


@pytest.mark.skipif(SOURCE_RUN is None or not SOURCE_RUN.is_dir(), reason="set FLYCODEX_WATCH_SOURCE_RUN for preserved-run export")
def test_export_watch_reproduces_the_explicit_preserved_run(tmp_path):
    output = tmp_path / "watch"
    export_watch(SOURCE_RUN, output)
    activity = _read_json(output / "activity.json")
    assert len(activity["bins"]) == 70
