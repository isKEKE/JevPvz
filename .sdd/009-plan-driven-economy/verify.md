# Verify

## 1. Verification Metadata

- Iteration: `009-plan-driven-economy`
- Verified at: 2026-09-29（UTC+8，本机时钟）；**2026-10-04 复核并依 Human 裁定再审**
- Executor: 独立验证 agent（fresh context，未参与本 Iteration 任何实现）；2026-10-04 由主 agent 在当前上下文复核
- Execution mode: Delegated verifier（`deepseek/deepseek-flash`，thinking off，由 Human 显式指定；未再委派任何 agent）；2026-10-04 主 agent 复核
- Overall result: **Passed（2026-10-04，依 Human 裁定；原判 Blocked）**
- Verification execution: Complete

> **2026-10-04 复核摘要**：工作树逐字节未变（`HEAD = d4c4fbc`、无 staged 文件）；定向 **286 OK**、`tests.test_web` **46 OK**、全量 **493 tests OK**、两个 JS `node --check` 通过，与 09-29 完全一致。Human 就 V11 作出裁定（「裁定本次不适用」，并指示「有 log/trace 就直接查看；没有则记录 Human 已人工验证、但代码无记录」）。据此：**直接从入库 Trace 独立复现**（§5-V11 替代证据）已取得 P02 对照的核心语义结果；唯一仍缺的只是 P01/P02 声明的**那个特定 run**（`3e6e1b07…`）的数字。Human 接受该剩余风险，V11 降为非门槛并记入 §9。G2 的 V13/V21 现场观察仍 **Not run**（Human 本轮未提供现场记录），不阻塞交付。

说明：本文件的唯一写入者是验证 agent；生产代码、测试、Plan、`.memory/*`、`.gitignore`、dashboard 静态资源一律未改（`git status --short` 见 §5）。未执行 `git add/commit/push`，未运行游戏、`main.py action`、`main.py jev-loop`、`serve` 或任何网络/API 命令。

## 2. Baseline Reviewed

- Original requirement source: Human 2026-09-29 需求摘要（Case B 候选不得被模型声明的目标截断；Case A 目标差钱且无中断行时本地攒钱；中断档位收窄为 `{high, critical}` 或「有僵尸且无攻击植物」；CD-07/CD-08 同一次 plant 请求内可铲除一格、一次一动作、铲除优先；CD-05 证据工具入库）。
- Plan Index revision/state: `.sdd/009-plan-driven-economy/plan-index.md`，Status **Approved 2026-09-29**（Human 回复 “approved 009”），CD-01–CD-09 已记录，无阻塞性 Open Decision。
- Concrete Plans reviewed（完整读取）:
  - `plans/01-plan-driven-offer-policy.md`（P01，R1–R7/R10，V1–V10）
  - `plans/02-economy-evidence-tool.md`（P02，R8/R9，V11–V14）
  - `plans/03-plant-removal-action.md`（P03，R11–R17，V15–V22）
- Implementation diff/revision: `HEAD = d4c4fbc`；本 Iteration 全部改动**未提交、无 staged 文件**。工作树 20 个已跟踪文件被修改（`+1876/−134`），另有 6 项未跟踪（`tools/evidence-plan-economy.py`、`tests/test_economy_evidence.py`、`.sdd/009-plan-driven-economy/`、`.log/2026-09-29-plan-economy-root-cause.md`、`.log/jev-dashboard.jsonl`、`.log/jev-dashboard-process.log`）。
- Current delivery goal and use: 让「资源充裕 → 高价值牌入选」「缺钱 → 主动攒钱」「升级/替换需先铲除」在自主 Runtime 中可发生；交付物 = 代码 + 测试 + 文档 + 入库离线证据工具。
- G1 minimum success conditions: P01 V1–V9、P02 V11–V12、P03 V15–V19 与 V22 取得充分通过证据；CD-02 的档位取值在代码与测试中体现。
- Excluded or future scenarios: V13（真机 Case A/B）、V21（真机 Replace/Upgrade）为 G2；V10（文档一致性）、V14（文档卫生）、V20（呈现层）以下按 Plan 分级处理；G3 = 模型是否主动声明高价值目标。
- Runtime environment and current state: Windows；`uv`、`node` 可用；**不需要**游戏进程、`.env` 或 API。工作树逐字节未改（未做变异测试）。
- Check executor: delegated verifier（本 agent）执行全部自动化与只读命令；Human 仅提供一项页面呈现观察（§6、§9）。
- State-changing action authority, scope, limits, and recovery/stop conditions: 仅允许写 `.sdd/009-plan-driven-economy/verify.md`；禁止修改生产代码/测试/Plan/memory、禁止 git 写操作、禁止运行游戏与网络命令。验证中发现**不**为取证而改写任何文件；`tools/evidence-plan-economy.py` 只读性由调用前后 sha256 对比独立复核（§5）。

## 3. Requirement Traceability

