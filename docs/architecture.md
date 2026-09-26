# Architecture

## Runtime boundaries

- `runtime/` owns generic Windows process discovery, executable identity checks,
  read-only handles, primitive memory reads, and 32-bit pointer chains. It does
  not import PvZ or other business modules.
- `configs/` stores the target executable identity and version-specific module
  relative offsets. Process-specific absolute addresses are never configured.
- `game/` interprets the raw memory layout for PvZ 1.0.0.1051 and retains the
  evidence level of known fields and public offset candidates.
- `state/` normalizes raw reads into the schema-v1 State contract and attaches
  availability/evidence to facts and conservative derivations.
- `dashboard/` serves a local read-only lawn dashboard and State observer. Both
  API profiles are derived from the same `StatePoller.latest` sample.
- `actions/` validates one semantic action, maps supported client points through the live HWND, sends guarded system mouse input, and confirms the result with a new State sample.
- The root `main.py` owns the user-facing command entry point.

Dependencies flow from `main.py` to the higher-level reader, then down through
`game/` and `configs/` to `runtime/`. The generic `runtime/` package does not
import the game reader or configuration.

## State contract

The serialized State keeps stable English machine identifiers and numeric
codes. The Dashboard owns Chinese display labels. Unknown codes remain visible
as codes and are not assigned guessed meanings. The zombie `hp` key remains an
alias for `body_hp`; helmet, shield, and balloon HP stay separate, and
`total_hp` is only a sum of known components.

`/api/state` remains the complete All State JSON contract. `/api/jev-state`
projects that same JSON-ready sample through an explicit allowlist: semantic
game fields, sun, a compact 5×9 occupancy board, and decision-facing
plant/zombie/lane/item/card fields. It omits process identity, raw snapshots,
candidate memory blocks, evidence, errors, missing field lists, availability,
and diagnostic aliases. Values not acquired remain `null`; field-level
availability stays in All State. The two routes never sample independently.
`snapshot --profile all|jev` applies the same choice to one CLI sample, with
`all` as the default.

The JEV board keeps a compact 5×9 `cells` matrix for the standard daytime lawn:
`null` means empty and plantable, `false` means not plantable, and
`plant:<type_name>` names the occupying plant. JEV omits the separate `terrain`
and `plantability` fields; if occupancy is invalid or the layout is unsupported,
`cells` is null. All State retains its full board diagnostics.

Within JEV State, per-zombie pixel/grid distances use
`distance_to_house_px` and `distance_to_house_cells`. `lanes[]` contains row,
zombie count, and `nearest_zombie_distance_to_house_cells`; JEV omits the
pixel-lane minimum and `collectible_suns`. Each JEV `items[]` entry includes the
English `type_name` alongside its numeric code and coordinates. All State
retains its original per-zombie distances and per-lane pixel/grid minima.

The `/state` observer defaults to JEV State and can switch to All State. Its
profile label, visible JSON tree, and copy action follow the selected profile;
the tree preserves key order and nesting, and its per-profile expanded paths
survive polling refreshes. A failed request clears the previous tree. Copy
serializes the selected profile data, not the styled DOM.

Card costs are read from the fixed executable's PlantDefinition base table.
Adventure and Normal/Hard Survival use the base price; Endless Survival adds
50 per existing same-type upgrade plant (types 40–44, 46, and 47). Imitater
uses its resolved copied type. A read-only Hard Survival screenshot matched
the visible prices against the table, and the Human confirmed the standard
Adventure/Survival price fields against gameplay. Those costs are available;
Endless upgrade pricing remains provisional until its surcharge event is
confirmed. Other modes and unresolved Imitater prices stay unavailable.

For supported modes, `cooldown_ready` is provisionally derived when the raw
usable byte and counters agree: ready is byte `1` with zero progress; cooling
is byte `0` with positive progress below total. Conflicting states stay null.
The Human confirmed that planting clears readiness and normal recovery restores
it. Resolved cooldown values are available; `usable` is available when its
price and other inputs are available. Contradictory or missing raw states remain
null. Slot-level `usable`
combines supported active gameplay, readiness, known cost, and current sun
balance; it does not describe whether a particular board cell accepts that
plant. For the standard daytime lawn, `distance_to_house_px` uses the Human
calibrated house line at X=0; `distance_to_house_cells` maps X to a 0–8
house-relative column index using the 80px cell pitch. Per-lane summaries
include both minima. The former `progress_to_house` field is removed. Other
backgrounds remain unavailable. `decision_ready` remains false while other
required evidence is missing.

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
