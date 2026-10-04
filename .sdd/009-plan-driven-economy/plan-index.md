# Plan Index

## 1. Metadata

- Iteration: `009-plan-driven-economy`
- Created at: 2026-09-29
- Status: Approved
- Owner: 本仓库维护者

编号说明：001–007 已存在，`008-collect-confirmation-latency` 已由并行会话正式使用，故本次按 Human 指定使用 `009`。

## 2. Goal

把"模型声明的建设目标是上下文而不是候选过滤器"这件事固化成一个可审阅、可实现、可验证、可交付的 Iteration：目标可支付时，候选是目标本身加上"余额超出目标价的部分"能支付的牌（Case B：高成本植物必须重新进入候选与请求态）；目标不可支付且没有行需要立即响应时，plant 分支本地等待 `await_plan`（Case A：为未来而不花钱）。同时按 Human 决定把"中断攒钱"的条件从 `{medium, high, critical}` 收窄为 `{high, critical}`，并正式取代 006 中与之冲突的 OD-29/OD-38 条款。此外（CD-07/CD-08）让模型能够在**同一次种植请求**里选择**铲除某一格植物**，补上“低级植物 → 移除 → 高级植物”的 Replace/Upgrade 缺口。

本次只对**代码可确定的部分**负责：候选空间、等待语义、请求态事实与审计面。模型最终选哪张牌、是否主动声明更高价值的目标，仍由模型自主，不在本次验收内。

### 仓库检查（Repository Check）

本 Plan 以当前仓库证据为依据，已逐文件检查：

- `jev/strategy.py`：`_read_affordable`/`build_plant_candidates` 的现有候选语义（`affordable × empty_plantable_cells`）、`evaluate_strategy`/`StrategySignals`、`management_facts`/`management_state_key`；第 45 行 `LANE_RESPONSE_URGENCIES` 当前为 `{medium, high, critical}`（T2 的收窄对象）。
- `jev/client.py`：`decide_plant` 中「只留目标类型」的手牌过滤、`build_plant_questions` 的 255 选项链式拆分、`build_typesafe_state` 的分支字段裁剪、`decide_shared` 的 management 答案校验。
- `jev/questions.py`：`PLANT_STATE_FIELDS`/`COLLECT_STATE_FIELDS`、`PLANT_LAYOUT_ANCHOR` + `load_plant_experience`（instructions 追加式、不缓存的既有先例）、`management_questions`/`_construction_option_text`。
- `jev/loop.py`：`_local_wait_reason`（`no_target`/`await_resource`/`await_cooldown` 三个本地结论）、`_proposal_source_guard`（`intent_changed`/`intent_type_conflict`）、`_branch_key`。
- `jev/trace.py`：`RELIABLE_OUTCOMES` 的可靠结论词表、`_actual_request_state` 的逐字段白名单与 `_select_scalars`、`SharedActualInputParityAcceptanceTests` 要求的“记录态 == builder 输出”。
- `jev/scheduler.py`：`_review_plant` 只校验目标自身的卡牌（type/usable/cooldown/cost/cell），不校验意图类型 —— 支持 R6“目标类型不构成授权前提”。
- `actions/boundary.py` / `actions/executor.py` / `jev/scheduler.py` 的铲除链（P03 的关键事实）：`_validate_shovel` 要求 JEV 格为 `plant:<type_name>` 且 All State 确有对应实体；`_execute_shovel` 选原生铲子 1 次 + 点格 1 次、不承诺叠层格指定实体；`_review_shovel` 在派发前复核；`scheduler._review` 已按 `target.action` 分派。**缺少的只是决策入口**：`BRANCHES = ("plant","collect")`、`AsyncJevClient` 无 `decide_shovel`、`jev/questions.py` 无铲除问题、`jev/strategy.py` 无可铲候选、仪表盘无铲除层（P02 同步路径的 `_shovel_questions`/`should_shovel` 只被测试调用）。
- 测试先例：`tests/test_jev_strategy.py::PlantCandidateTests`（全枚举基线）、`tests/test_jev_client.py::RequestFieldAcceptanceTests`（instructions 只能引用已下发字段）与 `PlantInstructionsGuidanceTests`、`tests/test_jev_loop.py::ManagementAcceptanceTests`。
- 证据：`.log/jev-dashboard.jsonl`（job-000002～000016 的候选/意图时间线）、`.log/jev-dashboard-process.log`（11 次运行、491 次 plant 决策的累计分布）、`.log/2026-09-29-plan-economy-root-cause.md`（直改任务的根因与 before/after）。
- 相似实现/先例复用：固定锚点常量（`COLLECT_ACT_THRESHOLD`、008 的 `COLLECT_CONFIRMATION_POLL_INTERVAL_MS`）、instructions 追加式语义段（`PLANT_LAYOUT_ANCHOR`）、OD 以“引用原文 + 声明取代”的修订方式（006 plan-index 的追加式修订惯例）。
- 依赖与配置：本 Iteration **零新依赖、零新配置项**（band 由手牌价格推出，中断档位是代码内闭集取值）。
- 编号：`008` 已由 `008-collect-confirmation-latency` 使用并交付（commit `d3071b2`）；`009` 无冲突。

