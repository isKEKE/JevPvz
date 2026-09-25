"""Find the one visible PvZ window and map supported client coordinates."""

from __future__ import annotations

import ctypes
import math
from ctypes import wintypes
from dataclasses import asdict, dataclass
from typing import Any

import win32api
import win32gui
import win32process


class TargetWindowError(RuntimeError):
    """Base class for target HWND discovery and geometry failures."""


class TargetWindowNotFoundError(TargetWindowError):
    """Raised when the verified process has no visible, enabled top-level HWND."""


class AmbiguousTargetWindowError(TargetWindowError):
    """Raised when the verified process owns multiple qualifying HWNDs."""


class UnsupportedWindowGeometryError(TargetWindowError):
    """Raised when the live display/window geometry is outside the fixed profile."""


@dataclass(frozen=True)
class TargetWindow:
    hwnd: int
    pid: int
    visible: bool
    enabled: bool

    def as_dict(self) -> dict[str, int | bool]:
        return asdict(self)


@dataclass(frozen=True)
class ClientRect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def as_dict(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class DisplayGeometry:
    x: int
    y: int
    width: int
    height: int
    primary_width: int
    primary_height: int
    effective_dpi_x: int
    effective_dpi_y: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)

    @property
    def is_single_primary_display(self) -> bool:
        return (
            self.x == 0
            and self.y == 0
            and self.width == self.primary_width
            and self.height == self.primary_height
        )


def find_target_window(pid: int) -> TargetWindow:
    """Return the unique visible and enabled top-level HWND owned by ``pid``."""
    matches: list[TargetWindow] = []

    def collect(hwnd: int, _extra: object) -> bool:
        try:
            _thread_id, owner_pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            return True
        if int(owner_pid) != int(pid):
            return True
        try:
            visible = bool(win32gui.IsWindowVisible(hwnd))
            enabled = bool(win32gui.IsWindowEnabled(hwnd))
            if visible and enabled:
                matches.append(
                    TargetWindow(hwnd=int(hwnd), pid=int(owner_pid), visible=visible, enabled=enabled)
                )
        except Exception as exc:
            raise TargetWindowError(
                f"Unable to inspect HWND 0x{int(hwnd):X} owned by target PID {pid}: {exc}"
            ) from exc
        return True

    try:
        win32gui.EnumWindows(collect, None)
    except Exception as exc:
        raise TargetWindowError(f"Unable to enumerate top-level windows: {exc}") from exc

    if not matches:
        raise TargetWindowNotFoundError(
            f"PID {pid} has no visible, enabled top-level window."
        )
    if len(matches) != 1:
        handles = ", ".join(f"0x{item.hwnd:X}" for item in matches)
        raise AmbiguousTargetWindowError(
            f"PID {pid} owns multiple visible, enabled top-level windows: {handles}."
        )
    return matches[0]


def client_rect(hwnd: int) -> ClientRect:
    """Read the current client bounds for ``hwnd``."""
    if not win32gui.IsWindow(int(hwnd)):
        raise TargetWindowError(f"HWND 0x{int(hwnd):X} is no longer a window.")
    try:
        left, top, right, bottom = win32gui.GetClientRect(int(hwnd))
    except Exception as exc:
        raise TargetWindowError(f"Unable to read client rect for HWND 0x{int(hwnd):X}: {exc}") from exc
    rect = ClientRect(int(left), int(top), int(right), int(bottom))
    if rect.width <= 0 or rect.height <= 0:
        raise UnsupportedWindowGeometryError(
            f"HWND 0x{int(hwnd):X} has an empty client rect {rect.as_dict()}."
        )
    return rect


def client_to_screen(hwnd: int, x: float, y: float) -> tuple[int, int]:
    """Map a finite client point through the live HWND."""
    if not (math.isfinite(float(x)) and math.isfinite(float(y))):
        raise UnsupportedWindowGeometryError("Client point must contain finite coordinates.")
    rect = client_rect(hwnd)
    client_x, client_y = int(round(float(x))), int(round(float(y)))
    if not (0 <= client_x < rect.width and 0 <= client_y < rect.height):
        raise UnsupportedWindowGeometryError(
            f"Client point ({x}, {y}) is outside {rect.width}x{rect.height}."
        )
    try:
        screen_x, screen_y = win32gui.ClientToScreen(int(hwnd), (client_x, client_y))
    except Exception as exc:
        raise TargetWindowError(f"Unable to map HWND client point to screen: {exc}") from exc
    return int(screen_x), int(screen_y)


def is_foreground(hwnd: int) -> bool:
    """Return whether this exact HWND currently owns the foreground."""
    try:
        return int(win32gui.GetForegroundWindow() or 0) == int(hwnd)
    except Exception:
        return False


