# Verify

## 1. Verification Metadata

- Iteration: `004-game-state-observation`
- Verified at: 2026-09-26 15:16 Asia/Shanghai (initial verification execution)
- Follow-up decision update: 2026-09-26, based on the user's scope decisions and evidence already collected; no checks were rerun per the user's instruction.
- Original verifier: fresh-context independent verifier (`/root/verify_004`)
- Follow-up updater: Main agent
- Execution mode: Main agent follow-up to the completed verification record
- Overall result: Passed
- Verification execution: Complete

This follow-up updates the earlier result against the user-approved scope revision. The 64-test run, browser observations, and supplied State/screenshot evidence below were already collected after the previous failed report. This update did not rerun tests or live checks.

## 2. Baseline Reviewed

- Original requirement source: Approved Plan Index and P01–P05 for `004-game-state-observation`, plus the user's 2026-09-26 decisions in the current conversation.
- Plan Index revision/state: Approved. P01–P05 concrete Plans are Approved. Their current G1/G2/G3 tiers reflect the user's latest decisions.
- Concrete Plans reviewed: `plans/01-state-contract.md`, `plans/02-live-state-page.md`, `plans/03-dashboard-reduction.md`, `plans/04-live-state-validation.md`, `plans/05-jev-state-presentation.md`.
- Current delivery goal and use: Trustworthy State facts, a JEV/All State observer, a reduced lawn dashboard, and bounded evidence tooling. No automated gameplay or strategy is in scope.
- Revised G1 minimum success conditions: supported standard-mode card cost/readiness/usability; English machine values and Chinese labels; layered HP; calibrated standard-day distances; explicit same-sample JEV/All projections; `/state` navigation and JSON tree; Dashboard card values matching State and grid markers matching calibrated rows/columns; user-supplied State/game screenshot agreement for visible facts; correct JEV board cell semantics and All State compatibility.
- Human scope decisions: no Endless Survival surcharge event for this iteration; no live sun-collection threshold run; current Dashboard design accepted without a reference-image score. V12 target viewport and V15 live plant action are G2, not delivery gates.
- Excluded/deferred: V04 prediction/strategy fields, Endless surcharge verification, and live sun-threshold verification are G3. Unsupported modes/layouts remain unavailable rather than guessed.
- Runtime and supplied evidence: fixed PvZ 1.0.0.1051, Hard Survival/day. User-supplied JEV sample at `2026-09-26T08:58:21.071+00:00` reports `status=ok`, 5×9 board, 10 cards, 13 zombies, and 7 plants. The paired screenshot shows nine normal zombies in row 0 and four special zombies in row 1, with visible plant positions matching the State. JEV intentionally omits `raw_snapshot`; HP component mapping is covered by State builder tests, and numeric HP is not inferred from pixels.
- Follow-up evidence source: direct-task execution after the prior report recorded 64/64 full-suite tests, 13/13 `test_web.py`, JavaScript/Python syntax checks, `git diff --check`, and browser DOM evidence for corrected card labels, JEV/All switching, same-tab navigation, and current grid markers. No game input was sent.
- State-changing action authority and recovery: no plant or collect action was performed in the follow-up. V15 remains an optional G2 scenario; user-provided same-scene State/screenshot evidence is the current visual cross-check.

## 3. Requirement Traceability