### Requirement Baseline

| Requirement ID | Requirement | Source | Verification tier | Reason for tier |
|---|---|---|---|---|
| R1 | 目标可支付时，候选 = 目标自身 + 余额超出目标价部分能支付的牌；高成本牌必须能进入候选、请求态与问题选项 | Human 2026-09-29 Case B 复现要求；`.log/jev-dashboard.jsonl` job-000010/000016 的 1 种/36 个候选证据 | G1 | Case B 的直接判据；不修则高级植物永不进入 JEV 视野 |
| R2 | 目标不可支付且无中断行时，plant 分支本地等待（`await_plan`）、不发请求、不产生动作 | Human 2026-09-29 Case A 复现要求 | G1 | Case A 的核心语义是"跨 tick 攒钱"，必须由代码确定产生 |
| R3 | 中断条件 = 任一行 urgency ∈ `{high, critical}`，或该行有僵尸且没有攻击植物；`medium` 不再中断 | Human 2026-09-29 选择「只在 high 起中断」 | G1 | 取值直接决定"何时可以不响应"，错误取值使 Case A 变成不响应 |
| R4 | 没有目标时行为与现状一致（OD-15 全枚举，无本地 shortlist） | 006 OD-15/R31 既有批准 | G1 | 防止本次改动引入候选裁剪回归 |
| R5 | 请求态携带 economy 事实组（band/plan/sun_above_plan/cheapest/highest）并附语义说明；band 边界只来自本手牌价格，不新增任何配置阳光阈值 | Human 2026-09-29「不要用阈值糊」；CD-01 | G1 | 模型只有拿到"目标价/还差多少/买完剩多少"才能判断该不该等 |
| R6 | 派发守卫不再因"目标类型 ≠ 声明目标类型"拒绝，但来源意图版本变化仍必须拒绝 | 006 R29/OD-43（意图仅上下文）与 R28/第 268 行（冲突即拒绝）互斥，本次二选一 | G1 | 守卫语义与候选规则必须一致，否则合法选择会在派发前被丢弃 |
| R7 | 006/007 既有契约不回归：collect 授权/cohort 账本、意图 keep/replace/cancel、Trace schema-2 字段集、`management_state_key` 语义 | 006/007 已交付并 Verify 的契约 | G1 | 本改动跨 5 个运行时文件，必须证明没有破坏既有行为 |
| R8 | 真机一局 Case A/B 观察有步骤、记录格式与升级条件 | CD-04 | G2 | 依赖 Human 时间与真实 API；代码可确定的部分已由 R1–R7 覆盖 |
| R9 | 冻结样本对照成为入库、可参数化、可测试的工具（`tools/evidence-plan-economy.py`） | CD-05 | G1 | Verify 需要一条不依赖游戏与模型的复现证据路径 |
| R10 | 006 的 OD-29（不做阳光预留）与 OD-38/冷启动第 6 条（攒钱由模型弃选项表达、目标候选只含当前可负担类型）被本 Iteration 明确取代并记录；`docs/architecture.md` 同步 | CD-01/CD-03；006 `plans/03-runtime-loop.md` 原文 | G1 | 不作记录则实现与既有批准文本冲突，Verify/Delivery 无法判定范围 |
| R11 | 自主 Runtime 端到端产出并执行一次 `shovel_cell`；一次决策最多一个动作；放置与铲除同时命中时只派发铲除并记录被丢弃的放置 | CD-07/CD-08；006 计划“shovel 仍须 JEV 明确选择”的落地缺口 | G1 | 这是 P03 的核心目标，决定 Replace/Upgrade 能否发生 |
| R12 | 可铲候选只来自 `board.cells` 的 `plant:<type_name>` 格；无可铲格不追加铲除子问题；请求在“有放置候选或可铲格”时发出 | CD-08/CD-09；`actions/boundary.py::_validate_shovel` 的编码要求 | G1 | 候选来源与请求条件直接决定安全边界与“铲除不被饿死” |
| R13 | 铲除 Choice 自带弃选项，按 `argmax ≠ 弃选 且 best > 弃选` 判定；不新增 Noul/绝对闸门；选项文本只陈述事实 | OD-41 先例；OD-37/R27 模型自主 | G1 | 复活绝对闸门或给出建议会偏离已批准的问题形态 |
| R14 | 新增状态字段（若有）必须进 `PLANT_STATE_FIELDS` 与 Trace 白名单且逐字段相等；instructions 只引用已下发字段；branch key 形状不变 | 006 V31/V44 与 OD-15/22；现存 parity 测试 | G1 | 审计面与去重语义不得被悄悄改变 |
| R15 | Trace 如实记录铲除问题/选项/答案/merge 与 `shovel_cell` 的 `action_result`；`_last_result` 记录真实 action（不冒充 plant） | 006 R41/OD-33 的 Trace 事实权威 | G1 | 无法离线核对就无法 Verify 铲除是否真的发生 |
| R16 | 成功的 `shovel_cell` 点亮对应草坪格且不冒充种植 | P03 CD-08 的呈现层推论 | G2 | 呈现层；Trace 已是事实权威，缺失不影响铲除能力 |
| R17 | 真机观察 Replace/Upgrade 两步（先铲后种）确实发生 | Human 需求中的“低级植物 → Remove → 高级植物” | G2 | 依赖 Human 时间、真机与真实 API |

