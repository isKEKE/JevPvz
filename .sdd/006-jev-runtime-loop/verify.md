# Verify

> 本 `verify.md` 覆盖 Iteration 006 中**已获批且已完成**的三个 Plan：**P01（R1）、P02（R2/R6/R7）、P05（R12–R14）**。
> **不覆盖** P03（异步 JEV Runtime，`Pending human review`、OD-15/OD-22 开放、T3–T7 未实施）与 P04（本轮未请求验证）。
> 因此 **Iteration 级整体结论仍未建立**。

## 1. Verification Metadata

- 本轮（2026-09-27，第二份结论）：范围 = Iteration 006 的 **P03（异步 JEV Runtime，含第 1–10 次修订）与 P04（Runtime Trace / JEV Timeline）**；执行者 = main agent（确定性检查）+ **Human 亲自运行的 5 局真实对局**（`.log/test_01..05.jsonl`，真实 TypeSafe API + 真实游戏输入）。代码版本 = 当前工作区（全量 `420 tests OK`）。
- 既有结论（同日第一份）：P01/P02/P05，见 §4 与 §10 的历史段落，未因本轮重跑而改变。

- Iteration: 006-jev-runtime-loop
- Verified at: 2026-09-27 (Asia/Shanghai)
- Executor: Main agent
- Execution mode: Main agent (default)
- Overall result: Passed
- Verification execution: Complete

- 验证范围（scope）: P01（V01、V02）、P02（V03–V05）、P05（V19–V25），共 12 条 G1 与 1 条 G2 检查。
- 检查 ID 命名空间: plan-index 现要求检查 ID 带 Plan 前缀；本文档把 P05 新增的真机会话检查写作 **P05/V25**，以区别于 `P03/V25`（异步隔离）。
- 分次执行: P05 子集于本日早先完成（结论 Passed）；P01/P02 子集于同日后段完成。两次结论一致，本文档合并记录。

## 2. Baseline Reviewed

本轮新增读取：`plans/03-runtime-loop.md`（第 1–10 次修订，R1–R55、T1–T38、V1–V80）、`plan-index.md`（P03 十次修订流水）、`.memory/context.md`、`.memory/project-map.md`、`configs/plant_experience.txt`（10 条标签策略）、`configs/plant_catalog.py`（`engagement` 标注）、`jev/{strategy,client,trace,loop}.py`、`tests/{test_jev_strategy,test_jev_client,test_jev_trace,test_jev_loop}.py`，以及 Human 提供的 5 局真实日志。

**Human 的日志语义（其本人标注）**：`test_01` 未添加任何经验；`test_02` 刚添加经验；`test_03` 经验迭代后**通过 1-1**；`test_04` 打 1-2 **失败**；`test_05` 应用最新改动后**通过 1-2**。

- Original requirement source:
  - P01/R1：用户引用的「游戏状态与动作边界」对话与 2026-09-27 补充的 `jev_eligible` 表达式；用户选择接受合规 provisional（OD-02）。
  - P02/R2、R6、R7：TypeSafe 官方 API/SDK 说明与 Router→专项 Action 两层设计；用户要求补齐 Plant/Zombie 英文能力描述并让门槛各自独立可配（OD-01、OD-04、OD-05、OD-06、OD-07、OD-08、OD-10、OD-13）。
  - P05/R12–R14：用户 2026-09-27 提出的「JEV runtime 需要 100ms 观察节奏、理论需要 100ms 刷新」与本次采集路径优化实测。
- Plan Index revision/state: `.sdd/006-jev-runtime-loop/plan-index.md`；R1/R2/R6/R7/R12–R14 均为 G1；Plan Catalog P01/P02/P05 = **Approved**。Iteration 级 Status = `Pending human review`。
- Concrete Plans reviewed: `plans/01-decision-ready.md`、`plans/02-jev-api.md`、`plans/05-capture-session.md`（均 Approved）。P03 因改写为待审、且其正文声明不改动 P05 的身份保证，仅作一致性对照，未作为验收基线。
- Implementation diff/revision: HEAD `4d9daa47ae60e7755a787926678ecc68b71387a1`（`4d9daa4 sync`）。P01/P02/P05 的实现**全部未提交**，位于工作区：`state/builder.py`、`configs/plant_catalog.py`、`configs/zombie_catalog.py`、`jev/`（整包未跟踪）、`pyproject.toml`、`uv.lock`、`docs/architecture.md`、`runtime/session.py`（新增）、`runtime/__init__.py`、`tests/test_state.py`、`tests/test_session.py`（新增）。
- Current delivery goal and use: 让 State 具备可验证的 JEV 准入判断；用官方 typed API 建立 Router/意图专项 Action 与植物/僵尸决策上下文；把采集改为持有已验证目标会话以支撑 100–250 ms 观察节奏。
- G1 minimum success conditions: `decision_ready` 精确实现 `jev_eligible` 与 OD-02 证据规则；三个门槛可独立配置且所有 typed 答案在派发前 fail-closed；Plant/Zombie 目录完整且只把当前局观测注入请求；采集稳态每样本不再枚举进程或做磁盘身份验证，且身份失败 fail-fast、`source.identity_verified_at_utc` 正确且不泄漏。
- Excluded or future scenarios: P03 异步分支/统一调度/Trace v2；P04 前端对照；动态对局语义；完整通关；真实 JEV API 的端到端连通性（Plan 指派给 P03/V07）。
- Runtime environment and current state: Windows，仓库 `F:\projects\JevPvz`，Python 3.12.13 / uv。目标游戏运行中，PID 10888，日间草坪，阳光 50，2 株植物（向日葵 + 坚果墙），1 只普通僵尸，**僵尸由 Human 冻结但游戏继续运行**。仓库存在真实 `.env`（提供 key 与代理）；所有校验均使用 fake typed 响应，未调用真实 API。
- Check executor: 自动化命令、真机只读测量与独立检查脚本均由 Main agent 执行；无 delegated verifier。
- State-changing action authority, scope, limits, and recovery/stop conditions: Human 于 2026-09-27 授权「启动并观察」。据此允许只读 `probe` / `snapshot` / `serve` 与本机只读测量脚本；**未**授权 `action`（游戏输入）与 `jev-loop`（真实 JEV API 调用），本次均未执行。不终止、不重启、不修改 Human 准备的游戏状态；`serve` 仅绑定 127.0.0.1 并在检查后终止（端口 8791 已确认释放）。

