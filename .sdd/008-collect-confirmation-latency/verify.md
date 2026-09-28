# Verify

## 1. Verification Metadata

- Iteration: `008-collect-confirmation-latency`
- Verified at: 2026-09-29
- Executor: Main agent
- Execution mode: Main agent (default)
- Overall result: Passed
- Verification execution: Complete

## 2. Baseline Reviewed

- Original requirement source: 用户 2026-09-29 对话「直接改降低下，太慢了」；澄清提问中选择「保留 poll 改动」「不恢复 loop 改动」。需求依据为 `.log/jev-dashboard.jsonl` 对 20 次成功 collect 的实测复算。
- Plan Index revision/state: `.sdd/008-collect-confirmation-latency/plan-index.md`，Status Approved（2026-09-29），R1–R4，G1×4，CD-01/CD-02 已回填。
- Concrete Plans reviewed: `.sdd/008-collect-confirmation-latency/plans/01-collect-poll-interval.md`（P01，T1 已 `[x]` 并回填）。
- Implementation diff/revision: commit `d3071b2`（`sdd(008): poll collect confirmation at 60 ms instead of 250 ms`），5 文件 / +403 −22；代码面仅 `jev/scheduler.py`(+21/−4) 与 `tests/test_jev_scheduler.py`(+36/−3)。
- Current delivery goal and use: 缩短 collect「点击→确认」闭环，使每次收集少付最多一个轮询间隔的量化开销，缓解真机上一屏多颗阳光时收集偏慢的观感。
- G1 minimum success conditions: R1–R4 全部成立——collect 请求携带 60 ms、预算仍 2500 ms、plant/shovel 不受影响、60 ms 通过真实 Boundary 校验，且定向与全量回归通过。
- Excluded or future scenarios: collect 分支「只收一个物品」的授权行为（契约级，属另一 Iteration）；乐观确认/并发点击；真机端到端耗时（V6，G2）。
- Runtime environment and current state: Windows，Python 3.12.13 via `uv`；工作区 `main` 分支，HEAD = `d3071b2`。工作区另有 9 个未提交文件属并行的 plan/economy 直改任务，非本 Iteration 范围，未被本阶段读取或修改。
- Check executor: 主 agent 执行 V1–V5（自动化）；V6 需 Human 真机运行，本阶段为 `Not run`。
- State-changing action authority, scope, limits, and recovery/stop conditions: 本阶段仅运行测试与只读探针。为做变异复算，临时把 `COLLECT_CONFIRMATION_POLL_INTERVAL_MS` 由 60 改为 250，随即逐字节还原并以 `git diff --exit-code` 确认与 HEAD 一致；未修改任何生产语义，未 commit/push。

## 3. Requirement Traceability

| Requirement ID | Plan / Task | Check ID and tier | Implementation evidence | Verification evidence | Observed result | Delivery disposition |
|---|---|---|---|---|---|---|
| R1 | P01 / T1 | V1 / G1 | `jev/scheduler.py:54` 新增 `COLLECT_CONFIRMATION_POLL_INTERVAL_MS = 60`；`:468` collect 请求写入 `poll_interval_ms` | 只读探针：常量 = 60，`50 ≤ 60 ≤ 2000` 成立，`60 < 250`（执行器默认）成立；`_dispatch_request(collect)` 键集含 `poll_interval_ms=60`；`test_the_collect_request_uses_the_denser_confirmation_poll_spacing` ok | Passed | Accept |
| R2 | P01 / T1 | V2 / G1 | `COLLECT_CONFIRMATION_TIMEOUT_MS` 未被改动 | 只读探针：`== 2500`；`test_every_collect_request_carries_the_bounded_confirmation_timeout` ok | Passed | Accept |
| R3 | P01 / T1 | V3 / G1 | `_dispatch_request` 仅在 `_COLLECT_ACTION` 分支写入轮询间隔 | 只读探针：plant 请求键集为 `['action','card_slot','col','row','type_name']`，**不含** `poll_interval_ms`；`test_plant_and_shovel_requests_keep_the_executor_default` ok | Passed | Accept |
| R4 | P01 / T1 | V4 / G1 | 60 位于 Boundary `_timing_arguments` 的 `poll_interval_ms ∈ [50, 2000]` 内 | 只读探针：2500 ÷ 60 = 41 次轮询可容；`test_the_denser_spacing_still_passes_the_real_boundary_validator`（走真实 `ActionValidator`）ok | Passed | Accept |

## 4. Plan and Task Results

| Plan ID | Task ID | Planned outcome | Actual result | G1 impact | Result |
|---|---|---|---|---|---|
| P01 | T1 | collect 请求以 60 ms 间隔确认，预算与 plant/shovel 默认不变 | 已在 `d3071b2` 实现并回填；4 项 G1 契约全部由测试与独立探针双路径确认 | 无不利影响 | Passed |

