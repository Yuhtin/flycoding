"""Bounded tests for the opt-in live OpenCode typing service."""

from __future__ import annotations

import http.client
import json
import threading
import time

import pytest

from flycodex.typing_live import TypingBusyError, TypingOpenCodeRunner, TypingService
from flycodex.web import create_server


class BlockingRunner:
    instances = []

    def __init__(self, workspace, model):
        self.workspace = workspace
        self.model = model
        self.started = threading.Event()
        self.cancelled = threading.Event()
        self.release = threading.Event()
        self.__class__.instances.append(self)

    def run(self, prompt, session_id, on_event):
        self.started.set()
        on_event({"kind": "text", "raw": {"part": {"text": "streamed "}}})
        self.release.wait(2)
        return {"status": "cancelled" if self.cancelled.is_set() else "completed"}

    def cancel(self):
        self.cancelled.set()
        self.release.set()


class FailingRunner:
    def __init__(self, workspace, model):
        pass

    def run(self, prompt, session_id, on_event):
        on_event({"kind": "text", "raw": {"part": {"text": "partial"}}})
        return {"status": "failed", "error": "synthetic runner failure"}

    def cancel(self):
        return None


def wait_for(predicate):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


def test_service_streams_deduplicates_busy_and_cancels(tmp_path):
    BlockingRunner.instances.clear()
    service = TypingService(tmp_path / "workspace", model="test-model", runner_factory=BlockingRunner)
    try:
        initial = service.submit("build tiny app", "request-1")
        assert initial["status"] in {"starting", "running"}
        runner = BlockingRunner.instances[0]
        runner.started.wait(1)
        wait_for(lambda: service.state()["text"] == "streamed ")
        duplicate = service.submit("build tiny app", "request-1")
        assert duplicate["job_id"] == initial["job_id"]
        assert duplicate["text"] == "streamed "
        with pytest.raises(TypingBusyError):
            service.submit("another app", "request-2")
        cancelled = service.cancel()
        assert cancelled["status"] == "cancelled"
        assert runner.cancelled.is_set()
        assert service.submit("build tiny app", "request-1")["status"] == "cancelled"
    finally:
        service.close()


def test_service_records_completed_and_failed_terminal_states(tmp_path):
    class CompletingRunner(FailingRunner):
        def run(self, prompt, session_id, on_event):
            on_event({"kind": "text", "raw": {"part": {"text": "done"}}})
            return {"status": "completed"}

    completed = TypingService(tmp_path / "complete", runner_factory=CompletingRunner)
    failed = TypingService(tmp_path / "failed", runner_factory=FailingRunner)
    try:
        completed.submit("prompt", "complete-1")
        wait_for(lambda: completed.state()["status"] == "completed")
        assert completed.state()["text"] == "done"
        failed.submit("prompt", "fail-1")
        wait_for(lambda: failed.state()["status"] == "failed")
        assert failed.state()["error"] == "synthetic runner failure"
        assert failed.state()["text"] == "partial"
    finally:
        completed.close()
        failed.close()


def test_opencode_typing_runner_sends_generic_workspace_prompt(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executable = tmp_path / "fake-opencode"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        "pathlib.Path('received-prompt.txt').write_text(sys.stdin.read())\n"
        "print(json.dumps({'type': 'session.created', 'sessionID': 'fake-session'}), flush=True)\n"
        "print(json.dumps({'type': 'text', 'part': {'text': 'built'}}), flush=True)\n"
        "print(json.dumps({'type': 'step_finish', 'part': {'reason': 'stop'}}), flush=True)\n"
    )
    executable.chmod(executable.stat().st_mode | 0o111)
    events = []
    runner = TypingOpenCodeRunner(workspace, model="test-model", executable=str(executable))
    result = runner.run("build a tiny app", None, events.append)
    prompt = (workspace / "received-prompt.txt").read_text()
    assert result["status"] == "completed"
    assert "discount.py" not in prompt
    assert "isolated coding workspace" in prompt
    assert "build a tiny app" in prompt
    assert events[0]["session_id"] == "fake-session"
    config = json.loads(runner._environment()["OPENCODE_CONFIG_CONTENT"])
    assert config["permission"]["edit"] == {"*": "deny", "**": "allow"}


def request(address, path, method="GET", body=None, headers=None):
    connection = http.client.HTTPConnection(*address, timeout=3)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    value = response.status, response.read()
    connection.close()
    return value


def headers(address, origin="127.0.0.1"):
    return {
        "Host": f"127.0.0.1:{address[1]}",
        "Origin": f"http://{origin}:{address[1]}",
        "Content-Type": "application/json",
    }


@pytest.fixture
def live_server(tmp_path):
    BlockingRunner.instances.clear()
    server = create_server(
        tmp_path / "run",
        port=0,
        opencode=True,
        workspace=tmp_path / "typing-workspace",
        model="test-model",
        typing_runner_factory=BlockingRunner,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_typing_http_contract_origin_limits_and_full_state(live_server):
    state_status, state_body = request(live_server, "/typing/state")
    state = json.loads(state_body)
    assert state_status == 200
    assert set(state) == {"enabled", "status", "request_id", "job_id", "text", "error", "model", "workspace"}
    assert state["enabled"] is True
    assert state["status"] == "idle"
    assert state["model"] == "test-model"

    payload = json.dumps({"prompt": "build tiny app", "request_id": "http-1"}).encode()
    accepted, body = request(live_server, "/typing/submit", "POST", payload, headers(live_server))
    submitted = json.loads(body)
    assert accepted == 202
    assert submitted["status"] in {"starting", "running"}
    wait_for(lambda: json.loads(request(live_server, "/typing/state")[1])["text"] == "streamed ")
    duplicate, duplicate_body = request(live_server, "/typing/submit", "POST", payload, headers(live_server))
    assert duplicate == 202
    assert json.loads(duplicate_body)["job_id"] == submitted["job_id"]
    assert request(live_server, "/typing/submit", "POST", payload, headers(live_server, origin="evil.invalid"))[0] == 403
    assert request(live_server, "/typing/submit", "POST", payload, {**headers(live_server), "Content-Type": "text/plain"})[0] == 400
    assert request(live_server, "/typing/submit", "POST", b"x" * 8193, headers(live_server))[0] == 400
    cancel_status, cancel_body = request(live_server, "/typing/cancel", "POST", b"{}", headers(live_server))
    assert cancel_status == 200
    assert json.loads(cancel_body)["status"] == "cancelled"


def test_typing_state_is_always_available_but_posts_are_disabled(tmp_path):
    server = create_server(tmp_path / "run", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, body = request(server.server_address, "/typing/state")
        assert status == 200
        assert json.loads(body)["enabled"] is False
        payload = json.dumps({"prompt": "x", "request_id": "r"}).encode()
        assert request(server.server_address, "/typing/submit", "POST", payload, headers(server.server_address))[0] == 503
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
