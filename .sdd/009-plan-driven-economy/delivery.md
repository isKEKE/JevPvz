# Delivery Report

## 1. Delivery Metadata

- Iteration: `009-plan-driven-economy`
- Delivered at: 2026-10-04（UTC+8，本机时钟）
- Branch: `main`（upstream `origin/main`）
- Commit type: `feat`
- Planned commit subject: `sdd(009): feat plan-driven economy with autonomous plant removal`

## 2. Summary

本 Iteration 让「资源充裕 → 高价值牌重回候选」「缺钱 → 本地攒钱等待」「升级/替换需先铲除」在自主 Runtime 中真正可能发生。交付三组能力：

1. **P01 plan-driven offer policy**：模型声明的目标从「授权前提」降为**上下文**——不再把手牌过滤成一种类型；目标差钱且无中断行时以 `await_plan` 本地等待；目标可支付后，用余额中超过目标自身价格的富余（surplus）把高成本牌放回候选。中断档位收窄为 `{high, critical}` 或「有僵尸且无攻击植物」。
2. **P02 economy evidence tool**：离线对照脚本从一次性工作区脚本升格为入库工具 `tools/evidence-plan-economy.py`（`--trace-file`、纯标准库、只读、fail-closed 非零退出），配 `tests/test_economy_evidence.py` 冒烟测试与 README/usage 命令。
3. **P03 autonomous plant removal**：在同一次 plant 请求内追加独立 `shovel_target` Choice（自带弃选项、弃选作主、无 Noul）；代码保证**一次决策最多一个动作**，铲除优先且被丢弃的放置记入 merge（`shovel_overrode_placement` / `overridden_placement_option`）；请求在「有放置候选或可铲格」时发出。

## 3. What Changed

| 领域 | 变更 |
|---|---|
| 策略层 | `jev/strategy.py`：新增 `economy_band`/`plan_facts`/`economy_facts`/`plant_spend_decision`（攒钱与 surplus 规则）、`removable_cells`（只收 `plant:<name>` 格）、`LANE_RESPONSE_URGENCIES` 收窄为 `{high, critical}`、`PLAN_HOLD_REASON = "await_plan"` |
| 问题层 | `jev/questions.py`：新增 `ECONOMY_ANCHOR`、`_plant_economy_guidance()`、`shovel_target_question`/`shovel_option_criteria`/`shovel_option_id`；`PLANT_STATE_FIELDS` 含 `economy` |
| 客户端/决策 | `jev/client.py`：`build_plant_questions(plan=)`、`_with_shovel_layer`（单层=2 问、lane 链后=3 问）；`jev/decision.py`：`combine_plant_decision`/`_shovel_selection`（δ=0 严格 argmax） |
| Runtime | `jev/loop.py`：`_local_wait_reason` 返回 `await_plan`；请求条件改为「有放置候选或可铲格」；`_last_result` 按真实 `target["action"]`（放置由 `plant` 变 `place_plant`） |
| Trace | `jev/trace.py`：`RELIABLE_OUTCOMES` 含 `await_plan`；`_economy_record` 有界投影；`MERGE_REVIEW_KEYS` 增加 9 个 shovel/overridden 键 |
| 呈现 | `dashboard/static/viewmodel.js` + `recording.js`：录制页 `/` 点亮铲除格并读作「铲除」，不冒充种植 |
| 工具 | 新增 `tools/evidence-plan-economy.py`；删除 `.log/evidence-plan-economy.py` |
| 测试 | 新增 20 个用例（strategy 5 / client 10 / loop 3 / trace 1 / web 1）+ 新增 `tests/test_economy_evidence.py`（3 用例） |
| 文档 | `docs/architecture.md`（`medium`→`high` 措辞 + 铲除语义）、`docs/usage.md`、`README.md`、`README.zh-CN.md` |
| 证据 | 新增 `.log/2026-09-29-plan-economy-root-cause.md`（只读根因分析） |

## 4. Plan and Task Status

| Plan ID | Status | Completed Tasks | Incomplete Tasks | Notes |
|---|---|---|---|---|
| P01 Plan-driven offer policy | Approved / Delivered | T1, T2, T3, T4, T5, T6 | 无 | T2（档位收窄）为本 Iteration 唯一新代码改动，已落地 |
| P02 Economy evidence tool and live observation | Approved / Delivered | T1, T2, T3 | 无（T3 的真机观察为 G2，见 §8） | 工具已入库；真机 Case A/B 观察未取得 |
| P03 Autonomous plant removal | Approved / Delivered | T1, T2, T3, T4, T5, T6 | 无（T6 的真机观察为 G2，见 §8） | `viewmodel.js`/`recording.js` 已点亮；`/jev` 页未纳入 Plan 影响面 |

无未完成项与 Passed 结论冲突。

## 5. Files Changed

源码与测试：

- `jev/strategy.py`、`jev/questions.py`、`jev/client.py`、`jev/decision.py`、`jev/loop.py`、`jev/trace.py`
- `dashboard/static/viewmodel.js`、`dashboard/static/recording.js`
- `tests/test_jev_strategy.py`、`tests/test_jev_client.py`、`tests/test_jev_loop.py`、`tests/test_jev_trace.py`、`tests/test_web.py`
- 新增 `tests/test_economy_evidence.py`、`tools/evidence-plan-economy.py`

文档与 SDD artifact：

- `docs/architecture.md`、`docs/usage.md`、`README.md`、`README.zh-CN.md`
- `.sdd/009-plan-driven-economy/`（plan-index、plans/01–03、verify.md、delivery.md）
- `.log/2026-09-29-plan-economy-root-cause.md`
- `.memory/context.md`、`.memory/project-map.md`

## 6. Verification Result

