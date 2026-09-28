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
  API profiles are derived from the same `StatePoller.latest` sample. Its JEV
  Trace route reads only the file the server was started with, and understands
  both the schema-1 legacy cycle trace and the schema-2 runtime trace.
- `jev/` owns the asynchronous JEV runtime: the observation loop, the layered
  strategy signals, the typed question/merge layer, the single dispatch
  scheduler, and the versioned Trace event contract.
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
backgrounds remain unavailable.

`decision_ready` is true only when the State is valid with `status == "ok"`,
the game is playing and unpaused, the JEV projection contains a valid 5×9
decision board, and the required game, sun, board, card, plant, zombie, lane,
and item fields have `available` or `provisional` evidence. A required field
with `unavailable` or `error` evidence, a missing value, or malformed projected
structure keeps the gate false. Evidence-backed empty entity arrays are valid;
the gate means JEV may decide, not that any particular action will pass the
ActionBoundary.

## Capture session and identity guarantee

State capture holds one already verified target process for the lifetime of a
sampling session instead of re-discovering and fully re-verifying it on every
sample. At establishment the session resolves the target process and runs the
full executable identity check once, then keeps the read-only process handle
open for the whole session.

Per sample the session only repeats the cheap guard: target liveness, the main
module path still matching the locked executable, and `main_module_base` for
the current module base. This replaces per-sample process enumeration and
on-disk SHA-256 hashing. Two independent re-verification cycles run against the
held handle: the disk identity is re-verified every 1.0 s, and process
uniqueness is re-resolved every 30.0 s. Because uniqueness is re-checked only
on that 30.0 s cycle, a second same-name/same-path process is detected within a
window of at most 30 s; for the rest of the window the session keeps operating
on the originally verified instance.

Holding the handle makes PID reuse structurally impossible: memory reads always
target the process that was verified at establishment. Process exit is still
detected, through the guard and the `GetExitCodeProcess` check that real memory
reads already perform. Identity/liveness failures fail the current sample and
drop the session, so the next sample re-resolves from scratch; data-read
failures leave the session and its identity intact.

`source.identity_verified_at_utc` records the time of the most recent
*successful* verification, in UTC with millisecond precision. It names when the
held identity was last confirmed; it does **not** claim that the sample itself
was verified at capture time, and `source.pid`/`source.exe_sha256` likewise no
longer imply per-sample verification. A connection-unavailable sample carries
no `identity_verified_at_utc`. The field is deliberately excluded from both the
JEV projection and the Trace, so their existing contracts are unchanged.

## JEV runtime loop

`jev/` is the asynchronous decision runtime. Responsibilities are split so every
layer has one job:

- **Observation** (`jev/loop.py`): one Observer task captures one All/JEV State
  pair after another on a controlled worker thread, projects it, and publishes
  the newest immutable pair through `SnapshotStore`. Continuous observation is
  the default; `--interval-ms` only paces the *start* of an observation and never
  paces JEV requests or the network timeout. Only the newest pair is kept, and a
  pair is usable for a decision job only while `decision_ready` is true and its
  age is inside the recorded limit.
