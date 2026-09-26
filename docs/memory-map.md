# PvZ 1.0.0.1051 memory map

This file separates user supplied/known offsets from public reverse-engineering
candidates and records only the evidence collected from the current target
process. `observed_once` means one paused-frame read; it does not establish
dynamic meaning. `verified_with_gameplay` is reserved for event-before/after
evidence from a game the user played.

## Target identity

| Field | Configured value | Evidence |
|---|---|---|
| Executable | `.game/PlantsVsZombies.exe` | Module-relative path under the repository |
| File version | `1.0.0.1051` | Read from the executable version resource |
| PE Machine | `0x014C` (x86) | Read from the PE COFF header |
| SHA-256 | `F587903E9C3AD3890C1F4E2FBC1FE1EA88BD191E3D623D6F291283F6658C8DD4` | Pinned target identity |
| Board chain | `module + 0x2A9EC0` → pointer, then `root + 0x768` → Board | User reported and re-read in the paused process |

## User supplied fields

All addresses below are relative to the resolved Board. Counts and alive-slot
rules are reported independently. The array scan checks the object ID high word
for a nonzero value through `max_used`; one paused sample cannot validate slot
reuse or removal behavior.

| Domain | Board field(s) | Layout | Evidence level | Current interpretation |
|---|---|---|---|---|
| Sun balance | `+0x5560` | `u32` | `observed_once` per probe | Direct balance candidate; compare with the visible counter |
| Zombies | header `+0x90`, stride `0x15C`; row `+0x1C`, type `+0x24`, X/Y `+0x2C/+0x30`, body HP `+0xC8`, helmet HP `+0xD0`, shield HP `+0xDC`, balloon HP `+0xE4`, ID `+0x158` | row/type/HP parts `i32` raw; X/Y `f32` | `observed_once` | Each HP part stays separate; State keeps legacy `hp` as body HP and reports a nullable parts sum for reference |
| Plants | header `+0xAC`, stride `0x14C`; row `+0x1C`, type `+0x24`, column `+0x28`, ID `+0x148` | `u32` raw | `observed_once` | Row/column are zero based; dynamic add/remove remains unverified |
| Items | header `+0xE4`, stride `0xD8`; X/Y `+0x24/+0x28`, type `+0x58`, collect flag `+0x50`, ID `+0xD0` | X/Y recorded as both `i32` and `f32` candidates | `observed_once` | Type codes 4/5/6 and coordinate kind stay candidates; items are not all called sun |

The DataArray header candidate layout is data pointer `+0x00`, `max_used` `+0x04`,
capacity `+0x08`, free-list head `+0x0C`, and live count `+0x10`. The scan rejects
`live_count > max_used`, `max_used > capacity`, and nonempty arrays with null
data pointers. Header `+0x04` is treated as a high-water bound, not the live
count.

## Public candidates

