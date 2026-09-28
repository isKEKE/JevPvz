# Delivery Report

## 1. Delivery Metadata

- Iteration: `006-jev-runtime-loop`
- Delivered at: 2026-09-27
- Branch: `main` (upstream `origin/main`)
- Commit type: `feat`
- Planned commit subject: `sdd(006): feat async JEV runtime loop with layered policy`
- Commit hash: `a08105bf109e7453938243a3cec78d926129f5d8`（60 文件）
- Pushed: `origin/main`（`4d9daa4..a08105b`，普通 push，2026-09-27）

## 2. Summary

本 Iteration 在当前受支持的 PvZ 对局上交付了默认连续观察、由各分支相关状态变化驱动的
JEV 判断、以及统一串行的动作执行，并把采集路径改为持有已验证目标的采样会话。交付范围
覆盖五个 Plan：

- **P01** 把恒为 false 的 `decision_ready` 改为有明确条件的准入闸门；
- **P02** 接入 TypeSafe typed API，建立 typed 请求/答案校验与植物、僵尸英文能力目录；
- **P03** 实现异步分支 JEV Runtime 与分层策略（collect/plant/管理三路问题、请求态裁剪、
  单槽调度、批成员账本、威胁标签化等）；
- **P04** 持久化 v2 JSONL Trace 并在 Dashboard 中只读呈现 JEV 时间线；
- **P05** 把 `capture_state` 默认路径切换到带锁的 `TargetSession`，在保持身份保证的前提下
  把稳态每样本固定采集开销从约 33 ms 降到中位约 3.49 ms。

交付验收依据 `verify.md` 的总体结论 **Passed**、执行完整性 **Complete**，主证据为 Human
亲自运行的 5 局真实对局（真实 TypeSafe API + 真实游戏输入 + 真实胜负），确定性侧全量
**420 tests OK** 且变异回放全部 CAUGHT。

## 3. What Changed

- **只读采集与目标身份**：`runtime/session.py` 新增持有已验证目标句柄的 `TargetSession`；
  `state/builder.py` 默认采集路径改为会话读取（`capture_state` 保持 `raw_reader` 注入的
  向后兼容旁路），每样本只做廉价守卫，磁盘身份与进程唯一性分别按 1 s / 30 s 周期重跑，
  `source.identity_verified_at_utc` 记录最近一次成功身份验证时间。
- **JEV 准入闸门**：`state/builder.py::evaluate_decision_readiness` 集中实现 `jev_eligible`
  必要条件、required field 的 available/provisional 门槛与投影结构校验，证据不足即
  fail-closed。
- **TypeSafe typed 请求与目录**：`jev/config.py`（dotenv、独立门槛、代理处理）、
  `jev/decision.py`（Noul/Choice typed 校验与独立门槛）、`jev/questions.py`（问题与阈值
  单一来源）、`configs/plant_catalog.py` 与 `configs/zombie_catalog.py` 补齐英文
  `description_en`；植物目录新增 `engagement ∈ {ranged, melee, none}` 标注并下发到 plant 选项。
- **异步 JEV Runtime 与分层策略**：`jev/loop.py` 实现默认连续观察、按决策相关语义 key
  变化触发/未变 skip、单观察者→单槽调度器（紧急度/FIFO、派发前来源/资源/新鲜度复核、
  TTL 交回）、collect 批成员终态账本（逐成员以 `executed` 或 `discarded(reason)` 收尾）、
  有界 FIFO 队列（上限 3）加等价合并去重、plant 弃选项作主、collect 固定锚点、空 items
  请求裁剪、`wave == 0` 守卫；`jev/scheduler.py` 保持不本地改选模型目标；`jev/strategy.py`
  提供观察事实/预算/可信波次与请求态裁剪，僵尸侧改为一组有序标签
  （`threat/crowd/composition/proximity/armor`，含 `undefended` 升档），并暴露
  `catalog_context.plant_abilities` 与 `plants[].role`。
- **问题/经验与结果事实**：三处植物 `instructions` 以 `board.column_direction` 锚定方向语义；
  手编 `configs/plant_experience.txt`（10 条标签策略，784/800 字符）由 `jev/questions.py`
  的加载器每次构建读取；run 级结果事实 `final_phase` 与 `lane_closest` 经 `main.py` run JSON 输出。
