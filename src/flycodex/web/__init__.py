"""Loopback spectator server. HTTP never constructs a pilot or a Codex runner."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import re
from urllib.parse import urlsplit

_ASSETS = {"/": ("index.html", "text/html; charset=utf-8"),
           "/app.js": ("app.js", "text/javascript; charset=utf-8"),
           "/style.css": ("style.css", "text/css; charset=utf-8")}
_IMAGE = re.compile(r"/images/((?:adaptive|frozen|random)-[12]-[1-5]-(?:input|feedback)\.png)\Z")


def create_server(run_dir: Path, *, host="127.0.0.1", port=8765):
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("Dashboard must bind to IPv4 loopback")
    public = Path(run_dir).resolve() / "public"
    assets = Path(__file__).parent

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status, body, content_type="text/plain; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path in _ASSETS:
                    filename, content_type = _ASSETS[path]
                    return self._reply(200, (assets / filename).read_bytes(), content_type)
                if path == "/snapshot.json":
                    snapshot = public / "snapshot.json"
                    if snapshot.is_symlink():
                        return self._reply(404, b"Not found")
                    return self._reply(200, snapshot.read_bytes(), "application/json; charset=utf-8")
                match = _IMAGE.fullmatch(path)
                if match:
                    filename = match[1]
                    snapshot = json.loads((public / "snapshot.json").read_text())
                    allowed = {turn[key]["file"] for attempt in snapshot.get("attempts", {}).values()
                               for turn in attempt.get("turns", []) for key in ("input", "feedback_input") if key in turn}
                    target = public / filename
                    if filename in allowed and not target.is_symlink() and target.resolve().parent == public.resolve():
                        return self._reply(200, target.read_bytes(), "image/png")
            except (OSError, ValueError, KeyError, TypeError):
                pass
            self._reply(404, b"Not found")

        def _read_only(self):
            self._reply(405, b"Read-only spectator dashboard")

        do_POST = do_PUT = do_DELETE = do_PATCH = _read_only

        def log_message(self, format, *args):
            pass

    return ThreadingHTTPServer((host, port), Handler)
