import json
from pathlib import Path
import sys
import threading
import time

from flycodex.opencode import DEFAULT_MODEL, OpenCodeRunner


def _fixture_executable(tmp_path: Path) -> Path:
    fixture = tmp_path / "fixture_opencode"
    fixture.write_text(
        f"#!{sys.executable}\n"
        + r'''
import json, os, pathlib, sys, time

capture = pathlib.Path(os.environ["FLYCODEX_OPENCODE_CAPTURE"])
capture.write_text(json.dumps({
    "argv": sys.argv[1:],
    "prompt": sys.stdin.read(),
    "config": os.environ.get("OPENCODE_CONFIG_CONTENT"),
    "config_dir": os.environ.get("OPENCODE_CONFIG_DIR"),
    "xdg": os.environ.get("XDG_CONFIG_HOME"),
}))
mode = os.environ.get("FLYCODEX_OPENCODE_MODE", "success")
session = "oc-session-fixture"
print(json.dumps({"type": "step_start", "sessionID": session, "part": {"id": "s1"}}), flush=True)
if mode == "mixed-session":
    print(json.dumps({"type": "text", "sessionID": "oc-session-other", "part": {"text": "wrong"}}), flush=True)
    print(json.dumps({"type": "step_finish", "sessionID": session, "part": {"reason": "stop"}}), flush=True)
    raise SystemExit
if mode == "tool-use":
    print(json.dumps({"type": "tool_use", "sessionID": session, "part": {"tool": "bash", "state": {"status": "completed", "input": {"command": "rtk proxy python -B -m unittest -v"}, "output": "5 tests passed"}}}), flush=True)
    print(json.dumps({"type": "step_finish", "sessionID": session, "part": {"reason": "stop"}}), flush=True)
    raise SystemExit
if mode == "malformed":
    print("not-json", flush=True)
elif mode == "error":
    print(json.dumps({"type": "error", "sessionID": session, "error": {"message": "provider failure"}}), flush=True)
elif mode == "stop":
    print(json.dumps({"type": "text", "sessionID": session, "part": {"text": "done"}}), flush=True)
    print(json.dumps({"type": "step_finish", "sessionID": session, "part": {"reason": "stop", "tokens": {"input": 2}}}), flush=True)
elif mode == "delay":
    time.sleep(30)
elif mode == "stderr":
    print("cli diagnostic", file=sys.stderr, flush=True)
    print(json.dumps({"type": "text", "sessionID": session, "part": {"text": "done"}}), flush=True)
    print(json.dumps({"type": "step_finish", "sessionID": session, "part": {"reason": "stop"}}), flush=True)
else:
    print(json.dumps({"type": "text", "sessionID": session, "part": {"text": "done"}}), flush=True)
    print(json.dumps({"type": "step_finish", "sessionID": session, "part": {"reason": "tool-calls"}}), flush=True)
'''
    )
    fixture.chmod(0o755)
    return fixture


def _runner(tmp_path, monkeypatch, mode="stop", **kwargs):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    capture = tmp_path / "capture.json"
    monkeypatch.setenv("FLYCODEX_OPENCODE_CAPTURE", str(capture))
    monkeypatch.setenv("FLYCODEX_OPENCODE_MODE", mode)
    return (
        OpenCodeRunner(
            workspace,
            executable=str(_fixture_executable(tmp_path)),
            **kwargs,
        ),
        capture,
    )


def test_fresh_turn_pins_model_sessionless_args_and_isolated_config(tmp_path, monkeypatch):
    runner, capture = _runner(tmp_path, monkeypatch, model=DEFAULT_MODEL)
    events = []

    result = runner.run("Run the task", None, events.append)

    invocation = json.loads(capture.read_text())
    assert invocation["argv"] == [
        "run",
        "--pure",
        "--format",
        "json",
        "--model",
        DEFAULT_MODEL,
        "--title",
        "flycodex-task",
        "--dir",
        str(tmp_path / "workspace"),
    ]
    assert invocation["prompt"].endswith("Selected instruction:\nRun the task")
    assert json.loads(invocation["config"])["model"] == DEFAULT_MODEL
    assert json.loads(invocation["config"])["small_model"] == DEFAULT_MODEL
    assert json.loads(invocation["config"])["share"] == "disabled"
    assert json.loads(invocation["config"])["permission"]["bash"] == {
        "*": "deny",
        "rtk proxy python -B -m unittest -v": "allow",
    }
    assert Path(invocation["config_dir"]).parent.parent == tmp_path
    assert Path(invocation["xdg"]).parent.parent == tmp_path
    assert result["status"] == "completed"
    assert result["session_id"] == "oc-session-fixture"
    assert events[-1]["kind"] == "step_finish"
    assert events[-1]["backend"] == "opencode"
    assert events[-1]["raw"]["type"] == "step_finish"
    persisted = [
        json.loads(line)
        for line in (tmp_path / "opencode-events.jsonl").read_text().splitlines()
    ]
    assert persisted[-1] == events[-1]