- **掉落物可点区域与 collect 确认**：`configs/pvz_1051.py` 的 `item_coordinates.bounds`
  改为 `(0.0, 80.0, 800.0, 600.0)`；collect 请求显式带 `timeout_ms=2500` 与超时证据；
  Boundary 扩展 item_id 请求而 Executor 点击/确认流程复用。
- **Trace 与 Dashboard**：`jev/trace.py` 提供 v2 事件流（`job_start`/`request_result`/
  `proposal_discarded`/`action_result`/`job_end`/`runtime_stop`），保持 v1/v2 兼容与白名单
  投影（不泄漏 item ID、`source`、凭据）；`dashboard/` 新增只读 JEV 导航页与时间线卡片，
  与 Loop 共读同一份显式指定的 JSONL 路径。

## 4. Plan and Task Status

| Plan ID | Status | Completed Tasks | Incomplete Tasks | Notes |
|---|---|---|---|---|
| P01 | Approved；实施完成、Passed | T1 | 无 | `decision_ready` 准入闸门；`verify.md` V01/V02 Passed。 |
| P02 | Approved；实施完成、Passed | T1–T2 | 无 | TypeSafe typed API 与机制目录；V03–V05 Passed。 |
| P03 | Approved（含第 10 次修订，2026-09-27 获批）；实施完成、本轮 Passed | T1–T38（全部 `[x]`） | 无 | 共 10 次修订；R50–R55/T33–T38 属「直接实施后追认」（见 §7）。全量 420 tests OK。 |
| P04 | Approved；本轮按 Human 接受记录 | T1–T3 | 无 | 实施产物在 5 局真机中持续产出并被消费；未单独重跑其确定性检查（Human 接受）。 |
| P05 | Approved；实施完成、Verify Passed（仅 P05 范围） | T1–T3 | 无 | 采样会话与目标身份；仅 R12–R14 为 Passed。 |

**未完成项：无。** 所有 Plan 的 Implementation 均已完成，`verify.md` 无与 Passed 冲突的未完成项。

## 5. Files Changed

- `jev/**`（`__init__.py`、`client.py`、`config.py`、`decision.py`、`loop.py`、`questions.py`、
  `scheduler.py`、`strategy.py`、`trace.py`）
- 测试：`tests/test_jev_{client,cli,loop,scheduler,strategy,trace}.py`（新增）、
  `tests/test_session.py`（新增）、`tests/test_{action_boundary,live_validation,state,web}.py`
- `actions/boundary.py`、`state/builder.py`
- `configs/{pvz_1051.py,plant_catalog.py,zombie_catalog.py,plant_experience.txt}`
- `dashboard/**`（`server.py`、`static/{index.html,jev.html,jev-page.js,state.html,style.css,app.js,state-page.js}`）
- `runtime/{session.py,__init__.py}`、`main.py`
- `README.md`、`docs/architecture.md`、`pyproject.toml`、`uv.lock`
- `.memory/{context.md,project-map.md}`、`.sdd/006-jev-runtime-loop/**`（含本 `delivery.md`）
- `.log/**`（Human 要求纳入的 5 局真机日志 `test_01..05.jsonl` 与分析文档
  `006-no-plant-analysis-2026-09-27.md`、`006-research-relay-2026-09-27.md`、
  `006-plan-03-pi-01.html`、`006-plan-03-pi-02.html`）

## 6. Verification Result

- Overall result: Passed
- Evidence: `verify.md`（总体结论 **Passed**、执行完整性 **Complete**）

判定依据（分两轮写入同一 `verify.md`）：

- 第一轮（P01/P02/P05）：P01 准入矩阵在真实样本上 52 项翻转全部符合预期；P02 配置/typed
  校验 36 项 + 目录完整性 49/34 项通过；P05 真机采集稳态中位 3.49 ms（对照被移除项 30.64 ms），
  fail-fast/重解析/字段隔离在真假两路成立。
- 第二轮（P03/P04，主证据为 Human 亲自运行的 5 局真实对局 `.log/test_01..05.jsonl`）：
  `test_01`（未加经验，wave 14）→ `test_02`（刚加经验，wave 10）→ `test_03`（经验迭代后
  **通过 1-1**，wave 20）→ `test_04`（1-2 **失败**，wave 20）→ `test_05`（应用最新改动后
  **通过 1-2**，wave 20，`final_phase=level_intro`）。四项量化对照：真越界收集记录
  （`outside_region` 且 x∈[10,40)、y≥80）**109/188 → 0**；`batch_superseded_by_newer_batch`
  **753 → 0**（改由 `cohort_member_already_pending` 355 逐成员记账）；`undefended` 标签出现
  **429** 次；`runtime_stop.final_phase` 首次可读。确定性侧全量 **420 tests OK**、变异回放
  4/4 + 2/2 + 8/8 全部 CAUGHT 且逐字节还原。

