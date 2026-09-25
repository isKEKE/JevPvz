"""Guarded semantic PvZ actions with same-process State confirmation."""

from __future__ import annotations

import ctypes
import json
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from configs.pvz_1051 import ACTION_WINDOW_PROFILE, TARGET_IDENTITY
from runtime.process import ProcessIdentity, ProcessInfo, locate_target_process, verify_target_identity
from runtime.window import (
    ClientRect,
    DisplayGeometry,
    TargetWindow,
    TargetWindowError,
    client_rect,
    display_geometry,
    dpi_for_window,
    find_target_window,
)
from state.builder import capture_state


DEFAULT_TIMEOUT_MS = 10_000
DEFAULT_POLL_INTERVAL_MS = 250
MAX_TIMEOUT_MS = 120_000


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _object_id(value: Any) -> bool:
    return _is_int(value) and 0 <= value <= 0xFFFFFFFF


def _normalized_path(path: str) -> str:
    return os.path.normcase(os.path.realpath(path))


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


@dataclass(frozen=True)
class ActionResult:
    status: str
    action: str | None
    message: str
    request: Any
    target: dict[str, Any] | None
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    details: dict[str, Any]
    started_at_utc: str
    finished_at_utc: str
    elapsed_ms: int

    def to_dict(self) -> dict[str, Any]:
        return _json_safe({
            "schema_version": 1,
            "status": self.status,
            "action": self.action,
            "message": self.message,
            "request": self.request,
            "target": self.target,
            "before_state": self.before_state,
            "after_state": self.after_state,
            "details": self.details,
            "started_at_utc": self.started_at_utc,
            "finished_at_utc": self.finished_at_utc,
            "elapsed_ms": self.elapsed_ms,
        })


@dataclass(frozen=True)
class _TargetContext:
    process: ProcessInfo
    identity: ProcessIdentity
    window: TargetWindow
    rect: ClientRect
    dpi: int
    display: DisplayGeometry


class _ActionProblem(RuntimeError):
    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None):
        self.details = dict(details or {})
        super().__init__(message)


class _StateUnavailable(_ActionProblem):
    pass


class _InputDeliveryError(_ActionProblem):
    def __init__(self, message: str, *, uncertain: bool, details: Mapping[str, Any] | None = None):
        self.uncertain = uncertain
        super().__init__(message, details=details)


class _UnsupportedRequest(_ActionProblem):
    pass


