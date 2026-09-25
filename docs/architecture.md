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
- `actions/` validates one semantic action, maps supported client points through the live HWND, sends guarded system mouse input, and confirms the result with a new State sample.
- The root `main.py` owns the user-facing command entry point.

Dependencies flow from `main.py` to the higher-level reader, then down through
`game/` and `configs/` to `runtime/`. The generic `runtime/` package does not
import the game reader or configuration.

## Read-only boundary

Process discovery and module inspection use pywin32. The remote-memory handle
uses only `PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION`; the only
remote-memory operation is `ReadProcessMemory`. The `action` command is an
explicit UI boundary: after checking the configured executable identity, the
unique visible/enabled HWND and the supported client profile, it posts mouse
messages directly to that HWND. It does not require foreground focus, activate
the game, or write process memory. It rechecks the same PID, identity and HWND
before every click, including between card/shovel selection and the lawn click.
Remote pointers are decoded as four-byte x86 addresses even when Python itself
is 64-bit.

## Semantic Action flow

`main.py action --action-json <JSON>` accepts exactly one semantic request.
`place_plant` maps a 1-based card slot and 0-based lawn row/column using the
fixed 800×600, 96-DPI profile. It does not gate on candidate cooldown fields;
it waits for a new plant ID in the requested cell.
`collect_item` maps the requested State item ID's resolved pixel candidate
directly into client space and succeeds only when that same ID disappears.
`shovel_cell` selects the native shovel once, clicks the cell once, and reports
the plant IDs that actually disappeared. A caller must submit another request
to remove another layer.

Every action result includes `rejected`, `success`, or `unverified`, target
PID/HWND/profile details, compact before/after State evidence, sample sequence,
click points, and the bounded wait result. The default post-click wait is
10000 ms and can be configured up to 120000 ms. Plant placement does not use a
separate card cooldown/readiness gate. There is no automatic input retry. Candidate or
unresolved card/item evidence, changed identity, ambiguous HWND or unsupported
window size/DPI/display fails closed. Primary-display effective
DPI is queried while the calling thread temporarily uses the system-aware DPI
context; the prior context is restored even on query failure, and an unavailable
context switch or restore fails closed. The separate HWND DPI value is not used
alone to detect scaling because an unaware window reports 96 DPI. This is not
an HTTP write endpoint and the executor does not choose plant types, inspect sun
balance or cost, start the game, or change foreground focus.

## Environment

The project pins Python 3.12.13 in `.python-version` and `pyproject.toml`.
`uv.lock` records the only runtime third-party dependency, `pywin32`. Recreate
the environment with `uv sync`; run one identity and memory probe with
`uv run python main.py probe`.