## 3. Requirement Traceability

本轮新增（P03/P04）：

| Requirement | Task | Check ID / tier | Evidence |
|---|---|---|---|
| R1–R47（P03 前九次修订） | T1–T32 | V1–V74（见 plan-03 §7） | 既有确定性证据 + 本轮 Human 真实对局（同一代码路径） |
| R48 掉落物可点区域 | T31 | V73 / G1 | **真机对照**：真越界（`outside_region` 且 x∈[10,40)、y≥80）`test_01` **109**、`test_02` **188** → `test_03/04/05` 均 **0** |
| R49 植物能力事实 | T32 | V74 / G1 | 真实请求 `catalog_context.plant_abilities` + `plants[].role`；`set(state)` 未变 |
| R50 威胁标签化 + `undefended` 升档 | T33 | V75 / G1 | `test_04` 标签生效（none/low/medium/high/critical）；`test_05` **`undefended` 出现 429 次** |
| R51 collect 授权队列与去重 | T34 | V76 / G1 | **真机对照**：`batch_superseded_by_newer_batch` `test_04` **753** → `test_05` **0**；`cohort_member_already_pending` 355（记账替代静默丢弃） |
| R52 管理答案仅 `replace` 要求类型 | T35 | V77 / G1 | `test_04` 的 5 次 `invalid_management_response` 成因已修；后续运行无该类错误 |
| R53 Trace 记 `final_phase` | T36 | V78 / G2 | `test_05` 的 `runtime_stop.final_phase = level_intro`（前四局该键不存在，属改动前） |
| R54 目录 `engagement` 标注并下发 | T37 | V79 / G1 | 49 项标注（18 ranged / 6 melee / 25 none）+ 选项 `engagement`；`test_05` 出现 squash/peashooter 主导的布局 |
| R55 描述事实补全 + 经验策略 | T38 | V80 / G1 | 手牌不丢卡、`plants[].description_en`、建造选项带能力文本；经验文件 10 条/784 字符（预算内） |
| P04 Runtime Trace / JEV Timeline | T7 族 | 见 `plans/04-runtime-trace.md` §7 | v2 事件流（`job_start`/`request_result`/`proposal_discarded`/`action_result`/`job_end`/`runtime_stop`）在**全部 5 局真机运行**中产出并被本轮分析消费；Dashboard JEV 页由 Human 现场使用 |