def test_resume_uses_only_explicit_session_and_preserves_raw_identity(tmp_path, monkeypatch):
    runner, capture = _runner(tmp_path, monkeypatch, model=DEFAULT_MODEL)

    result = runner.run("Continue", "oc-existing", lambda event: None)

    invocation = json.loads(capture.read_text())
    assert invocation["argv"][-2:] == ["--session", "oc-existing"]
    assert "--continue" not in invocation["argv"]
    assert "--share" not in invocation["argv"]
    assert result["session_id"] == "oc-session-fixture"


def test_fresh_turn_rejects_mixed_observed_session_ids(tmp_path, monkeypatch):
    runner, _ = _runner(tmp_path, monkeypatch, mode="mixed-session")
    result = runner.run("Run", None, lambda event: None)
    assert result["status"] == "failed"
    assert "session" in result["error"].lower()


def test_tool_use_fixture_preserves_command_output_and_status(tmp_path, monkeypatch):
    runner, _ = _runner(tmp_path, monkeypatch, mode="tool-use")
    events = []
    result = runner.run("Run", None, events.append)
    assert result["status"] == "completed"
    tool = next(event for event in events if event["kind"] == "tool")
    assert tool["raw"]["part"]["tool"] == "bash"
    assert tool["raw"]["part"]["state"]["input"]["command"].startswith("rtk proxy")
    assert tool["raw"]["part"]["state"]["output"] == "5 tests passed"


def test_explicit_resume_rejects_a_different_reported_session(tmp_path, monkeypatch):
    runner, _ = _runner(tmp_path, monkeypatch)

    result = runner.run("Continue", "oc-existing", lambda event: None)

    assert result["status"] == "failed"
    assert "did not match" in result["error"]


def test_stderr_diagnostic_does_not_mask_valid_stdout_completion(tmp_path, monkeypatch):
    runner, _ = _runner(tmp_path, monkeypatch, mode="stderr")

    result = runner.run("Run", None, lambda event: None)

    assert result["status"] == "completed"


def test_step_finish_tool_calls_is_not_completion(tmp_path, monkeypatch):
    runner, _ = _runner(tmp_path, monkeypatch, mode="tool-calls")

    result = runner.run("Continue", None, lambda event: None)

    assert result["status"] == "failed"
    assert "completion_evidence_missing" in result["error"]


def test_malformed_json_is_forwarded_as_diagnostic_and_fails_closed(tmp_path, monkeypatch):
    runner, _ = _runner(tmp_path, monkeypatch, mode="malformed")
    events = []

    result = runner.run("Run", None, events.append)

    assert result["status"] == "failed"
    assert "malformed" in result["error"]
    assert any(event["kind"] == "diagnostic" for event in events)


def test_error_event_and_nonzero_exit_fail_without_hiding_provider_message(tmp_path, monkeypatch):
    runner, _ = _runner(tmp_path, monkeypatch, mode="error")

    result = runner.run("Run", None, lambda event: None)

    assert result["status"] == "failed"
    assert "provider failure" in result["error"]


def test_deadline_terminates_fake_process_group(tmp_path, monkeypatch):
    runner, _ = _runner(tmp_path, monkeypatch, mode="delay", timeout=0.05)

    started = time.monotonic()
    result = runner.run("Run", None, lambda event: None)

    assert time.monotonic() - started < 2
    assert result["status"] == "timed_out"
    assert result["error"] == "OpenCode turn exceeded 0.05 seconds"


def test_cancel_terminates_fake_process_group(tmp_path, monkeypatch):
    runner, capture = _runner(tmp_path, monkeypatch, mode="delay", timeout=30)
    result = {}
    thread = threading.Thread(
        target=lambda: result.update(runner.run("Run", None, lambda event: None))
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
    assert result["error"] == "OpenCode turn was cancelled"
