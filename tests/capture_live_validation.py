"""Explicit, bounded PvZ live evidence capture; this module never starts the game."""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import struct
import sys
import time
import zlib
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from actions import ActionExecutor
from configs.pvz_1051 import ACTION_WINDOW_PROFILE, TARGET_IDENTITY
from runtime.process import locate_target_process, verify_target_identity
from runtime.window import find_target_window
from state.builder import capture_state

SUN_TYPE_CODES = frozenset({4, 5, 6})
COLLECT_DEADLINE_SECONDS = 10.0
COLLECT_POLL_INTERVAL_SECONDS = 0.2
PRIVATE_ADDRESS_FIELDS = frozenset({"module_base", "root_address", "board_address"})


def _valid_state(state: Any) -> bool:
    return isinstance(state, Mapping) and state.get("status") == "ok" and state.get("valid") is True


def _state_copy(state: Mapping[str, Any]) -> dict[str, Any]:
    """Remove raw memory candidates and other non-JSON implementation details."""
    def sanitize(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {key: sanitize(item) for key, item in value.items()
                    if key != "raw_snapshot" and key not in PRIVATE_ADDRESS_FIELDS}
        if isinstance(value, (list, tuple)):
            return [sanitize(item) for item in value]
        return value
    return sanitize(state)


def _plant_preflight(state: Mapping[str, Any], card_slot: int, row: int, col: int) -> tuple[bool, str, dict[str, Any]]:
    if not _valid_state(state):
        return False, "起始 State 无效；未执行动作。", {}
    if not (1 <= card_slot <= 10 and 0 <= row <= 4 and 0 <= col <= 8):
        return False, "卡槽或目标格超出支持范围；未执行动作。", {}
    availability = state.get("availability", {})
    if not isinstance(availability, Mapping):
        return False, "State 缺少可用性证据；未执行动作。", {}
    if availability.get("plants") not in {"available", "provisional"}:
        return False, "植物/格子状态不可用；未执行动作。", {}
    cells = (state.get("board") or {}).get("cells")
    if not isinstance(cells, list) or len(cells) != 5 or any(not isinstance(line, list) or len(line) != 9 for line in cells):
        return False, "草坪格子结构无效；未执行动作。", {}
    cell = cells[row][col]
    if cell is not None:
        if not isinstance(cell, Mapping) or not isinstance(cell.get("plants"), list) or cell["plants"]:
            return False, "目标格非空或无法确认为空；未执行动作。", {}
    if availability.get("cards") not in {"available", "provisional"}:
        return False, "卡槽状态不可用；未执行动作。", {}
    cards = state.get("cards")
    if not isinstance(cards, list):
        return False, "卡槽列表不可用；未执行动作。", {}
    card = next((item for item in cards if isinstance(item, Mapping) and item.get("slot") == card_slot - 1), None)
    if not card:
        return False, "指定卡槽不存在；未执行动作。", {}
    if availability.get("cards.cost") != "available":
        return False, "当局卡牌费用尚未核验；未执行动作。", {}
    if availability.get("cards.cooldown_ready") != "available":
        return False, "卡牌冷却就绪语义尚未核验；未执行动作。", {}
    if availability.get("cards.usable") != "available" or card.get("usable") is not True:
        return False, "卡槽尚未被核验为可用；未执行动作。", {}
    cost = card.get("cost")
    balance = state.get("sun_balance")
    if not isinstance(cost, int) or isinstance(cost, bool) or not isinstance(balance, int) or isinstance(balance, bool):
        return False, "卡牌费用或阳光余额未知；未执行动作。", {}
    if card.get("cooldown_ready") is not True:
        return False, "卡牌没有已核验的就绪状态；未执行动作。", {}
    if balance < cost:
        return False, "阳光不足；未执行动作。", {}
    return True, "前置检查通过。", {
        "card_slot": card_slot, "row": row, "col": col, "cost": cost,
        "sun_balance": balance, "cooldown_ready": True, "type_code": card.get("type_code"),
    }


def run_plant_scenario(
    *, card_slot: int, row: int, col: int,
    state_reader: Callable[[], Mapping[str, Any]] = capture_state,
    executor: ActionExecutor | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    screenshot: Callable[[], tuple[bytes, Mapping[str, Any]]] | None = None,
) -> tuple[dict[str, Any], bytes | None]:
    before = state_reader()
    accepted, reason, preflight = _plant_preflight(before, card_slot, row, col)
    if not accepted:
        return {"scenario": "plant", "status": "inconclusive", "reason": reason,
                "preflight": preflight, "before_state": _state_copy(before)}, None
    action = (executor or ActionExecutor(state_reader=state_reader)).place_plant(card_slot, row, col)
    sleeper(1.0)
    after = state_reader()
    screenshot_error = None
    try:
        png, window = screenshot() if screenshot else (None, {})
    except Exception as exc:
        png, window, screenshot_error = None, {}, str(exc)
    image_status = "inconclusive" if screenshot and png is None else "captured"
    return {
        "scenario": "plant", "status": image_status,
        "preflight": preflight, "before_state": _state_copy(before),
        "action_result": action.to_dict(), "wait_seconds": 1.0,
        "after_state": _state_copy(after), "window": dict(window),
        "screenshot_error": screenshot_error,
        "plant_confirmed_in_state": _plant_in_cell(after, row, col, preflight.get("type_code")),
        "multimodal_review": "待人工多模态核对截图中的类型和目标格；采集本身不代表通过。",
    }, png


def _plant_in_cell(state: Mapping[str, Any], row: int, col: int, type_code: Any) -> bool | None:
    if not _valid_state(state):
        return None
    if not (
        isinstance(row, int) and not isinstance(row, bool) and 0 <= row < 5
        and isinstance(col, int) and not isinstance(col, bool) and 0 <= col < 9
    ):
        return None
    board = state.get("board")
    if not isinstance(board, Mapping):
        return None
    cells = board.get("cells")
    if (
        not isinstance(cells, list) or len(cells) != 5
        or any(not isinstance(line, list) or len(line) != 9 for line in cells)
    ):
        return None
    cell = cells[row][col]
    if cell is None:
        return False
    if not isinstance(cell, Mapping) or not isinstance(cell.get("plants"), list) or not cell["plants"]:
        return None
    found = False
    for plant in cell["plants"]:
        if (
            not isinstance(plant, Mapping)
            or not isinstance(plant.get("id"), int) or isinstance(plant.get("id"), bool)
            or not isinstance(plant.get("type_code"), int) or isinstance(plant.get("type_code"), bool)
            or not isinstance(plant.get("row"), int) or isinstance(plant.get("row"), bool)
            or not isinstance(plant.get("col"), int) or isinstance(plant.get("col"), bool)
            or plant.get("row") != row or plant.get("col") != col
        ):
            return None
        found = found or plant["type_code"] == type_code
    return found


def _safe_sun_items(state: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    availability = state.get("availability", {})
    if not isinstance(availability, Mapping) or availability.get("items") not in {"available", "provisional"} or availability.get("items.position") not in {"available", "provisional"}:
        return []
    profile = ACTION_WINDOW_PROFILE["item_coordinates"]
    allowed_interpretations = set(profile["interpretations"])
    origin_x, origin_y = profile["origin"]
    left, top, right, bottom = profile["bounds"]
    result = []
    for item in state.get("items", []) if isinstance(state.get("items"), list) else []:
        if not isinstance(item, Mapping) or item.get("type_code") not in SUN_TYPE_CODES:
            continue
        x, y = item.get("x"), item.get("y")
        if item.get("coordinate_interpretation") not in allowed_interpretations:
            continue
        if not (isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))
                and isinstance(y, (int, float)) and not isinstance(y, bool) and math.isfinite(float(y))):
            continue
        client_x, client_y = float(x) + origin_x, float(y) + origin_y
        if left <= client_x < right and top <= client_y < bottom and isinstance(item.get("id"), int) and not isinstance(item.get("id"), bool):
            result.append(item)
    return result


