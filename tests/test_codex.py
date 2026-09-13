import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

import pytest

from flycodex.codex import CodexRunner, PROMPTS


def _fixture_executable(tmp_path: Path) -> Path:
    fixture = tmp_path / "fixture_codex"
    fixture.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

capture = Path(os.environ["FLYCODEX_FIXTURE_CAPTURE"])
capture.write_text(json.dumps({
    "argv": sys.argv[1:],
    "prompt": sys.stdin.read(),
    "session_identity": os.environ.get("CODEX_SESSION_ID"),
    "thread_identity": os.environ.get("CODEX_THREAD_ID"),
}))
mode = os.environ.get("FLYCODEX_FIXTURE_MODE", "success")

if mode != "omit-session":
    print(json.dumps({"type": "thread.started", "thread_id": "session-fixture", "fixture_pid": os.getpid()}), flush=True)

if mode in {"child-delay", "parent-exits"}:
    child_ready = os.environ["FLYCODEX_CHILD_READY"]
    child_source = (
        "import os, signal, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"open({child_ready!r}, 'w').write(str(os.getpid())); "
        "time.sleep(30)"
    )
    subprocess.Popen([sys.executable, "-c", child_source])
    deadline = time.monotonic() + 2
    while not Path(child_ready).exists() and time.monotonic() < deadline:
        time.sleep(0.01)

if mode in {"delay", "child-delay"}:
    time.sleep(30)
elif mode == "fail":
    print("fixture diagnostic on stdout", flush=True)
    print(json.dumps({"type": "turn.failed", "error": {"message": "fixture failure"}}), flush=True)
    print("fixture diagnostic on stderr", file=sys.stderr, flush=True)
    raise SystemExit(7)
else:
    print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "done"}}), flush=True)
    print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 3}}), flush=True)