| Requirement ID | Plan / Task | Check ID and tier | Implementation evidence | Verification evidence | Observed result | Delivery disposition |
|---|---|---|---|---|---|---|
| R1 目标可支付时候选 = 目标 + surplus 可支付的牌；高成本牌重回候选/请求态 | P01 / T1,T5 | V1、V4 / G1 | `jev/strategy.py::plant_spend_decision`（surplus 分支）、`build_plant_candidates(plan=)`；`jev/client.py::build_plant_questions(plan=)`、`decide_plant` 去手牌过滤 | 独立探针（4 价手牌 50/100/200/300、目标 sunflower）：sun50→仅目标 45cand；sun100→仅目标（peashooter 不可付 surplus=50）；sun150→目标是 peashooter；sun250→+repeater；sun350→+melon_pult（§5）。测试 `test_case_b_*`、`test_a_payable_goal_*` 全绿 | **Passed**（代码可确定部分） | Accept |
| R2 目标不可支付且无中断行 → `await_plan`、无请求、无动作 | P01 / T4,T5 | V2 / G1 | `jev/strategy.py::PLAN_HOLD_REASON`、`plant_spend_decision`；`jev/loop.py::_local_wait_reason`；`jev/trace.py::RELIABLE_OUTCOMES` | 探针：sun150/目标 melon_pult(300)、无僵尸 → `hold_reason=await_plan`、0 cand；`RELIABLE_OUTCOMES` 含 `await_plan`；`test_case_a_*`（strategy/client/loop）与 `test_await_plan_is_a_reliable_local_conclusion` 全绿 | **Passed** | Accept |
| R3 中断条件 = `{high,critical}` 或「有僵尸且无攻击植物」；`medium` 不中断 | P01 / T2,T5 | V3 / G1 | `jev/strategy.py::LANE_RESPONSE_URGENCIES`、`lane_needs_response` | 探针：`LANE_RESPONSE_URGENCIES == frozenset({"high","critical"})`；带 peashooter 的 medium 行（distance=4）→ urgency=medium、`lane_needs_response=False`、`hold=await_plan`；high 行（distance=3，带 peashooter）→ `needs=True`、`hold=None`；有僵尸无攻击植物（distance=8，urgency=low）→ `needs=True`（§5）。改写用例 `test_a_medium_lane_band_keeps_saving_and_high_does_not` 全绿 | **Passed** | Accept |
| R4 无目标时与 OD-15 全枚举一致（无 local shortlist/截断） | P01 / T1,T5 | V5 / G1 | `build_plant_candidates` 无 plan 路径 | 探针：sun400/3 种手牌/45 空格、无 plan → 135 cand = 3×45、`hold=None`；`PlantCandidateTests`、`test_no_plan_keeps_the_full_enumeration_and_never_holds` 全绿 | **Passed** | Accept |
| R5 请求态 economy 事实组；band 边界只来自本手牌价格，无配置化阳光阈值 | P01 / T3,T5 | V6 / G1 | `economy_facts`/`plan_facts`/`economy_band`/`card_price_band`；`jev/questions.py::PLANT_STATE_FIELDS`（含 `economy`）、`ECONOMY_ANCHOR`、`_plant_economy_guidance`；`jev/trace.py::_economy_record`、`_actual_request_state` | 探针：`economy_band` 边界全部由手牌阶梯推出（49/50 on (50,)→scarce/abundant；99/100/299/300 on (50,100,300)→normal/comfortable/comfortable/abundant）；`card_price_band`→low/mid/high；`PLANT_STATE_FIELDS` 第 114 行含 `economy`（`COLLECT_STATE_FIELDS` 继承）；`ECONOMY_ANCHOR` 经 `_plant_economy_guidance()` 追加到三处 plant instructions（含 `shovel_target`）；`test_all_current_plant_questions_reference_supplied_observations`、`test_all_three_state_the_resource_facts_and_the_offer_rule`、trace 白名单往返用例全绿。**未发现任何配置化阳光阈值**：`ECONOMY_ANCHOR` 与 `economy_facts` 无阳光常量，`configs/` 无新增经济配置项 | **Passed** | Accept |
| R6 派发守卫不再因「目标类型 ≠ 声明目标类型」拒绝；来源意图版本变化仍拒绝 | P01 / T4,T5 | V7 / G1 | `jev/loop.py::_proposal_source_guard`（无 `intent_type_conflict`，保留 `intent_changed`） | 代码逐行核对：守卫仅 epoch/stale_sample/intent 版本；`test_a_target_outside_the_declared_goal_is_context_not_a_conflict`、`test_stale_plant_intent_is_rejected_before_boundary`（`SharedSourceLifecycleTests`，断言 `error_code == "intent_changed"` 且 `boundary.requests == []`）全绿 | **Passed** | Accept |
| R7 006/007 既有契约不回归 | P01 / T5,T6 | V8 / G1 | 跨 5 个运行时文件的改动 | 全量 `unittest discover` = **493 OK**（§5）；collect 授权/cohort 账本、意图 keep/replace/cancel、Trace schema-2 字段集用例语义未改（仅新增断言） | **Passed** | Accept |
| R8 真机一局 Case A/B 观察有步骤/格式/升级条件（G2） | P02 / T3 | V13 / **G2** | P01 V1 升级条件；P02 Manual checks 步骤 | **Not run**：需 `.env` 与真实 API，且属授权/安全边界（禁止网络与游戏命令）。步骤与记录格式存在（P02 §7 Manual checks） | **Not run（G2）** | 不阻塞；留待 Human，升级条件见 §8 |
| R9 冻结样本对照升格为入库、可参数化、可测试工具 | P02 / T1,T2,T3 | V11、V12 / G1 | `tools/evidence-plan-economy.py`（`--trace-file`、只读、非零退出码）；`tests/test_economy_evidence.py` | **V12 Passed**：`tests.test_economy_evidence` 3 tests OK（含只读 sha256 断言）。**V11 原观察**：工具在 Plan 指定的 `.log/jev-dashboard.jsonl` 上以退出码 2 失败（`no plant decision with source_intent`），该 run 已被覆盖（§5、§7-I1）。**2026-10-04 替代证据（Human 指示「有 trace 就直接查看」）**：直接对**入库** Trace 运行同一工具成功复现对照语义——`test_02.jsonl` job-000287（sun 100 / goal wall_nut）**BEFORE 0 → AFTER 35** placements；`test_05.jsonl` 378 plant decisions、Case A sun150 `hold=await_plan` / sun320 `hold=None` 0 placements / sun400 45 placements `['sunflower']`；两次运行前后输入 sha256 逐字节一致（§5）。**Human 2026-10-04 裁定 V11 本次不适用并接受剩余风险**（§9） | **V12 Passed / V11 原 Failed，经 Human 裁定降为非门槛，附替代证据** | **不阻塞交付**（剩余风险见 §9） |
| R10 OD-29/OD-38 被 009 取代并记录；`docs/architecture.md` 同步 | P01 / T6 | V9、V10 / V9=G1、V10=G2 | 009 plan-index §5 CD-03/R10；`docs/architecture.md:174` | V9：`docs/architecture.md:174` 措辞为 ``no lane is at `high` urgency or higher``（不再是 `medium`）；plan-index §5 与 P01 §5.2 逐条引用 006 OD-29/OD-38/R28-R29 并声明取代。V10：`.log/2026-09-29-plan-economy-root-cause.md:113` 与 :115 已同步为 `high/critical` 并附 T2 回填注 | **Passed** | Accept |
| R11 端到端执行一次 `shovel_cell`；一次决策最多一动作；两层同命中只派发铲除并记录被弃放置 | P03 / T2,T3,T5 | V15 / G1 | `jev/decision.py::combine_plant_decision`/`_shovel_selection`；`jev/loop.py::_dispatch`（`_last_result` 按 action） | `test_a_selected_removal_dispatches_one_shovel_cell_and_records_its_action`、`test_two_selected_layers_dispatch_only_the_removal_and_record_the_drop`、client `test_a_selected_shovel_drops_a_selected_placement_with_a_record` 全绿；merge 记录 `shovel_overrode_placement`/`overridden_placement_option` | **Passed** | Accept |
| R12 可铲候选只来自 `plant:<name>` 格；无可铲格不加铲除层；「有放置候选或可铲格」时才发请求 | P03 / T1,T2,T5 | V16 / G1 | `jev/strategy.py::removable_cells`；`jev/client.py::build_plant_questions`/`_with_shovel_layer`；`jev/loop.py::_local_wait_reason` | 探针：`removable_cells` 只收 `plant:<name>`（`"unknown"`/`False`/`5`/`"plant:"` 空名全忽略；畸形/缺失板 → `()`）；无可铲格 → 无 `shovel_target` 层；放置层为空 + 有可铲格 → 问题集仅 `shovel_target`；两者皆无 → `questions == {}`（保持原有本地等待）；`test_local_wait_reason_asks_whenever_a_placement_or_a_removal_exists` 全绿 | **Passed** | Accept |
| R13 铲除 Choice 自带弃选项，`argmax ≠ 弃选 且 best > 弃选`；无新增 Noul/绝对闸门；选项文本只陈述事实 | P03 / T1,T2,T5 | V17 / G1 | `jev/questions.py::shovel_target_question`/`shovel_option_criteria`；`jev/decision.py::_shovel_selection`（δ=0 严格） | `test_a_discarded_shovel_layer_waits`、`test_a_flat_tie_with_the_shovel_discard_option_waits`、`test_a_discarded_shovel_layer_keeps_the_selected_placement`、`test_the_shovel_option_text_states_only_facts` 全绿；`shovel_target_question` 文本无 should/recommend/best 类建议词，仅行列/类型/角色事实，且明示不承诺叠层指定实体 | **Passed** | Accept |
| R14 新增状态字段进白名单且逐字段相等；instructions 只引用已下发字段；branch key 形状不变 | P03 / T1,T2,T5 | V18 / G1 | `PLANT_STATE_FIELDS` 未新增铲除专用字段；`jev/trace.py::_actual_request_state` 未扩字段；`build_plant_branch_state_key` 复用 `occupied_cells` | 探针：`build_plant_branch_state_key` 仍为 3 元组 `(frozenset, tuple, frozenset)`，形状未变；铲除复用 `occupied_cells`；`RequestFieldAcceptanceTests`、`SharedActualInputParityAcceptanceTests`、`test_a_declared_goal_round_trips_through_the_request_state_whitelist` 全绿 | **Passed** | Accept |
| R15 Trace 如实记录铲除问题/选项/答案/merge 与 `action_result.action == "shovel_cell"`；`_last_result` 记真实 action | P03 / T3,T4,T5 | V19 / G1 | `jev/trace.py::MERGE_REVIEW_KEYS`（9 个 shovel/overridden 键）；`jev/loop.py::_dispatch` 的 `_last_result` 按 `target["action"]` | 探针：`MERGE_REVIEW_KEYS` 含 `shovel_option`/`shovel_selected`/`shovel_discarded`/`shovel_overrode_placement`/`overridden_placement_option`/`shovel_best_option`/`shovel_best_probability`/`shovel_discard_probability`/`shovel_margin`；`test_the_removal_layer_answers_and_execution_are_recorded`（`action_result.target/boundary.action == shovel_cell`，不泄漏 item/plant 内部 id）、`test_a_selected_removal_dispatches_one_shovel_cell_and_records_its_action` 全绿 | **Passed** | Accept |
| R16 成功 `shovel_cell` 点亮对应草坪格且不冒充种植（G2） | P03 / T4,T5 | V20 / **G2** | `dashboard/static/viewmodel.js::shovelExecution`/`buildField`/`pickAuthoritativeQuestion`；`recording.js` 的 TARGET 文案 | **部分通过，存在缺口**：`tests.test_web` 46 OK，含 `test_a_confirmed_removal_lights_its_own_cell_and_never_reads_as_planting`（断言 `/api/jev-options` + `viewmodel.js` 路径）。但 `/jev` 页的固定草坪矩阵走 `dashboard/static/jev-page.js`（**Plan P03 §4.1 影响面未列出该文件**），其 `optionCategory` 不含 `shovel_target`，`dashboard/server.py::_apply_action_result` 只识别 `place_plant`/`collect_item`，**不点亮铲除格**；`grep -n "shovel" dashboard/static/jev-page.js` 无命中 | **Partially passed（G2 缺口）** | 不阻塞 G1；按 Plan 记为 G2 缺口（§7-I3） |
| R17 真机观察 Replace/Upgrade 两步（G2） | P03 / T6 | V21 / **G2** | P03 §7 Manual checks 步骤 | **Not run**：需 `.env`、真实 API 与真机；属授权/安全边界 | **Not run（G2）** | 不阻塞；留待 Human |
| V22 全量回归（含 006/007/008 契约） | P03 / T5 | V22 / G1 | 全量测试 | `uv run python -m unittest discover -s tests -p "test_*.py"` → **Ran 493 tests / OK**（独立复跑，与 P03 §7 声明的 493 一致） | **Passed** | Accept |