def run_collect_sun_scenario(
    *, state_reader: Callable[[], Mapping[str, Any]] = capture_state,
    executor: ActionExecutor | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    screenshot: Callable[[], tuple[bytes, Mapping[str, Any]]] | None = None,
    duration_seconds: float = COLLECT_DEADLINE_SECONDS,
) -> tuple[dict[str, Any], bytes | None]:
    if duration_seconds != COLLECT_DEADLINE_SECONDS:
        raise ValueError("The approved collect-sun deadline is exactly 10 seconds.")
    start_state = state_reader()
    if not _valid_state(start_state) or not isinstance(start_state.get("sun_balance"), int):
        return {"scenario": "collect-sun", "status": "inconclusive", "reason": "起始 State 或阳光余额无效。",
                "before_state": _state_copy(start_state)}, None
    start = clock()
    deadline = start + COLLECT_DEADLINE_SECONDS
    actions: list[dict[str, Any]] = []
    attempted: set[int] = set()
    last_state: Mapping[str, Any] = start_state
    action_executor = executor or ActionExecutor(state_reader=state_reader)
    poll_deadline = deadline - COLLECT_POLL_INTERVAL_SECONDS
    while clock() < poll_deadline:
        current = state_reader()
        sampled_at = clock()
        if sampled_at >= deadline:
            break
        if not _valid_state(current):
            last_state = current
            break
        last_state = current
        balance = current.get("sun_balance")
        if isinstance(balance, int) and not isinstance(balance, bool) and balance - start_state["sun_balance"] > 50:
            break
        candidate = next((item for item in _safe_sun_items(current) if item["id"] not in attempted), None)
        now = clock()
        action_budget = min(10.0, deadline - now - COLLECT_POLL_INTERVAL_SECONDS)
        if candidate is not None and action_budget >= 0.1:
            attempted.add(candidate["id"])
            timeout_ms = min(10000, int(action_budget * 1000))
            result = action_executor.collect_item(candidate["id"], timeout_ms=timeout_ms)
            actions.append({"item_id": candidate["id"], "type_code": candidate.get("type_code"),
                            "timeout_ms": timeout_ms, "result": result.to_dict()})
        remaining_poll = poll_deadline - clock()
        if remaining_poll > 0:
            sleeper(min(COLLECT_POLL_INTERVAL_SECONDS, remaining_poll))
        if clock() >= deadline:
            break
    final_state = state_reader() if clock() < deadline else None
    if final_state is not None and clock() >= deadline:
        final_state = None
    elapsed = max(0.0, clock() - start)
    screenshot_error = None
    try:
        png, window = screenshot() if screenshot and final_state is not None and clock() < deadline else (None, {})
    except Exception as exc:
        png, window, screenshot_error = None, {}, str(exc)
    after_state = final_state
    balance_before = start_state.get("sun_balance")
    balance_after = after_state.get("sun_balance") if _valid_state(after_state) else None
    delta = balance_after - balance_before if isinstance(balance_after, int) and isinstance(balance_before, int) else None
    action_failure = any(item["result"].get("status") != "success" for item in actions)
    within = elapsed <= COLLECT_DEADLINE_SECONDS and final_state is not None
    status = "success" if within and attempted and delta is not None and delta > 50 and not action_failure else (
        "failed" if within and attempted and delta is not None and delta <= 50 and not action_failure
        else "inconclusive"
    )
    return {
        "scenario": "collect-sun", "status": status,
        "reason": "成功标准是 10 秒内阳光增量严格大于 50；需人工确认期间不存在其他阳光来源。",
        "before_state": _state_copy(start_state),
        "after_state": _state_copy(after_state) if after_state is not None else None,
        "last_observed_state_before_deadline": _state_copy(last_state),
        "sun_balance_before": balance_before, "sun_balance_after": balance_after,
        "sun_balance_delta": delta, "elapsed_seconds": elapsed, "deadline_seconds": COLLECT_DEADLINE_SECONDS,
        "attempted_item_ids": sorted(attempted), "actions": actions,
        "possible_competing_sun_sources": "需人工排除；未自动归因",
        "window": dict(window), "screenshot_error": screenshot_error,
    }, png


