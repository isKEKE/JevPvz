"""Local-only HTTP endpoint and background State sampler."""

from __future__ import annotations

import copy
import json
import math
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping

from state.builder import capture_state
from state.projection import project_jev_state
from jev.questions import COLLECT_NOW_QUESTION_ID, plant_option_id
from jev.trace import EVENT_ACTION_RESULT, EVENT_REQUEST_RESULT, SCHEMA_VERSION_V2, trace_schema_version
from .runtime_control import DEFAULT_TRACE, RuntimeController


STATIC_DIR = Path(__file__).with_name("static")
STATIC_FILES = {
    "/static/viewmodel.js": ("viewmodel.js", "text/javascript; charset=utf-8"),
    "/static/recording.js": ("recording.js", "text/javascript; charset=utf-8"),
    "/static/state-page.js": ("state-page.js", "text/javascript; charset=utf-8"),
    "/static/jev-page.js": ("jev-page.js", "text/javascript; charset=utf-8"),
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


class TraceFileReader:
    """Read only the last complete JSONL events from one configured path.

    Both Trace schemas are read: schema-1 legacy cycles keep their original
    payload shape ``{"status", "events"}``, while a schema-2 runtime trace adds
    ``"schema_version": 2`` so the page can present branch/request/execution
    events separately. Records are validated against their own version and a file
    that changes version mid-run is reported as an error, so a legacy cycle is
    never displayed as a concurrent branch event. The path is always the one the
    Dashboard was started with; no request may name another file.
    """

    def __init__(self, path: str | Path | None, *, limit: int = 100):
        if limit < 1:
            raise ValueError("Trace event limit must be positive.")
        self.path = Path(path) if path is not None else None
        self.limit = limit

    def read(self) -> dict[str, Any]:
        if self.path is None:
            return {"status": "unconfigured", "events": []}
        try:
            with self.path.open("rb") as stream:
                stream.seek(0, 2)
                end = stream.tell()
                if end == 0:
                    return {"status": "empty", "events": []}
                data = self._read_tail(stream, end)
        except FileNotFoundError:
            return {"status": "missing", "events": []}
        except OSError:
            return {"status": "error", "events": []}

        events: list[dict[str, Any]] = []
        version: int | None = None
        for line in data.splitlines():
            if not line:
                continue
            try:
                event = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return {"status": "error", "events": []}
            line_version = trace_schema_version(event)
            if line_version is None or (version is not None and line_version != version):
                return {"status": "error", "events": []}
            version = line_version
            events.append(event)
        if not events:
            return {"status": "empty", "events": []}
        payload: dict[str, Any] = {"status": "ok", "events": events[-self.limit:]}
        if version == SCHEMA_VERSION_V2:
            payload["schema_version"] = SCHEMA_VERSION_V2
        return payload

    def _read_tail(self, stream: Any, end: int) -> bytes:
        position = end
        chunks: list[bytes] = []
        newline_count = 0
        while position > 0 and newline_count <= self.limit:
            size = min(65_536, position)
            position -= size
            stream.seek(position)
            chunk = stream.read(size)
            chunks.insert(0, chunk)
            newline_count += chunk.count(b"\n")
        data = b"".join(chunks)
        if position > 0:
            first_newline = data.find(b"\n")
            data = data[first_newline + 1:] if first_newline >= 0 else b""
        if data and not data.endswith(b"\n"):
            last_newline = data.rfind(b"\n")
            data = data[:last_newline + 1] if last_newline >= 0 else b""
        return data


class OptionMatrixReader:
    """Project the current run's latest complete option set for every question.

    One configured Trace file, read incrementally: the reader remembers how many
    complete bytes it already consumed, so a long run costs one append-sized read
    per request instead of rescanning the file. Unlike :class:`TraceFileReader` it
    keeps no 100-event window -- each question of the current run keeps the whole
    option set of its newest ``request_result``, because the decision grid must
    show every option that was actually offered rather than whatever happened to
    land in the last 100 events.

    Nothing here is a game action: an option is only marked ``executed`` when an
    ``action_result`` of the same ``job_id`` as the group's latest request reports
    ``boundary.status == "success"`` and its target maps exactly onto that option.
    Once proven, that option stays lit for the rest of the run even when the
    question is asked again: the same question keeps its lit option ids in a
    per-run set, so a later request rebuilds the group with those ids still lit.
    Collected state is dropped and rebuilt whenever the Trace belongs to another
    ``run_id`` or the file was truncated/replaced, and an incomplete trailing line
    is left for the next read. A schema-1 Trace has no complete option set, so it
    reports ``legacy`` instead of fabricating points.
    """

    ANCHOR_BYTES = 256
    """Leading bytes compared on every read to notice an in-place file rewrite."""

    def __init__(self, path: str | Path | None):
        self.path = Path(path) if path is not None else None
        self._offset = 0
        self._anchor = b""
        self._identity: tuple[int, int] | None = None
        self._schema_version: int | None = None
        self._run_id: str | None = None
        self._groups: dict[str, dict[str, Any]] = {}
        self._executed: dict[str, set[str]] = {}
        """Per-run proven option ids by question; cleared when the run changes."""
        self._decision: dict[str, Any] | None = None
        """The run's latest request_result, projected for the decision space."""
        self._execution: dict[str, Any] | None = None
        """The run's latest action_result, projected so ACT is not guessed."""

    def read(self) -> dict[str, Any]:
        """Return the current run's question groups without rescanning the file."""
        if self.path is None:
            return _option_payload("unconfigured")
        try:
            with self.path.open("rb") as stream:
                info = os.fstat(stream.fileno())
                identity = (info.st_dev, info.st_ino)
                head = stream.read(self.ANCHOR_BYTES)
                restart = self._file_changed(identity, info.st_size, head)
                offset = 0 if restart else self._offset
                stream.seek(offset)
                chunk = stream.read()
        except FileNotFoundError:
            self._reset()
            return _option_payload("missing")
        except OSError:
            return _option_payload("error")

        consumed = chunk
        if chunk and not chunk.endswith(b"\n"):
            last_newline = chunk.rfind(b"\n")
            consumed = chunk[: last_newline + 1] if last_newline >= 0 else b""

        mode = None if restart else self._schema_version
        run_id = None if restart else self._run_id
        groups = {} if restart else {
            question_id: _copy_option_group(group) for question_id, group in self._groups.items()
        }
        executed = {} if restart else {
            question_id: set(option_ids) for question_id, option_ids in self._executed.items()
        }
        decision = None if restart else self._decision
        execution = None if restart else self._execution

        if consumed:
            try:
                text = consumed.decode("utf-8")
            except UnicodeDecodeError:
                return _option_payload("error")
            for line in text.splitlines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    return _option_payload("error")
                version = trace_schema_version(event)
                if version is None:
                    return _option_payload("error")
                if mode is None:
                    mode = version
                elif version != mode:
                    return _option_payload("error")
                if version != SCHEMA_VERSION_V2:
                    continue
                event_run_id = event.get("run_id")
                if run_id is None:
                    run_id = event_run_id
                elif event_run_id != run_id:
                    # A new run owns its own options and lights; nothing carries over.
                    run_id = event_run_id
                    groups = {}
                    executed = {}
                    decision = None
                    execution = None
                event_name = event.get("event")
                if event_name == EVENT_REQUEST_RESULT:
                    _apply_request_result(groups, event, executed)
                    decision = _decision_summary(event)
                elif event_name == EVENT_ACTION_RESULT:
                    _apply_action_result(groups, event, executed)
                    execution = _execution_summary(event)

        self._offset = offset + len(consumed)
        self._identity = identity
        self._anchor = head
        self._schema_version = mode
        self._run_id = run_id
        self._groups = groups
        self._executed = executed
        self._decision = decision
        self._execution = execution

        if mode == SCHEMA_VERSION_V2:
            return _option_payload(
                "ok",
                run_id=run_id,
                schema_version=mode,
                questions=list(groups.values()),
                decision=decision,
                execution=execution,
            )
        if mode == 1:
            return _option_payload("legacy", schema_version=1)
        return _option_payload("empty")

    def _file_changed(self, identity: tuple[int, int], size: int, head: bytes) -> bool:
        """Whether this file is no longer the one the reader already consumed."""
        if self._identity is not None and identity != self._identity:
            return True
        if size < self._offset:
            return True
        if self._anchor and head[: len(self._anchor)] != self._anchor:
            return True
        return False

    def _reset(self) -> None:
        self._offset = 0
        self._anchor = b""
        self._identity = None
        self._schema_version = None
        self._run_id = None
        self._groups = {}
        self._executed = {}
        self._decision = None
        self._execution = None


def _option_payload(
    status: str,
    *,
    run_id: str | None = None,
    schema_version: int | None = None,
    questions: list[dict[str, Any]] | None = None,
    decision: Mapping[str, Any] | None = None,
    execution: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "schema_version": schema_version,
        "run_id": run_id,
        "questions": questions or [],
        "decision": dict(decision) if decision is not None else None,
        "execution": dict(execution) if execution is not None else None,
    }


def _decision_summary(event: Mapping[str, Any]) -> dict[str, Any]:
    """The latest decision as JEV actually recorded it.

    Only fields the Trace really carries are projected. The interface deliberately
    has no threat score, ETA, speed, or natural-language rationale: those do not
    exist in the Trace, and inventing them would put numbers on a demo screen that
    nothing in the run can be checked against.
    """
    answers = event.get("typed_answers")
    choices: dict[str, str] = {}
    if isinstance(answers, Mapping):
        for question_id, answer in answers.items():
            if isinstance(question_id, str) and isinstance(answer, Mapping):
                choice = answer.get("choice")
                if isinstance(choice, str):
                    choices[question_id] = choice
    return {
        "job_id": _option_text(event.get("job_id")),
        "branch_id": _option_text(event.get("branch_id")),
        "stage_id": _option_text(event.get("stage_id")),
        "status": _option_text(event.get("status")),
        "intent": _option_text(event.get("intent")),
        "effective_action": _option_text(event.get("effective_action")),
        "target": dict(target) if isinstance((target := event.get("target")), Mapping) else None,
        "target_choice_rule": _option_text(event.get("target_choice_rule")),
        "fallback_reason": _option_text(event.get("fallback_reason")),
        "model": _option_text(event.get("model")),
        "latency_ms": Number_or_none(event.get("latency_ms")),
        "sample_sequence": Number_or_none(event.get("sample_sequence")),
        "event_sequence": Number_or_none(event.get("event_sequence")),
        "timestamp_utc": _option_text(event.get("timestamp_utc")),
        "choices": choices,
    }


def _execution_summary(event: Mapping[str, Any]) -> dict[str, Any]:
    """The latest proven game action, so the interface can show ACT truthfully."""
    boundary = event.get("boundary")
    target = event.get("target")
    return {
        "job_id": _option_text(event.get("job_id")),
        "boundary_status": _option_text(boundary.get("status")) if isinstance(boundary, Mapping) else None,
        "outcome": _option_text(event.get("outcome")),
        "effective_action": _option_text(event.get("effective_action")),
        "target": dict(target) if isinstance(target, Mapping) else None,
        "execution_elapsed_ms": Number_or_none(event.get("execution_elapsed_ms")),
        "sample_sequence": Number_or_none(event.get("sample_sequence")),
        "event_sequence": Number_or_none(event.get("event_sequence")),
        "timestamp_utc": _option_text(event.get("timestamp_utc")),
    }


def Number_or_none(value: Any) -> int | float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _catalog_payload() -> dict[str, Any]:
    """Type-code → name → Chinese label for plants, zombies, and dropped items.

    The three label tables already live in ``configs`` and are index-ordered by
    ``type_code``. Serving them here keeps one source of truth: the interface must
    not carry its own copies of 49 plant and 34 zombie names, which would silently
    drift the moment a catalog entry changes. ``byName`` is what lets an option id
    such as ``sunflower@r0c0`` be labelled, because option ids carry the English
    name while the game reports type codes.
    """
    from configs.item_catalog import ITEM_LABELS_ZH, ITEM_NAMES
    from configs.plant_catalog import PLANT_LABELS_ZH, PLANTS
    from configs.zombie_catalog import ZOMBIE_LABELS_ZH, ZOMBIES

    def table(entries: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "entries": entries,
            "byCode": {str(entry["code"]): entry["name"] for entry in entries},
            "byName": {entry["name"]: entry for entry in entries},
        }

    plants = [
        {
            "code": code,
            "name": info.name,
            "zh": PLANT_LABELS_ZH[code] if code < len(PLANT_LABELS_ZH) else info.name,
            "cost": info.cost,
            "role": info.role,
        }
        for code, info in enumerate(PLANTS)
    ]
    zombies = [
        {
            "code": code,
            "name": info.name,
            "zh": ZOMBIE_LABELS_ZH[code] if code < len(ZOMBIE_LABELS_ZH) else info.name,
        }
        for code, info in enumerate(ZOMBIES)
    ]
    items = [
        {"code": code, "name": name, "zh": ITEM_LABELS_ZH[code] if code < len(ITEM_LABELS_ZH) else name}
        for code, name in enumerate(ITEM_NAMES)
    ]
    return {"plants": table(plants), "zombies": table(zombies), "items": table(items)}


def _copy_option_group(group: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "question_id": group["question_id"],
        "branch_id": group["branch_id"],
        "job_id": group["job_id"],
        "choice": group.get("choice"),
        "options": [dict(option) for option in group["options"]],
    }


def _apply_request_result(
    groups: dict[str, dict[str, Any]], event: Mapping[str, Any], executed: dict[str, set[str]]
) -> None:
    """Replace each asked question's group with this request's complete option set.

    The group is replaced, but options this run already proved executed stay lit,
    so re-asking a question cannot erase what the game actually did.
    """
    answers = event.get("typed_answers")
    if not isinstance(answers, Mapping):
        return
    job_id = _option_text(event.get("job_id"))
    branch_id = _option_text(event.get("branch_id"))
    for question_id, answer in answers.items():
        if not isinstance(question_id, str) or not isinstance(answer, Mapping):
            continue
        options = _option_probabilities(answer)
        if options is None:
            # The newest answer has no readable distribution; keep the last
            # complete option set rather than inventing points.
            continue
        proven = executed.get(question_id, frozenset())
        choice = answer.get("choice")
        groups[question_id] = {
            "question_id": question_id,
            "branch_id": branch_id,
            "job_id": job_id,
            "choice": choice if isinstance(choice, str) else None,
            "options": [
                {"option_id": option_id, "probability": probability, "executed": option_id in proven}
                for option_id, probability in options.items()
            ],
        }


def _apply_action_result(
    groups: dict[str, dict[str, Any]], event: Mapping[str, Any], executed: dict[str, set[str]]
) -> None:
    """Light the option a successful, same-job game action actually executed."""
    boundary = event.get("boundary")
    if not isinstance(boundary, Mapping) or boundary.get("status") != "success":
        return
    job_id = _option_text(event.get("job_id"))
    target = event.get("target")
    if job_id is None or not isinstance(target, Mapping):
        return
    action = target.get("action")
    for group in groups.values():
        if group["job_id"] != job_id:
            continue
        if action == "place_plant":
            option_id = _plant_option_id(target)
            if option_id is not None:
                _mark_option_executed(group, option_id)
                executed.setdefault(group["question_id"], set()).add(option_id)
        elif action == "collect_item" and group["question_id"] == COLLECT_NOW_QUESTION_ID:
            # The collect gate is a Noul: a confirmed collection executes its true.
            _mark_option_executed(group, "true")
            executed.setdefault(group["question_id"], set()).add("true")


def _option_probabilities(answer: Mapping[str, Any]) -> dict[str, float] | None:
    """The option set of one typed answer, or None when it has none.

    A Choice answer carries every offered option in ``probabilities``; a Noul
    answer carries one ``noul`` probability and is projected as its two criteria
    ``true``/``false``, the false complementing the recorded probability.
    """
    probabilities = answer.get("probabilities")
    if isinstance(probabilities, Mapping):
        options: dict[str, float] = {}
        for option_id, probability in probabilities.items():
            if not isinstance(option_id, str) or not _option_probability(probability):
                return None
            options[option_id] = float(probability)
        return options or None
    noul = answer.get("noul")
    if _option_probability(noul):
        probability = float(noul)
        return {"true": probability, "false": 1.0 - probability}
    return None


def _mark_option_executed(group: dict[str, Any], option_id: str) -> None:
    for option in group["options"]:
        if option["option_id"] == option_id:
            option["executed"] = True
            return


def _plant_option_id(target: Mapping[str, Any]) -> str | None:
    type_name = target.get("type_name")
    row = target.get("row")
    col = target.get("col")
    if not isinstance(type_name, str) or not _option_integer(row) or not _option_integer(col):
        return None
    return plant_option_id(type_name, row, col)


def _option_text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _option_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _option_probability(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0.0 <= value <= 1.0
    )


def create_dashboard_server(
    poller: StatePoller,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    jev_trace_file: str | Path | None = None,
    runtime_controller: RuntimeController | None = None,
) -> HTTPServer:
    """Create a loopback server with read routes and fixed JEV control routes."""

    if host != "127.0.0.1":
        raise ValueError("The dashboard may only bind to 127.0.0.1.")
    trace_reader = TraceFileReader(jev_trace_file)
    option_reader = OptionMatrixReader(jev_trace_file)
    controller = runtime_controller or (RuntimeController(jev_trace_file, poller.latest) if jev_trace_file is not None else None)

    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "PvZStateDashboard/1"

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            if self.path == "/api/catalog":
                self._send_json(200, _catalog_payload())
                return
            if self.path == "/api/state":
                payload = json.dumps(poller.latest(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self._send(200, payload, "application/json; charset=utf-8")
                return
            if self.path == "/api/jev-state":
                payload = json.dumps(project_jev_state(poller.latest()), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self._send(200, payload, "application/json; charset=utf-8")
                return
            if self.path == "/api/jev-trace":
                payload = json.dumps(trace_reader.read(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self._send(200, payload, "application/json; charset=utf-8")
                return
            if self.path == "/api/jev-options":
                self._send_json(200, option_reader.read())
                return
            if self.path == "/api/jev-runtime":
                status = controller.status() if controller is not None else {
                    "state": "disabled", "message": "Dashboard 未配置 JEV Trace", "can_start": False,
                    "can_stop": False, "game_ready": False, "pid": None, "exit_code": None,
                }
                self._send_json(200, status)
                return
            if self.path == "/":
                self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
                return
            if self.path == "/state":
                self._send_file(STATIC_DIR / "state.html", "text/html; charset=utf-8")
                return
            if self.path == "/jev":
                self._send_file(STATIC_DIR / "jev.html", "text/html; charset=utf-8")
                return
            resource = STATIC_FILES.get(self.path)
            if resource:
                filename, content_type = resource
                self._send_file(STATIC_DIR / filename, content_type)
                return
            self._send(404, b"Not found", "text/plain; charset=utf-8")

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            if self.path not in {"/api/jev-runtime/start", "/api/jev-runtime/stop"}:
                self._send(404, b"Not found", "text/plain; charset=utf-8")
                return
            expected_origin = f"http://127.0.0.1:{self.server.server_port}"
            valid_request = (
                self.headers.get("Origin") == expected_origin
                and self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"
                and self.headers.get("X-JEV-Control") == "1"
                and self.headers.get("Content-Type") == "application/json"
                and self.headers.get("Content-Length") == "2"
            )
            if not valid_request:
                self._send_json(403, {"error": "Invalid local control request"})
                return
            if self.rfile.read(2) != b"{}":
                self._send_json(400, {"error": "Expected empty JSON object"})
                return
            if controller is None:
                self._send_json(409, {"error": "JEV Runtime is not configured"})
                return
            code, status = controller.start() if self.path.endswith("/start") else controller.stop()
            self._send_json(code, status)

        def _send_json(self, code: int, value: dict[str, Any]) -> None:
            payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self._send(code, payload, "application/json; charset=utf-8")

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
            status = args[1] if len(args) > 1 else "request"
            print(f"dashboard: {self.command} response {status}")

    class DashboardServer(HTTPServer):
        allow_reuse_address = False

        def server_bind(self) -> None:
            # Windows permits two listeners on one port when SO_REUSEADDR is
            # enabled. That routed requests to stale Dashboard processes.
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()

        def server_close(self) -> None:
            if controller is not None:
                controller.close()
            super().server_close()

    try:
        return DashboardServer((host, port), DashboardHandler)
    except OSError as exc:
        raise OSError(f"Could not start dashboard at http://{host}:{port}/: {exc}") from exc


def serve_dashboard(
    *,
    port: int = 8765,
    poll_interval_ms: int = 200,
    jev_trace_file: str | Path | None = None,
) -> None:
    """Serve the dashboard only on loopback until interrupted."""
    poller = StatePoller(interval_ms=poll_interval_ms)
    server = create_dashboard_server(poller, port=port, jev_trace_file=jev_trace_file or DEFAULT_TRACE)
    poller.start()
    try:
        print(f"PvZ State dashboard listening at http://127.0.0.1:{port}/")
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        poller.stop()
