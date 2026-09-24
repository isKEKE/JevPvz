"""Read-only remote memory access using ctypes and Win32 APIs."""

from __future__ import annotations

import ctypes
import struct
from ctypes import wintypes
from typing import Protocol, Sequence


PROCESS_VM_READ = 0x0010
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ERROR_INVALID_PARAMETER = 87
STILL_ACTIVE = 259


class MemoryReadError(RuntimeError):
    """Base class for remote memory failures."""


class MemoryAccessError(MemoryReadError):
    """Raised when Windows cannot read a requested remote address."""


class ProcessExitedError(MemoryReadError):
    """Raised when the target process is no longer active."""


class ShortReadError(MemoryReadError):
    """Raised when fewer bytes were copied than requested."""

    def __init__(self, address: int, requested: int, received: int):
        self.address = address
        self.requested = requested
        self.received = received
        super().__init__(
            f"Short read at 0x{address:08X}: requested {requested} byte(s), got {received}."
        )


class NullPointerError(MemoryReadError):
    """Raised when a pointer chain contains a null remote pointer."""

    def __init__(self, pointer_address: int):
        self.pointer_address = pointer_address
        super().__init__(f"Null 32-bit pointer read at 0x{pointer_address:08X}.")


class ClosedMemoryError(MemoryReadError):
    """Raised when a read is attempted after its handle was closed."""


def ensure_process_active(pid: int, exit_code: int) -> None:
    if exit_code != STILL_ACTIVE:
        raise ProcessExitedError(f"PID {pid} exited with code {exit_code} before memory read.")


class MemoryReader(Protocol):
    def read_bytes(self, address: int, size: int) -> bytes: ...

    def read_u32(self, address: int) -> int: ...


class ReadOnlyMemory:
    """Own a PROCESS_VM_READ handle and expose bounded primitive reads."""

    def __init__(self, pid: int):
        if ctypes.sizeof(ctypes.c_void_p) not in (4, 8):
            raise OSError("Unsupported local handle width.")
        self.pid = int(pid)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        self._kernel32.OpenProcess.restype = wintypes.HANDLE
        self._kernel32.ReadProcessMemory.argtypes = (
            wintypes.HANDLE,
            wintypes.LPCVOID,
            wintypes.LPVOID,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        )
        self._kernel32.ReadProcessMemory.restype = wintypes.BOOL
        self._kernel32.GetExitCodeProcess.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        )
        self._kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        self._kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        self._kernel32.CloseHandle.restype = wintypes.BOOL

        self._handle = self._kernel32.OpenProcess(
            PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            self.pid,
        )
        if not self._handle:
            error = ctypes.get_last_error()
            if error == ERROR_INVALID_PARAMETER:
                raise ProcessExitedError(f"PID {self.pid} exited before a read-only handle was opened.")
            raise MemoryAccessError(
                f"OpenProcess read-only failed for PID {self.pid} (WinError {error})."
            )

    def __enter__(self) -> "ReadOnlyMemory":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        handle = getattr(self, "_handle", None)
        if handle:
            self._handle = None
            if not self._kernel32.CloseHandle(handle):
                error = ctypes.get_last_error()
                raise MemoryAccessError(f"CloseHandle failed (WinError {error}).")

    def read_bytes(self, address: int, size: int) -> bytes:
        if not self._handle:
            raise ClosedMemoryError("Read-only process handle is closed.")
        if address <= 0 or size < 0:
            raise ValueError(f"Invalid remote read address/size: 0x{address:X}, {size}.")
        if size == 0:
            return b""

        exit_code = wintypes.DWORD()
        if not self._kernel32.GetExitCodeProcess(self._handle, ctypes.byref(exit_code)):
            error = ctypes.get_last_error()
            raise MemoryAccessError(
                f"Unable to check PID {self.pid} state before reading (WinError {error})."
            )
        ensure_process_active(self.pid, int(exit_code.value))

        buffer = (ctypes.c_ubyte * size)()
        received = ctypes.c_size_t()
        succeeded = self._kernel32.ReadProcessMemory(
            self._handle,
            ctypes.c_void_p(address),
            ctypes.cast(buffer, wintypes.LPVOID),
            size,
            ctypes.byref(received),
        )
        if received.value != size:
            if received.value:
                raise ShortReadError(address, size, int(received.value))
            error = ctypes.get_last_error()
            raise MemoryAccessError(
                f"ReadProcessMemory failed at 0x{address:08X} for {size} byte(s) "
                f"(WinError {error}, success={bool(succeeded)})."
            )
        if not succeeded:
            error = ctypes.get_last_error()
            raise MemoryAccessError(
                f"ReadProcessMemory reported failure at 0x{address:08X} "
                f"(WinError {error})."
            )
        return bytes(buffer)

    def read_u32(self, address: int) -> int:
        return read_u32(self, address)

    def read_i32(self, address: int) -> int:
        return read_i32(self, address)

    def read_f32(self, address: int) -> float:
        return read_f32(self, address)

    def read_ptr32(self, address: int) -> int:
        return self.read_u32(address)


def read_u32(memory: MemoryReader, address: int) -> int:
    return struct.unpack("<I", memory.read_bytes(address, 4))[0]


def read_i32(memory: MemoryReader, address: int) -> int:
    return struct.unpack("<i", memory.read_bytes(address, 4))[0]


def read_f32(memory: MemoryReader, address: int) -> float:
    return struct.unpack("<f", memory.read_bytes(address, 4))[0]


def read_ptr32(memory: MemoryReader, address: int) -> int:
    """Read a four-byte remote pointer, even when this Python process is 64-bit."""
    return memory.read_u32(address)


def follow_ptr32(
    memory: MemoryReader,
    first_pointer_address: int,
    pointer_offsets: Sequence[int] = (),
) -> int:
    """Read a 32-bit pointer and follow each subsequent offset/dereference."""
    pointer = read_ptr32(memory, first_pointer_address)
    if pointer == 0:
        raise NullPointerError(first_pointer_address)
    for offset in pointer_offsets:
        pointer_address = pointer + int(offset)
        pointer = read_ptr32(memory, pointer_address)
        if pointer == 0:
            raise NullPointerError(pointer_address)
    return pointer
