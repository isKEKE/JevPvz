# Delivery Report

## 1. Delivery Metadata

- Iteration: `008-collect-confirmation-latency`
- Delivered at: 2026-09-29
- Branch: `main`
- Commit type: `fix`
- Planned commit subject: `sdd(008): fix collect confirmation polling at 60 ms`

## 2. Summary

把 JEV Runtime 的 collect 确认轮询间隔由执行器默认的 250 ms 收紧为 collect 专属的
60 ms。现场 Trace 复算显示：一次成功 collect 的确认中位耗时 1091 ms，其中游戏自身
把物品从 `items[]` 移除需要约 550–800 ms、单次 All State 采集仅约 53 ms，因此
250 ms 间隔给每次收集附加了最多一个整间隔的纯量化开销（实测 boundary 1014–1391 ms
对照真实等待 796–1093 ms）。60 ms 把该尾巴压到 ≤60 ms，且仍守在 Boundary 自身的
50 ms 下限之上。

`COLLECT_CONFIRMATION_TIMEOUT_MS = 2500` 与 plant/shovel 的 10 s 超时 + 250 ms 轮询
默认全部保持不变，故 OD-24（动作绝不交错）与 OD-47（有界确认预算）的安全语义
没有任何改变。

**本 Iteration 只削观测开销，不改变游戏结算延迟**，也不修 collect 分支「只收一个
物品」的授权行为（后者是契约级问题，需另行规划，见 §9）。

## 3. What Changed

**`jev/scheduler.py`**（+21 / −4）

- 新增 `COLLECT_CONFIRMATION_POLL_INTERVAL_MS = 60`，附完整依据注释（含本次实测数字）。
- `_dispatch_request` 的 collect 分支在写入 `timeout_ms` 之后追加
  `request["poll_interval_ms"] = COLLECT_CONFIRMATION_POLL_INTERVAL_MS`；plant/shovel
  分支未改，仍走执行器默认。
- 常量加入 `__all__`。
- 更新 `_dispatch_request` docstring：collect 请求现在同时携带超时与轮询间隔。

**`tests/test_jev_scheduler.py`**（+36 / −3）

- `import` 增补 `COLLECT_CONFIRMATION_POLL_INTERVAL_MS` 与 `DEFAULT_POLL_INTERVAL_MS`。
- `test_the_click_uses_the_current_coordinates_of_the_bound_item`：期望请求字典加
  `poll_interval_ms`。
- `test_the_bound_identity_reaches_the_boundary_without_coordinates`：键集断言加
  `poll_interval_ms`。
- 新增 `test_the_collect_request_uses_the_denser_confirmation_poll_spacing`
  （断言 60 及 `50 ≤ 60 < 250`）。
- 新增 `test_the_denser_spacing_still_passes_the_real_boundary_validator`
  （走真实 `ActionValidator`）。
- 更新 `CollectConfirmationTimeoutTests` docstring。

**SDD / memory**：新建 `.sdd/008-collect-confirmation-latency/{plan-index.md,plans/01-collect-poll-interval.md,verify.md,delivery.md}`；更新 `.memory/context.md`。

行为影响：collect 每次收集少付最多一个轮询间隔（实测约 150–250 ms 的量化尾巴），
名义轮询节奏由「采集 ≈53 ms + sleep 60 ms ≈ 113 ms/轮」主导，不会退化为忙等。

## 4. Plan and Task Status

| Plan ID | Status | Completed Tasks | Incomplete Tasks | Notes |
|---|---|---|---|---|
| P01 | Approved | T1 | 无 | T1 已实现、回填，并通过正式 Verify |

无未完成项，与 Passed 结论一致。

## 5. Files Changed

```text
.sdd/008-collect-confirmation-latency/plan-index.md                    (+135)
.sdd/008-collect-confirmation-latency/plans/01-collect-poll-interval.md (+199)
.sdd/008-collect-confirmation-latency/verify.md                        (new, delivery 阶段)
.sdd/008-collect-confirmation-latency/delivery.md                      (new, 本文件)
.memory/context.md                                                     (更新 Iteration 状态与 activity)
jev/scheduler.py                                                       (+21 / −4)
tests/test_jev_scheduler.py                                            (+36 / −3)
```