| Requirement ID | Plan / Task | Check ID and tier | Implementation evidence | Verification evidence | Observed result | Delivery disposition |
|---|---|---|---|---|---|---|
| R1 | P01 / T1 | V01 / G1 | `state/builder.py::evaluate_decision_readiness` 在 `build_state` 完成后判定：先校验 `valid`/`status`、`game.phase`/`paused`/mode 与 background code 一致性，再校验 18 个 required availability ⊆ {available, provisional}、`sun_balance`、以及 5×9 board.cells、cards、plants、zombies（含 hp 与 distance_to_house_cells 0–8）、lanes（5 行）结构。 | 独立脚本在**真实样本**上逐项翻转：9 个 `jev_eligible` 条件、18 个 required availability × {unavailable, error}、2 个「必须仍准入」的空数组情形、3 个 mode/background 一致性、2 个 sun 结构，共 **52 项，FAILURES: none**。 | Passed | 满足；表达式任一条件不满足即拒绝，证据不足即拒绝，证据有效的空数组不被误拒。 |
| R1 | P01 / T1 | V02 / G1 | 同上；`decision_ready` 仍由 `build_state` 写入同一样本，JEV projection schema 未改。 | `uv run python -m unittest discover -s tests -p "test_state.py"` → Ran 34, OK。 | Passed | 满足；既有 All State 与 JEV projection 契约未回归。 |
| R2 | P02 / T1 | V03 / G1 | `jev/config.py::load_typesafe_environment` 调用 `load_dotenv(override=False)`，缺 `TYPESAFE_API_KEY` 或代理即抛 `JevConfigurationError`；`load_jev_thresholds` 三个门槛各自独立读 env、缺省 0.6、非法值拒绝；`use_configured_http_proxy_fallback` 用 HTTPS_PROXY 覆盖继承的 SOCKS `ALL_PROXY`。 | 独立脚本 13 项：默认 0.6/0.6/0.6、空串回退默认、三个 env 各自独立生效、越界/NaN/非数字均拒绝、缺 key fail-closed、缺代理错误文本**不含** key（哨兵测试）、真实 `.env` 可提供 key+代理、fallback 期间 ALL_PROXY 等于 HTTPS_PROXY 且退出后还原。**FAILURES: none**。 | Passed | 满足；凭据与代理处理 fail-closed 且不泄漏。 |
| R2、R5 | P02 / T2 | V04 / G1 | `jev/decision.py::reconcile_router` 与 `validate_action_answers`：Noul 概率与 Choice 的 choice/confidence/probabilities 全部 typed 校验；候选线用 `JEV_NOUL_CANDIDATE_THRESHOLD`，Router 与 Action confidence 各自使用独立门槛；不合格即 `JevDecisionError` 或以 `effective_action="wait"` 收敛，不产生目标。 | 独立脚本 23 项 fake typed 响应：候选线 0.6 计入、0.59 不计；confidence 0.6 生效、0.59 转 wait 并记录原因；`choice="wait"` → wait；选项不在候选内 → wait 并记录 `selected_action_not_a_noul_candidate`；Noul 门槛放宽后同一请求可放行（证明门槛独立生效）；非最高概率选项、概率键集不符、非法 Noul 概率、缺 next_action Choice 全部被拒；Action 侧 plant 多问题任一 <0.6 即 low_confidence 且 target=None、恰好 0.6 生效、collect/shovel 目标映射正确、选项不在声明集合被拒、未声明概率键被拒、不支持的 intent 被拒。**FAILURES: none**。 | Passed | 满足；typed 答案在任何派发前完成校验，wait/低置信不产生目标。 |
| R6 | P02 / T1、T2 | V05 / G1 | `configs/plant_catalog.py`：`PLANTS` 49 项，`PlantInfo.description_en` 非空；`_plant_questions` 用当前 usable 卡的 `type_name` 生成 `plant_type` criteria，取值来自目录 `description_en`。 | 目录完整性：`PLANTS` 49 项，空 `description_en` = 0，`plant_info(code)` 名称一致 = 0 处不符，名称唯一。真实样本请求构造：`plant_type` criteria keys = 当前 3 个 usable 卡（potato_mine / sunflower / wall_nut）且为 usable 子集，取值与目录 `description_en` 逐项相等且非空。 | Passed | 满足；所有植物具备可用英文能力描述并实际进入 criteria。 |
| R7 | P02 / T1、T2 | V05 / G1 | `configs/zombie_catalog.py`：`ZOMBIES` 34 项均含 `name` 与 `description_en`；`build_typesafe_state` 只把当前样本出现的 type 追加为 `catalog_context.zombie_abilities`，未知/自定义类型不推测。 | 目录完整性：`ZOMBIES` 34 项，空 `description_en` = 0，空 `name` = 0，`zombie_info(code)` 一致，名称唯一，未知 code → `None`，`ZOMBIE_NAMES` 34 项且键为 `ZOMBIES` 子集。真实样本：`build_typesafe_state` 仅新增 `catalog_context` 一个键，上下文条目 = 当前出现的 `normal_zombie`（去重、仅当前类型、描述非空），且不含 `source`/`raw_snapshot`/`availability`/`evidence`/`errors`/`pid`。 | Passed | 满足；英文能力只作为当前局上下文，未改 JEV projection schema。 |
| R2、R6、R7 | P02 / T2 | V05 / G1（其余分支） | `_collect_questions`/`_shovel_questions` 只使用同样本 items 与已占用格；不支持的 intent 抛 `ValueError`。 | 真实样本：collect 的 `item_0` 目标 `type_code`/`type_name`/`x`/`y` 与样本 item 完全一致；shovel criteria 恰好为 2 个已占用格 `r1c1`/`r2c3`（与样本 2 株植物一致）；plant 的 cell criteria 为 43 个空格且**排除**已占用格；`build_action_questions("wait")` 被拒。 | Passed | 满足；target 映射与同样本前提成立。 |
| R12 | P05 / T1、T2 | V19 / G1 | `runtime/session.py::TargetSession.read` 稳态只调用 `module_base_reader` 与 `snapshot_reader`；`state/builder.py::_capture_raw` 改为 `_default_session().read()`，不再含进程枚举与磁盘 SHA-256。 | 自动化：`test_session.py` 固定 clock 调用计数矩阵。真机：40 与 60 样本两轮，`resolver=1`、`verifier=1+⌊T/1s⌋`、`module_base=N`、`snapshot=N`，1 s 边界落在每 10 个样本（=1.0 s）。 | Passed | 满足；真机稳态零枚举、零磁盘校验。 |
| R12 | P05 / T2 | V24 / G2 | 同上；真实内存读取仍通过持有句柄。 | 真机 60 样本：稳态中位 **3.49 ms**、p95 4.13 ms、max 5.02 ms、**0/54 超 10 ms**；建立样本 46.99 ms（一次性）；1 s 边界样本中位 13.02 ms。被移除项实测 locate 21.65 + verify 8.99 = **30.64 ms**，与 3.49 相加 ≈ 34.1 ms ≈ Plan 依据的 ~33 ms 基线。 | Passed（G2，未触发升级） | 未达升级条件；R12 的「约 5–6 ms」估计偏保守，实测更低。 |
| R13 | P05 / T1 | V20 / G1 | `TargetSession.read` 先判身份/存活类异常（`ProcessDiscoveryError`、`ProcessExitedError`）再作废并原样重抛；`invalidate()` 关闭真实句柄且吞掉 `CloseHandle` 的 `MemoryAccessError`；数据读取类失败不作废。 | 自动化：guard / 1 s 重验证 / 30 s 重解析三处注入失败均原样抛、句柄关闭计数 1、下一 `read()` 各自重跑定位与验证一次；`MemoryAccessError` 不作废且下一采样不重解析。真机：注入 guard 失败 → 样本 2 `error` 且真实句柄关闭，样本 3 重新解析成功（PID 10888、SHA-256 与 pinned 一致）；真实不存在路径 → `disconnected`。 | Passed | 满足；fail-fast 与下样本重解析在真假两路均成立。 |
| R13 | P05 / T1 | V21 / G1 | 第二次解析 PID 不一致抛 `IdentityMismatchError`；解析/验证异常原样冒泡；失败路径不调用 `snapshot_reader`。 | 自动化（Plan 明确以 fake 覆盖）：PID 变化 / 歧义 / 零匹配 / 主模块路径变化 / 摘要不符各抛对应既有异常且 `snapshot_reader` 从未被调用。真机部分：真实零匹配路径得到 `disconnected`。 | Passed | 满足；真机歧义与磁盘摘要分支需改变目标系统状态，Plan 未要求且未获授权。 |
| R14 | P05 / T2 | V22 / G1 | `TargetSession.read` 在 `identity.as_dict()` 基础上追加 `identity_verified_at_utc`；`state/projection.py` 不输出 `source`；`jev/trace.py::summarize_jev_state` 不输出 `source`；`_unavailable_record` 不新增该键。 | 自动化：注入值精确出现；projection 与 `build_trace_event` 文本均无该字段；`schema_version==1`；`raw_reader` 注入路径无该字段且 monkeypatch 使默认会话访问器抛错仍成功。真机：40/40 样本含该字段、4 个互异值间隔 ≈1.05 s；`snapshot --once` 为 `ok/valid` 并含该字段；`serve` 的 `/api/state` 含该字段而 `/api/jev-state` 既无 `source` 也无该字段。 | Passed | 满足；证据链诚实且隔离在真实 HTTP 面成立。 |
| R12 | P05 / T1–T3 | V23 / G1 | P05 三个 Task 的 backfill 与 `Actual` 已填，T1–T3 均 `[x]`。 | `-p "test_*.py"` → Ran 148, OK, exit 0（P05 前基线 129）；`test_session.py` 13、`test_state.py` 34、`test_jev_trace.py` 7 均 OK；三种导入顺序成功。 | Passed | 满足；无回归。 |
| R12、R13 | P05 / T1、T2 | P05/V25 / G1（本次新增） | V19–V21 的全部自动化证据均为 fake 注入；真实协作者链在 `TargetSession` 下此前从未真机执行。 | 真机执行成功：`probe` 身份匹配 pinned SHA-256 `F587…8DD4`、PID 10888；`snapshot --once` 为 `ok/valid`；`serve` 采样正常；注入会话真机测量 100 个样本全部 `valid`、`sample_sequence` 严格递增、`retry_count` 恒 0。 | Passed | 满足；未新增此检查将无法排除「实现只在 fake 下成立」这一会推翻 R12/R13 的可能。 |

