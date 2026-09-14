"""Loopback spectator server and the explicitly enabled local brain lab."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

import numpy as np
from PIL import Image

from ..activity import ActivityReader
from ..lab import LabBusyError, LabClosedError, InvalidObservation, LabService

_ASSETS = {
    "/": ("player.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}
_PLAYER = {
    "/observatory": ("index.html", "text/html; charset=utf-8"),
    "/player.css": ("player.css", "text/css; charset=utf-8"),
    "/player.mjs": ("player.mjs", "text/javascript; charset=utf-8"),
    "/player-state.mjs": ("player-state.mjs", "text/javascript; charset=utf-8"),
    "/watch/run.json": ("watch/run.json", "application/json; charset=utf-8"),
    "/watch/activity.json": ("watch/activity.json", "application/json; charset=utf-8"),
}
_WORKSTATION = {
    "/workstation-view.js": ("workstation-view.js", "text/javascript; charset=utf-8"),
    "/workstation-state.mjs": ("workstation-state.mjs", "text/javascript; charset=utf-8"),
    "/workstation-audio.mjs": ("workstation-audio.mjs", "text/javascript; charset=utf-8"),
}
_IMAGE = re.compile(r"/images/((?:adaptive|frozen|random)-[12]-[1-5]-(?:input|feedback)\.png)\Z")
_BRAIN = {
    "/brain/manifest.json": ("brain/manifest.json", "application/json; charset=utf-8"),
    "/brain/positions.bin": ("brain/positions.bin", "application/octet-stream"),
    "/brain/indices.bin": ("brain/indices.bin", "application/octet-stream"),
    "/brain/neurons.json": ("brain/neurons.json", "application/json; charset=utf-8"),
}
_ARCHIVE_IMAGE = re.compile(r"/archive/images/((?:adaptive|frozen|random)-[12]-[1-5]-(?:input|feedback)\.png)\Z")


def _json_bytes(value):
    return (json.dumps(value, separators=(",", ":"), allow_nan=False) + "\n").encode()


def create_server(run_dir: Path, *, host="127.0.0.1", port=8765, demo=False,
                  lab=False, data_dir=None, policy_factory=None):
    """Create a server with static routes and, only when requested, LabService."""
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("Dashboard must bind to IPv4 loopback")
    if demo and lab:
        raise ValueError("--demo and --lab are mutually exclusive")
    assets = Path(__file__).parent
    run_root = Path(run_dir).expanduser().resolve()
    public = assets / "demo" if demo else run_root / "public"
    archive = assets / "demo"
    service = None
    if lab:
        from ..neural import NeuralPolicy

        service = LabService(Path(data_dir or "data"), policy_factory=policy_factory or NeuralPolicy)
    routes = dict(_ASSETS)
    routes.update(_PLAYER)
    routes.update(_WORKSTATION)
    for route, mime in json.loads((assets / "body/routes.json").read_text()).items():
        routes[route] = (route.lstrip("/"), mime)
    routes.update({"/presentation.mjs": ("presentation.mjs", "text/javascript; charset=utf-8"),
                   "/brain-view.js": ("brain-view.js", "text/javascript; charset=utf-8"),
                   "/brain-state.mjs": ("brain-state.mjs", "text/javascript; charset=utf-8"),
                   "/live-extra.css": ("live-extra.css", "text/css; charset=utf-8"),
                   "/translations.json": ("demo/translations.json", "application/json; charset=utf-8")})
    if demo:
        routes["/demo-provenance.json"] = ("demo/provenance.json", "application/json; charset=utf-8")
    routes.update(_BRAIN)

    class Server(ThreadingHTTPServer):
        allow_reuse_address = True

        def server_close(self):
            if service is not None:
                service.close()
            super().server_close()

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status, body, content_type="text/plain; charset=utf-8"):
            if isinstance(body, str):
                body = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def _json_reply(self, status, value):
            return self._reply(status, _json_bytes(value), "application/json; charset=utf-8")

        def _not_found(self):
            return self._reply(404, b"Not found")

        def _expected_host(self):
            host_header = self.headers.get("Host", "")
            if host_header.count(":") == 1:
                host_name, raw_port = host_header.rsplit(":", 1)
                if not raw_port.isdecimal() or len(raw_port) > 5:
                    return None
                try:
                    port = int(raw_port)
                except (ValueError, OverflowError):
                    return None
                if not 1 <= port <= 65535:
                    return None
            else:
                host_name = host_header
                port = 80
            if host_name not in {host, "127.0.0.1", "localhost"}:
                return None
            if port != self.server.server_port:
                return None
            return host_name, port

        def _same_origin(self):
            expected = self._expected_host()
            if expected is None:
                return False
            origin = self.headers.get("Origin")
            if not origin:
                return False
            parsed = urlsplit(origin)
            try:
                origin_port = parsed.port if parsed.port is not None else 80
            except ValueError:
                return False
            expected_host, expected_port = expected
            return (
                parsed.scheme == "http"
                and parsed.hostname == expected_host
                and origin_port == expected_port
            )

        def _read_json(self):
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                raise ValueError("application/json is required")
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError as exc:
                raise ValueError("invalid Content-Length") from exc
            if length < 0 or length > 1024:
                raise ValueError("JSON body must be at most 1 KiB")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("incomplete JSON body")
            def reject_constant(value):
                raise ValueError(f"invalid JSON constant {value}")
            value = json.loads(raw.decode("utf-8"), parse_constant=reject_constant)
            if not isinstance(value, dict):
                raise ValueError("JSON body must be an object")
            return value

        def _lab_state(self):
            if service is None:
                return self._not_found()
            state = service.state()
            available = bool(service.data_dir.is_dir() and (service.data_dir / "graph.npz").is_file())
            state.update({"availability": available,
                          "event_cursor": {"oldest_seq": state["oldest_seq"], "latest_seq": state["latest_seq"], "reset": False},
                          "mode": "lab"})
            if not available:
                state["error"] = state.get("error") or "Prepared neural data is unavailable"
            return self._json_reply(200 if available else 503, state)

        def do_GET(self):
            split = urlsplit(self.path)
            path = split.path
            try:
                if path == "/lab/state":
                    return self._lab_state()
                if path == "/lab/events":
                    if service is None:
                        return self._not_found()
                    query = parse_qs(split.query, keep_blank_values=True)
                    raw_after = query.get("after", ["0"])[0]
                    if not raw_after.isdecimal() or len(raw_after) > 20:
                        return self._json_reply(400, {"error": "after must be a nonnegative integer"})
                    page = service.events(after=int(raw_after))
                    available = service.data_dir.is_dir() and (service.data_dir / "graph.npz").is_file()
                    page["availability"] = bool(available)
                    return self._json_reply(200 if available else 503, page)
                if path == "/activity.json":
                    query = parse_qs(split.query, keep_blank_values=True)
                    raw_after = query.get("after", [None])[0]
                    if raw_after is not None and (not raw_after.isdecimal() or len(raw_after) > 20):
                        return self._json_reply(400, {"error": "after must be a nonnegative integer"})
                    result = ActivityReader(public).read(after=int(raw_after) if raw_after is not None else None)
                    return self._json_reply(200, result)
                if path == "/lab/input.png":
                    if service is None:
                        return self._not_found()
                    query = parse_qs(split.query, keep_blank_values=True)
                    job_id = query.get("job_id", [None])[0]
                    state = service.state()
                    if not job_id or state.get("job_id") != job_id or not state.get("input"):
                        return self._not_found()
                    frame = service._frame(state["input"])
                    output = BytesIO()
                    Image.fromarray(np.asarray(frame, dtype=np.uint8), mode="RGB").save(output, format="PNG")
                    return self._reply(200, output.getvalue(), "image/png")
                if path in routes:
                    filename, content_type = routes[path]
                    return self._reply(200, (assets / filename).read_bytes(), content_type)
                if path == "/snapshot.json":
                    target = public / "snapshot.json"
                    if target.is_symlink():
                        return self._not_found()
                    return self._reply(200, target.read_bytes(), "application/json; charset=utf-8")
                if path == "/archive/snapshot.json":
                    return self._reply(200, (archive / "snapshot.json").read_bytes(), "application/json; charset=utf-8")
                match = _IMAGE.fullmatch(path)
                if match:
                    filename = match[1]
                    snapshot = json.loads((public / "snapshot.json").read_text())
                    allowed = {turn[key]["file"] for attempt in snapshot.get("attempts", {}).values()
                               for turn in attempt.get("turns", []) for key in ("input", "feedback_input") if key in turn}
                    target = public / filename
                    if filename in allowed and not target.is_symlink() and target.resolve().parent == public.resolve():
                        return self._reply(200, target.read_bytes(), "image/png")
                match = _ARCHIVE_IMAGE.fullmatch(path)
                if match:
                    filename = match[1]
                    snapshot = json.loads((archive / "snapshot.json").read_text())
                    allowed = {turn[key]["file"] for attempt in snapshot.get("attempts", {}).values()
                               for turn in attempt.get("turns", []) for key in ("input", "feedback_input") if key in turn}
                    target = archive / filename
                    if filename in allowed and not target.is_symlink() and target.resolve().parent == archive.resolve():
                        return self._reply(200, target.read_bytes(), "image/png")
            except (OSError, ValueError, KeyError, TypeError, UnicodeError, json.JSONDecodeError):
                pass
            return self._not_found()

        def do_POST(self):
            path = urlsplit(self.path).path
            if service is None or path not in {"/lab/observe", "/lab/cancel"}:
                return self._reply(405, b"Read-only spectator dashboard")
            if not self._same_origin():
                return self._json_reply(403, {"error": "Host and Origin must be loopback and same-origin"})
            if path == "/lab/observe" and not (service.data_dir.is_dir() and (service.data_dir / "graph.npz").is_file()):
                return self._json_reply(503, {"availability": False, "error": "Prepared neural data is unavailable"})
            try:
                value = self._read_json()
                if path == "/lab/observe":
                    if set(value) != {"kind", "passed"}:
                        raise ValueError("observation must contain only kind and passed")
                    job_id = service.observe(value)
                    return self._json_reply(202, {"job_id": job_id})
                if value != {}:
                    raise ValueError("cancel body must be an empty JSON object")
                if service.cancel():
                    return self._json_reply(202, {"cancelled": True})
                return self._json_reply(409, {"error": "no observation is running", "cancelled": False})
            except (InvalidObservation, ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
                return self._json_reply(400, {"error": str(exc)})
            except LabBusyError as exc:
                return self._json_reply(409, {"error": str(exc)})
            except LabClosedError as exc:
                return self._json_reply(503, {"error": str(exc)})

        def _read_only(self):
            return self._reply(405, b"Read-only spectator dashboard")

        do_PUT = do_DELETE = do_PATCH = _read_only

        def log_message(self, format, *args):
            pass

    return Server((host, port), Handler)