代码面只有 `jev/scheduler.py` 与 `tests/test_jev_scheduler.py` 两个文件被修改；
`jev/loop.py`、`actions/executor.py`、`configs/` 均未触碰。

## 6. Verification Result

- Overall result: **Passed**
- Verification execution: **Complete**
- Evidence: `.sdd/008-collect-confirmation-latency/verify.md`

R1–R4 四项 G1 均以「定向测试 + 独立只读探针」双路径取得通过证据；变异复算
（60 → 250）得 FAILED 并逐字节还原，证明断言可捕获回归；全量 `unittest discover`
**470 tests OK**。V6（真机确认耗时）按 Plan 定为 G2、`Not run`，不阻塞交付。

## 7. Deviations from Approved Plan

1. **commit 拆分**：Plan 未规定 commit 结构。实际先提交了代码+Plan 的 `d3071b2`，
   随后本 delivery 阶段补 `verify.md`、`delivery.md` 与 memory 更新为第二个
   commit（依 `sdd-memory` 的 Delivery contract：memory 变更随 Delivery 一起纳入
   Iteration commit）。内容与 Plan 一致，仅提交顺序不同。
2. **未纳入 loop.py 改动**：Plan Index 的 CD-02 已预先记录此决定（Human 2026-09-29
   选择「不恢复」），非偏差，此处复述以便审计。

无其他偏差；未扩充 Scope，未新增依赖。

## 8. Known Risks

- **收益上限受游戏引擎限制**：本次无法压缩游戏自身约 550–800 ms 的结算延迟。
  若 Human 期望更大幅度提速，需契约级方案（乐观确认 / 并发点击），不在本范围。
- **60 ms 距 Boundary 50 ms 下限仅 10 ms 余量**：任何上调 `_timing_arguments`
  下限的改动都会使该值失效。已由 V3/V4 断言守护。
- **V6 未取得改动后真机数据**：在库 Trace 早于本改动，只能记录 BEFORE 状态
  （132 次 collect 确认、`waited_ms` 中位 875 ms、`polls ∈ {1,9–14,34–36}`）。
  改动后效果未经真机确认，属 G2 已接受。
- **平台差异**：Trace 依据来自本机 Windows 实机，跨机器绝对收益可能有差异，
  正确性不受影响。

## 9. Follow-up Items

1. **collect「只收一个物品」仍未修**（与本次独立）：现场证据显示 225 次授权中
   141 次（63%）零收集，`cohort_member_already_pending` 108 次。已定位的成因是
   `management_state_key` 中的 sun 反复刷新 collect 分支去重键（等价复现：去掉 sun
   后丢弃数 12 → 0），叠加 `combine_collect_decision` 只取 `candidates[0]` 作 target、
   以及 `COLLECT_TARGET_QUESTION_ID` 定义却从未启用。修它属契约级变更，需
   `$sdd-plan` 新 Iteration。
2. **工作区仍有 9 个未提交文件**属并行的 plan/economy 直改任务
   （`jev/{client,loop,questions,strategy,trace}.py` + 4 个对应测试 + `.log/` 证据），
   本 Iteration 完整排除、未触碰。需其自身 Plan 与交付。
3. V6 真机复核：Human 运行一局后读取新 Trace 的 `boundary.wait.waited_ms` / `polls`。

## 10. Git Scope

- Files intended for this Iteration commit: `.sdd/008-collect-confirmation-latency/`（四个文件）、
  `.memory/context.md`、`jev/scheduler.py`、`tests/test_jev_scheduler.py`
- Unrelated working-tree files explicitly excluded: `jev/client.py`、`jev/loop.py`、
  `jev/questions.py`、`jev/strategy.py`、`jev/trace.py`、`tests/test_jev_client.py`、
  `tests/test_jev_loop.py`、`tests/test_jev_strategy.py`、`tests/test_jev_trace.py`
  （9 个文件，均属并行 plan/economy 任务）；`.log/*.jsonl`、`.log/*.md`、`.log/*.py`（未跟踪证据/临时产物）
- Remote / branch intended for push: `origin` / `main`
