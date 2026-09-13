"""Read-only HTTP routes exercise controlled local artifacts."""
import http.client
import json
from pathlib import Path
import subprocess
import sys
import threading

import pytest
from PIL import Image

from flycodex.web import create_server
from flycodex.storage import atomic_save_json


@pytest.fixture
def dashboard(tmp_path):
    public = tmp_path / "public"
    public.mkdir()
    Image.new("RGB", (320, 180)).save(public / "adaptive-1-1-input.png")
    snapshot = {"evidence": "synthetic", "status": "running", "events": [{"type": "diagnostic", "message": "<script>window.injected=true</script>"}], "attempts": {"adaptive-1": {"turns": [{"input": {"file": "adaptive-1-1-input.png"}}]}}}
    atomic_save_json(public / "snapshot.json", snapshot)
    (tmp_path / "secret.txt").write_text("LOCAL SECRET")
    (public / "secret.txt").write_text("PUBLIC SECRET")
    (public / "frozen-1-1-input.png").symlink_to(tmp_path / "secret.txt")
    server = create_server(tmp_path, port=0)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    yield server.server_address, tmp_path
    server.shutdown()
    server.server_close()
    thread.join()


def request(address, path, method="GET"):
    connection = http.client.HTTPConnection(*address, timeout=3)
    connection.request(method, path)
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def test_http_only_enumerated_artifacts_and_no_mutation(dashboard):
    address, root = dashboard
    for path in ("/", "/app.js", "/style.css", "/snapshot.json", "/images/adaptive-1-1-input.png"):
        status, headers, body = request(address, path)
        assert status == 200
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert "default-src 'self'" in headers["Content-Security-Policy"]
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/secret.txt", "/images/../secret.txt", "/images/frozen-1-1-input.png", "/manifest.json", "/controller.json"):
        assert request(address, path)[0] == 404
    before = (root / "public/snapshot.json").read_bytes()
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        assert request(address, "/run", method)[0] == 405
    assert (root / "public/snapshot.json").read_bytes() == before


def test_untrusted_text_stays_json_and_html_is_static(dashboard):
    address, _ = dashboard
    status, headers, body = request(address, "/snapshot.json")
    assert status == 200
    assert headers["Content-Type"].startswith("application/json")
    assert json.loads(body)["events"][0]["message"].startswith("<script>")
    html = request(address, "/")[2]
    assert b"window.injected" not in html


def test_server_rejects_non_loopback_binding(tmp_path):
    with pytest.raises(ValueError, match="loopback"):
        create_server(tmp_path, host="0.0.0.0", port=0)


def test_cli_missing_data_is_nonzero_and_spends_nothing(tmp_path):
    result = subprocess.run([sys.executable, "-m", "flycodex", "run", "--data-dir", str(tmp_path / "missing"), "--run-dir", str(tmp_path / "run"), "--model", "synthetic-do-not-send"], capture_output=True, text=True)
    assert result.returncode == 1
    assert "Prepared source required" in result.stderr
    assert not (tmp_path / "run/state.json").exists()
