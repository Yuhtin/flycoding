import json
from pathlib import Path
import threading
import time

from flycodex.codex import CodexRunner, PROMPTS


def _fixture_executable(tmp_path: Path) -> Path:
    fixture = tmp_path / "fixture_codex"
    fixture.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path
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
    print(json.dumps({"type": "thread.started", "thread_id": "session-fixture"}), flush=True)

if mode == "delay":
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
    runner = CodexRunner(workspace, executable=str(_fixture_executable(tmp_path)), **kwargs)
    return runner, capture


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