def _stable_visible_candidates(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    ignored = {"items", "raw_snapshot", "observed_at_utc", "sample_sequence"}
    return {key: before[key] for key in before.keys() & after.keys()
            if key not in ignored and before[key] == after[key]}


def run_current_scenario(
    *, state_reader: Callable[[], Mapping[str, Any]] = capture_state,
    screenshot: Callable[[], tuple[bytes, Mapping[str, Any]]] | None = None,
) -> tuple[dict[str, Any], bytes | None]:
    before = state_reader()
    if not _valid_state(before):
        return {"scenario": "current", "status": "inconclusive", "reason": "截图前 State 无效。",
                "before_state": _state_copy(before)}, None
    screenshot_error = None
    try:
        png, window = screenshot() if screenshot else (None, {})
    except Exception as exc:
        png, window, screenshot_error = None, {}, str(exc)
    after = state_reader()
    stable = _stable_visible_candidates(before, after) if _valid_state(after) else {}
    status = "captured" if _valid_state(after) and (not screenshot or png is not None) else "inconclusive"
    return {
        "scenario": "current", "status": status,
        "before_state": _state_copy(before), "after_state": _state_copy(after),
        "stable_state_candidates_for_multimodal_review": stable,
        "excluded_fields": ["items", "raw_snapshot", "observed_at_utc", "sample_sequence"],
        "window": dict(window), "screenshot_error": screenshot_error,
        "multimodal_review": "仅核对画面可见字段；逐项记录 match / mismatch / not visible / sample changed。",
    }, png


class LiveTarget:
    def __init__(self) -> None:
        process = locate_target_process(str(TARGET_IDENTITY["path"]))
        identity = verify_target_identity(process, TARGET_IDENTITY)
        window = find_target_window(identity.pid)
        self.hwnd = window.hwnd
        self.identity = {"pid": identity.pid, "profile": "pvz-1.0.0.1051",
                         "file_version": identity.file_version, "window_handle": f"0x{window.hwnd:X}"}

    def screenshot(self) -> tuple[bytes, Mapping[str, Any]]:
        from runtime.window import win32gui, win32process
        if not win32gui.IsWindow(self.hwnd) or not win32gui.IsWindowVisible(self.hwnd) or not win32gui.IsWindowEnabled(self.hwnd):
            raise OSError("The previously verified game HWND is no longer a visible, enabled window.")
        _thread_id, current_pid = win32process.GetWindowThreadProcessId(self.hwnd)
        if int(current_pid) != int(self.identity["pid"]):
            raise OSError("The game HWND changed owner after target verification.")
        return capture_game_window_png(self.hwnd), self.identity


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)