## 4. Plan and Task Results

本轮新增：

- **P03（Approved；第 10 次修订的 Plan 状态见 §9）**：T1–T38 全部 `[x]`，backfill 与 §7 检查（V1–V80）已在 plan-03 回填。第十次修订属**追认回填**（Human 指示「不走 SDD、直接改」后已实施），无未完成实现项。全量回归 **420 tests OK**。
- **P04（Approved）**：其实施产物（`jev/trace.py` 的 v2 `RuntimeEventBuilder`、Dashboard JEV 页）在 5 局真机中持续产出并被消费；本轮按 **Human 接受**记录其验证（见 §9），未单独重跑 P04 的确定性检查。

| Plan ID | Task ID | Planned outcome | Actual result | G1 impact | Result |
|---|---|---|---|---|---|
| P01 | T1 | 实现并说明可验证的 decision_ready gate | `evaluate_decision_readiness` 集中实现 `jev_eligible` 必要条件、18 个 required availability 的 available/provisional 门槛、5×9 投影与 cards/plants/zombies/lanes/items 结构校验；证据有效的空数组保留；unsupported mode/background 与损坏投影 fail-closed。 | 直接覆盖 R1。 | Passed |
| P02 | T1 | 接入官方 SDK/dotenv 依赖与 Plant/Zombie catalogs | 安装 typesafe-sdk 0.7.1 与 python-dotenv 1.2.3（`pyproject.toml` + `uv.lock`）；`load_dotenv(override=False)` 在 SDK 之前加载且先校验 key/代理；`PLANTS` 49 项与 `ZOMBIES` 34 项均含非空英文 `description_en`；`ZOMBIE_NAMES` 保持兼容。 | 覆盖 R2（配置部分）、R6、R7。 | Passed |
| P02 | T2 | 实现 Decision Router 与 intent-specific Action requests | `build_router_questions` 固定 3 Noul + 1 next_action Choice；`build_action_questions` 按 intent 生成 collect/plant/shovel typed Choices；`reconcile_router` 与 `validate_action_answers` 校验 typed 答案、独立门槛与候选一致性，未达门槛一律不产生目标。 | 覆盖 R2、R5、R6、R7。 | Passed |
| P05 | T1 | 新增 `TargetSession` 与采样守卫 | `runtime/session.py`（154 行）+ `runtime/__init__.py` 导出 + `tests/test_session.py`（13 用例）。 | 覆盖 R12/R13。 | Passed |
| P05 | T2 | 默认采集路径切到会话并记录身份验证时间 | `state/builder.py`：`_DEFAULT_SESSION` + 锁、`_default_session()` 惰性、`reset_default_session()`、`_capture_raw` 改为委托、`capture_state(raw_reader=None, session=None)` 三级优先且 `raw_reader` 完全绕开会话、清理 5 个失效 import；`tests/test_state.py` +6 用例。 | 覆盖 R12/R14。 | Passed |
| P05 | T3 | 更新架构说明中的身份保证与采集契约 | `docs/architecture.md` 新增 `## Capture session and identity guarantee`，含 ≤30 s 歧义窗口与 `identity_verified_at_utc` 的证据边界。 | 支撑 R13/R14。 | Passed |

## 5. Commands Run

本轮新增（确定性）：

- `uv run python -m unittest discover -s tests -p "test_*.py"` → **Ran 420 tests, OK**（本轮直接改动前基线 414）。
- 变异回放（每次逐字节还原并复核 sha256）：OD-59 队列 **4/4 CAUGHT**（去重删除、溢出记录删除、FIFO→LIFO、上限失效）；威胁升档 **2/2 CAUGHT**（去掉升档、`undefended` 并回 `critical`）；区域/植物事实/经验文件轮次 **8/8 CAUGHT**（区域 x/y 回退、去重失效、排序丢失、名称匹配失效、`plants[].role` 删除、Trace 丢弃 `plant_abilities` 等）。
- 真机日志分析（只读，逐行 JSON 解析）：对 `.log/test_01..05.jsonl` 统计事件/动作/丢弃原因/`reason_category` 证据/威胁标签分布，命令与输出见本轮对话记录与 §6 表格。