- **Decision**: the collect worker sends one shared request with independent
  collection Noul (only when there are collectable items), construction intent
  (keep/replace/cancel), and next construction type answers. Empty items still
  permit the management questions.
  Inputs contain actual counts, budget/cards, board, plants, zombies, per-lane
  observed counts and distances, per-lane own-side composition
  (`lane_composition`: `resource`/`attacker`/`defender` counts per row, explicit
  rows at zero, `null` when plants are unknown), the board's factual column
  direction (`house_side_col` 0, `zombie_side_col` = highest column, matching the
  executor's `first_cell_center + col * horizontal_spacing` geometry),
  `cards[].role` from the catalog (`null` when unknown), waves guarded by matching
  All State availability,
  catalog capabilities, current model intent and the last actual action result.
  These are facts and semantics only: no prescribed lineup, economic size, layout,
  column recommendation, quota, phase policy or ideal deficit is supplied.
  Items contain only type_code/type_name/count; identity stays local.
  A positive collection gate authorizes all valid IDs frozen from that source
  sample, consumed serially; new IDs require another answer. An affirmative answer
  that arrives while a batch is still being consumed is held as the single latest
  unauthorized batch (a later answer replaces it and the replaced one is recorded),
  then started when the active batch ends under the same 5 s authorization window
  measured from the moment it was accepted -- never renewed by queueing -- and
  discarded with a recorded reason if it is already past it. The collection gate
  is the reviewable fixed anchor ``COLLECT_ACT_THRESHOLD = 0.5`` in
  ``jev/questions.py``, decoupled from the P02 ``JEV_NOUL_CANDIDATE_THRESHOLD``.
  Plant decisions ask only a complete legal placement Choice: the model's own
  discard option expresses waiting (strictly only when its probability beats the
  discard option), there is no absolute plant gate, and the selected option is
  taken by argmax with no local lane reranking. The declared construction goal is
  context, not an authorization premise: it never filters the hand down to one
  type, and it limits the offered placements only through `economy` -- while the
  goal still needs sun and no lane is at `medium` urgency or higher (or holds a
  zombie with nothing able to attack it), the branch waits locally with
  `await_plan`; once the goal is payable it offers that goal's placements plus
  every card the balance above the goal's own price can pay for. `economy` states
  the balance band against this hand's own prices
  (`scarce`/`normal`/`comfortable`/`abundant`), the goal's cost and shortfall, and
  `sun_above_plan`. At `wave == 0` the pre-level
  zombie transient is excluded from the PlantBranch change key (a missing or
  malformed wave stays conservative), while the zombie facts still reach the
  model.
- **Scheduling**: the existing two workers share one non-preemptible executor.
  Urgency is mechanical: plant proposals are low priority and ready actions run
  FIFO otherwise.
  Source domain, intent content version, target, current actual resources,
  identity, stop and TTL are checked before dispatch. Invalid/stale proposals
  are rejected without substituting another model target. Intent is context,
  never standalone action authorization. No income is forecast; the only
  reservation is the declared goal's own price, and it only bounds the offered
  placements as described above.
  A collect request carries its own bounded confirmation budget
  (`COLLECT_CONFIRMATION_TIMEOUT_MS = 2500` in `jev/scheduler.py`), because an
  unconfirmed collect click holds the only executor until its wait elapses;
  plant and shovel requests keep the executor's own default.
- **Execution** (`actions/`): the unchanged `ActionBoundary` performs one complete
  input transaction (select -> click -> confirm) and returns an `ActionResult`.

Late answers are voided by source pair, not by the clock: a stop or identity
change bumps the epoch and invalidates every in-flight job and pending proposal,
and a job whose branch key changed while it was in flight is superseded and
rebuilt from the newest pair. A rising `sample_sequence` alone never expires a
result; only an unchanged key past the recorded deadline does.

### Trace schema

The runtime writes a **schema-2** JSONL trace with one writer and a monotonic
`event_sequence`: `job_start`, `request_result`, `proposal_discarded`,
`action_result`, `job_end`, and `runtime_stop`, linked by
`job_id`/`stage_id`/`request_id`/`execution_id`/`branch_id`. A job's group
records the age of the source sample, the API latency, the queue delay, the
wait/discard reason, and the actual shared request input. Collection records its
single Noul and authorized count; management records keep/replace/cancel and
construction type. Plant records the offered
placement distribution, the selected option without reranking, and its
``best_option``/``best_probability``/``discard_probability``/``margin`` facts.
Model intent content versions and source job links connect these decisions to
actual executions. The per-lane/economy Noul gates and the collected
``needed_rows``/reranking fields are historical records: they are no longer part
of any runtime question set and no longer act as policy. Target Choice uses
argmax without a per-entry confidence threshold on the path. Every job writes a bounded group rather than one record per observation,
and the trace never contains the raw All State, a raw SDK response, credentials,
or any reserved or predicted income. `job_end` follows decision-completion order
while `action_result` follows the actual execution order. The Dashboard no longer
renders those two orders as lists: the Runtime page shows one point per option of
the latest request for each question and lights only the options that a
successful same-job game action proved executed. Schema-1 legacy cycle files stay readable and are validated
against their own shape, so an old cycle record is never presented as a
concurrent branch event.

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
directly into client space and succeeds only when that same ID disappears. A
candidate outside the configured item region (x and y from 40 client points in the
fixed 800×600 profile, so the left half of the first lawn column and an item still
falling through the top of the client area both stay clickable) is rejected with
its resolved point and the region bounds as evidence, and no input is sent.
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
`uv.lock` records `pywin32` for Windows access, `python-dotenv` for environment
loading, and `typesafe-sdk` for typed asynchronous JEV requests, together with
the SDK dependencies. Recreate
the environment with `uv sync`; run one identity and memory probe with
`uv run python main.py probe`.