class ActionExecutor:
    """Execute one semantic request without activating or steering the game."""

    def __init__(
        self,
        *,
        state_reader: Callable[[], Mapping[str, Any]] = capture_state,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self._state_reader = state_reader
        self._clock = clock
        self._sleep = sleeper

    def place_plant(
        self,
        card_slot: int,
        row: int,
        col: int,
        *,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
    ) -> ActionResult:
        return self.execute({
            "action": "place_plant",
            "card_slot": card_slot,
            "row": row,
            "col": col,
            "timeout_ms": timeout_ms,
            "poll_interval_ms": poll_interval_ms,
        })

    def collect_item(
        self,
        item_id: int,
        *,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
    ) -> ActionResult:
        return self.execute({
            "action": "collect_item",
            "item_id": item_id,
            "timeout_ms": timeout_ms,
            "poll_interval_ms": poll_interval_ms,
        })

    def shovel_cell(
        self,
        row: int,
        col: int,
        *,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
    ) -> ActionResult:
        return self.execute({
            "action": "shovel_cell",
            "row": row,
            "col": col,
            "timeout_ms": timeout_ms,
            "poll_interval_ms": poll_interval_ms,
        })

    @staticmethod
    def rejected_request(raw_request: str | None, message: str) -> ActionResult:
        now = _utc_now()
        return ActionResult(
            status="rejected",
            action=None,
            message=message,
            request={"raw_json": raw_request},
            target=None,
            before_state=None,
            after_state=None,
            details={"input_clicks": []},
            started_at_utc=now,
            finished_at_utc=now,
            elapsed_ms=0,
        )

    def execute(self, request: Any) -> ActionResult:
        started_at = _utc_now()
        started = self._clock()
        self._latest_state = None
        self._current_before = None
        request_copy = dict(request) if isinstance(request, Mapping) else request
        action = request.get("action") if isinstance(request, Mapping) else None
        if not isinstance(action, str):
            return self._result(
                status="rejected", action=None, message="Request must be a JSON object with an action name.",
                request=request_copy, started=started, started_at=started_at,
                target=None, before=None, after=None, details={"input_clicks": []},
            )

        try:
            normalized = self._validate_request(request)
        except _UnsupportedRequest as exc:
            return self._result(
                status="rejected", action=action, message=str(exc), request=request_copy,
                started=started, started_at=started_at, target=None, before=None, after=None,
                details={"input_clicks": [], **exc.details},
            )

        target: dict[str, Any] | None = None
        before_state: dict[str, Any] | None = None
        after_state: dict[str, Any] | None = None
        details: dict[str, Any] = {"input_clicks": []}
        click_log: list[dict[str, Any]] = details["input_clicks"]
        try:
            context = self._target_context()
            target = self._context_record(context)
            initial = self._capture_for_target(context)

            if action == "place_plant":
                before_state, after_state, outcome_details, success = self._execute_place(
                    normalized, context, initial, click_log
                )
            elif action == "collect_item":
                before_state, after_state, outcome_details, success = self._execute_collect(
                    normalized, context, initial, click_log
                )
            else:
                before_state, after_state, outcome_details, success = self._execute_shovel(
                    normalized, context, initial, click_log
                )
            details.update(outcome_details)
            return self._result(
                status="success" if success else "unverified",
                action=action,
                message=("State confirmed the requested action." if success else
                         "Input was sent, but the requested State change was not confirmed."),
                request=normalized,
                started=started,
                started_at=started_at,
                target=target,
                before=before_state,
                after=after_state,
                details=details,
            )
        except KeyboardInterrupt:
            if before_state is None:
                before_state = self._current_before
            latest = self._latest_state
            after_state = self._summarize_state(latest, normalized) if latest else after_state
            status = "unverified" if self._input_may_have_been_sent(click_log) else "rejected"
            return self._result(
                status=status, action=action,
                message="Request was interrupted; no automatic input retry was made.",
                request=normalized, started=started, started_at=started_at,
                target=target, before=before_state, after=after_state,
                details=details,
            )
        except _ActionProblem as exc:
            details.update(exc.details)
            if before_state is None:
                before_state = self._current_before
            latest = self._latest_state
            if latest is not None and after_state is None and self._input_may_have_been_sent(click_log):
                after_state = self._summarize_state(latest, normalized)
            status = "unverified" if self._input_may_have_been_sent(click_log) else "rejected"
            return self._result(
                status=status, action=action, message=str(exc), request=normalized,
                started=started, started_at=started_at, target=target,
                before=before_state, after=after_state, details=details,
            )
        except Exception as exc:
            if before_state is None:
                before_state = self._current_before
            latest = self._latest_state
            if latest is not None and after_state is None and self._input_may_have_been_sent(click_log):
                after_state = self._summarize_state(latest, normalized)
            status = "unverified" if self._input_may_have_been_sent(click_log) else "rejected"
            return self._result(
                status=status, action=action, message=f"Action stopped safely: {exc}",
                request=normalized, started=started, started_at=started_at,
                target=target, before=before_state, after=after_state, details=details,
            )

    @property
    def _latest_state(self) -> Mapping[str, Any] | None:
        return getattr(self, "__latest_state", None)

    @_latest_state.setter
    def _latest_state(self, value: Mapping[str, Any] | None) -> None:
        self.__latest_state = value

    @property
    def _current_before(self) -> dict[str, Any] | None:
        return getattr(self, "__current_before", None)

    @_current_before.setter
    def _current_before(self, value: dict[str, Any] | None) -> None:
        self.__current_before = value

    def _validate_request(self, request: Any) -> dict[str, Any]:
        if not isinstance(request, Mapping):
            raise _UnsupportedRequest("Request must be a JSON object.")
        action = request.get("action")
        if action not in {"place_plant", "collect_item", "shovel_cell"}:
            raise _UnsupportedRequest("action must be place_plant, collect_item, or shovel_cell.")

        common = {"action", "timeout_ms", "poll_interval_ms"}
        allowed = {
            "place_plant": common | {"card_slot", "row", "col"},
            "collect_item": common | {"item_id"},
            "shovel_cell": common | {"row", "col"},
        }[action]
        extras = set(request) - allowed
        if extras:
            raise _UnsupportedRequest(f"Unsupported request key(s): {', '.join(sorted(map(str, extras)))}.")
        required = {
            "place_plant": {"card_slot", "row", "col"},
            "collect_item": {"item_id"},
            "shovel_cell": {"row", "col"},
        }[action]
        missing = required - set(request)
        if missing:
            raise _UnsupportedRequest(f"Missing request key(s): {', '.join(sorted(missing))}.")

        normalized = dict(request)
        if action == "place_plant":
            self._require_integer_range(normalized, "card_slot", 1, 10)
            self._require_integer_range(normalized, "row", 0, 4)
            self._require_integer_range(normalized, "col", 0, 8)
        elif action == "collect_item":
            item_id = normalized.get("item_id")
            if not _object_id(item_id):
                raise _UnsupportedRequest("item_id must be an unsigned 32-bit integer.")
        else:
            self._require_integer_range(normalized, "row", 0, 4)
            self._require_integer_range(normalized, "col", 0, 8)

        normalized.setdefault("timeout_ms", DEFAULT_TIMEOUT_MS)
        normalized.setdefault("poll_interval_ms", DEFAULT_POLL_INTERVAL_MS)
        self._require_integer_range(normalized, "timeout_ms", 100, MAX_TIMEOUT_MS)
        self._require_integer_range(normalized, "poll_interval_ms", 50, 2_000)
        return normalized

    @staticmethod
    def _require_integer_range(request: Mapping[str, Any], name: str, minimum: int, maximum: int) -> None:
        value = request.get(name)
        if not _is_int(value) or not minimum <= value <= maximum:
            raise _UnsupportedRequest(f"{name} must be an integer from {minimum} through {maximum}.")

    def _target_context(self) -> _TargetContext:
        process = locate_target_process(str(TARGET_IDENTITY["path"]))
        identity = verify_target_identity(process, TARGET_IDENTITY)
        window = find_target_window(process.pid)
        rect = client_rect(window.hwnd)
        expected_width, expected_height = ACTION_WINDOW_PROFILE["client_size"]
        if (rect.width, rect.height) != (expected_width, expected_height):
            raise _ActionProblem(
                f"Unsupported client size {rect.width}x{rect.height}; the action profile requires "
                f"{expected_width}x{expected_height}.",
                details={"observed_client_rect": rect.as_dict()},
            )
        dpi = dpi_for_window(window.hwnd)
        if dpi != int(ACTION_WINDOW_PROFILE["dpi"]):
            raise _ActionProblem(
                f"Unsupported window DPI {dpi}; the action profile requires "
                f"{ACTION_WINDOW_PROFILE['dpi']}.",
                details={"observed_dpi": dpi},
            )
        display = display_geometry()
        if not display.is_single_primary_display:
            raise _ActionProblem(
                "Unsupported multi-display geometry; only one primary display is supported.",
                details={"display": display.as_dict()},
            )
        if (
            display.effective_dpi_x != int(ACTION_WINDOW_PROFILE["dpi"])
            or display.effective_dpi_y != int(ACTION_WINDOW_PROFILE["dpi"])
        ):
            raise _ActionProblem(
                "Unsupported primary display scaling; the action profile requires 96 DPI.",
                details={"display": display.as_dict()},
            )
        return _TargetContext(process, identity, window, rect, dpi, display)

    @staticmethod
    def _context_record(context: _TargetContext) -> dict[str, Any]:
        return {
            **context.identity.as_dict(),
            "hwnd": context.window.hwnd,
            "window_visible": context.window.visible,
            "window_enabled": context.window.enabled,
            "client_rect": context.rect.as_dict(),
            "dpi": context.dpi,
            "display": context.display.as_dict(),
        }

    def _capture_for_target(self, context: _TargetContext) -> Mapping[str, Any]:
        state = self._state_reader()
        if not isinstance(state, Mapping):
            raise _StateUnavailable("State reader returned a non-object sample.")
        source = state.get("source")
        if not isinstance(source, Mapping):
            raise _StateUnavailable("State sample has no target identity; stopping without another action.")
        source_path = source.get("executable_path")
        source_hash = source.get("sha256", source.get("exe_sha256"))
        same = (
            source.get("pid") == context.process.pid
            and isinstance(source_path, str)
            and _normalized_path(source_path) == _normalized_path(context.identity.executable_path)
            and source.get("file_version") == context.identity.file_version
            and source.get("pe_machine") == context.identity.pe_machine
            and str(source_hash or "").upper() == context.identity.sha256.upper()
        )
        if not same:
            raise _StateUnavailable(
                "State sample PID or executable identity changed; stopping without further input.",
                details={"observed_source": dict(source)},
            )
        self._latest_state = state
        return state

    def _send_left_click(
        self,
        context: _TargetContext,
        client_point: tuple[float, float],
        label: str,
        click_log: list[dict[str, Any]],
    ) -> None:
        fresh = self._target_context()
        if fresh.process.pid != context.process.pid or fresh.window.hwnd != context.window.hwnd:
            raise _ActionProblem("Target PID or HWND changed before input; no further input was sent.")

        x, y = float(client_point[0]), float(client_point[1])
        rect = client_rect(fresh.window.hwnd)
        if not (math.isfinite(x) and math.isfinite(y) and 0 <= x < rect.width and 0 <= y < rect.height):
            raise _ActionProblem(f"{label} maps outside the supported client area; no input was sent.")
        client_x, client_y = int(round(x)), int(round(y))
        if client_x > 0x7FFF or client_y > 0x7FFF:
            raise _ActionProblem(f"{label} exceeds the supported client-message coordinate range.")
        click = {
            "label": label,
            "client_point": [x, y],
            "hwnd": fresh.window.hwnd,
            "delivery": "targeted_window_messages",
            "status": "pending",
        }
        click_log.append(click)
        try:
            delivery = self._post_background_click(fresh.window.hwnd, client_x, client_y)
        except Exception as exc:
            click["status"] = "uncertain"
            click["error"] = str(exc)
            raise _InputDeliveryError(
                f"Background mouse-message delivery for {label} could not be confirmed.",
                uncertain=True,
                details={"input_delivery_error": str(exc)},
            ) from exc
        click.update(delivery)
        if delivery["messages_posted"] != 3:
            sent = int(delivery["messages_posted"])
            click["status"] = "uncertain" if sent > 0 else "rejected"
            raise _InputDeliveryError(
                f"Posted {sent} of 3 background mouse messages for {label}; the request was not retried.",
                uncertain=sent > 0,
                details={
                    "background_messages_posted": sent,
                    "background_messages_requested": 3,
                    "mouse_release_cleanup_posted": delivery.get("mouse_release_cleanup_posted"),
                    "winerror": delivery.get("winerror"),
                },
            )
        click["status"] = "sent"

    @staticmethod
    def _post_background_click(hwnd: int, x: int, y: int) -> dict[str, Any]:
        if os.name != "nt":
            raise OSError("Targeted window messages are available only on Windows.")
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        post_message = user32.PostMessageW
        post_message.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)
        post_message.restype = ctypes.c_int
        lparam = ((y & 0xFFFF) << 16) | (x & 0xFFFF)
        messages = (
            (0x0200, 0, lparam),       # WM_MOUSEMOVE
            (0x0201, 0x0001, lparam),  # WM_LBUTTONDOWN / MK_LBUTTON
            (0x0202, 0, lparam),       # WM_LBUTTONUP
        )
        posted = 0
        button_down_posted = False
        for message, wparam, packed_point in messages:
            ctypes.set_last_error(0)
            if not post_message(ctypes.c_void_p(int(hwnd)), message, wparam, packed_point):
                error = ctypes.get_last_error()
                cleanup_posted = False
                if button_down_posted:
                    cleanup_posted = bool(
                        post_message(ctypes.c_void_p(int(hwnd)), 0x0202, 0, packed_point)
                    )
                return {
                    "messages_posted": posted,
                    "failed_message": message,
                    "winerror": error,
                    "mouse_release_cleanup_posted": cleanup_posted,
                }
            posted += 1
            if message == 0x0201:
                button_down_posted = True
        return {"messages_posted": posted, "mouse_release_cleanup_posted": False}

    def _execute_place(
        self,
        request: Mapping[str, Any],
        context: _TargetContext,
        initial: Mapping[str, Any],
        click_log: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any], bool]:
        slot = int(request["card_slot"])
        row, col = int(request["row"]), int(request["col"])
        before_ids = self._plant_ids(initial)
        cell_before = self._cell_ids(initial, row, col)
        before_summary = self._summarize_state(initial, request)
        self._current_before = before_summary
        if before_ids is None or cell_before is None:
            raise _ActionProblem("Plant State is unavailable or has unresolved plant IDs; no input was sent.")

        card_profile = ACTION_WINDOW_PROFILE["card_slots"]
        first_x, card_y = card_profile["first_center"]
        card_point = (
            float(first_x) + (slot - 1) * float(card_profile["horizontal_spacing"]),
            float(card_y),
        )
        lawn = ACTION_WINDOW_PROFILE["lawn"]
        first_x, first_y = lawn["first_cell_center"]
        cell_point = (
            float(first_x) + col * float(lawn["horizontal_spacing"]),
            float(first_y) + row * float(lawn["vertical_spacing"]),
        )
        self._send_left_click(context, card_point, "card selection", click_log)
        # Process identity and HWND are checked again after card selection.
        self._send_left_click(context, cell_point, "lawn cell", click_log)

        def evaluate(state: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
            after_ids = self._plant_ids(state)
            cell_after = self._cell_ids(state, row, col)
            if after_ids is None or cell_after is None:
                return "pending", {"reason": "plant State unavailable"}
            new_ids = sorted(cell_after - cell_before)
            new_global_ids = sorted(after_ids - before_ids)
            confirmed = [plant_id for plant_id in new_ids if plant_id in new_global_ids]
            if len(confirmed) == 1:
                return "met", {"new_plant_ids": confirmed, "cell_plant_ids": sorted(cell_after)}
            if len(confirmed) > 1:
                return "ambiguous", {
                    "new_plant_ids": confirmed,
                    "cell_plant_ids": sorted(cell_after),
                    "reason": "more than one new plant ID appeared in the requested cell",
                }
            return "pending", {
                "new_plant_ids": new_ids,
                "cell_plant_ids": sorted(cell_after),
                "reason": "no new plant ID confirmed in the requested cell",
            }

        after_state, outcome, wait_details = self._wait_for_postcondition(
            context, request, evaluate
        )
        details = {
            "target_cell": {"row": row, "col": col},
            "postcondition": "a new plant ID appears in the requested cell",
            "postcondition_result": outcome,
            **wait_details,
        }
        return before_summary, self._summarize_state(after_state, request), details, outcome == "met"

    def _execute_collect(
        self,
        request: Mapping[str, Any],
        context: _TargetContext,
        initial: Mapping[str, Any],
        click_log: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any], bool]:
        item_id = int(request["item_id"])
        item = self._find_item(initial, item_id)
        if item is None:
            self._current_before = self._summarize_state(initial, request)
            raise _ActionProblem(
                f"Item ID {item_id} is not uniquely present in current State; no input was sent.",
                details={"requested_item_id": item_id},
            )
        before_summary = self._summarize_state(initial, request)
        self._current_before = before_summary
        point, coordinate_evidence = self._resolve_item_point(initial, item)
        self._send_left_click(context, point, "item collection", click_log)

        def evaluate(state: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
            availability = state.get("availability", {})
            items = state.get("items")
            if not isinstance(availability, Mapping) or availability.get("items") not in {"available", "provisional"}:
                return "pending", {"reason": "items State unavailable"}
            if not isinstance(items, list):
                return "pending", {"reason": "items State is not a list"}
            ids = [entry.get("id") for entry in items if isinstance(entry, Mapping)]
            if len(ids) != len(items) or any(not _object_id(value) for value in ids):
                return "pending", {"reason": "item IDs are unresolved"}
            duplicates = len(ids) != len(set(ids))
            if duplicates:
                return "pending", {"reason": "item IDs are ambiguous"}
            still_present = item_id in ids
            return ("pending" if still_present else "met"), {
                "item_id": item_id,
                "same_item_present": still_present,
            }

        after_state, outcome, wait_details = self._wait_for_postcondition(
            context, request, evaluate
        )
        details = {
            "item": coordinate_evidence,
            "postcondition": "the same item ID disappears",
            "postcondition_result": outcome,
            **wait_details,
        }
        return before_summary, self._summarize_state(after_state, request), details, outcome == "met"

    def _execute_shovel(
        self,
        request: Mapping[str, Any],
        context: _TargetContext,
        initial: Mapping[str, Any],
        click_log: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any], bool]:
        row, col = int(request["row"]), int(request["col"])
        before_all = self._plant_ids(initial)
        before_cell = self._cell_ids(initial, row, col)
        if before_all is None or before_cell is None:
            raise _ActionProblem("Plant State is unavailable or has unresolved plant IDs; no input was sent.")
        if not before_cell:
            raise _ActionProblem("Requested cell is already empty; no shovel input was sent.")
        before_summary = self._summarize_state(initial, request)
        self._current_before = before_summary
        point = tuple(float(value) for value in ACTION_WINDOW_PROFILE["shovel_center"])
        self._send_left_click(context, point, "native shovel selection", click_log)
        lawn = ACTION_WINDOW_PROFILE["lawn"]
        first_x, first_y = lawn["first_cell_center"]
        cell_point = (
            float(first_x) + col * float(lawn["horizontal_spacing"]),
            float(first_y) + row * float(lawn["vertical_spacing"]),
        )
        # The shovel and target cell are separate clicks; the exact same HWND
        # must still identify the target window for the second one.
        self._send_left_click(context, cell_point, "lawn cell", click_log)

        def evaluate(state: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
            after_cell = self._cell_ids(state, row, col)
            if after_cell is None:
                return "pending", {"reason": "plant State unavailable"}
            removed = sorted(before_cell - after_cell)
            added = sorted(after_cell - before_cell)
            if removed:
                return "met", {
                    "removed_plant_ids": removed,
                    "remaining_plant_ids": sorted(after_cell),
                    "added_plant_ids": added,
                }
            return "pending", {
                "removed_plant_ids": [],
                "remaining_plant_ids": sorted(after_cell),
                "added_plant_ids": added,
                "reason": "no prior plant ID disappeared from the requested cell",
            }

        after_state, outcome, wait_details = self._wait_for_postcondition(
            context, request, evaluate
        )
        details = {
            "target_cell": {"row": row, "col": col},
            "native_shovel_clicks_per_request": 1,
            "postcondition": "one or more prior plant IDs disappear from the requested cell",
            "postcondition_result": outcome,
            **wait_details,
        }
        return before_summary, self._summarize_state(after_state, request), details, outcome == "met"

    def _wait_for_postcondition(
        self,
        context: _TargetContext,
        request: Mapping[str, Any],
        evaluate: Callable[[Mapping[str, Any]], tuple[str, dict[str, Any]]],
    ) -> tuple[Mapping[str, Any], str, dict[str, Any]]:
        timeout_ms = int(request["timeout_ms"])
        poll_interval_ms = int(request["poll_interval_ms"])
        started = self._clock()
        deadline = started + timeout_ms / 1000
        polls = 0
        last_state: Mapping[str, Any] | None = None
        last_evidence: dict[str, Any] = {}
        while True:
            last_state = self._capture_for_target(context)
            polls += 1
            outcome, last_evidence = evaluate(last_state)
            if outcome in {"met", "ambiguous"}:
                break
            remaining = deadline - self._clock()
            if remaining <= 0:
                break
            self._sleep(min(poll_interval_ms / 1000, remaining))
        assert last_state is not None
        return last_state, outcome, {
            "polls": polls,
            "waited_ms": int((self._clock() - started) * 1000),
            "timeout_ms": timeout_ms,
            "last_observation": last_evidence,
        }

    @staticmethod
    def _plant_ids(state: Mapping[str, Any]) -> set[int] | None:
        availability = state.get("availability", {})
        plants = state.get("plants")
        if (
            not isinstance(availability, Mapping)
            or availability.get("plants") not in {"available", "provisional"}
            or not isinstance(plants, list)
        ):
            return None
        ids: list[int] = []
        for plant in plants:
            if not isinstance(plant, Mapping) or not _object_id(plant.get("id")):
                return None
            ids.append(plant["id"])
        if len(ids) != len(set(ids)):
            return None
        return set(ids)

    @staticmethod
    def _cell_ids(state: Mapping[str, Any], row: int, col: int) -> set[int] | None:
        if ActionExecutor._plant_ids(state) is None:
            return None
        board = state.get("board")
        cells = board.get("cells") if isinstance(board, Mapping) else None
        if not isinstance(cells, list) or len(cells) != 5:
            return None
        if any(not isinstance(line, list) or len(line) != 9 for line in cells):
            return None
        cell = cells[row][col]
        if cell is None:
            return set()
        if not isinstance(cell, Mapping) or not isinstance(cell.get("plants"), list):
            return None
        ids: list[int] = []
        for plant in cell["plants"]:
            if not isinstance(plant, Mapping) or not _object_id(plant.get("id")):
                return None
            ids.append(plant["id"])
        if len(ids) != len(set(ids)):
            return None
        return set(ids)

    @staticmethod
    def _find_item(state: Mapping[str, Any], item_id: int) -> Mapping[str, Any] | None:
        availability = state.get("availability", {})
        items = state.get("items")
        if (
            not isinstance(availability, Mapping)
            or availability.get("items") not in {"available", "provisional"}
            or availability.get("items.position") not in {"available", "provisional"}
            or not isinstance(items, list)
        ):
            return None
        matches = [
            item for item in items
            if isinstance(item, Mapping) and item.get("id") == item_id
        ]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _resolve_item_point(
        state: Mapping[str, Any], item: Mapping[str, Any]
    ) -> tuple[tuple[float, float], dict[str, Any]]:
        profile = ACTION_WINDOW_PROFILE["item_coordinates"]
        interpretation = item.get("coordinate_interpretation")
        x, y = item.get("x"), item.get("y")
        evidence = state.get("evidence", {})
        raw_evidence = ActionExecutor._raw_item_evidence(state, item.get("id"))
        coordinate_evidence = {
            "item_id": item.get("id"),
            "state_coordinates": [x, y],
            "coordinate_interpretation": interpretation,
            "coordinate_evidence_level": evidence.get("items") if isinstance(evidence, Mapping) else None,
            "raw_candidate_evidence": raw_evidence,
        }
        if interpretation not in profile["interpretations"]:
            raise _ActionProblem(
                "Item coordinates are unresolved or ambiguous; no input was sent.",
                details={"item_coordinate_evidence": coordinate_evidence},
            )
        if not (
            isinstance(x, (int, float)) and not isinstance(x, bool)
            and isinstance(y, (int, float)) and not isinstance(y, bool)
            and math.isfinite(float(x)) and math.isfinite(float(y))
        ):
            raise _ActionProblem(
                "Item coordinates are null or non-finite; no input was sent.",
                details={"item_coordinate_evidence": coordinate_evidence},
            )
        origin_x, origin_y = profile["origin"]
        client_x, client_y = float(x) + float(origin_x), float(y) + float(origin_y)
        left, top, right, bottom = profile["bounds"]
        if not (left <= client_x < right and top <= client_y < bottom):
            raise _ActionProblem(
                "Item coordinate mapping falls outside the supported lawn/client region; no input was sent.",
                details={
                    "item_coordinate_evidence": coordinate_evidence,
                    "item_client_point": [client_x, client_y],
                    "item_bounds": [left, top, right, bottom],
                },
            )
        coordinate_evidence.update({
            "item_type_code": item.get("type_code"),
            "item_type_meaning": item.get("type_meaning"),
            "mapping": "direct client pixels per the fixed PvZ 1.0.0.1051 profile",
            "client_point": [client_x, client_y],
        })
        return (client_x, client_y), coordinate_evidence

    @staticmethod
    def _raw_item_evidence(state: Mapping[str, Any], item_id: Any) -> dict[str, Any] | None:
        raw = state.get("raw_snapshot")
        arrays = raw.get("arrays") if isinstance(raw, Mapping) else None
        item_domain = arrays.get("items") if isinstance(arrays, Mapping) else None
        entities = item_domain.get("entities") if isinstance(item_domain, Mapping) else None
        if not isinstance(entities, list):
            return None
        matches = [
            entity for entity in entities
            if isinstance(entity, Mapping) and entity.get("object_id") == item_id
        ]
        if len(matches) != 1:
            return None
        entity = matches[0]
        return {
            "x_i32_candidate": entity.get("x_i32_candidate"),
            "y_i32_candidate": entity.get("y_i32_candidate"),
            "x_f32_candidate": entity.get("x_f32_candidate"),
            "y_f32_candidate": entity.get("y_f32_candidate"),
            "coordinate_interpretation": entity.get("coordinate_interpretation"),
            "coordinate_meaning_status": entity.get("coordinate_meaning_status"),
        }

    def _summarize_state(self, state: Mapping[str, Any] | None, request: Mapping[str, Any]) -> dict[str, Any] | None:
        if not isinstance(state, Mapping):
            return None
        source = state.get("source", {})
        source_summary = {
            key: source.get(key)
            for key in ("pid", "profile", "executable_path", "file_version", "pe_machine", "sha256", "exe_sha256")
        } if isinstance(source, Mapping) else None
        availability = state.get("availability", {})
        evidence = state.get("evidence", {})
        action = request.get("action")
        relevant_availability = {
            "plants": availability.get("plants") if isinstance(availability, Mapping) else None,
            "board.occupancy": availability.get("board.occupancy") if isinstance(availability, Mapping) else None,
        }
        if action == "collect_item":
            relevant_availability.update({
                "items": availability.get("items") if isinstance(availability, Mapping) else None,
                "items.position": availability.get("items.position") if isinstance(availability, Mapping) else None,
            })
        relevant_evidence = {
            key: evidence.get(key)
            for key in ("plants", "items", "cards")
            if isinstance(evidence, Mapping) and key in evidence
        }
        board = state.get("board", {})
        cells = board.get("cells") if isinstance(board, Mapping) else None
        occupied_cell_count = None
        if (
            isinstance(cells, list) and len(cells) == 5
            and all(isinstance(line, list) and len(line) == 9 for line in cells)
            and isinstance(availability, Mapping)
            and availability.get("plants") in {"available", "provisional"}
        ):
            occupied_cell_count = sum(cell is not None for line in cells for cell in line)
        result: dict[str, Any] = {
            "sample_sequence": state.get("sample_sequence"),
            "observed_at_utc": state.get("observed_at_utc"),
            "status": state.get("status"),
            "valid": state.get("valid"),
            "source": source_summary,
            "availability": relevant_availability,
            "evidence": relevant_evidence,
            "board": {
                "rows": board.get("rows") if isinstance(board, Mapping) else None,
                "cols": board.get("cols") if isinstance(board, Mapping) else None,
                "occupied_cell_count": occupied_cell_count,
            },
        }
        if action in {"place_plant", "shovel_cell"}:
            row, col = request.get("row"), request.get("col")
            if _is_int(row) and _is_int(col):
                ids = self._cell_ids(state, row, col)
                valid_cells = (
                    isinstance(cells, list) and len(cells) == 5
                    and all(isinstance(line, list) and len(line) == 9 for line in cells)
                )
                cell = cells[row][col] if valid_cells else None
                plants = cell.get("plants", []) if isinstance(cell, Mapping) else []
                result["target_cell"] = {
                    "row": row,
                    "col": col,
                    "plant_ids": sorted(ids) if ids is not None else None,
                    "plants": [
                        {
                            "id": plant.get("id"),
                            "type_code": plant.get("type_code"),
                            "type_name": plant.get("type_name"),
                            "slot": plant.get("slot"),
                        }
                        for plant in plants if isinstance(plant, Mapping)
                    ] if isinstance(plants, list) else None,
                }
        if action == "collect_item":
            item_id = request.get("item_id")
            items = state.get("items")
            matches = [
                item for item in items
                if isinstance(item, Mapping) and item.get("id") == item_id
            ] if isinstance(items, list) else []
            result["target_item"] = dict(matches[0]) if len(matches) == 1 else None
            if len(matches) == 1:
                result["target_item"]["evidence_level"] = (
                    evidence.get("items") if isinstance(evidence, Mapping) else None
                )
                result["target_item"]["raw_candidate_evidence"] = self._raw_item_evidence(
                    state, item_id
                )
        return result

    @staticmethod
    def _input_may_have_been_sent(click_log: list[dict[str, Any]]) -> bool:
        return any(click.get("status") in {"sent", "uncertain", "pending"} for click in click_log)

    def _result(
        self,
        *,
        status: str,
        action: str | None,
        message: str,
        request: Any,
        started: float,
        started_at: str,
        target: dict[str, Any] | None,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        details: dict[str, Any],
    ) -> ActionResult:
        finished = self._clock()
        return ActionResult(
            status=status,
            action=action,
            message=message,
            request=request,
            target=target,
            before_state=before,
            after_state=after,
            details=details,
            started_at_utc=started_at,
            finished_at_utc=_utc_now(),
            elapsed_ms=max(0, int((finished - started) * 1000)),
        )