补充：`status` 为 **Not run** 的 V13/V21 均为 Plan 明确的 G2，且属授权/安全边界（禁止网络/游戏命令），不是验证执行遗漏；因此 **Verification execution = Complete**。

## 4. Plan and Task Results

| Plan ID | Task ID | Planned outcome | Actual result | G1 impact | Result |
|---|---|---|---|---|---|
| P01 | T1 | 目标降为上下文，手牌过滤删除 | `decide_plant` 已无 `intent["type_name"]` 过滤；候选只经 `plant_spend_decision` 受限 | 支撑 R1/R4 | Passed |
| P01 | T2 | `LANE_RESPONSE_URGENCIES` 收窄为 `{high,critical}`（唯一新代码） | 常量已收窄；两处 docstring 同步；medium 用例已改写为 `test_a_medium_lane_band_keeps_saving_and_high_does_not` | 支撑 R3 | Passed |
| P01 | T3 | economy 事实组与问题语义 | `PLANT_STATE_FIELDS` 含 `economy`；`ECONOMY_ANCHOR` 追加三处 plant instructions；`management_questions(..., economy=)` | 支撑 R5 | Passed |
| P01 | T4 | 本地攒钱、守卫、Trace | `_local_wait_reason` 返回 `await_plan`；守卫无 `intent_type_conflict`；`RELIABLE_OUTCOMES` 含 `await_plan`；`_economy_record` 有界投影 | 支撑 R2/R6/R7 | Passed |
| P01 | T5 | Case A/B 回归测试 | 四个测试文件中 Case A/B 与档位用例齐备且全绿 | 支撑 V1–V7 | Passed |
| P01 | T6 | 文档与条款取代记录 | `docs/architecture.md:174` 已改为 `high`；plan-index §5 记录取代 | 支撑 R10/V9 | Passed |
| P02 | T1 | 升格为入库工具 | `tools/evidence-plan-economy.py` 存在，`--trace-file`、只读、输入错误退出码 2（在缺失文件上实测） | 支撑 R9 | Passed（工具本身） |
| P02 | T2 | 冒烟测试 | `tests/test_economy_evidence.py` 3 tests OK（含只读 sha256 断言） | 支撑 V12 | Passed |
| P02 | T3 | 文档命令与旧脚本下线 | `README.md:80`/`README.zh-CN.md:80`/`docs/usage.md:184` 均指向 `tools/`；`.log/evidence-plan-economy.py` 已删除，无残留 | 支撑 V14 | Passed |
| P02 | — | **V11 在冻结 Trace 上复现对照** | **工具对 `--trace-file .log/jev-dashboard.jsonl` 返回退出码 2**：该文件已被覆盖为 5 行、`source_intent` 计数 0（§7-I1） | **阻塞 R9/V11** | **Failed** |
| P03 | T1 | 可铲候选与铲除问题 | `removable_cells`/`shovel_target_question`/`shovel_option_id`/`shovel_option_criteria` 齐备 | 支撑 R12/R13 | Passed |
| P03 | T2 | 一次请求两问与代码合并 | `_with_shovel_layer`（单层=2、lane 链后=3）；`_shovel_selection` 严格 δ=0；铲除优先 | 支撑 R11/R13 | Passed |
| P03 | T3 | Runtime 提案与结果记录 | 请求条件改为「有放置候选或可铲格」；`_last_result` 按真实 action | 支撑 R11/R15 | Passed |
| P03 | T4 | Trace 与仪表盘 | Trace merge 键齐备；`viewmodel.js`/`recording.js` 已有铲除点亮；**`jev-page.js` 未改** | 支撑 R15；R16 部分 | Partially passed（G2 缺口） |
| P03 | T5 | 测试 | 新增 20 个用例；定向 286 OK、`tests.test_web` 46 OK | 支撑 V15–V20 | Passed |
| P03 | T6 | 文档 | `docs/architecture.md` 与 `docs/usage.md` 已补铲除语义 | 支撑 R11–R13 可读性 | Passed |