- Overall result: **Passed**
- Verification execution: Complete
- Evidence: `.sdd/009-plan-driven-economy/verify.md`

复核证据（2026-10-04）：定向 **286 tests OK**、`tests.test_web` **46 OK**、全量 **493 tests OK**、两个 JS `node --check` 通过。原唯一阻塞项 V11 经 Human 2026-10-04 裁定「本次不适用并接受剩余风险」；对照语义已由**入库** Trace 独立复现（`test_02.jsonl` job-000287 `BEFORE 0 → AFTER 35`；`test_05.jsonl` Case A sun150 `await_plan` / sun320 goal-only / sun400 45 placements）。原 `Failed` 观察在 `verify.md` 中保留未改写。

## 7. Deviations from Approved Plan

1. **`_last_result` 的放置动作由 `plant` 变为 `place_plant`**：Plan 要求 `_last_result` 记录真实 action（P03 T3/§6 风险）。该字段进入 collect 分支 key 的 `repr` 与 prompt 上下文，属行为可见变化，但未改变语义。
2. **P03 实现超出 20 轮工具调用预算**（约 35 次）。不影响交付内容。
3. **`/jev` 页矩阵不点亮铲除格**：P03 §4.1 影响面只列出 `viewmodel.js`（+`recording.js`）与 `tests/test_web.py`，未包含 `dashboard/static/jev-page.js` 或 `dashboard/server.py`。这是 **Plan 覆盖范围的缺口**，非实现越界；R16 本身为 G2，录制页 `/` 已实现并有测试覆盖。记为 I3 与 §9 follow-up。
4. **P01/P02 的 §7 声明 473 tests 为历史快照**：P03 落地后实际为 493（P03 §7 已修正 492→493），与仓库现状一致，非错误。

## 8. Known Risks

1. **V11 证据可追溯性（已接受）**：Plan 指定的 `.log/jev-dashboard.jsonl` 是 Dashboard 实时输出文件，会被后续运行**原地覆盖**；引用的 run `3e6e1b07…`（305 事件 / sun 7300、7375）已不可从仓库复算。工具本身只读且可用，对照语义已由入库 Trace 复现。Human 2026-10-04 明确接受此剩余风险。
2. **真机观察未取得（G2）**：V13（Case A/B 攒钱与高成本牌入选）与 V21（Replace/Upgrade 两步）均 **Not run**。Human 2026-10-04 表示已人工验证但仓库无记录，按 skill 记为「人工验证过、代码无记录」，不作为现场观察证据。升级条件：若富余下仍只出目标类型/不出现高成本候选，或实机出现误点/无法确认铲除，则升为 G1。
3. **`/jev` 页呈现缺口（G2）**：固定草坪矩阵不点亮铲除格（`jev-page.js` 无 `shovel_target`；`server.py::_apply_action_result` 只认 `place_plant`/`collect_item`）。`/` 录制页正常。
4. **`configs/plant_experience.txt` 未纳入本提交**：该文件有 Iteration 外的手编改动（措辞微调 + 新增第 11 条「very_close/at_the_door 时优先近战攻击植物」，16:49），只影响模型提示文本、不改决策语义，且不在任何 Plan 的 Impact Surface 内。工作区保留未提交。
5. **`docs/jev-capability-analysis.md` / `.en.md` 未纳入本提交**：两文件于 2026-10-04 被新增 007–009 评述，其中声明「Iteration 009 is currently Blocked」。该表述已因本次 Verify 改判而过期，且两文件不在任何 Plan 影响面内。工作区保留未提交。
6. **`collect`「只收一个物品」缺陷未修**：属契约级变更，需另行 `$sdd-plan`。
7. **环境注意**：Human 的活 JEV Runtime 持有单实例锁时，`tests/test_jev_cli` 的锁相关用例会失败，属 R3 正常行为，非回归。

## 9. Follow-up Items

1. `/jev` 页铲除格点亮（I3）：如要修需扩 Plan 范围（涉及 `dashboard/static/jev-page.js` 与 `dashboard/server.py`）。
2. 证据基线可追溯性：把 P01/P02 与根因文档中引用 `3e6e1b07…` 的路径与数字声明改为**入库 Trace 基线**（或另存带日期的只读冻结切片），避免再次被实时输出覆盖。
3. `configs/plant_experience.txt` 与 `docs/jev-capability-analysis.*` 两处工作区变更需单独裁定归属，并同步分析文档中已过期的「009 Blocked」表述。
4. 真机 Case A/B（V13）与 Replace/Upgrade（V21）观察记录，落盘为 `.log/009-live-*.md`。

## 10. Git Scope

- Files intended for this Iteration commit:
  - `jev/{strategy,questions,client,decision,loop,trace}.py`
  - `dashboard/static/{viewmodel.js,recording.js}`
  - `tests/{test_jev_strategy,test_jev_client,test_jev_loop,test_jev_trace,test_web,test_economy_evidence}.py`
  - `tools/evidence-plan-economy.py`
  - `docs/{architecture.md,usage.md}`、`README.md`、`README.zh-CN.md`
  - `.sdd/009-plan-driven-economy/`（含本文件）
  - `.log/2026-09-29-plan-economy-root-cause.md`
  - `.memory/{context.md,project-map.md}`
- Unrelated working-tree files explicitly excluded:
  - `configs/plant_experience.txt`（Iteration 外手编改动；Human 2026-10-04 裁定排除）
  - `docs/jev-capability-analysis.md`、`docs/jev-capability-analysis.en.md`（2026-10-04 新增评述且含过期 Blocked 表述；Human 2026-10-04 裁定排除）
  - `.log/jev-dashboard.jsonl`、`.log/jev-dashboard-process.log`（易失实时输出，历史提交从未纳入）
- Remote / branch intended for push: `origin/main`（当前分支 `main`，upstream 已存在）