| Requirement ID | Plan / Task | Check ID and tier | Implementation evidence | Verification evidence | Observed result | Delivery disposition |
|---|---|---|---|---|---|---|
| R1 State contract | P01/T1 | V01/G1 | `docs/memory-map.md`, `docs/architecture.md`, `state/builder.py` | Original schema/source review and sanitized snapshot | Pass for the documented fields and evidence limits. | Pass |
| R2 Cost, cooldown, `usable` | P01/T2 | V02,V03/G1 | `state/builder.py`, catalogs, `dashboard/static/app.js::renderCards` | 64-test suite; user Hard Survival card-price/cooldown evidence; post-fix browser DOM and All State availability | Standard supported mode has 10 card costs and boolean cooldown/usability values; the Dashboard displays them without the old “candidate/unverified raw counter” labels. Endless surcharge is excluded and remains provisional there. | Pass for revised scope; Endless event deferred G3 |
| R3 Live State page | P02/T1,T2 | V05,V06/G1 | `dashboard/server.py`, `state.html`, `state-page.js` | 13 web tests and CUA same-tab `/` ↔ `/state` navigation | Routes, profile display, refresh, and normal same-tab navigation pass. | Pass |
| R4 Reduced Dashboard | P03/T1,T2 | V08/G1; V12/G2 | `index.html`, `app.js`, `style.css` | Web tests and browser DOM; user accepted the current design | State views and current content are correct. Exact 1672×941 scroll measurement was not run and is G2. | Pass; V12 accepted as non-blocking G2 |
| R5 Prediction/decision fields | P01/T1–T3 | V04/G3 | Plans and docs explicitly defer these fields | Source/docs review from original verification | Deferred; no unsupported predictions were added. | Deferred G3 |
| R6 Shared sampling/error display | P02/T2 | V07/G2 | Shared poller and error handling; DOM tests | Automated error-path tests pass; browser disconnect was not observed | Real-browser disconnect check remains unrun. | Accepted non-blocking G2 |
| R7 English State / Chinese UI | P01/T2, P03/T1,T2 | V09,V13/G1 | Catalogs, builder, JS localization | Existing API/browser observations and tests | Supported names display in Chinese; State identifiers remain English; unknown values preserve codes. No plant image resources were added. | Pass |
| R8 Layered zombie HP | P01/T1,T2 | V10/G1 | Builder HP components and `tests/test_state.py` | User screenshot/JEV sample plus raw-to-State component tests and All State HP display | Conehead, buckethead, football, and balloon zombies’ visible types/rows/positions match the sample; component values are present and builder tests cover the mapping/sums. HP numbers are not inferred from the screenshot. | Pass for revised evidence contract |
| R9 Calibrated distance | P01/T3 | V11/G1 | `LAWN_GEOMETRY`, builder, lane minima | Human calibration and boundary harness from original verification; supplied sample agrees | X positions map to pixel/grid distances and row minima; unsupported backgrounds return unavailable; `progress_to_house` is absent. | Pass |
| R10 Plant State/screenshot agreement | P04/T1 | V14/G1; V15/G2 | Evidence script and deterministic boundary tests | User-supplied same-scene State/screenshot shows visible plants at the corresponding cells; V14 tests pass | Visible plant/type/cell correspondence passes. A live planting action is not required for this delivery. | Pass; optional action run deferred G2 |
| R11 Live sun threshold | P04/T1,T2 | V14/G1 for tool logic; live V16 removed | Bounded collector and deterministic threshold/deadline tests | `test_live_validation.py` 13/13 from prior execution | Tool logic regression passes; live >50-in-10-seconds result is not a current requirement. | Deferred G3 by user decision |
| R12 State/game screenshot agreement | P04/T1 | V14,V17/G1 | Stable-field projection excludes `items` | User-supplied same-scene State/screenshot; visible modes, entity counts/types/rows, and plant cells reviewed | Visible stable fields match; dynamic `items` are excluded. | Pass |
| R13 Dashboard visual score | P03/T2 | V18 removed; Human acceptance/G1 | Current Dashboard | User explicitly accepted the current design and removed the reference-score requirement | Accepted by Human; no image score is required. | Pass by Human acceptance |
| R14 Grid-column markers | P03/T3 | V19/G1 | `zombiePositionsForState`, CSS marker rendering, web tests | Current browser DOM and supplied State agree on row/grid labels | Valid grid markers align with row and 0–8 cell index; labels do not claim plant-cell occupancy. | Pass |
| R15 JEV/All projection | P01/T4, P02/T3, P05/T1 | V20–V25/G1 | Explicit allowlist, shared API poller, profile controls | State/web tests and browser JEV/All toggle | JEV omits `availability` and diagnostic fields; All State preserves them; both profiles use the shared sample. | Pass |
| R16 JSON tree | P02/T3, P05/T2 | V26–V28/G1; V29/G2 | Safe tree renderer, profile-specific expansion state and copy | Web/DOM tests and browser inspection from prior evidence | Structure, escaping, profile switching, and copy behavior pass. Large-All-State render performance V29 was not separately measured. | Pass; V29 remains non-blocking G2 |
| R17 JEV board cell semantics | P01/T5 | V30/G1 | `state/projection.py` and State/Web tests | Tests plus user sample/API evidence | JEV board is 5×9 with `null`/`false`/`plant:<type_name>` semantics; JEV omits `terrain`/`plantability`; All State retains them. | Pass |

## 4. Plan and Task Results