## 3. Scope

### In scope

- `jev/strategy.py`：经济/目标事实与候选策略函数；**T2 的 `LANE_RESPONSE_URGENCIES` 收窄**。
- `jev/client.py`：`decide_plant` 不再过滤手牌、改传 `plan`；`build_plant_questions`/`build_typesafe_state` 的 `plan` 参数；`decide_shared` 下发 economy。
- `jev/questions.py`：`ECONOMY_ANCHOR` 与三处 plant instructions；`PLANT_STATE_FIELDS` 增 `economy`；management 问题附相对价格档与目标语义。
- `jev/loop.py`：`await_plan` 本地等待；派发守卫只保留意图版本校验。
- `jev/trace.py`：`await_plan` 可靠结论；economy 有界投影。
- （P03/CD-08）`jev/strategy.py` 的可铲候选、`jev/questions.py` 的铲除 Choice、`jev/client.py` 的同请求两问、`jev/decision.py` 的“一次一动作 + 铲除优先”、`jev/loop.py` 的请求发出条件与 `_last_result`、`jev/trace.py` 与 `dashboard/static/viewmodel.js` 的如实记录/点亮。
- 上述行为的回归测试与 `docs/architecture.md` 同步。
- 新增 `tools/evidence-plan-economy.py` 与 `tests/test_economy_evidence.py`，README/usage 命令，旧脚本下线。

### Out of scope

- 模型目标质量（是否在富余时主动声明高成本目标）、阵容/经济规模建议（R27/OD-37 仍由模型自主）。
- `jev/scheduler.py` 与 `tests/test_jev_scheduler.py`（008 正在修改）。
- collect 分支的授权/账本/目标选择（含"只收一个物品"缺陷，`.memory` 已记需另行规划）。
- 真机脚本自动化、乐观确认、并发点击等执行侧改动。
- 任何可调阈值/配置项的新增。
- （P03）新增第三个 shovel 分支/worker/在途预算（CD-08 已排除）；叠层格中指定移除某一株实体（执行器不承诺）；“该不该铲”的策略答案与阵容建议；攒钱期间（`await_plan` 轮次）的铲除（CD-09）。

## 4. Plan Catalog

| Plan ID | Plan | Main outcome | Depends on | Status | Link |
|---|---|---|---|---|---|
| P01 | Plan-driven offer policy | 目标成为上下文：富余时高成本牌回到候选（Case B）；目标差钱时本地 `await_plan` 攒钱（Case A）；中断条件收窄为 high/critical；006 冲突条款被取代并记录 | None | Approved | `plans/01-plan-driven-offer-policy.md` |
| P02 | Economy evidence tool and live observation | 冻结样本对照升格为入库工具 + 冒烟测试 + 文档命令；真机 Case A/B 观察步骤与记录格式（G2） | P01（符号与规则稳定） | Approved | `plans/02-economy-evidence-tool.md` |
| P03 | Autonomous plant removal in the plant request | 同一次种植请求里可铲除某一格：可铲候选 + 铲除 Choice（弃选作主）+ 一次一动作与铲除优先 + Trace 如实记录 + 仪表盘点亮（G2） | P01 | Approved | `plans/03-plant-removal-action.md` |

