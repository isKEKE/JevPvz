# Architecture

## Runtime boundaries

- `runtime/` owns generic Windows process discovery, executable identity checks,
  read-only handles, primitive memory reads, and 32-bit pointer chains. It does
  not import PvZ or other business modules.
- `configs/` stores the target executable identity and version-specific module
  relative offsets. Process-specific absolute addresses are never configured.
- `game/` interprets the raw memory layout for PvZ 1.0.0.1051 and retains the
  evidence level of known fields and public offset candidates.
- `state/` will normalize raw reads into a versioned snapshot in P03.
- `dashboard/` will serve the local read-only view in P04.
- The root `main.py` owns the user-facing command entry point.

Dependencies flow from `main.py` to the higher-level reader, then down through
`game/` and `configs/` to `runtime/`. The generic `runtime/` package does not
import the game reader or configuration.

## Read-only boundary

Process discovery and module inspection use pywin32. The remote-memory handle
uses only `PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION`; the only
remote operation is `ReadProcessMemory`. No process write, input, injection, or
hook API is used. Remote pointers are decoded as four-byte x86 addresses even
when Python itself is 64-bit.

## Environment

The project pins Python 3.12.13 in `.python-version` and `pyproject.toml`.
`uv.lock` records the only runtime third-party dependency, `pywin32`. Recreate
the environment with `uv sync`; run one identity and memory probe with
`uv run python main.py probe`.