| Plan ID | Task ID | Planned outcome | Actual result | G1 impact | Result |
|---|---|---|---|---|---|
| P01 | T1–T5 | State contract, standard card derivations, distances, profiles, and board cells | All tasks are checked complete with current backfills; card UI alignment and revised cost scope are recorded. | R1,R2,R7–R9,R15,R17 pass for revised scope. | Complete |
| P02 | T1–T3 | Dynamic State page, refresh/error behavior, and profiles | All tasks checked complete; same-tab navigation observed. | R3,R15 pass; V07 remains G2. | Complete |
| P03 | T1–T3 | Reduced Dashboard and grid-column markers | All tasks checked complete; current layout accepted; exact viewport is G2. | R4,R7,R13,R14 pass for revised scope. | Complete |
| P04 | T1–T2 | Evidence capture tool and deterministic boundary tests | Both tasks checked complete; user supplied the visible State/screenshot pair. | R10,R12 pass; live plant action G2, sun threshold G3. | Complete |
| P05 | T1–T2 | JEV field boundary and JSON tree page | Both tasks checked complete and covered by current web/state evidence. | R15,R16 pass; V29 remains G2. | Complete |

## 5. Commands Run

The following results are from the earlier follow-up execution after the card UI fix; they were not rerun for this decision update.

| Check ID / tier | Command | Observed result | Evidence / important output |
|---|---|---|---|
| V02,V09–V11,V14,V20–V28,V30 / G1 | `uv run python -m unittest discover -s tests -p "test_*.py"` | 64 tests passed | Full suite after the card-label fix. |
| V08,V13,V19,V24–V28 / G1 | `uv run python -m unittest discover -s tests -p "test_web.py"` | 13 tests passed | Includes `test_card_labels_follow_state_cost_cooldown_and_usable_values`. |
| V08,V13,V19 / G1 | `node --check dashboard/static/app.js`; `node --check dashboard/static/state-page.js` | Both passed | JavaScript syntax. |
| V01,V11,V19 / G1 | `uv run python -m py_compile state/builder.py state/projection.py game/reader.py dashboard/server.py main.py tests/capture_live_validation.py` | Passed | Python syntax. |
| Hygiene | `git diff --check` | Passed | CRLF normalization notices only; no whitespace errors. |

## 6. Manual / Browser Verification

| Check ID / tier | Check | Observed result | Evidence / human source and date |
|---|---|---|---|
| V03 / G1 | Standard-mode card costs and cooldown behavior | Standard Hard Survival menu prices correspond to the supplied State; Human previously confirmed planting clears readiness and normal recovery restores it. No Endless event is required. | Human screenshots/messages and current JEV sample, 2026-09-26. |
| V10 / G1 | Armored-zombie screenshot and State comparison | Screenshot shows nine normal row-0 zombies plus conehead, buckethead, football, and balloon zombies in row 1. State reports the same 13 entities, rows, positions, and HP components; seven plant positions also match. Numeric HP is validated by tests/State, not inferred from image pixels. | User-supplied screenshot and JEV State timestamped 2026-09-26T08:58:21.071+00:00. |
| V11 / G1 | House/grid calibration | Human calibration establishes house X=0, boundary X=50, 80px pitch, and row-0 X sequence 10/90/…/650; the original boundary harness passed. | User-provided same-scene calibration and original Verify harness, 2026-09-26. |
| V06,V24 / G1 | `/` and `/state` same-tab navigation and JEV/All toggle | Browser opened the State page, switched profile, and returned to the home page in the same tab; content and labels tracked the selected profile. | Main-agent CUA browser observations after the previous report, 2026-09-26. |
| V19 / G1 | Zombie grid marker positions | DOM positions/labels corresponded to row and grid cell; descriptions disclaim occupancy. | Main-agent CUA browser and tests, 2026-09-26. |
| V17 / G1 | Same-scene State/game screenshot visible fields | Visible zombie counts/types/rows and plant cells match the user-supplied sample; `items` excluded; numeric HP not inferred visually. | User-supplied screenshot and JEV State, 2026-09-26. |
| V07 / G2 | Browser disconnect UI | Not run in a real browser; automated failure handling tests passed. | User accepted non-blocking tier adjustment, 2026-09-26. |
| V12 / G2 | Exact 1672×941 viewport/scroll measurement | Not run; the current Dashboard design was explicitly accepted. | User accepted non-blocking tier adjustment and design, 2026-09-26. |
| V15 / G2 | Live plant action on an empty cell | Not run; tool preconditions are covered by deterministic tests and the supplied current State/screenshot pair validates visible plant occupancy. | User accepted this as non-blocking, 2026-09-26. |
| V29 / G2 | Large All State tree performance | No dedicated large-sample performance measurement. | Non-blocking G2; recheck if All State size causes visible refresh delay. |

## 7. Issues Found

- Resolved: Dashboard formerly labeled known prices as candidates and showed raw cooldown counts as unverified. `renderCards` now renders State `cost`, `cooldown_ready`, and `usable`; live DOM showed the values and “已核验” group status.
- Superseded: The earlier 62-test run had one stale wording assertion and an older live sample with null card states. The later full run passed 64 tests, and the current Hard Survival sample has all ten card readiness/usability values as booleans.
- No unresolved G1 implementation failure remains under the revised user-approved scope.