## 5. Commands Run

| Check ID / tier | Command | Observed result | Evidence / important output |
|---|---|---|---|
| V1–V4 / G1 | `uv run python -m unittest tests.test_jev_scheduler` | Ran 50 tests … OK | 相关 7 项用例全部 ok（含 2 项新增契约用例） |
| V1–V4 / G1 | `uv run python -c "from jev.scheduler import ..."`（只读探针） | 全部 4 项断言为真 | 见 §3 的 Implementation evidence 列 |
| V1–V4 / G1 | 变异复算：`COLLECT_CONFIRMATION_POLL_INTERVAL_MS = 60 → 250` | Ran 50 tests … **FAILED (failures=1)** | 证明断言真能捕获回归；还原后 OK，且 `git diff --exit-code jev/scheduler.py` 通过（逐字节一致） |
| V5 / G1 | `uv run python -m unittest discover -s tests -p "test_*.py"` | **Ran 470 tests … OK** | 无新增失败；并行任务的 9 个未提交文件不属本范围 |

## 6. Manual / Browser Verification

| Check ID / tier | Check | Observed result | Evidence / human source and date |
|---|---|---|---|
| V6 / G2 | Human 真机一局：读取 collect `action_result.boundary.wait.waited_ms` / `polls`，期望 `polls` 明显多于 4–5、`waited_ms` 向游戏结算下限收敛 | Not run | 现有 `.log/jev-dashboard.jsonl`（132 次 collect 确认，`polls ∈ {1,9..14,34..36}`，`waited_ms` 中位 875 ms）捕获于本改动之前，只能记录 BEFORE 状态，不能作为改动后效果证据 |

## 7. Issues Found

无影响 G1 的问题。核查中发现并在此如实记录（均不属本 Iteration 范围）：

1. **V6 无可用前后对照数据**：唯一在库 Trace 早于本改动，无法证明改动后耗时下降。已按 G2 记为 `Not run`，不阻塞交付，重查条件见 §8。
2. **非本范围的既有现象**：在库 Trace 显示 collect 确认的 `polls` 分布极宽（1 到 36），其中 34–36 次轮询的样本对应旧代码在接近 2.5 s 预算处才确认或超时的路径。这是**改动前**的行为，本次只缩短轮询间隔、不放宽预算，故不改变该分布的上界；未发现本改动引入的越界变更。

## 8. Missing Evidence and Blockers

| Check ID / tier | Missing evidence or deferred check | Cause category and reason | Current delivery impact | Recheck trigger |
|---|---|---|---|---|
| V6 / G2 | 改动后的真机 collect 确认耗时 | External condition：需要 Human 启动真实对局并运行 JEV Runtime，主 agent 不得代为操作游戏 | 不阻塞（Plan 已定 G2） | Human 运行一局后读取新 Trace 的 `waited_ms`/`polls` |

## 9. Human Decisions and Accepted Risks

| Check ID | Original tier / observed result | Decision and source/date | Reason and applicable scope | Remaining risk / recheck trigger |
|---|---|---|---|---|
| CD-02 | P01 原拟同时移除 collect 分支键中的 `repr(self._last_result)` | Human 2026-09-29 选择「不恢复（推荐）」 | 等价复现实测该改动未降低 `cohort_member_already_pending` 丢弃数（12 → 12），收益未证实；主导因素是 `management_state_key` 中的 sun，改动它会使既有测试失败 | 若日后修 collect「只收一个物品」，需另行 `$sdd-plan` 并重新评估分支键 |
| V6 / G2 | `Not run` | Plan Index 与 P01 均已预先定为 G2，非阻塞 | 只影响「收益幅度」的确认，不影响改动正确性 | 见 §8 |

## 10. Conclusion

- Overall result: **Passed**
- Verification execution: **Complete**
- Reason: R1–R4 四项 G1 需求均以「定向测试 + 独立只读探针」双路径取得通过证据，并以变异复算证明断言具备捕获回归的能力；全量 470 tests OK 无新增失败。无 G1 失败，无 G1 证据缺口。
- G1 evidence summary: collect 请求携带 `poll_interval_ms = 60`（V1）、预算仍 2500 ms（V2）、plant/shovel 不含该键（V3）、60 通过真实 Boundary 校验且预算内可轮询 41 次（V4）、全量回归 470 OK（V5）。
- Accepted G2 risks and deferred G3 checks: V6（真机耗下降幅度）`Not run`，依 Plan 定为 G2 且不阻塞交付；无 G3 项。
- Required next stage: `$sdd-delivery 008`（无修复需求）