def capture_game_window_png(hwnd: int) -> bytes:
    """Capture the verified HWND client area using Win32 GDI; return PNG bytes."""
    if sys.platform != "win32":
        raise OSError("Game-window screenshot capture is supported only on Windows.")
    from ctypes import wintypes
    user32, gdi32 = ctypes.WinDLL("user32", use_last_error=True), ctypes.WinDLL("gdi32", use_last_error=True)
    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]
    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]
    user32.IsWindow.argtypes = (wintypes.HWND,)
    user32.IsWindow.restype = wintypes.BOOL
    user32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    user32.GetClientRect.restype = wintypes.BOOL
    user32.GetDC.argtypes = (wintypes.HWND,)
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
    user32.ReleaseDC.restype = ctypes.c_int
    user32.PrintWindow.argtypes = (wintypes.HWND, wintypes.HDC, wintypes.UINT)
    user32.PrintWindow.restype = wintypes.BOOL
    gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateDIBSection.argtypes = (wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
                                       ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD)
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = (wintypes.HDC,)
    gdi32.DeleteDC.restype = wintypes.BOOL
    rect = wintypes.RECT()
    if not user32.IsWindow(hwnd) or not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise OSError("Target game HWND is unavailable.")
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise OSError("Target game client area is empty.")
    window_dc = user32.GetDC(hwnd)
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    info = BITMAPINFO()
    info.bmiHeader = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -height, 1, 32, 0, width * height * 4, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    bitmap = gdi32.CreateDIBSection(window_dc, ctypes.byref(info), 0, ctypes.byref(bits), None, 0)
    if not bitmap or not memory_dc:
        raise OSError("Could not create screenshot bitmap.")
    previous = gdi32.SelectObject(memory_dc, bitmap)
    try:
        if not user32.PrintWindow(hwnd, memory_dc, 1):
            raise OSError("PrintWindow could not capture the target game client.")
        raw = ctypes.string_at(bits, width * height * 4)
    finally:
        gdi32.SelectObject(memory_dc, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hwnd, window_dc)
    rows = []
    for y in range(height):
        source = raw[y * width * 4:(y + 1) * width * 4]
        rgba = bytearray()
        for x in range(width):
            b, g, r, _a = source[x * 4:x * 4 + 4]
            rgba.extend((r, g, b, 255))
        rows.append(b"\0" + bytes(rgba))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", header) + _png_chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + _png_chunk(b"IEND", b"")


