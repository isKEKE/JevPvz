"""Local-only HTTP endpoint and background State sampler."""

from __future__ import annotations

import copy
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable

from state.builder import capture_state
from state.projection import project_jev_state


STATIC_DIR = Path(__file__).with_name("static")
STATIC_FILES = {
    "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/static/state-page.js": ("state-page.js", "text/javascript; charset=utf-8"),
    "/static/style.css": ("style.css", "text/css; charset=utf-8"),
}


class StatePoller:
    """One sampler shared by every HTTP request and browser tab."""

    def __init__(self, interval_ms: int = 200, sampler: Callable[[], dict[str, Any]] | None = None):
        if interval_ms < 50:
            raise ValueError("Sampling interval must be at least 50 ms.")
        self.interval_seconds = interval_ms / 1000
        self.sampler = sampler or capture_state
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest: dict[str, Any] = {
            "schema_version": 1,
            "status": "connecting",
            "valid": False,
            "decision_ready": False,
            "availability": {"sun_balance": "unavailable"},
            "errors": [],
            "observed_at_utc": None,
        }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="pvz-state-poller", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout)

    def latest(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._latest)

    def sample_once(self) -> dict[str, Any]:
        try:
            state = self.sampler()
        except Exception as exc:
            state = {
                "schema_version": 1,
                "status": "error",
                "valid": False,
                "decision_ready": False,
                "availability": {"sun_balance": "error"},
                "errors": [{"scope": "sampler", "message": str(exc)}],
                "observed_at_utc": None,
            }
        with self._lock:
            self._latest = copy.deepcopy(state)
        return state

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.sample_once()
            self._stop_event.wait(self.interval_seconds)


def create_dashboard_server(
    poller: StatePoller,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> HTTPServer:
    """Create a server with an allowlisted set of read-only GET routes."""

    if host != "127.0.0.1":
        raise ValueError("The dashboard may only bind to 127.0.0.1.")

    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "PvZStateDashboard/1"

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            if self.path == "/api/state":
                payload = json.dumps(poller.latest(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self._send(200, payload, "application/json; charset=utf-8")
                return
            if self.path == "/api/jev-state":
                payload = json.dumps(project_jev_state(poller.latest()), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self._send(200, payload, "application/json; charset=utf-8")
                return
            if self.path == "/":
                self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
                return
            if self.path == "/state":
                self._send_file(STATIC_DIR / "state.html", "text/html; charset=utf-8")
                return
            resource = STATIC_FILES.get(self.path)
            if resource:
                filename, content_type = resource
                self._send_file(STATIC_DIR / filename, content_type)
                return
            self._send(404, b"Not found", "text/plain; charset=utf-8")

        def _send_file(self, path: Path, content_type: str) -> None:
            try:
                content = path.read_bytes()
            except OSError:
                self._send(500, b"Dashboard resource unavailable", "text/plain; charset=utf-8")
                return
            self._send(200, content, content_type)

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, fmt: str, *args: Any) -> None:
            print("dashboard: " + fmt % args)

    try:
        return HTTPServer((host, port), DashboardHandler)
    except OSError as exc:
        raise OSError(f"Could not start dashboard at http://{host}:{port}/: {exc}") from exc


def serve_dashboard(*, port: int = 8765, poll_interval_ms: int = 200) -> None:
    """Serve the dashboard only on loopback until interrupted."""
    poller = StatePoller(interval_ms=poll_interval_ms)
    server = create_dashboard_server(poller, port=port)
    poller.start()
    try:
        print(f"PvZ State dashboard listening at http://127.0.0.1:{port}/")
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        poller.stop()