| Check ID / tier | Command | Observed result | Evidence / important output |
|---|---|---|---|
| V01 / G1 | 独立只读脚本（`%TEMP%\p01_readiness_check.py`，真机样本 + 逐项翻转） | **52 项，FAILURES: none** | 基线 `decision_ready=True`；9 个表达式条件、18 个 required availability × 2、2 个空数组必须通过、3 个 mode/background、2 个 sun 结构全部符合预期 |
| V02 / G1 | `uv run python -m unittest discover -s tests -p "test_state.py"` | Ran 34, OK | 含 `CaptureSessionTests` 6 例 |
| V03 / V04 / G1 | 独立只读脚本（`%TEMP%\p02_typed_check.py`，fake typed 响应） | **36 项，FAILURES: none** | 门槛默认/独立性/校验 13 项；Router reconcile 13 项；Action validate 10 项 |
| V05 / G1 | 独立只读脚本（`%TEMP%\p02_catalog_check.py`，真机样本） | 全部符合预期 | `PLANTS` 49/49 与 `ZOMBIES` 34/34 均有非空 `description_en`；`build_typesafe_state` 只新增 `catalog_context`、无禁止键泄漏；3 Noul + 1 Choice；plant criteria = 3 个 usable 卡且取值等于目录；cell criteria 43 个空格并排除已占用格；shovel criteria 恰为 `r1c1`/`r2c3`；collect `item_0` 与样本 item 完全一致；`wait` intent 被拒 |
| V05 / G1 | `uv run python -m unittest discover -s tests -p "test_jev_client.py"` | Ran 19, OK | dotenv 优先级、catalog 覆盖、Router/Action request、typed mapping、SDK 错误脱敏 |
| V19、V20、V21 / G1 | `uv run python -m unittest discover -s tests -p "test_session.py"` | Ran 13, OK | 固定 clock 与调用计数器；失败注入四路；fail-closed 五分支 |
| V22 / G1 | `uv run python -m unittest discover -s tests -p "test_jev_trace.py"` | Ran 7, OK | Trace 不含 `source` 与该字段 |
| V23 / G1 | `uv run python -m unittest discover -s tests -p "test_*.py"` | Ran **148**, OK, exit 0 | 逐次执行共 3 轮结果一致 |
| P05/V25 / G1 | `uv run python -c "import runtime; import runtime.session; import state.builder"` | 三者均成功 | `runtime.TargetSession` 可解析 |
| V03、P05/V25 / G1 | `uv run python main.py probe` | 成功 | `pid=10888`、`file_version=1.0.0.1051`、`pe_machine=0x014C`、`sha256=F587903E…C8DD4`（与 pinned 一致）、`sun=50`、`plants.max_used=2` |
| V22、P05/V25 / G1 | `uv run python main.py snapshot --once` | `status=ok`、`valid=True`、`schema_version=1`、`sun_balance=50`、`decision_ready=True`、`source` 含 `identity_verified_at_utc` | 真实 CLI 默认路径（`_default_session`）端到端可用 |
| V22 / G1 | `uv run python main.py serve --port 8791 --interval-ms 100` + `GET /api/state`、`/api/jev-state` | `/api/state` 含 `source.identity_verified_at_utc`；`/api/jev-state` 键集无 `source` 且文本无该字段 | R14 隔离在真实 HTTP 面成立；检查后已终止并确认端口释放 |
| V19、V24 / G2 | 独立只读测量脚本（`%TEMP%\p05_live_verify.py`、`p05_live_verify2.py`） | 稳态中位 **3.49 ms**、p95 4.13、max 5.02、**0/54 超 10 ms**；`resolver=1`；被移除项 30.64 ms | 见 §3 V24 行 |
| V20 / G1 | 独立只读恢复脚本（`%TEMP%\p05_live_recovery.py`） | (a) 真实不存在路径 → `disconnected`；(b) 样本1 `ok` → 样本2 guard 失败 `error` 且真实句柄关闭 → 样本3 重解析成功 | 见 §3 V20 行 |

## 6. Manual / Browser Verification

**Human 亲自运行的真实对局（真实 TypeSafe API + 真实游戏输入；本人标注其语义）**：

| 日志 | Human 标注 | 时间(UTC) | 最大 wave | stop / `final_phase` | 动作(collect/plant) | `batch_superseded` | 真越界(x∈[10,40),y≥80) | `already_pending` | `undefended` |
|---|---|---|---|---|---|---|---|---|---|
| `.log/test_01.jsonl` | 未添加任何经验 | 10:33–10:39 | 14 | `level_finished` / — | 216 (169/47) | 585 | **109** | — | 无标签 |
| `.log/test_02.jsonl` | 刚添加经验 | 11:05–11:10 | 10 | `level_finished` / — | 156 (116/40) | 545 | **188** | — | 无标签 |
| `.log/test_03.jsonl` | 经验迭代后**通过 1-1** | 11:38–11:44 | **20** | `game_left_playing_phase` / — | 251 (192/59) | 604 | **0** | — | 无 |
| `.log/test_04.jsonl` | 打 1-2 **失败** | 11:46–11:54 | **20** | `level_finished` / — | 302 (235/67) | 753 | **0** | — | 0（标签已生效） |
| `.log/test_05.jsonl` | 应用最新改动后**通过 1-2** | 12:16–12:25 | **20** | `game_left_playing_phase` / **`level_intro`** | 251 (195/56) | **0** | **0** | **355** | **429** |

关键对照（Human 操作产生的可观察变化）：

1. **掉落物区域（R48/T31）**：真越界记录从 109/188 → **0/0/0**，Human 观察到的「最后 1–2 列向日葵的阳光无法收集、百分百消失」不再复现。
2. **collect 授权队列（R51/T34）**：`batch_superseded_by_newer_batch` 753 → **0**，改由 `cohort_member_already_pending`（355）逐成员记账 —— 授权不再被新回答丢弃（OD-59 闭环）。
3. **威胁标签与升档（R50/T33）**：`test_04` 起请求态只有标签；`test_05` 中 `undefended` 出现 429 次，「无攻击植物的行」首次对模型可见。
4. **胜负可读（R53/T36）**：`test_05` 的 `runtime_stop.final_phase = level_intro`，可与 `level_finished` 区分。
5. **经验与目录（R54/R55）**：布局随经验变化 —— `test_01/02` 以 sunflower（23/24）为主 → `test_03` peashooter 23 + jalapeno 5 → `test_05` **peashooter 22 + squash 13**（攻击优先 + 即时清场），且最终**通过 1-2**。
6. Human 逐局结论：`1-1` 由 `test_03` 通过；`1-2` 由 `test_04` 失败、`test_05` 通过 —— 与日志中的 `stop_reason`/wave 20/末帧威胁分布一致。

