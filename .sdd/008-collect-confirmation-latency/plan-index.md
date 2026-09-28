# Plan Index

## 1. Metadata

- Iteration: 008-collect-confirmation-latency
- Created at: 2026-09-29
- Status: Approved
- Owner: 本仓库维护者

## 2. Goal

把一次 collect 动作的**确认轮询间隔**从执行器默认的 250 ms 收紧为 collect 专属的
60 ms，使每次收集少付最多一个轮询间隔的量化尾巴，同时不改变 OD-47 已批准的
2.5 s 有界预算、不触碰 plant/shovel 的 10 s 默认、不改变任何既有安全语义。

本 Iteration 只修**观测开销**，不修**游戏自身结算延迟**。经 JEV Trace 复算，一次
成功 collect 的确认中位耗时 1091 ms，其中真实等待（物品从 `items[]` 消失）为
796–1093 ms、单次 All State 采集仅约 53 ms，因此在 250 ms 间隔下每次收集要多付
约 150–250 ms 的纯量化开销。60 ms 间隔把该尾巴压到 ≤60 ms 且仍守在 Boundary 自身
的 50 ms 下限之上。

明确**不在本 Iteration 范围内**：collect 分支"只收一个物品"的行为（该缺陷的主因是
`management_state_key` 里的 sun 反复刷新 collect 分支去重键、以及 `combine_collect_decision`
只取 `candidates[0]` 作为 target），属于契约级变更，需另行规划。

### Requirement Baseline

| Requirement ID | Requirement | Source | Verification tier | Reason for tier |
|---|---|---|---|---|
| R1 | collect 请求必须携带 60 ms 的确认轮询间隔；该值必须 ≥ Boundary 允许的 50 ms 下限，且严格小于执行器的 250 ms 默认。 | 用户 2026-09-29 明确指示「直接改降低下，太慢了」，并选择保留该改动；依据为 `.log/jev-dashboard.jsonl` 的 20 次成功 collect 实测（4–5 polls / 796–1093 ms waited / boundary 1014–1391 ms，per-poll 采集约 53 ms）。 | G1 | 这是本次唯一的行为变更；值不对则改动无意义或违反 Boundary 契约。 |
| R2 | collect 的确认预算必须保持 `COLLECT_CONFIRMATION_TIMEOUT_MS = 2500`，不得因本次改动而放宽。 | OD-47 / R36 既有批准；`jev/scheduler.py` 现状与该常量注释。 | G1 | 该预算保护唯一执行 worker 不被未确认点击长期占用。 |
| R3 | plant 与 shovel 的请求不得携带 collect 专属轮询间隔，仍走执行器 10 s 超时与 250 ms 轮询默认。 | 既有 OD-47 边界与 `_dispatch_request` 现状；本次范围仅 collect。 | G1 | 越界改写会改变种植/铲除的既有安全语义。 |
| R4 | 60 ms 必须能通过真实 `ActionValidator` 校验，且在 2.5 s 预算内的最坏轮询次数不得使确认退化为忙等。 | Boundary `_timing_arguments` 的 `poll_interval_ms ∈ [50, 2000]` 约束。 | G1 | 配置值若被 Boundary 拒绝，collect 会在派发前失败。 |

## 3. Scope

### In scope

- `jev/scheduler.py`：新增 `COLLECT_CONFIRMATION_POLL_INTERVAL_MS = 60` 常量、
  在 `_dispatch_request` 中为 collect 请求写入 `poll_interval_ms`、导出该常量、
  更新 `_dispatch_request` 的 docstring。
- `tests/test_jev_scheduler.py`：更新 2 处断言（collect 请求键集）、新增 2 个契约
  测试（60 ms 值与 Boundary 通过性）、更新 OD-47 测试类 docstring。

### Out of scope

- 任何 collect 分支的**授权/目标选择/cohort 账本**行为（含 `_branch_key`、
  `_accept_latest_cohort`、`combine_collect_decision`）。
- `actions/executor.py` 的 `DEFAULT_POLL_INTERVAL_MS`（保持 250 ms 供 plant/shovel）。
- `COLLECT_CONFIRMATION_TIMEOUT_MS` 的取值。
- 乐观确认、并发点击、取消确认等任何削弱 OD-24/OD-47 的方案。
- `jev/loop.py`：本 Iteration 不修改该文件。早先试验过的「从 collect 分支键移除
  `repr(self._last_result)`」已被回滚，且经等价复现实测**未降低**丢弃数
  （12 → 12），故不作为本次交付内容。

## 4. Plan Catalog

