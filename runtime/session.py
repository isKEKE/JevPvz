"""Hold one already verified target process for the lifetime of a sampling session."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from configs.pvz_1051 import TARGET_IDENTITY
from runtime.memory import MemoryAccessError, ProcessExitedError, ReadOnlyMemory
from runtime.process import (
    IdentityMismatchError,
    ProcessDiscoveryError,
    ProcessInfo,
    ProcessIdentity,
    locate_target_process,
    main_module_base,
    verify_target_identity,
)


IDENTITY_REVERIFY_SECONDS = 1.0
RESOLUTION_REVERIFY_SECONDS = 30.0


def utc_now() -> str:
    """Format the current UTC time exactly like ``state/builder.py::_now``."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _default_snapshot_reader(memory: Any, module_base: int) -> dict[str, Any]:
    # Imported lazily: game.reader imports runtime.memory, so a module-level
    # import here would create a cycle when game.reader is loaded first.
    from game.reader import read_raw_snapshot

    return read_raw_snapshot(memory, module_base)


class TargetSession:
    """The holding period of an already verified target process."""

    def __init__(
        self,
        *,
        target_identity: Mapping[str, object] = TARGET_IDENTITY,
        clock: Callable[[], float] = time.monotonic,
        identity_reverify_seconds: float = IDENTITY_REVERIFY_SECONDS,
        resolution_reverify_seconds: float = RESOLUTION_REVERIFY_SECONDS,
        resolver: Callable[[str], ProcessInfo] = locate_target_process,
        verifier: Callable[[ProcessInfo, Mapping[str, object]], ProcessIdentity] = verify_target_identity,
        module_base_reader: Callable[[int, str], int] = main_module_base,
        memory_factory: Callable[[int], Any] = ReadOnlyMemory,
        snapshot_reader: Callable[[Any, int], dict[str, Any]] = _default_snapshot_reader,
    ) -> None:
        self._target_identity = target_identity
        self._clock = clock
        self._identity_reverify_seconds = identity_reverify_seconds
        self._resolution_reverify_seconds = resolution_reverify_seconds
        self._resolver = resolver
        self._verifier = verifier
        self._module_base_reader = module_base_reader
        self._memory_factory = memory_factory
        self._snapshot_reader = snapshot_reader

        self._lock = threading.Lock()
        self._pid: int | None = None
        self._process: ProcessInfo | None = None
        self._identity: ProcessIdentity | None = None
        self._memory: Any = None
        self._resolved_monotonic = 0.0
        self._verified_monotonic = 0.0
        self._identity_verified_at_utc: str | None = None

    @property
    def identity_verified_at_utc(self) -> str | None:
        return self._identity_verified_at_utc

    def _establish(self) -> None:
        path = str(self._target_identity["path"])
        process = self._resolver(path)
        identity = self._verifier(process, self._target_identity)
        memory = self._memory_factory(process.pid)
        now = self._clock()
        self._pid = process.pid
        self._process = process
        self._identity = identity
        self._memory = memory
        self._resolved_monotonic = now
        self._verified_monotonic = now
        self._identity_verified_at_utc = utc_now()

    def read(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return one ``(raw, source)`` sample using the held target handle."""
        with self._lock:
            try:
                if self._memory is None:
                    self._establish()
                pid = self._pid
                path = str(self._target_identity["path"])
                module_base = self._module_base_reader(pid, path)
                now = self._clock()
                if now - self._verified_monotonic >= self._identity_reverify_seconds:
                    self._identity = self._verifier(self._process, self._target_identity)
                    self._verified_monotonic = now
                    self._identity_verified_at_utc = utc_now()
                if now - self._resolved_monotonic >= self._resolution_reverify_seconds:
                    fresh = self._resolver(path)
                    if fresh.pid != pid:
                        raise IdentityMismatchError(
                            f"Target process changed: session holds PID {pid}, "
                            f"resolution returned PID {fresh.pid}."
                        )
                    self._resolved_monotonic = now
                raw = self._snapshot_reader(self._memory, module_base)
            except (ProcessDiscoveryError, ProcessExitedError):
                self.invalidate()
                raise
            source = self._identity.as_dict()  # type: ignore[union-attr]
            source.update(
                {
                    "profile": "pvz-1.0.0.1051",
                    "exe_sha256": self._identity.sha256,  # type: ignore[union-attr]
                    "identity_verified_at_utc": self._identity_verified_at_utc,
                }
            )
            return raw, source

    def _clear(self) -> None:
        self._pid = None
        self._process = None
        self._identity = None
        self._identity_verified_at_utc = None
        self._resolved_monotonic = 0.0
        self._verified_monotonic = 0.0

    def invalidate(self) -> None:
        """Drop the session after an identity/liveness failure, closing best-effort."""
        memory = self._memory
        self._memory = None
        self._clear()
        if memory is not None:
            try:
                memory.close()
            except MemoryAccessError:
                pass

    def close(self) -> None:
        """Close the held handle. Idempotent; may propagate ``MemoryAccessError``."""
        memory = self._memory
        self._memory = None
        self._clear()
        if memory is not None:
            memory.close()