Plan 与仓库不一致（记录，不修复）：
- P01 §7 与 P02 §7 声称全量为 `Ran 473 tests`、P03 §7 声称 `Ran 493 tests`；**493 与仓库现状一致**（独立复跑），但 P01/P02 的 473 是 P03 未落地时的中间态，属历史快照而非错误。
- P03 §7 的 「20 个新用例」逐类计数与实测一致（strategy 5 / client 10 / loop 3 / trace 1 / web 1 = 20；473+20=493）。
- P01 §7 Implementation evidence 引用的 `.log/evidence-plan-economy.py` 已在 P02 T3 删除，属预期演进。

## 5. Commands Run

| Check ID / tier | Command | Observed result | Evidence / important output |
|---|---|---|---|
| V1–V7 / G1 | `uv run python -m unittest tests.test_jev_strategy tests.test_jev_client tests.test_jev_loop tests.test_jev_trace tests.test_economy_evidence` | **passed** | `Ran 286 tests in 6.345s` / `OK` |
| V15–V20 / G1+G2 | `uv run python -m unittest tests.test_web` | **passed** | `Ran 46 tests in 14.031s` / `OK` |
| V8、V22 / G1 | `uv run python -m unittest discover -s tests -p "test_*.py"` | **passed** | `Ran 493 tests in 23.217s` / `OK`（与 P03 §7 的 493 一致） |
| V11 / G1 | `uv run python tools/evidence-plan-economy.py --trace-file .log/jev-dashboard.jsonl` | **failed** | stdout 空；stderr `error: F:\projects\JevPvz\.log\jev-dashboard.jsonl: no plant decision with source_intent`；**退出码 2**。无法复现 36/1→360/10 与 Case A 三档 |
| V11 只读性 / G1 | `sha256sum .log/jev-dashboard.jsonl`（运行前后各一次） | **passed** | 前后均 `c0275dd55b922dd1deae9f3808b3bd0cb3b7c67c53892b63d7bc23d5553262a3` → 工具不修改输入 |
| V11 负例 / G1 | `uv run python tools/evidence-plan-economy.py --trace-file .log/does-not-exist.jsonl` | **passed** | stderr `error: trace file not found: F:\projects\JevPvz\.log\does-not-exist.jsonl`；退出码 2 |
| V11 交叉核对（只读） | `uv run python tools/evidence-plan-economy.py --trace-file .log/test_02.jsonl`（等） | **passed（工具可用）** | `test_02.jsonl`：214 plant decisions，`job-000287 sun 100` BEFORE 0 → AFTER 35；`test_05.jsonl`：378 plant decisions，`job-000028 sun 50` BEFORE 43 → AFTER 43。证明工具本身可用，失败原因是**输入 Trace 已非冻结样本** |
| V11 **替代证据**（2026-10-04 复核） / G1 | `uv run python tools/evidence-plan-economy.py --trace-file .log/test_02.jsonl`；`--trace-file .log/test_05.jsonl` | **passed** | `test_02.jsonl`：214 decisions / 手牌 10 种；`job-000287 sun 100 goal wall_nut(50)` → **BEFORE 0 placements [] → AFTER 35 placements ['sunflower']**（即需求所述「目标截断」现象）；`job-000290 sun 125` → 0 → 35。`test_05.jsonl`：378 decisions；**Case A sun 150 → `hold=await_plan`（0 placements）；sun 320 → `hold=None`（0 placements）；sun 400 → 45 placements `['sunflower']`**；`job-000033 sun 50 goal squash(50)` → 0 → 0。两者均为**入库**文件，可长期重跑 |
| V11 只读性 **复核**（2026-10-04） / G1 | `sha256sum .log/test_05.jsonl .log/test_02.jsonl`（运行前后各一次） | **passed** | 前后均为 `af78ebfc…cf9902`（test_05）/ `c5a1af9b…4df793`（test_02）→ 工具不修改输入 |
| 2026-10-04 复核：定向 / G1 | `uv run python -m unittest tests.test_jev_strategy tests.test_jev_client tests.test_jev_loop tests.test_jev_trace tests.test_economy_evidence` | **passed** | `Ran 286 tests in 5.639s` / `OK` |
| 2026-10-04 复核：web / G2 | `uv run python -m unittest tests.test_web` | **passed** | `Ran 46 tests in 13.511s` / `OK` |
| 2026-10-04 复核：全量 / G1 | `uv run python -m unittest discover -s tests -p "test_*.py"` | **passed** | `Ran 493 tests in 22.712s` / `OK`（与 09-29 及 P03 §7 一致） |
| V6/V12 静态 / G1 | `node --check dashboard/static/viewmodel.js`；`node --check dashboard/static/recording.js` | **passed** | 两条命令均无输出（语法通过） |
| 基线复核 | `git status --short`；`git diff --cached --stat`；`git diff --stat` | **passed** | `--cached` 为空（**无 staged 文件**）；工作树 20 个已跟踪文件修改 `+1876/−134`，6 项未跟踪；`HEAD = d4c4fbc` |
| V14 / G2 | `grep -rn "evidence-plan-economy" README.md README.zh-CN.md docs tests tools` | **passed** | 5 处命中全部指向 `tools/evidence-plan-economy.py` 自身（README×2、usage、test、tool 文档串），**无 `.log/evidence-plan-economy.py` 残留** |
| V9/V10 / G1+G2 | `grep -n "medium\|high" docs/architecture.md`；`grep -n "medium\|high" .log/2026-09-29-plan-economy-root-cause.md` | **passed** | `docs/architecture.md:174` = ``no lane is at `high` urgency or higher``；根因文档 :113/:115 已同步 `high/critical` 并注明 T2 回填 |
| V1/V4/V5/V6/V16 独立探针 / G1 | `uv run python -c "..."`（直接调用已实现函数，只读） | **passed** | 见 §3 各行与下方「探针输出」 |
| V1 真实 Trace 复核 / G1 | `wc -l .log/jev-dashboard.jsonl`；`grep -c source_intent ...`；`grep -c '"job_start"' ...` | **failed（发现反例）** | 当前文件仅 **5 行**、`source_intent` **0 次**、`job_start` 2 次（job-000001 plant + job-000002 collect，均 `state: null`、`job_end=cancelled`、`run_id=707bd5d5…`）。P01/P02 依赖的 run `3e6e1b07…`（305 事件、job-000010/16、sun 7300/7375）**已不在该文件**，`jev-dashboard-process.log` 中也检索不到该 run id |

