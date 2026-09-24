"""Locate and identify one exact target process using pywin32."""

from __future__ import annotations

import hashlib
import os
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

import win32api
import win32con
import win32process


class ProcessDiscoveryError(RuntimeError):
    """Base class for process lookup and identity errors."""


class TargetNotRunningError(ProcessDiscoveryError):
    """Raised when no process matches the configured executable path."""


class AmbiguousTargetError(ProcessDiscoveryError):
    """Raised when more than one process matches the configured path."""


class IdentityMismatchError(ProcessDiscoveryError):
    """Raised when the executable does not match its pinned identity."""


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    executable_path: str


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    executable_path: str
    file_version: str
    pe_machine: int
    sha256: str

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["pe_machine_hex"] = f"0x{self.pe_machine:04X}"
        return result


def _normalized_path(path: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(path)))


def locate_target_process(executable_path: str | os.PathLike[str]) -> ProcessInfo:
    """Find the unique running process whose main image is at ``executable_path``."""
    expected_path = Path(executable_path).resolve()
    expected_name = expected_path.name.casefold()
    candidates: list[ProcessInfo] = []

    # Module enumeration requires PROCESS_QUERY_INFORMATION and PROCESS_VM_READ.
    # The handle is used only to ask pywin32 for the main module path.
    access = win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ
    for pid in win32process.EnumProcesses():
        if not pid:
            continue
        handle = None
        try:
            handle = win32api.OpenProcess(access, False, pid)
            path = win32process.GetModuleFileNameEx(handle, 0)
        except Exception:
            # Other processes may exit or deny module inspection while we scan.
            continue
        finally:
            if handle is not None:
                try:
                    win32api.CloseHandle(handle)
                except Exception:
                    pass

        if Path(path).name.casefold() == expected_name:
            candidates.append(ProcessInfo(pid=int(pid), executable_path=str(Path(path).resolve())))

    matching = [
        candidate
        for candidate in candidates
        if _normalized_path(candidate.executable_path) == _normalized_path(expected_path)
    ]
    if not matching:
        if candidates:
            found = ", ".join(f"PID {item.pid}: {item.executable_path}" for item in candidates)
            raise TargetNotRunningError(
                f"No {expected_path} process is running; same-name process(es) found at {found}."
            )
        raise TargetNotRunningError(f"No running process found for {expected_path}.")
    if len(matching) != 1:
        pids = ", ".join(str(item.pid) for item in matching)
        raise AmbiguousTargetError(f"Multiple target processes match {expected_path}: PIDs {pids}.")
    return matching[0]


def _file_version(path: Path) -> str:
    info = win32api.GetFileVersionInfo(str(path), "\\")
    version_ms = int(info["FileVersionMS"])
    version_ls = int(info["FileVersionLS"])
    parts = (
        version_ms >> 16,
        version_ms & 0xFFFF,
        version_ls >> 16,
        version_ls & 0xFFFF,
    )
    return ".".join(str(part) for part in parts)


def read_pe_machine(path: str | os.PathLike[str]) -> int:
    """Return the PE COFF Machine value after checking the DOS and PE headers."""
    with Path(path).open("rb") as executable:
        dos_header = executable.read(0x40)
        if len(dos_header) < 0x40 or dos_header[:2] != b"MZ":
            raise IdentityMismatchError(f"{path} is not a valid PE executable (missing MZ header).")
        pe_offset = struct.unpack_from("<I", dos_header, 0x3C)[0]
        if pe_offset > 64 * 1024 * 1024:
            raise IdentityMismatchError(f"{path} has an invalid PE header offset {pe_offset}.")
        executable.seek(pe_offset)
        header = executable.read(6)
    if len(header) != 6 or header[:4] != b"PE\0\0":
        raise IdentityMismatchError(f"{path} is not a valid PE executable (missing PE signature).")
    return struct.unpack_from("<H", header, 4)[0]


def verify_target_identity(
    process: ProcessInfo,
    expected: Mapping[str, object],
) -> ProcessIdentity:
    """Check the process path and pinned on-disk version, PE type, and SHA-256."""
    expected_path = Path(str(expected["path"])).resolve()
    actual_path = Path(process.executable_path).resolve()
    if _normalized_path(actual_path) != _normalized_path(expected_path):
        raise IdentityMismatchError(
            f"Executable path mismatch: expected {expected_path}, got {actual_path}."
        )

    try:
        version = _file_version(actual_path)
        machine = read_pe_machine(actual_path)
        digest = hashlib.sha256(actual_path.read_bytes()).hexdigest().upper()
    except OSError as exc:
        raise IdentityMismatchError(f"Unable to inspect target executable {actual_path}: {exc}") from exc

    expected_version = str(expected["file_version"])
    expected_machine = int(expected["pe_machine"])
    expected_digest = str(expected["sha256"]).upper()
    mismatches: list[str] = []
    if version != expected_version:
        mismatches.append(f"version {version} (expected {expected_version})")
    if machine != expected_machine:
        mismatches.append(f"PE machine 0x{machine:04X} (expected 0x{expected_machine:04X})")
    if digest != expected_digest:
        mismatches.append(f"SHA-256 {digest} (expected {expected_digest})")
    if mismatches:
        raise IdentityMismatchError("Target identity mismatch: " + "; ".join(mismatches))

    return ProcessIdentity(
        pid=process.pid,
        executable_path=str(actual_path),
        file_version=version,
        pe_machine=machine,
        sha256=digest,
    )


def main_module_base(pid: int, expected_path: str | os.PathLike[str] | None = None) -> int:
    """Read the main module base through pywin32's process-module APIs."""
    access = win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ
    handle = None
    try:
        handle = win32api.OpenProcess(access, False, int(pid))
        modules = win32process.EnumProcessModules(handle)
        if not modules:
            raise ProcessDiscoveryError(f"PID {pid} has no enumerated main module.")
        module = modules[0]
        module_path = win32process.GetModuleFileNameEx(handle, module)
        if expected_path is not None and _normalized_path(module_path) != _normalized_path(expected_path):
            raise IdentityMismatchError(
                f"PID {pid} main module path changed: expected {expected_path}, got {module_path}."
            )
        return int(module)
    except ProcessDiscoveryError:
        raise
    except Exception as exc:
        raise ProcessDiscoveryError(f"Unable to inspect main module for PID {pid}: {exc}") from exc
    finally:
        if handle is not None:
            try:
                win32api.CloseHandle(handle)
            except Exception:
                pass
