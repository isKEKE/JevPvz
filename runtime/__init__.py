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
from .session import (
    IDENTITY_REVERIFY_SECONDS,
    RESOLUTION_REVERIFY_SECONDS,
    TargetSession,
)

__all__ = [
    "AmbiguousTargetError",
    "ClosedMemoryError",
    "IDENTITY_REVERIFY_SECONDS",
    "IdentityMismatchError",
    "MemoryAccessError",
    "NullPointerError",
    "ProcessDiscoveryError",
    "ProcessInfo",
    "ProcessExitedError",
    "RESOLUTION_REVERIFY_SECONDS",
    "ReadOnlyMemory",
    "ShortReadError",
    "TargetNotRunningError",
    "TargetSession",
    "follow_ptr32",
    "locate_target_process",
    "main_module_base",
    "verify_target_identity",
]