探针输出（关键摘录，均由本 agent 独立构造的状态复算，非引用测试名）：

```text
V3 LANE_RESPONSE_URGENCIES = ['critical', 'high']   PLAN_HOLD_REASON = await_plan
V6 economy_band(49,(50,))=scarce   (50,(50,))=abundant
V6 economy_band(99,(50,100,300))=normal   (100)=comfortable   (299)=comfortable   (300)=abundant
V6 card_price_band(50/100/300, (50,100,300)) = low / mid / high
V1/V4 手牌 50/100/200/300，目标 sunflower(50)：
  sun 49  affordable []                                    hold=await_plan  #cand 0
  sun 50  allowed ['sunflower']                            hold=None        #cand 45
  sun 100 allowed ['sunflower']                            hold=None        #cand 45   (surplus 50 付不起 peashooter 100)
  sun 150 allowed ['peashooter','sunflower']               hold=None        #cand 90
  sun 250 allowed ['peashooter','repeater','sunflower']    hold=None        #cand 135
  sun 350 allowed [全部 4 种，含 melon_pult(300)]           hold=None        #cand 180
V2 sun150 目标 melon_pult(300) 无僵尸 → hold=await_plan, 0 cand
V3 medium(distance=4,1 僵尸,带 peashooter) → urgency=medium, needs=False, hold=await_plan
V3 high(distance=3,1 僵尸,带 peashooter)   → urgency=high,   needs=True,  hold=None, allowed=['peashooter','sunflower']
V3 low(distance=8,1 僵尸,无攻击植物)        → urgency=low,    needs=True,  hold=None   (独立条件仍中断)
V5 无 plan：affordable 3 种 × 45 空格 = 135 cand，hold=None
V16 removable_cells 只收 plant:<name>；'unknown'/False/5/'plant:' 空名忽略；畸形/缺失板 → ()
V16 无可铲格 → questions 无 shovel_target；仅可铲格 → 只有 shovel_target(level 2)；两者皆无 → questions == {}
V16 255 链：10 种 ×45 = 450 > 255 → split=True，
    levels = [plant_target_lane(1,6), plant_target_lane_0..4(2,91/91/91/91/81), shovel_target(3,2)]
V18 build_plant_branch_state_key 形状 = 3 元组 (frozenset, tuple, frozenset)，未变
V19 MERGE_REVIEW_KEYS 含 shovel_option/shovel_selected/shovel_discarded/
    shovel_overrode_placement/overridden_placement_option/shovel_best_option/
    shovel_best_probability/shovel_discard_probability/shovel_margin
```