def dpi_for_window(hwnd: int) -> int:
    """Read the HWND's DPI-awareness result; display DPI is checked separately."""
    try:
        function = getattr(win32gui, "GetDpiForWindow", None)
        if function is not None:
            value = int(function(int(hwnd)))
        else:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            function = getattr(user32, "GetDpiForWindow", None)
            if function is None:
                raise TargetWindowError("GetDpiForWindow is unavailable; cannot verify display scaling.")
            function.argtypes = (ctypes.c_void_p,)
            function.restype = ctypes.c_uint
            value = int(function(ctypes.c_void_p(int(hwnd))))
    except TargetWindowError:
        raise
    except Exception as exc:
        raise TargetWindowError(f"Unable to read target window DPI: {exc}") from exc
    if value <= 0:
        raise TargetWindowError("GetDpiForWindow returned an invalid DPI value.")
    return value


def display_geometry() -> DisplayGeometry:
    """Return virtual and primary display dimensions plus effective DPI."""
    try:
        primary_dpi_x, primary_dpi_y = _primary_monitor_dpi()
        result = DisplayGeometry(
            x=int(win32api.GetSystemMetrics(76)),  # SM_XVIRTUALSCREEN
            y=int(win32api.GetSystemMetrics(77)),  # SM_YVIRTUALSCREEN
            width=int(win32api.GetSystemMetrics(78)),  # SM_CXVIRTUALSCREEN
            height=int(win32api.GetSystemMetrics(79)),  # SM_CYVIRTUALSCREEN
            primary_width=int(win32api.GetSystemMetrics(0)),  # SM_CXSCREEN
            primary_height=int(win32api.GetSystemMetrics(1)),  # SM_CYSCREEN
            effective_dpi_x=primary_dpi_x,
            effective_dpi_y=primary_dpi_y,
        )
    except Exception as exc:
        raise TargetWindowError(f"Unable to read display geometry: {exc}") from exc
    if min(result.width, result.height, result.primary_width, result.primary_height) <= 0:
        raise TargetWindowError("Windows returned invalid display dimensions.")
    return result


class _POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def _primary_monitor_dpi() -> tuple[int, int]:
    """Read system-effective DPI under a temporary system-aware thread context.

    GetDpiForMonitor returns 96 for DPI-unaware callers even on scaled displays.
    SetThreadDpiAwarenessContext returns the prior context, which is restored
    before this function returns. Missing APIs or a failed restore are fatal.
    """
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        set_thread_context = user32.SetThreadDpiAwarenessContext
        get_thread_context = getattr(user32, "GetThreadDpiAwarenessContext", None)
        contexts_equal = getattr(user32, "AreDpiAwarenessContextsEqual", None)
        if get_thread_context is None or contexts_equal is None:
            raise TargetWindowError("DPI thread-context verification APIs are unavailable.")
        set_thread_context.argtypes = (ctypes.c_void_p,)
        set_thread_context.restype = ctypes.c_void_p
        get_thread_context.argtypes = ()
        get_thread_context.restype = ctypes.c_void_p
        contexts_equal.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        contexts_equal.restype = wintypes.BOOL
        pointer_mask = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
        system_aware_context = ctypes.c_void_p(pointer_mask - 1)  # DPI_AWARENESS_CONTEXT_SYSTEM_AWARE (-2)
        previous_context = set_thread_context(system_aware_context)
        if not previous_context:
            raise TargetWindowError(
                "SetThreadDpiAwarenessContext could not establish system-aware DPI queries."
            )

        try:
            current_context = get_thread_context()
            if not current_context or not contexts_equal(current_context, system_aware_context):
                raise TargetWindowError("Current thread DPI context is not system-aware after switching.")
            return _query_primary_monitor_dpi(user32)
        finally:
            try:
                restored_context = set_thread_context(ctypes.c_void_p(previous_context))
            except Exception as exc:
                raise TargetWindowError(f"Unable to restore the prior thread DPI context: {exc}") from exc
            if not restored_context:
                raise TargetWindowError("Unable to restore the prior thread DPI context.")
    except TargetWindowError:
        raise
    except Exception as exc:
        raise TargetWindowError(f"Unable to verify primary display scaling: {exc}") from exc


def _query_primary_monitor_dpi(user32: Any) -> tuple[int, int]:
    try:
        monitor_from_point = user32.MonitorFromPoint
        monitor_from_point.argtypes = (_POINT, wintypes.DWORD)
        monitor_from_point.restype = ctypes.c_void_p
        monitor = monitor_from_point(_POINT(0, 0), 1)  # MONITOR_DEFAULTTOPRIMARY
        if not monitor:
            raise TargetWindowError("MonitorFromPoint could not find the primary display.")
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        get_dpi = shcore.GetDpiForMonitor
        get_dpi.argtypes = (
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.POINTER(wintypes.UINT),
            ctypes.POINTER(wintypes.UINT),
        )
        get_dpi.restype = ctypes.c_long
        dpi_x, dpi_y = wintypes.UINT(), wintypes.UINT()
        result = int(get_dpi(monitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)))
        if result != 0:
            raise TargetWindowError(f"GetDpiForMonitor failed with HRESULT 0x{result & 0xFFFFFFFF:08X}.")
        if dpi_x.value <= 0 or dpi_y.value <= 0:
            raise TargetWindowError("GetDpiForMonitor returned invalid DPI values.")
        return int(dpi_x.value), int(dpi_y.value)
    except TargetWindowError:
        raise
    except Exception as exc:
        raise TargetWindowError(f"Unable to read primary display DPI: {exc}") from exc
