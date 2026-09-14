"""Read-only HTTP routes exercise controlled local artifacts."""
import hashlib
import http.client
import json
from pathlib import Path
import shutil
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
    for path in ("/", "/observatory", "/app.js", "/style.css", "/player.css", "/player.mjs", "/player-state.mjs", "/watch/run.json", "/watch/activity.json", "/snapshot.json", "/images/adaptive-1-1-input.png"):
        status, headers, body = request(address, path)
        assert status == 200
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert "default-src 'self'" in headers["Content-Security-Policy"]
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/secret.txt", "/images/../secret.txt", "/images/frozen-1-1-input.png", "/manifest.json", "/controller.json", "/watch/../snapshot.json"):
        assert request(address, path)[0] == 404
    before = (root / "public/snapshot.json").read_bytes()
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        assert request(address, "/run", method)[0] == 405
    assert (root / "public/snapshot.json").read_bytes() == before


def test_simple_player_and_advanced_observatory_have_distinct_readonly_routes(dashboard):
    address, _ = dashboard
    player = request(address, "/")[2]
    observatory = request(address, "/observatory")[2]
    assert b"id=\"play-toggle\"" in player
    assert b"Live brain observatory" in observatory
    run = json.loads(request(address, "/watch/run.json")[2])
    activity = json.loads(request(address, "/watch/activity.json")[2])
    assert run["version"] == activity["version"] == 1
    assert run["backend"] == "opencode"
    assert len(activity["bins"]) == 70


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


def test_dashboard_projection_and_replay():
    if not shutil.which("node"):
        pytest.skip("Node.js is required for presentation tests")
    result = subprocess.run(["node", "--test", "tests/web_presentation.mjs"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


def test_simple_player_state_projection():
    if not shutil.which("node"):
        pytest.skip("Node.js is required for player tests")
    result = subprocess.run(["node", "--test", "tests/player_state.mjs"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


def test_brain_state_projection():
    if not shutil.which("node"):
        pytest.skip("Node.js is required for brain state tests")
    result = subprocess.run(["node", "--test", "tests/brain_state.mjs"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


def test_demo_is_bundled_read_only_and_routes_are_exact(tmp_path):
    server = create_server(tmp_path / "absent", port=0, demo=True)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        address = server.server_address
        before = request(address, "/snapshot.json")[2]
        snapshot = json.loads(before)
        assert snapshot["evidence"] == "genuine"
        assert snapshot["presentation"]["mode"] == "demo"
        assert snapshot["budget"]["used"] == 9
        assert len(snapshot["attempts"]) == 6
        assert all(a["status"] == "success" for a in snapshot["attempts"].values())
        assert b"session_id" not in before and b"/Users/" not in before
        for path in ("/body-view.js", "/brain-view.js", "/brain-state.mjs", "/live-extra.css", "/body/flybody.glb", "/body/motion.json", "/body/provenance.json", "/presentation.mjs", "/translations.json", "/demo-provenance.json"):
            assert request(address, path)[0] == 200
        for a in snapshot["attempts"].values():
            for turn in a["turns"]:
                for key in ("input", "feedback_input"):
                    status, _, body = request(address, "/images/" + turn[key]["file"])
                    assert status == 200
                    assert hashlib.sha256(body).hexdigest() == turn[key]["png_sha256"]
        for path in ("/body/../demo/snapshot.json", "/demo/snapshot.json", "/images/%2e%2e/snapshot.json", "/body/unknown.json"):
            assert request(address, path)[0] == 404
        assert request(address, "/run", "POST")[0] == 405
        assert request(address, "/snapshot.json")[2] == before
        assert not (tmp_path / "absent").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_cli_demo_flag_selects_bundled_server(monkeypatch, tmp_path, capsys):
    from flycodex.cli import main
    import flycodex.web
    calls = []
    class Server:
        server_port = 8772
        def serve_forever(self): pass
        def server_close(self): pass
    def server(run_dir, **kwargs):
        calls.append((run_dir, kwargs))
        return Server()
    monkeypatch.setattr(flycodex.web, "create_server", server)
    assert main(["serve", "--demo", "--run-dir", str(tmp_path)]) == 0
    assert calls[0][1]["demo"] is True
    assert "read-only" in capsys.readouterr().out


def test_bundled_provenance_and_translations_preserve_original_identity():
    public = Path(__file__).parents[1] / "src/flycodex/web/demo"
    raw = (public / "snapshot.json").read_bytes()
    snapshot = json.loads(raw)
    provenance = json.loads((public / "provenance.json").read_text())
    assert hashlib.sha256(raw).hexdigest() == provenance["snapshot_sha256"]
    assert snapshot["settings"]["source_revision"] == "a16e1713f340a15a4e87f2d5651536f03aa9fe3a"
    assert snapshot["presentation"]["source_snapshot_sha256"] == provenance["source_snapshot_sha256"]
    assert len(provenance["images"]) == 18
    assert not any(key in raw for key in (b"session_id", b"thread_id", b"/Users/", b"checkpoint", b"send_id"))
    messages = [event["item"]["text"] for a in snapshot["attempts"].values() for turn in a["turns"]
                for event in turn["events"] if event.get("item", {}).get("type") == "agent_message"]
    curated = json.loads((public / "translations.json").read_text())
    assert len(messages) == 18
    assert len(curated) == 16
    assert {entry["original"] for entry in curated} == set(messages)
    for entry in curated:
        assert hashlib.sha256(entry["original"].encode()).hexdigest() == entry["source_sha256"]
        assert entry["original"] != entry["english"]