| Check ID / tier | Check | Observed result | Evidence / human source and date |
|---|---|---|---|
| V24 / G2 | Human 提供受支持的真实对局并要求 agent 启动观察 | 游戏运行中（PID 10888），日间草坪、阳光 50、2 株植物、1 只僵尸且**僵尸被 Human 冻结** | Human 提供的游戏截图与说明，2026-09-27；本轮只读测量即基于该实机状态 |
| V05 / G1 | 目录与请求构造对照真实局面 | plant 的 usable 卡为 potato_mine/sunflower/wall_nut；shovel 候选恰为 `r1c1`/`r2c3`，与样本 2 株植物一致 | 独立脚本对真机样本的实测输出，2026-09-27 |
| V22 / G1 | HTTP 证据（不以只读源码代替） | `/api/state` 含 `identity_verified_at_utc`；`/api/jev-state` 无 `source` 亦无该字段 | `urllib` 对 `http://127.0.0.1:8791` 的实测响应，2026-09-27 |
| P02 §7「真实网络/代理/密钥确认」 | TypeSafe SDK 经 `.env` 代理访问官方 endpoint 并返回 typed Choice | **Not run**（见 §8）：Plan 将该确认明确指派给 P03/V07 的 Human 有界 live loop，不属于 P02 的检查项；且真实 API 调用未被授权 | `plans/02-jev-api.md` §7 Commands 与 Manual checks |
| Plan P05 §7「手工确认」 / G2 | 目标游戏**退出**后输出 `disconnected`、重启后恢复采样 | **Not run**（见 §8）：会改变 Human 已准备的系统状态，超出「观察」授权。已用不触碰游戏的真实等价证据替代 | 授权边界见 §9；等价证据见 §5 V20 行 |

## 7. Issues Found

### 本轮（P03/P04）发现并已解决

| # | 问题 | 观察证据 | 处置 |
|---|---|---|---|
| P03-1 | 掉落物可点区域过窄（x 下限 40 = 第 0 列左缘），第 0 列向日葵产的阳光漂到 x∈[10,40) 即被判 `outside_region`、永不点击 | `test_01` 109 条、`test_02` 188 条真越界记录 | 直接实施 `bounds = (0, 80, 800, 600)`（T31/V73）；`test_03/04/05` 真越界 **0** |
| P03-2 | collect 只保留 1 个待执行批准，新的肯定回答会丢弃尚未执行的旧批准 | `test_04` 753 条 `batch_superseded_by_newer_batch` vs 302 个动作（39%） | 直接实施有界 FIFO 队列 + 等价合并去重（T34/V76、OD-59）；`test_05` 该类丢弃 **0** |
| P03-3 | 管理答案若在 `cancel`/`keep` 时不给建造类型即被判 `invalid_management_response`，模型自己的 cancel 被丢弃 | `test_04` 5 次 | 仅 `replace` 要求类型（T35/V77） |
| P03-4 | 手牌目录解析不出即整张卡不进入请求；`plants[]` 无能力文本；威胁只用数字表达（模型对数字不敏感） | 现场构建对照（`run d8a00084` 的 `cards`/`plants`/`observed_lanes`） | 直接实施描述补全、`engagement` 标注、威胁标签化 + `undefended` 升档（R50/R54/R55） |
| P03-5 | Trace 无法区分通关与被推（`stop_reason` 只有 `level_finished`） | `test_04`（实际失败）与胜利局同为 `level_finished` | `runtime_stop` 增 `final_phase`（T36/V78）；`test_05` 实测可见 |

（本表所列为**已解决**项；Verify 不修复代码，修复由 Human 指示的直接改动或后续 `$sdd-implementation` 完成。）

1. **测试模块耦合（非核心，不阻塞）** — `tests/test_state.py:15` 以 `from test_jev_trace import sample_cycle` 跨测试模块导入，而 `tests/` 下没有 `__init__.py`。仅因 `unittest discover -s tests` 会把 `tests/` 放入 `sys.path` 才成立；`python -m unittest tests.test_state` 会失败，且 `test_jev_trace.py` 改名或改结构会连带损坏 `test_state.py`。影响范围仅测试代码，无 G1 影响。Verify 不修复。
2. **跨 Plan 表述过期（非核心，已于 2026-09-27 解决，见本节第 4 项）** — `plans/03-runtime-loop.md:47,578,598` 仍把 P05 描述为「独立待审计划」「尚未实施」「其尚未存在的 session」。P05 现已获批并实施，表述已过期。**无功能矛盾**：P03 明确声明不修改 P05 的身份保证与重验证决策，且 P03 尚未获批、不在本次验证范围。Verify 不修改 Plan，仅记录。
3. **P01/P02 验证中未发现实现缺陷** — 需要说明的是，本轮独立脚本首轮曾报 14 项失败，经逐项归因**全部为校验脚本自身缺陷**（缺少一个关键字参数、真实 `.env` 被 `load_dotenv` 回填导致未走到缺 key 分支、以及对未知选项报错文案的期望过窄）。修正后 36/36 通过；这些失败**不**计入产品发现。
4. **跨 Plan 表述已同步修正（原第 2 项问题的解决记录）** — 本轮验证开始时 `plans/03-runtime-loop.md:47,578,598` 曾把 P05 描述为「独立待审计划」「尚未实施」「其尚未存在的 session」。Human 在同日的 P03/plan-index 修订中同步修正：P03 的 `Depends on` 现为「P01、P02、P05（已实施采集基线）」，正文明确「P05 已 Approved、T1–T3 实施完成、verify.md 仅 R12–R14 Passed」，并声明「既有 148 项与 3.49 ms 现场数据是 P05 历史证据，不是异步 Runtime 验证结果」。原表述**无功能矛盾**（P03 从未修改 P05 的身份保证），现亦不再存在。Verify 不修改 Plan，仅在此记录该解决。
5. **检查 ID 命名空间（已在本文档消歧）** — plan-index 现要求检查 ID 带 Plan 前缀。P03 修订同时存在 `P03/V25`（异步隔离）与 `P05/V25`（真机采集会话路径，本验证新增），两者是不同检查。本文档把该新增检查统一标注为 **P05/V25**；§3 与 §5 中涉及该检查的行均使用带前缀写法。

