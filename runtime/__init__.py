"""Read-only Windows process and memory primitives."""

from .memory import (
    ClosedMemoryError,
    MemoryAccessError,
    NullPointerError,
    ProcessExitedError,
    ReadOnlyMemory,
    ShortReadError,
    follow_ptr32,
)
from .process import (
    AmbiguousTargetError,
    IdentityMismatchError,
    ProcessDiscoveryError,
    ProcessInfo,
    TargetNotRunningError,
    locate_target_process,
    main_module_base,
    verify_target_identity,
)

__all__ = [
    "AmbiguousTargetError",
    "ClosedMemoryError",
    "IdentityMismatchError",
    "MemoryAccessError",
    "NullPointerError",
    "ProcessDiscoveryError",
    "ProcessInfo",
    "ProcessExitedError",
    "ReadOnlyMemory",
    "ShortReadError",
    "TargetNotRunningError",
    "follow_ptr32",
    "locate_target_process",
    "main_module_base",
    "verify_target_identity",
]