## 6. Manual / Browser Verification

| Check ID / tier | Check | Observed result | Evidence / human source and date |
|---|---|---|---|
| V11 / G1 | 人工运行离线对照命令，逐行比对 P01/P02 声明的三个数字组（BEFORE 36/1 种 → AFTER 360/10 种；Case A sun150 `await_plan`、sun320 仅 `melon_pult`、sun400 目标+便宜牌） | **无法比对**：工具在当前 Trace 上退出码 2，未产生任何 BEFORE/AFTER 行 | 本 agent 2026-09-29 实跑（§5）；对 `.log/2026-09-29-plan-economy-root-cause.md` §5 的对照只能读到文档声明，无法从 Trace 独立复算 |
| V11 / G1 | 核对根因文档 §5 的声明是否与 Trace 存在性一致 | **不一致**：文档 §1 引用 `.log/jev-dashboard.jsonl`（run `3e6e1b07…`、305 事件、17:06:17–17:10:41 UTC），但当前该文件为 run `707bd5d5…`、5 行 | `grep -c "3e6e1b07" .log/jev-dashboard-process.log` → **0** |
| V20 / G2 | Human 查看页面呈现 | Human 2026-09-29 表示「我已经验证还可以」，**范围仅为页面呈现**；未提供具体观察项、截图，也未区分 `/` 与 `/jev` | Human 口头，2026-09-29（经任务书转述）。**不得据此记为「页面检查通过」** |
| V20 / G2 | `/jev` 页固定草坪矩阵是否点亮铲除格（代码核对） | **不点亮**：`dashboard/static/jev-page.js` 的 `PLANT_QUESTIONS = {plant_target, plant_target_lane}` 与 `optionCategory()` 均不含 `shovel_target`，`grep -n "shovel" dashboard/static/jev-page.js` **无命中**；`dashboard/server.py:493 _apply_action_result` 只处理 `place_plant` 与 `collect_item`（`action == "shovel_cell"` 不点亮） | 本 agent 2026-09-29 代码核对 |
| V20 / G2 | `/`（`recording.js` + `viewmodel.js`）路径 | 已有实现：`viewmodel.js::shovelExecution` 要求同 job、`boundary_status == "success"`、`target.action == "shovel_cell"`、行列精确，再点亮并读作「铲除」；`recording.js` 的 TARGET 对格上动作显示行列 | 本 agent 2026-09-29 代码核对 + `tests.test_web` 46 OK |
| V3/V9 / G1 | 阅读档位取值与取代记录 | `LANE_RESPONSE_URGENCIES = frozenset({"high","critical"})`；`docs/architecture.md` 与 009 plan-index §5 一致 | 本 agent 2026-09-29 |

## 7. Issues Found

### I1（原 G1，已经 Human 裁定降为非门槛）P02 V11 的证据输入已消失，工具在声明的默认路径上失败

- 检查 ID：V11 / R9（G1）
- 复现：`uv run python tools/evidence-plan-economy.py --trace-file .log/jev-dashboard.jsonl` → 退出码 **2**，`error: … no plant decision with source_intent`。
- 事实：当前 `.log/jev-dashboard.jsonl` 仅 **5 行 / 3988 字节**（mtime 2026-09-29 16:51），含 `job_start`×2 + `job_end`×2 + `runtime_stop`×1，`source_intent` 出现 **0** 次；两个 job 的 `state` 均为 `null`、`job_end.outcome` 均为 `cancelled`、`run_id = 707bd5d5…`。P01 §7/P02 §7 与根因文档 §5 所依赖的 run `3e6e1b07…`（305 事件、job-000010 sun 7300、job-000016 sun 7375）**已不在该文件**，且在 `.log/jev-dashboard-process.log` 中也检索不到该 run id（`grep -c "3e6e1b07"` → 0）。
- 因果：`.log/jev-dashboard.jsonl` 是 Dashboard/Loop 的**实时输出文件**（`docs/usage.md:74` 说明 `serve` 默认写该路径），**未纳入版本控制、未被 `.gitignore` 忽略但也不在 HEAD**（`git cat-file -e HEAD:.log/jev-dashboard.jsonl` → 不存在）。因此任何后续 Dashboard/Loop 运行都会**原地覆盖**它；本次被覆盖后，P01/P02 的「同一冻结样本」证据不再可从仓库复现。
- 影响路径：V11 是 P02 唯一的 G1 证据路径（Plan 原文：「这是 Case A/B 离线证据的唯一复现路径」）；V1/V4 的**真实 Trace 复核**部分（36/1→360/10、Case A 三档）随之失去可复查基线。G1 的**代码可确定部分**（V1–V7 的规则本身）已由本 agent 的独立探针与 286 项定向测试充分覆盖，因此本条不构成「核心目标有可复现缺陷」，而是**必要证据缺失且无等价替代**。
- Verify 处置（2026-09-29）：**记录，不修复**（验证不修复；且 .log 证据文件不在授权写入清单内）。
- **2026-10-04 处置（依 Human 裁定）**：本条**不构成产品缺陷**这一判断得到完全确认——工具本身可用且只读，已由**入库的** `test_02.jsonl` / `test_05.jsonl` 独立复现出与 R9 声明同构的对照语义（含 Case A 三档：`await_plan` / goal-only / goal+surplus）。Human 明确裁定 V11 本次不适用并接受剩余风险（§9）。原 `Failed` 观察**保留不改写**；差异仅在于：P01/P02 与根因文档引用的**那个特定 run**（`3e6e1b07…`、305 事件、sun 7300/7375）的精确数字仍无法复算，属**证据可追溯性**问题而非语义真实性问题。