Delivery may proceed only when the recorded formal result is `Passed`. —— 本项已满足。

## 7. Deviations from Approved Plan

1. **Expected-files 偏差**（均已记入各 Task backfill）：T29 另改 `tests/test_jev_cli.py`；
   T31 另改 `tests/test_jev_loop.py`（3 处 fixture）与 `tests/test_live_validation.py`（1 处）；
   T32 另改 `jev/strategy.py`（`plants[]` 的实际装配处）。
2. **R50–R55 / T33–T38 属「直接实施后追认」**：Human 明确指示「不走 SDD、直接改」，主 agent
   直接实施并验证（全量 420 tests OK + 变异回放 CAUGHT），随后由 `$sdd-plan` 第 10 次修订
   追认为正式需求与实现记录。
3. **P03 第 10 次修订的 Plan Approval**：交付时记为 `Pending human review`（实质修订会重置），
   Human 于 2026-09-27 明确批准后已同步为 **Approved**（追认型修订，实现与交付内容未变）。
4. **`configs/plant_experience.txt` 内容由 Human 直接编辑**：工程只保证格式/预算/字段引用合法，
   经验文本内容不在工程可控范围。

## 8. Known Risks

- **TTL 交回缺测试断言**（既有空缺，非本轮引入）：suite 中无 `_release_branch`/`proposal_expired`
  断言；当前 TTL 行为经阅读确认与修订前等价，不阻塞本阶段。
- **经验文件接近预算**（784/800 字符）：再加策略条当前需压缩既有行或显式提高预算（需修订）。
- **`undefended` 仅呈现层升档**：调度优先级不变，仅让模型看到正确严重度；如需调度层优先须另开修订。
- **collect 队列接受面放宽**：最多 3 批待执行，长队列尾部可能超窗（逐成员记
  `cohort_authorization_expired`，不静默）。
- **V41 未逐条留痕**：问题措辞/阈值/事实/reason 词表/经验文本未写成逐条审阅清单；Human 裁定
  接受，范围限本次交付。
- **P04 未重跑确定性检查**：其验证按 Human 接受记录，实施产物在 5 局真机中持续产出并被消费。
- **区域放宽副作用（G2）**：x 下限放到 0 后，草坪左缘/割草机条带内落点会被点击；预期无害，
  但若现场出现误碰需回 Plan 重定。

## 9. Follow-up Items

- 新增经验行前需压缩既有行或提高预算（需 `$sdd-plan` 修订）。
- 如需调度层也按 `undefended` 优先，须另开修订。
- `.codex/config.toml`、`configs/plant_experience-v1.txt`（旧版备份）、`.pi/**` 仍在工作区未提交，
  属于本交付的排除项。
- V41 建议下一轮补成逐条审阅清单（问题措辞、两个门槛锚点、reason 词表、经验文本）。
- TTL 交回测试断言可在下一轮修订或后续 `$sdd-verify` 时补齐。

## 10. Git Scope

- **Files intended for this Iteration commit**：§5 列出的文件族 —— 即当前已暂存的 59 个文件中
  去掉 `configs/plant_experience-v1.txt`，再加上 `uv.lock`、`.memory/context.md`、
  `.memory/project-map.md` 与本 `delivery.md`。覆盖 `jev/**`、`tests/**`、`actions/boundary.py`、
  `state/builder.py`、`configs/**`、`dashboard/**`、`runtime/**`、`main.py`、`README.md`、
  `docs/architecture.md`、`pyproject.toml`、`uv.lock`、`.memory/**`、`.sdd/006-jev-runtime-loop/**`
  与 `.log/**`（含 Human 要求纳入的 5 局真机日志与分析文档）。
- **Unrelated working-tree files explicitly excluded**：`.codex/config.toml`、
  `configs/plant_experience-v1.txt`（旧版备份）、`.pi/**`。
- **Remote / branch intended for push**：`origin/main`（普通 `git push`，已获 Human 授权）。