## 8. Missing Evidence and Blockers

| Check ID / tier | Missing evidence or deferred check | Cause category and reason | Current delivery impact | Recheck trigger |
|---|---|---|---|---|
| P02 §7 真实 API 确认（非 P02 自有检查项） | 未通过真实 network/proxy/key 访问 TypeSafe endpoint 并取回 typed Choice | External condition + Plan 指派：`plans/02-jev-api.md` §7 明确把该确认交给 **P03/V07** 的 Human 有界 live loop；P03 现为待审且未实施。另：真实 API 调用（计费 + 状态外发）未被授权。 | 不阻塞 P02 自身 G1：V03 已证明 `.env`/代理/门槛配置与脱敏正确，V04/V05 已用 fake typed 响应证明 typed 校验与请求构造；端到端连通性属 P03/V07。 | P03 获批并实施后由 Human 执行 V07 |
| Plan P05 §7「手工确认」 / G2 | 未在**真实游戏退出与重启**下观察 `disconnected` 与恢复采样 | Authorization or safety boundary：Human 授权范围为「启动并观察」，并要求保留其已准备的冻结僵尸对局；终止或重启游戏会改变目标系统状态，超出授权。 | 不影响核心目标：fail-fast、`disconnected` 映射与下一采样重解析已由 V20 的自动化证据与真机等价证据覆盖。 | Human 自行关闭并重启游戏后运行 `snapshot --once`，或明确授权 agent 执行 |
| V21 / G1（真机部分） | 未在真机制造第二个同名同路径进程（歧义）与磁盘摘要改动 | Authorization or safety boundary：二者都需启动第二个游戏实例或替换目标 exe，会改变受保护的目标系统并与 003/004 既有策略冲突。Plan 已将 V21 明确限定为 fake 覆盖。 | 无；V21 按 Plan 口径已 Passed。 | 若需真机确认 ≤30 s 歧义窗口，需 Human 授权并说明恢复条件 |
| — | 未验证**动态对局语义** | External condition：僵尸被 Human 冻结，样本自身标注 `evidence_policy = "Single paused-frame evidence; not a dynamic gameplay verification."` | 不影响 R1/R2/R6/R7/R12–R14：这些验收都不依赖动态玩法；动态语义属其它 Plan。 | 需要动态语义时应由相应 Plan 在非冻结对局中验证 |

- 全部适用的 G1 检查均已执行并取得通过证据。上表各项均为 G2、Plan 已指派给其它 Plan、或 Plan 已限定覆盖口径，不构成总体 `Blocked`，也不构成本次目标的产品失败。

## 9. Human Decisions and Accepted Risks

| Check ID | Original tier / observed result | Decision and source/date | Reason and applicable scope | Remaining risk / recheck trigger |
|---|---|---|---|---|
| — | Iteration 006 级审批为 `Pending human review`（因 P03 未获批），而 P01/P02/P05 已 Approved | Human 裁定「P05 获批即足够，仅 P05 范围内实施」，2026-09-27；P01/P02 已由 Human 明确批准 | 使已获批且无 Open Decision 的 Plan 可在 Iteration 未整体获批时实施与验证；本次验证覆盖 P01/P02/P05，**不延伸**至 P03/P04 | Iteration 整体结论仍需 P03 获批并实施后单独验证 |
| — | 只读观测授权 | Human 于 2026-09-27 说明「游戏已经准备好，你来启动吧，你来观察」，并说明僵尸已冻结但游戏仍运行 | 授权 `probe`/`snapshot`/`serve` 与本机只读测量；**未**授权 `action`（游戏输入）、`jev-loop`（真实 JEV API 调用）或终止/重启游戏 | 如需 `action`/`jev-loop` 真机验证，需 Human 另行显式授权并给出停止/恢复条件 |
| V24 / G2 | G2，实测稳态中位 3.49 ms，未超过升级阈值 10 ms | 未触发升级，无需 Human 接受风险 | Plan 规定「稳态每样本 >10 ms 才升级为 G1」 | 若后续机器或负载变化使稳态超过 10 ms，重新评估数组/字段批量读 |
| P05 §3 Out of scope | 不改数组/字段批量读 | 已在 Plan 获批时接受，2026-09-27；且真机实测 `plants.max_used=2`、「capacity=1024」使循环次数远小于按容量估算的最坏情况 | 批量读取收益上限不足 5 ms | 仅在 V24 升级时重查 |

### 本轮新增：缺失证据与阻塞（P03/P04）

| Check ID / tier | Missing or deferred | Cause category | Current delivery impact | Recheck trigger |
|---|---|---|---|---|
| V07 / G1（受控真实 API + 真实游戏） | 无缺失 | 由 **Human 亲自完成**：5 局真实对局（`test_01..05`）覆盖真实 TypeSafe 调用、真实鼠标输入、真实胜负 | 不阻塞；作为 P03 的 G1 真实环境证据 | 若更换 `.env`/代理/游戏版本或 mod，重跑一局 |
| V41 / G1（问题/阈值/事实/reason 词表/经验文本逐条人工审阅） | 未逐条留痕 | 授权与范围：Human 连续驱动并逐项接受这些改动（含经验文本与标签词表），未写成逐条审阅清单 | 由 §9 的 Human 裁定接受（范围限本次交付），不阻塞 | 下一 Iteration 若继续改问题集/阈值/词表，应重新逐条审阅 |
| 执行完整性 | — | 本轮适用的 G1 检查均已执行或有 Human 真机证据 ⇒ **Complete** | — | — |

