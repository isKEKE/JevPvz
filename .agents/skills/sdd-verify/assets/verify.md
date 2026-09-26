# Verify

## 1. Verification Metadata

- Iteration: `<NNN-short-title>`
- Verified at:
- Executor: Main agent
- Execution mode: Main agent (default)
- Overall result: Not run
- Verification execution: Not run

Allowed final values: `Passed`, `Failed`, or `Blocked`.
Verification execution values: `Complete` or `Incomplete`; `Not run` is for drafts.
Execution mode records whether the current main agent or an optional delegated
verifier performed the work; it does not change evidence or result thresholds.
Use `Incomplete` when an authorized, executable G1 check was skipped because of
a verification execution omission.

## 2. Baseline Reviewed

- Original requirement source:
- Plan Index revision/state:
- Concrete Plans reviewed:
- Implementation diff/revision:
- Current delivery goal and use:
- G1 minimum success conditions:
- Excluded or future scenarios:
- Runtime environment and current state:
- Check executor (main agent / delegated verifier / Human / automation):
- State-changing action authority, scope, limits, and recovery/stop conditions (if applicable):

## 3. Requirement Traceability

| Requirement ID | Plan / Task | Check ID and tier | Implementation evidence | Verification evidence | Observed result | Delivery disposition |
|---|---|---|---|---|---|---|
| R1 | P01 / T1 | V1 / G1 | TBD | TBD | Not run | Pending |

## 4. Plan and Task Results

| Plan ID | Task ID | Planned outcome | Actual result | G1 impact | Result |
|---|---|---|---|---|---|
| P01 | T1 | TBD | TBD | TBD | Not run |

## 5. Commands Run

| Check ID / tier | Command | Observed result | Evidence / important output |
|---|---|---|---|
| V1 / G1 | TBD | Not run | |

## 6. Manual / Browser Verification

| Check ID / tier | Check | Observed result | Evidence / human source and date |
|---|---|---|---|
| V1 / G1 | TBD | Not run | |

## 7. Issues Found

记录可复现问题、需求遗漏、越界变更及证据位置。每项注明检查 ID、G1 影响
路径或非核心理由。Verify 只记录，不修复。

## 8. Missing Evidence and Blockers

| Check ID / tier | Missing evidence or deferred check | Cause category and reason | Current delivery impact | Recheck trigger |
|---|---|---|---|---|
| TBD | TBD | External condition / authorization or safety boundary / verification execution omission / other: TBD | TBD | TBD |

未知或无法运行的检查不能按通过处理。只有缺失 G1 必要证据且无可用替代证据时
才构成总体 Blocked；G2/G3 可在有依据的处置下保留为未验证或暂缓。
若已获授权且可执行的 G1 检查因验证执行遗漏而未运行，应标记
Verification execution 为 Incomplete，记录该遗漏并安排重跑；不要写成外部阻塞
或产品失败。

## 9. Human Decisions and Accepted Risks

| Check ID | Original tier / observed result | Decision and source/date | Reason and applicable scope | Remaining risk / recheck trigger |
|---|---|---|---|---|
| None | | | | |

Human 的手工验证应记录实际操作、观察结果和范围；风险接受或暂缓应保留原始
检查结果，不能记成检查通过。Plan 中门槛的本次例外也在此记录原级别和裁定依据。

## 10. Conclusion

- Overall result: Not run
- Verification execution: Not run
- Reason:
- G1 evidence summary:
- Accepted G2 risks and deferred G3 checks:
- Required next stage: None / `$sdd-implementation` repair / unblock and rerun `$sdd-verify`