### I2（非阻塞，G2 一致性）根因文档的「冻结」声明与仓库现状不符

- 检查 ID：V11（附带）
- `.log/2026-09-29-plan-economy-root-cause.md` §1 把 `.log/jev-dashboard.jsonl` 描述为固定的 run `3e6e1b07…`（305 事件），但该 run 已不在该路径。文档措辞暗示该文件是稳定证据，实际是易失的实时输出。建议在 Delivery 说明中改为「当时的 run id + 事后不可复现」，或把冻结切片另存为带日期的只读证据文件。
- 影响：文档卫生与证据可追溯性，不影响代码行为。

### I3（非阻塞，G2 缺口）`/jev` 页矩阵不点亮铲除格

- 检查 ID：V20 / R16（G2）
- 事实：`dashboard/static/jev-page.js` 的 `PLANT_QUESTIONS`/`optionCategory()` 不含 `shovel_target`；`dashboard/server.py:493 _apply_action_result` 只识别 `place_plant`/`collect_item`。因此 `/jev` 页（`docs/usage.md:74` 描述的「固定的 5×9 草坪矩阵」）**不会点亮铲除格**。
- 与 Plan 的关系：P03 §4.1 的影响面把「仪表盘」指向 `dashboard/static/viewmodel.js`（+ `recording.js`）与 `tests/test_web.py`，**未列出 `jev-page.js` 或 `server.py`**。故这是 Plan 覆盖范围的缺口，而非实现越界；`tests.test_web` 的 46 OK 覆盖的是 `/api/jev-options`+`viewmodel.js` 路径。
- Human 证据不可用于弥补：Human 仅表示「页面呈现还可以」，未区分 `/` 与 `/jev`、未给出观察项，**不得据此记为页面检查通过**。
- 与 G1 的因果距离：R16 本身是 G2；Trace 已是事实权威，`/` 页已能点亮。因此**不阻塞 G1**，也不得写成「通过」。

### I4（非阻塞，范围观察）`configs/plant_experience.txt` 变更不在三份 Plan 的 Impact Surface 内

- 事实：`git diff` 显示 `configs/plant_experience.txt` 被修改（第 2/3/7/9 条措辞微调，并新增第 11 条「very_close/at_the_door 时优先近战攻击植物」）。
- 与 Plan 的关系：三份 Plan 的 §4.1 均未列出该文件。它通过 `load_plant_experience()` 追加到 plant instructions，属**模型提示内容**而非决策代码，且不改变候选/等待/守护语义（V1–V19 全部探针与测试独立通过）。
- 影响：仅影响模型看到的手感文本；不构成 R1–R17 的语义越界，也不改变 G1 结论。记录供 Delivery 判断是否需补记范围。

## 8. Missing Evidence and Blockers

| Check ID / tier | Missing evidence or deferred check | Cause category and reason | Current delivery impact | Recheck trigger |
|---|---|---|---|---|
| V11 / G1 → **降为非门槛（Human 裁定）** | 工具在 `--trace-file .log/jev-dashboard.jsonl` 上的 **原特定 run** `3e6e1b07…` 的 BEFORE 36/1 种 → AFTER 360/10 种与 job-000010/16 的 sun 7300/7375 数字 | **other：证据输入被后续运行覆盖**（非外部条件、非授权边界、非验证执行遗漏）。当前 Trace 无 `source_intent`，工具按设计 fail closed 返回退出码 2 | **不再阻塞**：Human 2026-10-04 裁定本次不适用并接受剩余风险（§9）；对照**语义**已由入库 Trace 独立复现（§5） | 若需复算该精确 run：恢复其 305 事件切片到 `--trace-file` 路径，或接受以入库 Trace 为基线并在后续 Iteration 修正 P01/P02/根因文档中的路径与数字声明 |
| V13 / G2 | 真机一局 Case A/B 观察记录（`.log/009-live-case-ab-<date>.md`） | 外部条件（需真实 API/游戏）+ 授权或安全边界（禁止网络与游戏命令） | 不阻塞（P01 CD-04 明确 G2） | Human 执行 P02 §7 Manual checks 并落盘记录；若出现「目标已可支付且余额有富余但候选仍只含目标类型」→ 升 G1 |
| V21 / G2 | 真机 Replace/Upgrade 两步观察记录（`.log/009-live-shovel-<date>.md`） | 外部条件 + 授权或安全边界 | 不阻塞（P03 明确 G2） | Human 执行 P03 §7 Manual checks；若实机出现误点或无法确认铲除 → 升 G1 |
| V20 / G2 | `/jev` 页铲除格点亮的实现与断言 | 验证执行范围内只需记录（Plan 未把 `jev-page.js`/`server.py` 列入影响面）；已按缺口如实记录（I3） | 不阻塞 | Human 要求 `/jev` 页也呈现铲除，或 R16 被升级为 G1 |
| V10 / G2 | — | 已取得充分证据（根因文档档位已同步） | 无 | — |

注意：V13/V21 的 **Not run** 不是验证执行遗漏；本 agent 已执行所有授权且可执行的 G1 检查（包括 2026-10-04 的替代证据路径），故 **Verification execution = Complete**。

## 9. Human Decisions and Accepted Risks