### 本轮新增：Human 裁定与接受风险（P03/P04）

| Item | Observed | Decision / source | Reason and scope | Recheck trigger |
|---|---|---|---|---|
| 006 整体验收 | P01–P05 全部实施完成；P03 T1–T38 `[x]`；全量 420 tests OK | **Human 声明**：「006 已达到我的期望，我已经测出了 JEV 的能力上限，所以 006 可以 passed」；2026-09-27 | 接受 006 当前状态；以真人 5 局（含 1-1 通过、1-2 失败→通过）为主要真实证据 | 若继续迭代 006，需重新建立需求与检查 |
| P03 第 10 次修订的 Plan Approval | plan-03/plan-index 记为 `Pending human review`（因实质修订被重置） | 该修订是对 Human 直接实施内容的**追认**（T33–T38 均 `[x]`、无未完成实现），Human 在同一条指示中要求按真人测试直接回填并称「符合期望」 | 本文档按 Human 裁定接受为本次交付依据；**不修改 Plan** | Human 若回一句 `approved`，Plan 状态同步为 Approved（只改状态） |
| V41 逐条审阅 | 未留逐条记录 | Human 持续驱动并接受相关改动 | 接受范围限本次交付；不改变未来 Iteration 的需求基线 | 见 §8 |
| P04 验证 | 未单独重跑 P04 的确定性检查 | Human 接受（其实施产物在 5 局真机中持续产出并被消费） | 接受范围限本次交付 | 若修改 Trace/Dashboard 结构，重跑 P04 检查 |
| G2/G3 保留项 | 见 §8 与 plan-03 §8 | 未触发升级条件 | 队列接受面、`undefended` 仅呈现层、经验文件接近预算、TTL 交回缺测试断言 | 各条对应的升级触发条件 |

## 10. Conclusion

- Overall result: **Passed**（范围：P01/P02/P05 的 G1 要求与核心路径）
- Verification execution: **Complete**
- Reason: P01 的准入矩阵在真实样本上 52 项翻转全部符合预期，P02 的配置/typed 校验/目录与请求构造在 36 项独立检查与 49+34 项目录完整性检查下全部通过，P05 的真机采集稳态中位 3.49 ms 且 fail-fast/重解析/字段隔离在真假两路均成立。全部适用的 G1 检查均已执行，无影响核心目标的失败，无 G1 必要证据缺失。真实 API 连通性与真实游戏退出/重启两项按 Plan 指派或授权边界未运行，均不阻塞各自 Plan 的自有 G1。
- G1 evidence summary: 全量回归 **148 tests OK**（含 `test_state.py` 34、`test_jev_client.py` 19、`test_session.py` 13、`test_jev_trace.py` 7）；独立检查脚本 52 + 36 项及目录 49/34 项全部通过；真机 PID 10888 身份匹配 pinned SHA-256，100 个采集样本全部 `valid`、`sequence` 严格递增、重试恒 0，稳态采集中位 **3.49 ms**（对照被移除项实测 30.64 ms）。
- Accepted G2 risks and deferred G3 checks: 真实游戏退出/重启下的 `disconnected` 与恢复采样未运行（授权边界，已有等价真机证据）；真机歧义与磁盘摘要改动分支未制造（Plan 限定为 fake 口径）；动态对局语义未验证（僵尸被冻结）；真实 TypeSafe 端到端连通性由 P03/V07 承担。
- Scope limitation: 本结论只适用于 **P01、P02、P05**。P03（异步 JEV Runtime）为待审且 T3–T7 未实施、OD-15/OD-22 开放；P04 本轮未请求验证。**Iteration 006 的整体结论仍未建立。**
- Required next stage: 无。P01/P02/P05 的实现仍**未提交**（无 `delivery.md`），可经 Human 显式调用 `$sdd-delivery` 交付。§7 的两项非核心问题如需修复，应由 Human 显式调用 `$sdd-implementation`。

- 总体结论（本轮更新）：**Passed**（范围：**Iteration 006 全部** —— P01、P02、P05 的既有结论 + **P03**（T1–T38，含第 10 次修订的追认记录）+ **P04**（按 Human 接受））。
- 执行完整性：**Complete**（本轮适用的 G1 检查均已执行，或有 Human 真机证据/明确裁定）。
- 依据：**Human 亲自运行的 5 局真实对局**提供了真实 API、真实输入与真实胜负的端到端证据 —— `1-1` 由 `test_03` 通过、`1-2` 由 `test_04` 失败、`test_05` 通过；同一批日志同时给出四项可量化对照：真越界收集记录 **109/188 → 0**、`batch_superseded_by_newer_batch` **753 → 0**（改为 `cohort_member_already_pending` 355 逐成员记账）、`undefended` 标签出现 **429** 次、`runtime_stop.final_phase` 首次可读。确定性侧：全量 **420 tests OK**，变异回放 4/4 + 2/2 + 8/8 全部 CAUGHT 且逐字节还原。
- 非核心保留项（已按 §9 接受或 §8 记录）：V41 未逐条留痕（Human 裁定接受）；P03 第 10 次修订的 Plan Approval 仍为 Pending（Human 裁定接受，未改 Plan）；P04 未单独重跑确定性检查（Human 接受）；TTL 交回缺测试断言、经验文件接近预算（784/800）、`undefended` 仅呈现层升档。
- 历史段落（第一份结论，范围 P01/P02/P05）仍有效：P01 准入矩阵 52 项、P02 36 项 + 目录 49/34 项、P05 真机稳态中位 3.49 ms（对照 30.64 ms），当时的全量基线为 148 tests OK。
- Required next stage: 无强制项。006 的实现仍**未提交**（无 `delivery.md`），可由 Human 显式调用 `$sdd-delivery` 交付；§7 的非核心问题如需修复，应由 Human 显式调用 `$sdd-implementation`。Verify 未修改任何生产代码、测试或 Plan。
