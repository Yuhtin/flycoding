import json

import pytest

from flycodex.storage import BudgetExceeded, RunStore, StoreCorrupt, StoreLocked


ATTEMPTS = (
    "adaptive-1",
    "frozen-1",
    "random-1",
    "adaptive-2",
    "frozen-2",
    "random-2",
)


def test_manifest_persists_settings_allocation_and_fixed_limits(tmp_path):
    with RunStore(tmp_path) as store:
        store.initialize({"model": "gpt-6-astra", "seed": 17})

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["settings"] == {"model": "gpt-6-astra", "seed": 17}
    assert manifest["limits"] == {"global": 30, "attempt": 5, "condition": 10}
    assert manifest["attempt_order"] == list(ATTEMPTS)
    assert [manifest["attempts"][attempt]["condition"] for attempt in ATTEMPTS] == [
        "adaptive",
        "frozen",
        "random",
        "adaptive",
        "frozen",
        "random",
    ]


def test_attempt_budget_counts_completed_and_pending_reservations(tmp_path):
    with RunStore(tmp_path) as store:
        store.initialize({})
        sends = [store.reserve("adaptive-1") for _ in range(5)]
        store.complete(sends[0], {"status": "completed"})

        with pytest.raises(BudgetExceeded, match="attempt"):
            store.reserve("adaptive-1")


def test_condition_budget_is_not_reallocated_between_attempts(tmp_path):
    with RunStore(tmp_path) as store:
        store.initialize({})
        for attempt in ("adaptive-1", "adaptive-2"):
            for _ in range(5):
                store.reserve(attempt)

        with pytest.raises(BudgetExceeded, match="condition"):
            store.reserve("adaptive-1")


def test_global_budget_is_exhausted_across_all_six_attempts(tmp_path):
    with RunStore(tmp_path) as store:
        store.initialize({})
        for attempt in ATTEMPTS:
            for _ in range(5):
                store.reserve(attempt)

        with pytest.raises(BudgetExceeded, match="global"):
            store.reserve("random-2")


def test_pending_reservation_remains_consumed_after_reopen(tmp_path):
    with RunStore(tmp_path) as store:
        store.initialize({"model": "fixture"})
        send_id = store.reserve("frozen-1")

    with RunStore(tmp_path) as reopened:
        snapshot = reopened.snapshot()
        assert snapshot["reservations"][send_id]["status"] == "pending"
        for _ in range(4):
            reopened.reserve("frozen-1")
        with pytest.raises(BudgetExceeded, match="attempt"):
            reopened.reserve("frozen-1")


def test_completion_closes_exactly_one_reservation_once(tmp_path):
    with RunStore(tmp_path) as store:
        store.initialize({})
        send_id = store.reserve("random-1")
        store.complete(send_id, {"status": "completed", "passed": 5})

        assert store.snapshot()["reservations"][send_id] == {
            "attempt": "random-1",
            "condition": "random",
            "status": "completed",
            "result": {"status": "completed", "passed": 5},
        }
        with pytest.raises(ValueError, match="already completed"):
            store.complete(send_id, {"status": "completed"})


def test_unserializable_completion_does_not_close_a_pending_reservation(tmp_path):
    with RunStore(tmp_path) as store:
        store.initialize({})
        send_id = store.reserve("random-1")

        with pytest.raises(TypeError):
            store.complete(send_id, {"not_json": object()})

        assert store.snapshot()["reservations"][send_id]["status"] == "pending"
        store.complete(send_id, {"status": "completed"})


def test_event_journal_is_complete_json_lines_for_reserve_and_complete(tmp_path):
    with RunStore(tmp_path) as store:
        store.initialize({})
        send_id = store.reserve("adaptive-1")
        store.complete(send_id, {"status": "failed", "error": "fixture"})

    events = [json.loads(line) for line in (tmp_path / "journal.jsonl").read_text().splitlines()]
    assert [event["event"] for event in events] == [
        "store_initialized",
        "send_reserved",
        "send_completed",
    ]
    assert events[1]["send_id"] == send_id
    assert events[2]["result"] == {"status": "failed", "error": "fixture"}


def test_single_writer_lock_rejects_a_competing_store(tmp_path):
    first = RunStore(tmp_path)
    try:
        with pytest.raises(StoreLocked):
            RunStore(tmp_path)
    finally:
        first.close()

    with RunStore(tmp_path) as reopened:
        reopened.initialize({})


def test_settings_cannot_change_after_the_first_reservation(tmp_path):
    with RunStore(tmp_path) as store:
        store.initialize({"model": "one"})
        store.reserve("adaptive-1")

        with pytest.raises(ValueError, match="after the first reservation"):
            store.initialize({"model": "two"})


def test_loaded_manifest_cannot_weaken_fixed_budget_constants(tmp_path):
    with RunStore(tmp_path) as store:
        store.initialize({})

    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["limits"]["global"] = 31
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(StoreCorrupt, match="limits"):
        RunStore(tmp_path)


def test_unknown_attempt_cannot_reserve_budget(tmp_path):
    with RunStore(tmp_path) as store:
        store.initialize({})
        with pytest.raises(ValueError, match="unknown attempt"):
            store.reserve("adaptive-user-input")