## 5. Decision

- **Open Decision：无。** 三项会影响实现与验收的选择已由 Human 在 2026-09-29 的本次 Plan 执行中确认；006 条款的记账方式由 CD-03 定义。具体选项与影响已写入各 Plan 的 §5。
- **Confirmed Decision（摘要）**
  - CD-01：机制定稿为"代码代攒钱"（`await_plan` + surplus 规则），不采用"只给事实、由模型弃选项表达攒钱"。
  - CD-02：中断条件为 `{high, critical}` 或"该行有僵尸且无攻击植物"；`medium` 不再中断。
  - CD-03：不回改 006 已交付 artifact；由 009 逐条引用并声明取代 OD-29 与 OD-38/冷启动第 6 条，同时记录 R28 让位于 R29/OD-43。
  - CD-04：真机 Case A/B 观察为 G2 非阻塞，升级条件见 P01 V1。
  - CD-05：证据脚本升格为入库工具，不额外编写 loop 级场景脚本。
  - CD-06：保留工作区已落地的 plan/economy 改动（5 个源文件 + 4 个测试文件，~855 行），由 `$sdd-implementation 009` 逐 Task 核对/修正/补测/回填并落地唯一未实现的 T2；不做整体回退重写。
  - CD-07：铲除能力并入本 Iteration 作 P03（不另开 010、不只做记录）。
  - CD-08：铲除以 plant 分支同一次 fan-out 请求里的独立 Choice 接入（不新增第三分支）；一次决策最多一个动作，两层同时命中时铲除优先并记录被丢弃的放置。
  - CD-09：请求在“有放置候选或可铲格”时发出（可能只含铲除层）；`await_plan`（P01 R2）保持最高优先级，该轮不发请求、棋盘不变；无可铲格时不追加铲除子问题。

## 6. Task

执行顺序与依赖：

1. **P01 T1 → T3 → T4**（核心链路：候选上下文 → 事实下发 → 本地等待与守卫）。工作量最大且已有工作区实现，Implementation 阶段先核对现状再回填。
2. **P01 T2**（中断档位收窄）可在 T1/T3/T4 之后单独完成，属本 Iteration 唯一尚未落地的新代码改动。
3. **P01 T5**（Case A/B 测试）依赖 T1–T4 的最终语义，必须包含 T2 的改写用例。
4. **P01 T6**（文档与条款取代记录）最后执行。
5. **P02 T1 → T2 → T3** 依赖 P01 的符号与规则稳定；可与 T6 并行。
6. **P03 T1 → T2 → T3 → T4 → T5 → T6** 必须在 P01 之后（共用 `client.py`/`decision.py`/`loop.py`/`trace.py`）；其中 T4 的仪表盘部分与 T6 文档可在 T5 前并行。

每条 Task 的目标、影响文件与 Implementation backfill 见对应 Plan 的第 6 节；验收意图与验证方法见各 Plan 第 7 节。

## 7. Validation

### Current delivery boundary

- **本次产物与实际用途**：把已经在工作区落地（未提交）的 plan/economy 改动纳入受控 Iteration，成为后续 `$sdd-verify 009` / `$sdd-delivery 009` 的唯一范围依据；同时为 Case A/B 提供一条离线可复现证据路径。
- **本次交付成功的最小条件**：R1–R7、R9、R10 **以及 R11–R15** 的 G1 检查全部通过（含全量 `unittest discover` 全绿、离线对照输出与记录一致、一次决策最多一个动作与铲除优先已测试）；CD-02 的中断档位已在代码与测试中体现。
- **不作为本次交付门槛的场景**：真机 Case A/B 观察（R8/G2，需 Human 授权与真实 API）；模型是否主动声明更高价值目标（G3）；仪表盘铲除点亮（R16/G2）与真机 Replace/Upgrade 观察（R17/G2）。

### Verification tiers