These addresses follow the public [PvZLib 1.0.0.1051 header](https://github.com/HenryJk/PvZLib/blob/main/include/pvz_reference/1_0_0_1051_en.h),
[Board structure notes](https://github.com/Electr0Gunner/PvZ-Reconstruction-BugFix/blob/main/Lawn/Board.h),
[SeedPacket layout](https://github.com/Electr0Gunner/PvZ-Reconstruction-BugFix/blob/main/Lawn/SeedPacket.h),
[Coin layout](https://github.com/Electr0Gunner/PvZ-Reconstruction-BugFix/blob/main/Lawn/Coin.h),
and [enumerations](https://github.com/Electr0Gunner/PvZ-Reconstruction-BugFix/blob/main/ConstEnums.h).
The sources are third-party reconstruction material, not a binary-layout
guarantee for this exact executable.

| Domain | Candidate address/layout | Captured evidence | Status |
|---|---|---|---|
| Scene/mode | `Root+0x7FC` scene, `Root+0x7F8` mode | Raw `u32` codes retained; known enum codes get names | `observed_once`, `provisional` | Unknown codes remain numeric; menu/loading/credits scenes suppress Board-only progress |
| Background/progress | `Board+0x554C` background, `+0x5550` level, `+0x5564` total waves, `+0x557C` spawned waves | Raw `u32` values retained; Adventure level `1..50` is labeled `1-N`; other modes keep the raw number | `observed_once`, `provisional` | `mCurrentWave` is shown as waves generated, not currently alive zombies |
| Pause/level complete | `Board+0x164`, `Board+0x55FC` | Each flag reads exactly one byte; State accepts only `0` or `1` | `observed_once`, `provisional` | A single frame does not establish pause/completion transitions |
| Seed bank | pointer `Board+0x144`; slot count `SeedBank+0x24`; inline slots at `+0x28`, stride `0x50` | Reads card type/imitator, raw cooldown counters and byte-sized usable flag; emits provisional `cooldown_ready` and slot-level `usable` when raw values agree | Full normal cooldown recovery is not captured; contradictory/boundary states remain null |
| Terrain | bytes at `Board+0x168`, candidate 6×9 shape | Raw bytes retained without decoding | Cell type and direction unavailable |
| Items | coordinate candidates `i32/f32` at `+0x24/+0x28`; type at `+0x58`; type 4/5/6 as sun candidates | Raw values retained per item; name mapped through static CoinType table | Type and pixel interpretation remain provisional/candidate |
| Card cost | `PlantDefinition` table at `module_base + 0x29F2B0`, stride `0x24`, type `+0x00`, cost `+0x10` | Reads the live base price, applies standard-mode pricing rules, and uses the copied plant type for Imitater | Price evidence is provisional until supported-mode price transitions are fully compared |

Plant names and static prices come from the reconstructed [plant definitions](https://github.com/ruslan831/PlantsVsZombies-decompilation/blob/master/Lawn/Plant.cpp).
Zombie names are mapped from the [ZombieType enumeration](https://github.com/Patoke/re-plants-vs-zombies/blob/main/ConstEnums.h).
Item names are mapped from the same source's `CoinType` enumeration; type 4 is a sun candidate and type 1 a silver coin candidate.
Unknown type IDs keep their raw codes and receive no invented name or price.

## Earlier baseline probe (2026-09-23)

One read-only sample was captured at **2026-09-23T16:38:59.767+00:00**
(2026-09-24 00:38:59.767 Asia/Shanghai). The process was PID **26120** at the
configured `.game/PlantsVsZombies.exe` path. It matched version **1.0.0.1051**,
PE Machine **0x014C**, and the pinned SHA-256. The module base was `0x00400000`,
Root `0x027CA3C0`, and Board `0x16F67D20`. These absolute addresses belong only
to this sample; runtime configuration stores the module RVA and pointer chain.

| Readout | Raw sample | Evidence/status |
|---|---|---|
| Sun | `3333` | `observed_once`; same value as the paused-scene reference |
| Plant array | live `2`, max-used `2`, capacity `1024`; slot 0 type `1`, row 0, column 3, ID `0xDC610000`; slot 1 type `29`, row 2, column 3, ID `0xDC620001` | ID-high-word filter returned 2/2; one-frame provisional |
| Zombie array | live `1`, max-used `10`, capacity `1024`; slot 9 type `0`, row 2, X `687.00946`, Y `250.0`, HP `270`, ID `0xDF6D0009` | ID-high-word filter returned 1/1; X/Y `f32` and HP meanings have not been tested across events |
| Item array | live `1`, max-used `1`, capacity `1024`; slot 0 type `4`, X `551.0`, Y `448.0`, ID `0xDF6C0000`, collecting raw `0` | f32 coordinates are the plausible pixel candidate; type and collection meanings remain unknown/candidate |
| SeedBank | candidate address `0x16AD3520`, slot count `10`; slot types `[35,5,29,7,40,41,1,23,20,22]` | Count observed once; card type/cooldown/usable meanings remain candidate |
| Scene/progress | Root scene raw `3`, mode raw `0`; pause raw `1`, level raw `3`, total waves raw `20`, current wave raw `1`, won raw `4284372992` | Candidate values only; no scene, level, wave, or pause transition was observed |
| Terrain | Board `+0x168` at `0x16F67E88`, 54 raw bytes: `010000000100000001000000010000000100000002000000010000000100000001000000010000000100000002000000010000000100` | Candidate address/shape only; bytes and row/column direction are not decoded |

This sample was collected while the process was paused, without sending input or
writing memory. The pause value shown here is a four-byte pre-fix read and is
retained as historical evidence for the width bug; current reads take one byte.
It does not verify movement, damage, cooldown progression, collection, slot
reuse, or progress transitions. An item with type code 4 is labeled as a sun
candidate; collection eligibility is not asserted until the type offset and
item behavior are validated. The captured screenshot remains a scene reference
and was not treated as this probe's raw-data source.

## 2026-09-24 implementation sample

A read-only capture at `2026-09-24T05:09:42.675+00:00` was normalized from the
same raw snapshot. Raw scene/mode/background/level/waves/pause/complete values
were `3/1/0/0/9/10/1/0`; State labeled these as playing, normal Survival Stage
1, daytime, raw level `0`, 9 generated waves out of 10, paused, and not level
complete. The raw flag values were one byte each. Every progress field remains
`provisional` with `observed_once` evidence.

In that sample, zombie slot 2 had body HP `218`, helmet HP `0`, shield HP
`1048`, and balloon HP `0`; State preserved `hp=218` and reported a parts sum of
`1266`. A localhost `/api/state` response on the updated server exposed the
same decoded fields and raw snapshot. Its sample included a shielded zombie at
body HP `270` plus shield HP `1100`, for a parts sum of `1370`. The page and
`/static/app.js` both returned HTTP 200 with the updated renderer. The API
snapshot's overall status was `error` because the existing plant reader found
two plants at row 0, column 6; progress and zombie HP availability remained
`provisional`. The old server on port 8765 still returned the pre-fix `root`
field and four-byte pause value, so the check used a second port and left that
process untouched. A second same-capture raw/State check at
`2026-09-24T05:12:08.880+00:00` found a type-4 bucket zombie with body HP `270`,
helmet HP `1100`, and parts sum `1370` in both layers.

## P01 State contract update (2026-09-25)

The normalized State uses English identifiers for plant, zombie, item, scene,
mode, and background values. The Dashboard translates known identifiers by
numeric code for Chinese display; unknown codes retain their numeric code and
show a Chinese unknown label. `hp` remains the body HP compatibility alias;
`total_hp` is a reference sum only when every component was read.

Card cost reads each selected plant's `PlantDefinition` base cost from
`module_base + 0x29F2B0 + type_code * 0x24 + 0x10`, after checking the adjacent
type code. Adventure and Normal/Hard Survival use the base price. Endless
Survival stages 1–5 add 50 per existing same-type plant for upgrade plants
(types 40–44, 46, and 47). Imitater uses its resolved copied type. A read-only
Hard Survival screenshot and State captured on 2026-09-26 showed all ten visible
card prices matching the table. The Human also confirmed the supported standard
price fields against gameplay; Adventure and Normal/Hard Survival costs are
available. Endless prices still depend on the existing-plant surcharge rule.
Other modes, unresolved Imitater types, unavailable Endless plant arrays, and
table read/type failures have null cost.

`cooldown_ready` uses the dynamically checked usable byte when the raw counter
pair is valid (`0 <= progress <= total`): byte `1` means true and byte `0` means
false. Missing flags or malformed counters remain null. Prior placement samples
showed the raw transition from `(0, total, 1)` to `(positive, total, 0)`, and the
Human confirmed that planting makes the card false and natural cooldown
recovery restores true. A read-only Hard Survival sample initially had six
cards null because ready cards could report `progress == total`; the builder now
accepts that valid boundary when the usable byte is set. Current card readiness
and `usable` values are available when all required inputs are valid.
Slot-level `usable` is true only when the supported game is actively playing,
the card is cooldown-ready, and the live balance covers its calculated cost; a
known pause, completed scene, cooling card, or insufficient balance yields
false. Missing inputs yield null. This does not claim any particular board
cell is plantable. The Human confirmed the current standard-mode card states
against gameplay; slot states are available when their price inputs are
available. Values derived from unverified Endless pricing remain provisional.
`decision_ready` remains false.

On 2026-09-26 the Human calibrated the standard daytime lawn house touch line
at X=0, the house-side column boundary at X=50, and 80px columns. The State
reports `distance_to_house_px=max(0, x-house_x)` plus an integer
`distance_to_house_cells` index from 0 (house-side column) to 8 (far column),
using `clamp(floor((x+30)/80), 0, 8)`. Lane summaries report the minimum of
both distance fields. The former `progress_to_house` field was removed; other
backgrounds/modes remain unavailable. A live read-only
`snapshot --once` at 2026-09-25 10:00:12 UTC confirmed that the fixed process
was running and returned one valid sample; it did not include a corresponding
screenshot or movement/cooldown event, so it is not V03/V11 evidence.
The later Human-provided same-scene screenshot/State sample reported row-0
zombie X values 10, 90, and 170, plus row-1 X=490.5. With `house_x=0`, the
pixel distances are those same values and the observed lane minima are 10 and
490.5; the nine-zombie sample at X=10/90/…/650 maps to grid indices 0–8. The
pasted snapshot predates the geometry update and still shows the new fields as
unavailable.

## P05 JEV State profile update (2026-09-26)

The JEV profile remains an explicit decision-facing allowlist, but no longer
contains the top-level `availability` mapping. Fields that cannot be acquired
remain `null`; All State retains the original availability/evidence diagnostics
for human inspection. The `/state` page renders either selected profile as a
collapsible JSON tree without changing its keys, order, nesting, or values.
Expanded object/array paths are kept per profile across polling updates. Copy
uses the serialized selected profile payload rather than the rendered DOM. The
page's “latest snapshot” badge is UI status, not a State availability field.
JEV per-zombie distances use `distance_to_house_px` and
`distance_to_house_cells`. JEV lane entries contain row, zombie count, and the
nearest cell distance; the redundant pixel-lane minimum and `collectible_suns`
are omitted. All State retains its original per-zombie `distance_to_house_*`
fields and both lane minima. JEV item entries include `type_name` with their
code and coordinates; All State keeps its existing item fields.

## P01 CD-08 JEV board cell update (2026-09-26)

For the standard daytime 5×9 lawn, JEV `board.cells[row][col]` uses `null` for
an empty plantable tile, `false` for a known non-plantable tile, and
`plant:<type_name>` for an occupied tile. The JEV projection omits separate
`terrain` and `plantability` fields. Invalid occupancy or an unsupported board
layout returns `board.cells=null`; All State retains its existing board fields.