def write_evidence_bundle(output_dir: Path, record: Mapping[str, Any], png: bytes | None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + f"-{time.time_ns() % 1_000_000_000:09d}"
    png_name = f"pvz-live-{stamp}.png" if png else None
    def sanitize(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): sanitize(item) for key, item in value.items()
                    if key != "raw_snapshot" and str(key) not in PRIVATE_ADDRESS_FIELDS}
        if isinstance(value, (list, tuple)):
            return [sanitize(item) for item in value]
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value
    safe_record = sanitize(record)
    safe_record["captured_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    safe_record["screenshot_file"] = png_name
    if png_name:
        (output_dir / png_name).write_bytes(png)
    target = output_dir / f"pvz-live-{stamp}.json"
    target.write_text(json.dumps(safe_record, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="显式采集 PvZ 实机 State/截图证据，不自动启动游戏。")
    sub = parser.add_subparsers(dest="scenario", required=True)
    plant = sub.add_parser("plant")
    plant.add_argument("--card-slot", type=int, required=True)
    plant.add_argument("--row", type=int, required=True)
    plant.add_argument("--col", type=int, required=True)
    collect = sub.add_parser("collect-sun")
    collect.add_argument("--duration-seconds", type=float, default=COLLECT_DEADLINE_SECONDS)
    current = sub.add_parser("current")
    for command in (plant, collect, current):
        command.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        target = LiveTarget()
        if args.scenario == "plant":
            record, png = run_plant_scenario(card_slot=args.card_slot, row=args.row, col=args.col,
                executor=ActionExecutor(), screenshot=target.screenshot)
        elif args.scenario == "collect-sun":
            record, png = run_collect_sun_scenario(duration_seconds=args.duration_seconds,
                executor=ActionExecutor(), screenshot=target.screenshot)
        else:
            record, png = run_current_scenario(screenshot=target.screenshot)
        record["target"] = target.identity
        path = write_evidence_bundle(args.output_dir, record, png)
        print(json.dumps({"status": record["status"], "evidence_json": str(path),
                          "screenshot": record.get("screenshot_file")}, ensure_ascii=False))
        return 0 if record["status"] in {"captured", "success"} else 3
    except Exception as exc:
        print(f"live validation capture failed closed: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