## 8. Missing Evidence and Blockers

| Check ID / tier | Missing evidence or deferred check | Cause category and reason | Current delivery impact | Recheck trigger |
|---|---|---|---|---|
| V07 / G2 | Real-browser disconnect/stale-sample observation | Current browser covered normal navigation; automated error-path tests passed. | Accepted non-blocking risk. | Recheck if connection failure behavior becomes a core requirement. |
| V12 / G2 | 1672×941 target viewport measurement | User accepted the current Dashboard design and explicitly allowed non-blocking checks to be downgraded. | No delivery impact. | Recheck after redesign or if the target viewport becomes a hard requirement. |
| V15 / G2 | Live plant action/after-State capture | User-supplied State/screenshot pair and deterministic preflight tests cover the current observation goal; no live input was sent. | No delivery impact. | Recheck only if the live action tool’s deployment behavior must be certified. |
| V29 / G2 | Large All State render performance sample | Dedicated performance sample not collected. | No delivery impact. | Recheck if larger snapshots visibly stall refresh or interaction. |
| R2 / G3 | Endless upgrade-price event | User removed this event from current acceptance; Endless prices remain provisional. | Deferred. | Before claiming verified Endless pricing. |
| R11 / G3 | Live sun-collection >50/10s result | User removed V16 live threshold test; deterministic collector logic tests remain. | Deferred. | If a future goal requires an attributable live collection result. |
| V04 / G3 | Speed/ETA/universal plantability/strategy | Explicitly outside current scope. | Deferred. | Before future decision-closure work. |

No G1 evidence blocker remains under the revised scope. V16 and V18 are removed checks, not failed or unrun checks.

## 9. Human Decisions and Accepted Risks

| Check ID | Original tier / observed result | Decision and source/date | Reason and applicable scope | Remaining risk / recheck trigger |
|---|---|---|---|---|
| V03 / R2 | G1 included an Endless surcharge event | User removed the Endless event from current acceptance, 2026-09-26. | Standard Adventure/Hard Survival pricing remains G1; Endless stays provisional. | Recheck before claiming Endless pricing. |
| V12 / R4 | G1 exact target-size viewport | User accepted the current Dashboard and instructed that non-blocking checks be downgraded, 2026-09-26. | Exact no-scroll measurement is G2 only; current design remains accepted. | Recheck after redesign or target-environment change. |
| V15 / R10 | G1 real planting action | User supplied a same-scene State/screenshot and instructed downgrading non-blocking checks, 2026-09-26. | Visible plant State/screenshot agreement remains G1; actual tool action is G2. | Recheck if the live plant-action tool is a delivery requirement. |
| V16 / R11 | G1 live sun threshold | User removed V16, 2026-09-26. | R11 is G3 Deferred; unit coverage of collector logic remains. | Recheck if live collection is required later. |
| V18 / R13 | G1 reference image and ≥95 score | User stated the current design is accepted and removed the scoring requirement, 2026-09-26. | Human approval satisfies current design acceptance; no score is claimed. | Revisit only on a future redesign. |
| V10,V17 / R8,R12 | G1 paired screenshot/State evidence | User supplied the screenshot and State and said the comparison was acceptable, 2026-09-26. | Visible entity/plant fields match; numeric HP uses deterministic component tests, not pixel inference. | Recheck if a same-frame All State/raw bundle becomes specifically required. |
| V07,V29 | G2 not run | User instructed that non-blocking checks be downgraded, 2026-09-26. | Preserve as current risk; do not claim passed. | Recheck only on relevant environment/scale change. |

## 10. Conclusion

- Overall result: Passed
- Verification execution: Complete (the original execution was complete; this decision update did not rerun checks)
- Reason: All revised G1 requirements have existing test, browser, runtime, calibration, or Human-provided paired evidence. The earlier card-label defect is fixed and the post-fix full suite passed. User-approved G1 scope changes are recorded with their original findings and remaining limits.
- G1 evidence summary: Standard card state/UI alignment, HP component derivation with visible armored-zombie correlation, calibrated distances and grid markers, JEV/All projection, same-tab State page and JSON tree, board-cell semantics, and supplied State/screenshot comparison have supporting evidence.
- Accepted G2 risks and deferred G3 checks: V07, V12, V15, V29 remain unrun G2 checks; Endless surcharge, live sun threshold and V04 are deferred G3 checks. V16/V18 are removed from the current plan.
- Required next stage: `$sdd-delivery`.