| Check ID | Original tier / observed result | Decision and source/date | Reason and applicable scope | Remaining risk / recheck trigger |
|---|---|---|---|---|
| **V11** | **G1 / Failed**（指定 Trace `.log/jev-dashboard.jsonl` 退出码 2，无 BEFORE/AFTER） | **Human 2026-10-04：裁定 V11 本次不适用，接受剩余风险**；并指示「**有 log 或 trace 就直接查看；没有则记录 Human 已人工验证但代码无记录**」。据此已对**入库** Trace 直接查看并复现对照语义（`test_02.jsonl` 0→35、`test_05.jsonl` Case A 三档；§5） | **本次交付范围**：R9 要的是「冻结样本对照可复现、可参数化、可测试」；这一机制已成立（工具、`--trace-file`、只读、退出码、3 个冒烟测试）。被裁定不适用的是**对该特定 run 数字的复算**，它影响的仅是 P01/P02 与根因文档中的**文字数字可追溯性**，不改变代码行为语义。原级别 G1、原观察 Failed **保留不改写** | **剩余风险**：`3e6e1b07…` 的 36/1→360/10 与 sun 7300/7375 无法从仓库复算，文档数字属「事后不可复现的历史声明」。**重查触发**：若任何下游结论依赖这些具体数字，需恢复该切片或改以入库 Trace 为基线并修正文档 |
| V20 | G2 / 未由本 agent 执行现场呈现判定 | Human 2026-09-29：「我已经验证还可以」，范围 = **仅查看页面呈现**（口头，无截图、无具体观察项、未区分 `/` 与 `/jev`） | 仅覆盖「页面看起来可接受」这一主观观察，**不覆盖**铲除格是否点亮、不覆盖 `/` 与 `/jev` 的差异、不覆盖任何真机行为 | 该声明**不得**作为 V20 通过证据；`/jev` 缺口见 I3。若 Human 需以视觉证据判定铲除是否发生，R16 升级为 G1 并需先补断言 |
| V13 | G2 / Not run | Plan P01 CD-04 选择「真机观察 G2 非阻塞」；**2026-10-04 Human 未提供现场记录**（其验证说明已被指示记录为「人工验证过但代码/仓库无记录」，不作为现场观察证据） | 依赖 Human 时间与真实 API；代码可确定部分已由 R1–R7 覆盖 | 交付后长期未执行则 Case A/B 现场结论保持「未取得」 |
| V21 | G2 / Not run | Plan P03 明确 G2；**2026-10-04 Human 未提供现场记录** | 依赖 Human 时间、真机与真实 API | 同上；升级条件见 §8 |
| V10 | G2 / 已通过 | Plan P01 将 V10 定为 G2（文档一致性），G1 判据是 V9 | 根因文档档位已同步，风险已消除 | 无 |
| I4 | 非门槛 / 已记录 | 本次未取得 Human 对 `configs/plant_experience.txt` 的范围裁定 | 该文件不改决策语义 | 若 Human 认为越界，属 Delivery 阶段的范围裁定 |
| **新观察（非门槛）** | `docs/jev-capability-analysis.md` / `.en.md` 在 2026-10-04 被修改（正文新增 007–009 评述，声明 009 仍 Blocked） | 未取得 Human 范围裁定；两文件不在任何 Plan 的 Impact Surface 内 | 仅文档表述，不改代码语义；但其中「009 is currently Blocked」在本次改判为 Passed 后**将成为过期表述** | **Delivery 需一并裁定**：是否纳入 009 提交，并同步 009 的最终结论措辞 |

## 10. Conclusion

- Overall result: **Passed**
- Verification execution: **Complete**
- Reason: G1 的代码可确定部分（P01 R1–R7/R10、P03 R11–R15、V8/V22）已取得充分且可独立复现的通过证据：定向 286 tests OK、`tests.test_web` 46 OK、全量 **493 tests OK**（2026-10-04 复核与 09-29 逐项一致），且本 agent 用自建状态独立复算了 surplus 规则、`await_plan`、`{high,critical}` 档位与「有僵尸无攻击植物」独立中断、OD-15 全枚举、`economy_band` 手牌边界、可铲候选来源、空放置层仅铲除层、255 链 + 铲除层共存（level 3）、branch key 形状未变、merge 铲除键齐备。
- 关于唯一的原阻塞项 V11：`tools/evidence-plan-economy.py` 在 Plan 指定的 `.log/jev-dashboard.jsonl` 上仍返回退出码 2（该实时输出文件已被后续运行覆盖），**这一原始失败事实保留不改写**。但：**(1)** 工具本身可用且只读（入库输入 sha256 前后一致）；**(2)** 依 Human 指示「有 trace 就直接查看」，已对**入库** Trace 独立复现出 R9 所需的对照语义——`test_02.jsonl` job-000287 `BEFORE 0 → AFTER 35` placements，`test_05.jsonl` Case A sun150 `await_plan` / sun320 goal-only / sun400 goal+surplus 45 placements；**(3)** Human 2026-10-04 明确**裁定 V11 本次不适用并接受剩余风险**（§9）。按 skill「对 Plan 中误列为门槛的检查，Human 可明确裁定其对本次交付不适用或接受剩余风险」，已将**原级别 G1、新判断非门槛、依据、决定来源与适用边界**记入 §9，未修改 Plan、未抹去原始发现。因此 V11 **不再阻塞交付**；仅余「特定 run 数字事后不可复算」的**证据可追溯性**风险。
- G1 evidence summary:
  - 通过：V1、V2、V3、V4、V5、V6、V7（规则与实现层，含独立探针）、V8/V22（493 OK）、V12（3 OK，含只读性）、V15、V16、V17、V18、V19。
  - V11：原观察 **Failed**（指定路径退出码 2）→ 依 Human 裁定**降为非门槛**，附**入库 Trace 的替代证据**（对照语义已复现）；指定 run 的精确数字仍不可复算（剩余风险，§9）。
- Accepted G2 risks and deferred G3 checks:
  - 接受/暂缓：V13、V21（真机，**Not run**，Human 本轮未提供现场记录）；记录：V10（已通过）、V14（已通过）、V20（部分通过 + `/jev` 缺口 I3）；G3 = 模型是否主动声明高价值目标（本次不评）。
  - 明确未记成通过：Human「页面呈现还可以」不作为 V20 或任何 G1 检查的通过证据。
- Required next stage: **`$sdd-delivery 009`**。Delivery 阶段需一并裁定的范围项：**(a)** `configs/plant_experience.txt` 的手编改动（I4）；**(b)** `docs/jev-capability-analysis.md`/`.en.md` 在 2026-10-04 的新增评述，其中「009 is currently Blocked」已因本次改判而过期，需同步或排除出提交；**(c)** 可选低风险跟进：P01/P02 与根因文档中引用 `3e6e1b07…` 的路径与数字声明，可改为入库 Trace 基线以避免再次失效。I3（`/jev` 铲除点亮）不阻塞交付，建议作为 follow-up 记录。