| Tier | Meaning | Handling in Verify |
|---|---|---|
| G1 核心路径 | 直接决定本次目标能否实现或结果是否可信 | 必须取得充分通过证据；失败或缺少必要证据影响交付 |
| G2 当前风险 | 当前可能遇到，但不必然妨碍核心路径 | 如实记录影响；Human 明确接受的剩余风险不阻塞交付 |
| G3 后续场景 | 主要针对未来用途，不属于本次目标 | 可暂缓验证；记录理由和未来重查条件 |

验证顺序：先跑 P01 的自动化检查（V1–V8，覆盖候选、攒钱、中断、surplus、无目标回归、请求态与守卫、全量测试），再做 P01 的离线对照与条款一致性手工检查（V1/V4/V9/V10），然后跑 P02 的工具检查（V11/V12/V14），**最后跑 P03 的检查（V15–V19 自动化 + V20 呈现层）**；P03 的 V15–V19 都依赖 P01 的符号稳定。真机观察（V13 Case A/B、V21 Replace/Upgrade）均为 G2，未执行不阻塞交付，但必须如实写入 `verify.md`。

自动化：V1–V8、V11–V12、V14 的 grep、V15–V20、V22；手工：V9/V10 的条款与文档对照、V13/V21 的真机记录。本 Iteration 不涉及浏览器验证（V20 由 `tests.test_web` 的 DOM/字符串断言覆盖）。

## 8. Risks

- **工作区已有实现**：P01 的多数改动已在 direct 任务中落地（未提交，见 `.log/2026-09-29-plan-economy-root-cause.md`）；Implementation 必须"核对 + 补测 + 回填"，不得重复实现或覆盖 Human 侧修改。T2 是唯一尚未落地的新改动。
- **T2 会推翻既有断言**：`test_a_medium_or_closer_lane_band_also_outranks_the_goal` 当前断言 medium 中断，与新决定相反；漏改会让 V3 失败并阻塞交付。
- **模型行为不由代码保证**：本次只保证候选空间与等待语义；"富余时是否真的会选高成本牌"是模型侧问题，属 G2/G3。
- **与已交付 008 的边界**：008 已交付（commit `d3071b2`，含 `jev/scheduler.py` 的 collect `poll_interval_ms`）；本 Iteration 不触碰 `jev/scheduler.py` 与 `tests/test_jev_scheduler.py`，避免混入已交付行为。
- **已交付文档早于代码**：`docs/architecture.md` 的经济段落已随 `007` 的提交 `7da972d` 进入已推送历史，对应代码在本 Iteration 才交付；Delivery 记录必须注明该时序。
- **006 条款冲突已用取代方式处理**：`OD-29` 原文"不做阳光预留"与 `OD-38/冷启动第 6 条`原文"攒钱由模型选 `none_of_the_above` 表达"仍留在 006 artifact 中；若读者只看 006，会认为当前实现越界。CD-03 要求 009 引用原文并写明取代，Delivery 后应把 `.memory` 的 Open Decision 一并关闭。
- **真机证据依赖 Human**：V13/V21 不会由 agent 自动执行；长期未执行时，Case A/B 与 Replace/Upgrade 的现场结论保持“未取得”。
- **（P03）仲裁语义**：两层同时命中时铲除优先会丢弃一次已选中的放置（下一轮随 `occupied_cells` 变化自动重问）；若 Human 认为应改为放置优先，属 Plan 修订（影响 V15）。
- **（P03）`_last_result` 形状**：该字段进入 collect 分支 key 的 `repr` 与 prompt 上下文；把 `action=plant` 写死改为通用 action 时必须同步所有读取点，否则会产生意外的 key 抖动。
- **（P03）与 P01 同批符号**：P03 与 P01 共用 `client.py`/`decision.py`/`loop.py`/`trace.py`，实现顺序必须先 P01 后 P03，不得在同一次编辑里混淆两层语义。
- **（P03）叠层格与诚实性**：执行器不承诺移除堆叠中的某一株；选项文本、Trace 与仪表盘都必须保持“移除该格植物”而非“移除指定实体”，且铲除不得被标成种植。

## 9. Approval

- Status: Approved
- Approved by: 本仓库维护者（Human）
- Approval date: 2026-09-29
- Notes: Human 于 2026-09-29 明确回复“approved 009”。批准覆盖 Iteration 与 P01/P02/P03 三个具体 Plan；§5.1 无阻塞性 Open Decision，CD-01–CD-09 均为已确认或已记录的决策。批准后第一步为 `$sdd-implementation 009`（先核对工作区既有改动，再落地 P01 T2 与 P03）；本阶段不执行实现、Verify、Delivery 或 commit/push。