| Plan ID | Plan | Main outcome | Depends on | Status | Link |
|---|---|---|---|---|---|
| P01 | Collect confirmation poll interval | collect 请求以 60 ms 间隔确认，边界与预算不变 | None | Approved | `plans/01-collect-poll-interval.md` |

## 5. Decision

- Open Decision：无。
- Confirmed Decision：见下。

### Confirmed Decision Record — CD-01

- Decision ID: CD-01
- Confirmed choice: 直接实施 60 ms collect 确认轮询间隔（方案 A）。
- Source: 用户 2026-09-29 对话「直接改降低下，太慢了」，并在澄清提问中选择「保留 poll 改动」。
- Date: 2026-09-29
- Reason: 依据现场 Trace 复算，250 ms 间隔构成每次收集约 150–250 ms 的纯量化开销；
  60 ms 仍守在 Boundary 50 ms 下限之上且不放宽 2.5 s 预算，属零契约风险的性能修复。

### Confirmed Decision Record — CD-02

- Decision ID: CD-02
- Confirmed choice: 本次不纳入 `jev/loop.py` 的 `_last_result` 相关改动。
- Source: 用户 2026-09-29 在澄清提问中选择「不恢复（推荐）」。
- Date: 2026-09-29
- Reason: 该改动的等价复现实测未降低 `cohort_member_already_pending` 丢弃数（12 → 12），
  收益未证实；主导因素是 `management_state_key` 中的 sun，改动它会导致既有测试
  `test_model_can_wait_change_and_cancel_without_cheaper_substitute` 失败，属契约级变更。

## 6. Task

- P01/T1 是本次唯一 Task，无跨 Plan 依赖。Task 的目标、影响文件与 Implementation
  backfill 详见 `plans/01-collect-poll-interval.md`。

## 7. Validation

### Current delivery boundary

- 本次产物与实际用途：JEV Runtime 的 collect 动作每次收集少付最多一个轮询间隔的
  量化开销，缩短"点击→确认"闭环，缓解真机上一屏多颗阳光时收集偏慢的观感。
- 本次交付成功的最小条件：R1–R4 全部满足——collect 请求携带 60 ms、预算仍为
  2500 ms、plant/shovel 不受影响、60 ms 通过真实 Boundary 校验，且定向测试与全量
  回归通过。
- 不作为本次交付门槛的场景：真机端到端收集耗时（需 Human 运行一局，记为 G2）；
  collect 分支"只收一个物品"的授权行为（属另一 Iteration 的契约级范围）。

### Verification tiers

| Tier | Meaning | Handling in Verify |
|---|---|---|
| G1 核心路径 | 直接决定本次目标能否实现或结果是否可信 | 必须取得充分通过证据；失败或缺少必要证据影响交付 |
| G2 当前风险 | 当前可能遇到，但不必然妨碍核心路径 | 如实记录影响；Human 明确接受的剩余风险不阻塞交付 |
| G3 后续场景 | 主要针对未来用途，不属于本次目标 | 可暂缓验证；记录理由和未来重查条件 |

验证顺序：先跑 `tests.test_jev_scheduler` 定向断言（V1–V4），再跑全量
`unittest discover`（V5）。真机端到端耗时（V6）为 G2，由 Human 在一局真实对局中
读取 Trace 的 `boundary.wait.polls` / `waited_ms` 确认；不执行不阻塞交付。

## 8. Risks

- **收益上限受游戏结算限制**：60 ms 只能移除观测侧量化开销，无法缩短 PvZ 引擎
  自身把物品从 `items[]` 移除的约 550–800 ms。若 Human 期望更大幅度提速，需要
  契约级方案（乐观确认/并发点击），不在本次范围。
- **更密集轮询意味着更多内存读取**：60 ms 下每轮仍是一次完整 All State 采集
  （实测约 53 ms），故实际轮询节奏受采集耗时主导（约 113 ms/轮），不会造成
  比原先更重的 CPU 争用；若现场发现采集成为瓶颈，需另行评估。
- **常量漂移风险**：60 ms 贴近 Boundary 的 50 ms 下限，仅余 10 ms 余量；任何把
  `_timing_arguments` 下限上调的改动都会使该值失效。已由 V3/V4 断言守护。
- **平台差异**：Trace 依据来自本机 Windows 实机；不同机器/负载下的采集耗时可能
  不同，60 ms 的绝对收益可能变化，但正确性不受影响。

## 9. Approval

- Status: Approved
- Approved by: 本仓库维护者（Human）
- Approval date: 2026-09-29
- Notes: Human 以「直接改降低下，太慢了」明确指示本次直接实施，并在澄清提问中确认
  「保留 poll 改动」「不恢复 loop 改动」。本 Iteration 为对已实施改动的正式追认与
  回填记录，使其重新成为唯一事实来源。