"""
    )
    fixture.chmod(0o755)
    return fixture


def _runner(tmp_path, monkeypatch, mode="success", **kwargs):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    capture = tmp_path / "capture.json"
    monkeypatch.setenv("FLYCODEX_FIXTURE_CAPTURE", str(capture))
    monkeypatch.setenv("FLYCODEX_FIXTURE_MODE", mode)
    monkeypatch.setenv("FLYCODEX_CHILD_READY", str(tmp_path / "child-ready"))
    runner = CodexRunner(workspace, executable=str(_fixture_executable(tmp_path)), **kwargs)
    return runner, capture


def _pid_exists(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_prompts_match_the_three_predeclared_actions_exactly():
    assert PROMPTS == {
        "investigate": "Analise a falha e explique a provável causa, sem editar.",
        "fix": "Corrija a função de desconto, preservando os testes.",
        "test": "Execute os testes e relate o resultado.",
    }


def test_new_turn_uses_explicit_safe_flags_context_and_streams_complete_events(tmp_path, monkeypatch):
    runner, capture = _runner(tmp_path, monkeypatch, model="gpt-fixture")
    delivered = []
    monkeypatch.setenv("CODEX_SESSION_ID", "parent-session")
    monkeypatch.setenv("CODEX_THREAD_ID", "parent-thread")

    result = runner.run(PROMPTS["fix"], session_id=None, on_event=delivered.append)

    invocation = json.loads(capture.read_text())
    assert invocation["argv"] == [
        "-a",
        "never",
        "exec",
        "--sandbox",
        "workspace-write",
        "--ignore-user-config",
        "--json",
        "--color",
        "never",
        "-C",
        str(tmp_path / "workspace"),
        "--model",
        "gpt-fixture",
        "-",
    ]
    assert "already approved" in invocation["prompt"]
    assert "Only edit `discount.py`" in invocation["prompt"]
    assert PROMPTS["fix"] in invocation["prompt"]
    assert invocation["session_identity"] is None
    assert invocation["thread_identity"] is None
    assert result == {
        "session_id": "session-fixture",
        "status": "completed",
        "usage": {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 3},
        "error": None,
    }
    assert [event["type"] for event in delivered] == [
        "thread.started",
        "item.completed",
        "turn.completed",
    ]


def test_resume_targets_the_explicit_session_without_repeating_initial_context(tmp_path, monkeypatch):
    runner, capture = _runner(tmp_path, monkeypatch)

    result = runner.run(PROMPTS["test"], session_id="session-existing", on_event=lambda event: None)

    invocation = json.loads(capture.read_text())
    assert invocation["argv"][-3:] == ["resume", "session-existing", "-"]
    assert "already approved" not in invocation["prompt"]
    assert invocation["prompt"] == PROMPTS["test"]
    assert result["session_id"] == "session-fixture"


def test_non_event_diagnostics_are_delivered_and_do_not_mask_a_failed_turn(tmp_path, monkeypatch):
    runner, _ = _runner(tmp_path, monkeypatch, mode="fail")
    delivered = []

    result = runner.run(PROMPTS["investigate"], None, delivered.append)

    assert result["status"] == "failed"
    assert "fixture failure" in result["error"]
    assert {event.get("stream") for event in delivered if event["type"] == "diagnostic"} == {
        "stdout",
        "stderr",
    }


def test_success_without_a_new_session_id_is_reported_as_failure(tmp_path, monkeypatch):
    runner, _ = _runner(tmp_path, monkeypatch, mode="omit-session")

    result = runner.run(PROMPTS["test"], None, lambda event: None)

    assert result["session_id"] is None
    assert result["status"] == "failed"
    assert result["error"] == "Codex did not report a session ID"


def test_complete_events_are_persisted_as_json_lines(tmp_path, monkeypatch):
    runner, _ = _runner(tmp_path, monkeypatch)
    runner.run(PROMPTS["test"], None, lambda event: None)

    events = [
        json.loads(line)
        for line in (tmp_path / "codex-events.jsonl").read_text().splitlines()
    ]
    assert [event["type"] for event in events] == [
        "thread.started",
        "item.completed",
        "turn.completed",
    ]


def test_timeout_terminates_the_fixture_and_returns_a_timeout(tmp_path, monkeypatch):
    runner, _ = _runner(tmp_path, monkeypatch, mode="delay", timeout=0.05)

    started = time.monotonic()
    result = runner.run(PROMPTS["test"], None, lambda event: None)

    assert time.monotonic() - started < 2
    assert result["status"] == "timed_out"
    assert result["error"] == "Codex turn exceeded 0.05 seconds"


def test_cancel_terminates_and_waits_for_the_active_process_group(tmp_path, monkeypatch):
    runner, capture = _runner(tmp_path, monkeypatch, mode="delay", timeout=30)
    result = {}

    thread = threading.Thread(
        target=lambda: result.update(
            runner.run(PROMPTS["test"], None, lambda event: None)
        )
    )
    thread.start()
    deadline = time.monotonic() + 2
    while not capture.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert capture.exists()

    runner.cancel()
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert result["status"] == "cancelled"
    assert result["error"] == "Codex turn was cancelled"


def test_overlapping_startup_is_rejected_before_a_second_process_spawns(tmp_path, monkeypatch):
    runner, _ = _runner(tmp_path, monkeypatch)
    original_popen = subprocess.Popen
    first_entered = threading.Event()
    release_first = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    def delayed_first_spawn(*args, **kwargs):
        nonlocal calls
        with calls_lock:
            calls += 1
            call_number = calls
        if call_number == 1:
            first_entered.set()
            assert release_first.wait(timeout=2)
        return original_popen(*args, **kwargs)

    monkeypatch.setattr("flycodex.codex.subprocess.Popen", delayed_first_spawn)
    outcomes = []

    def invoke():
        try:
            outcomes.append(runner.run("fixture", None, lambda event: None))
        except Exception as exc:
            outcomes.append(exc)

    first = threading.Thread(target=invoke)
    first.start()
    assert first_entered.wait(timeout=2)
    second = threading.Thread(target=invoke)
    second.start()
    second.join(timeout=1)
    release_first.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert calls == 1
    assert sum(isinstance(outcome, RuntimeError) for outcome in outcomes) == 1
    assert sum(
        isinstance(outcome, dict) and outcome["status"] == "completed"
        for outcome in outcomes
    ) == 1


def test_cancellation_during_startup_prevents_prompt_submission(tmp_path, monkeypatch):
    runner, capture = _runner(tmp_path, monkeypatch)
    original_popen = subprocess.Popen
    startup_entered = threading.Event()
    release_startup = threading.Event()

    def delayed_spawn(*args, **kwargs):
        startup_entered.set()
        assert release_startup.wait(timeout=2)
        return original_popen(*args, **kwargs)

    monkeypatch.setattr("flycodex.codex.subprocess.Popen", delayed_spawn)
    result = {}
    run_thread = threading.Thread(
        target=lambda: result.update(runner.run("must-not-send", None, lambda event: None))
    )
    run_thread.start()
    assert startup_entered.wait(timeout=2)
    cancel_thread = threading.Thread(target=runner.cancel)
    cancel_thread.start()
    release_startup.set()
    cancel_thread.join(timeout=2)
    run_thread.join(timeout=2)

    assert not cancel_thread.is_alive()
    assert not run_thread.is_alive()
    assert result["status"] == "cancelled"
    assert not capture.exists() or json.loads(capture.read_text())["prompt"] == ""


def test_cancel_kills_a_sigterm_ignoring_descendant_and_finishes_readers(tmp_path, monkeypatch):
    runner, _ = _runner(tmp_path, monkeypatch, mode="child-delay", timeout=30)
    started = threading.Event()
    parent_pid = []
    result = {}

    def on_event(event):
        if event["type"] == "thread.started":
            parent_pid.append(event["fixture_pid"])
            started.set()

    run_thread = threading.Thread(
        target=lambda: result.update(runner.run("fixture", None, on_event))
    )
    run_thread.start()
    assert started.wait(timeout=2)
    child_ready = tmp_path / "child-ready"
    deadline = time.monotonic() + 2
    while not child_ready.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert child_ready.exists()
    child_pid = int(child_ready.read_text())

    runner.cancel()
    run_thread.join(timeout=2)
    finished = not run_thread.is_alive()
    child_survived = _pid_exists(child_pid)
    if not finished or child_survived:
        try:
            os.killpg(parent_pid[0], signal.SIGKILL)
        except ProcessLookupError:
            pass
        run_thread.join(timeout=2)

    assert finished
    assert not child_survived
    assert result["status"] == "cancelled"


def test_direct_child_exit_kills_descendants_and_finishes_readers(tmp_path, monkeypatch):
    runner, _ = _runner(tmp_path, monkeypatch, mode="parent-exits", timeout=0.5)
    result = {}
    parent_pid = []

    def on_event(event):
        if event["type"] == "thread.started":
            parent_pid.append(event["fixture_pid"])

    run_thread = threading.Thread(
        target=lambda: result.update(runner.run("fixture", None, on_event))
    )
    run_thread.start()
    child_ready = tmp_path / "child-ready"
    deadline = time.monotonic() + 2
    while not child_ready.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert child_ready.exists()
    child_pid = int(child_ready.read_text())
    run_thread.join(timeout=1)
    finished = not run_thread.is_alive()
    child_survived = _pid_exists(child_pid)
    if not finished or child_survived:
        try:
            os.killpg(parent_pid[0], signal.SIGKILL)
        except ProcessLookupError:
            pass
        run_thread.join(timeout=2)

    assert finished
    assert not child_survived
    assert result["status"] == "completed"


def test_event_callback_can_cancel_its_own_turn_without_deadlocking(tmp_path, monkeypatch):
    runner, _ = _runner(tmp_path, monkeypatch, mode="delay", timeout=30)
    result = {}

    def on_event(event):
        if event["type"] == "thread.started":
            runner.cancel()

    run_thread = threading.Thread(
        target=lambda: result.update(runner.run("fixture", None, on_event))
    )
    run_thread.start()
    run_thread.join(timeout=1)
    finished_without_help = not run_thread.is_alive()
    if not finished_without_help:
        with runner._state_changed:
            runner._active = False
            runner._state_changed.notify_all()
        run_thread.join(timeout=2)

    assert finished_without_help
    assert result["status"] == "cancelled"


@pytest.mark.parametrize("setup_error", [OSError("log unavailable"), KeyboardInterrupt()])
def test_setup_failure_or_interrupt_reaps_published_process_and_releases_lifecycle(
    tmp_path, monkeypatch, setup_error
):
    runner, _ = _runner(tmp_path, monkeypatch, mode="delay", timeout=30)
    original_popen = subprocess.Popen
    spawned = []

    def recording_spawn(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        spawned.append(process)
        return process

    original_open = Path.open

    def failing_event_log(path, *args, **kwargs):
        if path == runner.events_path:
            raise setup_error
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr("flycodex.codex.subprocess.Popen", recording_spawn)
    monkeypatch.setattr(Path, "open", failing_event_log)

    with pytest.raises(type(setup_error)):
        runner.run("fixture", None, lambda event: None)

    active_after_error = runner._active
    process_survived = spawned[0].poll() is None
    if active_after_error or process_survived:
        runner._terminate(spawned[0], spawned[0].pid)
        runner._release_active()

    assert not active_after_error
    assert not process_survived
