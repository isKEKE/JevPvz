# Plan Index

## 1. Metadata

- Iteration: 006-jev-runtime-loop
- Created at: 2026-09-27
- Status: Approved
- Owner: 本仓库维护者

## 2. Goal

在当前受支持PvZ对局中实现默认连续观察、各分支相关状态变化驱动的JEV判断、统一串行动作执行。Observer无默认100ms/5s等待，--interval-ms仅为可选观察限速；collect/plant分别比较最近提交/可靠决定的语义key，变化才请求，无变化skip，在途仅保留latest。收集与种植无任务依赖或阳光预留，收集成功后的确认余额经最新State自然进入PlantBranch。全局2个请求在途、每分支1个，内部依赖stage顺序调用；动作仍有typed来源并经当前资源/目标/新鲜度校验与Boundary。Trace v2关联分支/job/stage/execution且兼容v1。P05采样会话已实施并验证Passed（仅R12–R14）；现行capture使用带锁TargetSession，既有148项与现场3.49ms为P05证据，不证明异步JEV已实现。

请求设计对齐 TypeSafe 官方 pattern：一次决策 = 一次 fan-out 请求（含推测性问题）、问题原子化并由**代码按显式权重合并**、数值与算术一律在代码完成、`state` 按问题裁剪、questions 与 thresholds 集中单一可审阅文件；目标采用「本地枚举完整候选 + 一次 Choice + 代码用返回的完整 `probabilities` 做约束下重排」，仅当候选空间无法本地枚举时才允许第二轮。

本次收集修订（2026-09-27）：用户确认 JEV 仅是否收集，模型不看坐标/ID，不再选择目标；本地冻结请求样本全部有效 item ID，一次肯定回答授权整批逐个执行；新 ID 下一批询问。实际点击由 Executor 按 ID 获取即时坐标。该条保留此前收集修订范围，最新经营扩展见下一段。当前规范以 P03 的 OD-34/OD-35、R23/R24、T10–T12、V45–V49 为准；T1–T9 是已完成历史。

本次自主经营修订（2026-09-27，当前规范）：用户明确应由JEV自主选择，不由Human预给攻略答案。撤回预定义目标方案、经济规模/布局/防线完成参数与理想阵容缺口；OD-37改为模型选择/保持/替换/取消建设意图，OD-39按“不需业务参数”解决，OD-40取消新Runtime本地phase/urgency驱动与候选重排覆盖。代码只提供观察事实/能力/合法行动、当前计数/费用/支付能力、执行守卫与记录。收集/经营同state同请求、冻结整批ID、PlantBranch具体合法目标仍保留；等待指定建设由JEV决定并可改变/取消。技术门槛是实验条件，不是经营答案。R23–R30、T10–T15、V45–V56待实施，P03/Iteration已由Human本轮批准，无阻塞性Open Decision。

当前实施状态（2026-09-27）：P03 T1–T15均已实施完成；本次主agent完整回归350 tests OK。收集单Noul/本地ID整批、经营shared请求/自主意图、同样本可信波次、无本地目标重排、来源/TTL/不确定输入守卫与Trace证据均已实现。Approval保持Approved；正式Verify待显式调用，V07/V41未执行。下方“待实施”等旧修订文字为历史规划记录，不代表当前完成状态。

本次冷启动修订（2026-09-27，当前规范，待批准）：两次受控实机运行（`run c8c02e90` 58.8 s、`run 78993a85` 31.4 s 新开局）显示收集路径已恢复（31.4 s 内 5 个可见阳光全部收到、0 拒绝、0 过期，Trace 无 ID 泄漏；collect 闸门完全二分：空 items 0.10–0.12 / 有阳光 0.54–0.60），但同一窗口内**零种植**（sun 150、45 空位、3 种可负担植物）。根因有二：plant 的 act-now 绝对 Noul 实测 0.18–0.26 低于部署门槛 0.3 并反复 `model_wait`，而模型自己的 `plant_target` 已明确给出 `sunflower@r0c0`（0.36/0.50）与 `peashooter@r2c0`（0.54/0.38）；冷启动 `construction_intent` 恒为 null，而 `keep/replace/cancel` 三选项均相对当前意图定义，模型 17/17 选 `cancel`。Human 已确认六项修订：**OD-41** plant 删除 act-now Noul、改由弃选项作主（`argmax ≠ none_of_above` 且 `best > none`，零新增可调参数，`best`/`discard`/`margin` 记入 Trace）；**OD-42** collect 闸门铆定 `COLLECT_ACT_THRESHOLD = 0.5` 并与 `JEV_NOUL_CANDIDATE_THRESHOLD` 解耦；**OD-43** 删除 `needs_immediate_response`（实测 7/17 为真却无消费者）；**OD-44** 空 items 不问收集子问题；**OD-45** 开局 `wave == 0` 时僵尸分量不进 PlantBranch key（实测 9 僵尸 0.93 s 后归 0，吞掉了开局唯一一次通过闸门的种植）。连带修订 OD-05/OD-13/OD-22（`model_wait` 语义），新增 R31–R34、T16–T19、V57–V60，并改写 V33/V38/V45/V50/V53/V55 的闸门断言。**P02 历史同步路径与 `actions/executor.py` 不动**；`x<80` 点击区域限制（G2）未解除。T16–T19 未实施。

本次可用性与布局事实修订（2026-09-27，第 5 次，当前规范，待批准）：受控运行 `run 92f9a6ac`（104.5 s、50 动作）显示 collect 36 次派发里 **8 次（22%）被点击区域直接拒绝**（边界证据 `rejection_evidence: ["item_coordinate_evidence"]`、`input_status: not_sent`），几何对账证明 `bounds` 的 x 下限 80 恰等于列 0 中心（`first_cell_center.x=80`、`horizontal_spacing=80`）而把列 0 左半 `x∈[40,80)` 整块排除、y 下限 80 又排除高处下落物（实测 y≈60）；另有 1 次 collect 因 10 s 确认超时**阻塞唯一 worker 10.2 s**（`polls: 40`、`waited_ms: 10000`），期间同屏阳光堆到 5 个、丢弃 1 个；以及 **46/72 次「模型已授权收集」既无动作也无记录**（活跃批期间的 `selected` 被静默丢弃，OD-35 的「latest 未授权状态」槽位缺失）。plant 侧模型只拿到全局按类型计数与逐株坐标，没有每行构成与列方向语义，实测退化为「向日葵全在 row 0、坚果放在房屋侧 c0/c1」。Human 已确认四项取值：`bounds=(40,40,800,600)`、collect `timeout_ms=2500`、布局/列方向/角色事实进入共享 state、角色仅作事实暴露（不拆问题、不按角色过滤）。新增 R35–R38、OD-46–OD-50、T20–T23、V61–V64；OD-46 按 §8 既有条件把掉落物区域 **G2→G1**；同步改写 V31/V44 的 state 字段集断言与 collect 请求键集断言。**T20–T23 已实施完成。**（主 agent 验收：全量 377 tests OK；变异复算 4/4 CAUGHT 且逐字节还原；V61–V64 探针全 PASS。）

本次账本/轮转修订（2026-09-27，第 6 次，当前规范，待批准）：受控运行 `run 94a40c3c`（26.7 s，结束时暂停）显示坐标拒绝 **0 次**（T20 生效）、`unverified` 仅 **2.656 s**（T21 生效，旧为 10.2 s），但 collect 的**授权与执行不守恒**：13 次 `selected`、**16 个已授权成员槽位**，却只有 **6 次 collect 派发**与 **1 条丢弃记录** → **约 9 个成员槽位无任何记录**；用户截图那一刻正是 2 件批只执行第 1 件。四条静默路径已定位：`stop_dispatch` 清批不记录（尾部授权在此消失）、`_discard_cohort` 只按 `targets[0]` 记一条、`_pump_cohort` 的 id 剪枝 `return`、以及忙闸门/队首阻塞 `return`（后者会让同批兄弟成员一直等到批时效）。Human 确认三项：**OD-51** 批成员终态账本（每成员必须以 `executed` 或 `discarded(reason)` 收尾；含 stop 路径；四个新 reason）、**OD-52** 队首轮转（`_blocked_collect` 队首移到队尾，条件未变不重复排队首）、**OD-53** 不可执行证据（原因类别 + client 坐标，**不含 item ID**）。**OD-35 保持不变**（授权窗口仍自接受起算、不续期、排队计入窗口内）—— Human 明确确认，不修订。新增 R39–R41、OD-51–OD-53、T24–T25、V65–V67；记账复用既有 action-discard 通道（不新增事件类型，避免污染 v2 job 计数）。**T24–T25 已实施完成。**（主 agent 验收：全量 389 tests OK；变异 2/2 CAUGHT 且逐字节还原；纯函数探针 10/10 PASS。）

本次 finished/重试修订（2026-09-27，第 7 次，当前规范，待批准）：受控运行 `run e6c84636`（23.3 s）显示 collect `selected` **12 次 / 15 个成员槽位**，却只有 **4 次派发**（3 success + 1 `unverified`，`same_item_present: true`）与 **0 条丢弃记录**；**8 次空手而归全部发生在唯一一次 `unverified` 之后**，同屏太阳一直未消失。根因（符号级已核实）：`jev/loop.py:1126-1128` 的 `else` 把**除 TTL 过期外**的所有派发结果都记入 `_finished_ids`（含 `unverified` 与调度侧丢弃），而 `_finished_ids` 只在 `:665` 按「当前样本仍存在的 id」清理 → **可见物品被永久拉黑**；`:629` 的前置过滤随后把授权过滤成**空批**且不记录；`collect_identity_key` 未变又使分支因 `last_decided_key` 命中而 skip、连重问都不发生。Human 确认三项：**OD-54** `finished` 只由「物品确实消失」（`success` / `postcondition_result == "met"`）判定，`unverified` 且物品仍在 → 保持可重试并**重臂该分支**（清 `last_decided_key` + `request_recheck`）以获得**新的一次**授权（只要物品还在就允许无限重试；重试不是重放同一 proposal，OD-35 窗口仍自新授权被接受起算）；**OD-55** 空批过滤必须记账（`cohort_members_all_finished`）。新增 R42–R44、OD-54/OD-55、T26–T27、V68–V69；「可能已发送输入后的 rejected」等其它状态**保持既有保守语义不变**。**T26–T27 已实施完成（全量 391 tests OK；主 agent 独立验收：生产形态探针 PASS、定向 70 OK、变异回放 5 项中 4 项 CAUGHT 且逐字节还原；M5「TTL 交回失效」未被捕获 = suite 既有空缺）。**

本次布局经验与结果事实修订（2026-09-27，第 8 次，当前规范，待批准）：Human 提出「要不要在 state 里写几条经验（资源植物靠房屋侧、防御靠僵尸侧、攻击靠后因血低且多为远程，除非近战）」。结论：**不写进 `state`** —— `state` 的已批准边界是 facts-only（OD-49/OD-50），且会连带白名单与 Trace parity 成本；Human 定为**只改 `instructions` 文本**（OD-56）并**同时加入最小结果事实**（OD-57）。文本以 `board.column_direction`（`house_side_col: 0` / `zombie_side_col` 最高列）锚定方向语义、只表达倾向且显式让位给即时威胁，**不写列号**（Human 原话的前/后列号自相矛盾）、不做区位过滤或配额（OD-15 全枚举不变）、catalog 不加射程/耐久字段（「除非近战」暂由模型读 `description_en`，记为已知限制）。结果事实取 run 级：`JevLoopSummary.final_phase`（`_state_stop_reason` 已读 `game.phase` 却把 `level_complete` 与 `zombies_win`/`level_award` 折叠成 `level_finished`，胜负被丢弃）+ `lane_closest`（run 内每行 `nearest_cells` 最小值 = 僵尸最近逼近几格），经 `main.py` run JSON 暴露；**不新增 v2 事件类型**，逐样本接近度已在 Trace 中可离线交叉校验。新增 R45–R46、OD-56/OD-57、T28–T29、V70–V71。**T28–T29 未实施。*
**补充（OD-58，Human 追加）**：经验不硬编码，改由一个**入库的手编文件** `configs/plant_experience.txt` 管理（UTF-8、`#` 注释与空行忽略、每行一条、建议英文），加载器在 `jev/questions.py`，每次构建植物问题时读取（不缓存）、追加到三处 `instructions` 的固定锚定句之后；缺文件视为空、**运行时不因内容失败**，预算（≤12 行/≤800 字符）与 `state.<字段>` 引用合法性只由测试守护（既有 `RequestFieldAcceptanceTests` 会扫描最终 instructions）。**T30 已实施完成（全量 406 tests OK；主 agent 独立验收：差分证明 `jev/loop.py` 仅 26 行改动、`_state_stop_reason` 逐字未动、探针 13/13 PASS、变异回放 7/7 CAUGHT 且逐字节还原）。**

本次掉落物区域与植物能力事实修订（2026-09-27，第 9 次，当前规范，待批准）：Human 报告「边缘太阳无法收集、百分百消失」，受控运行 `run d8a00084` 复算证实 **82 条** collect 批成员记录因 `outside_region` 从未点击（去重 **29 个落点**，其中 **26 个在 x∈[10,36]、y∈[103,414]** —— 草坪左缘/割草机条带上方、客户区内、**可点却被拒**；另 3 个 y∈[17,31] 在种子栏 UI 之后，拒绝正确），同局实际收集动作仅 50 次；根因是 `configs/pvz_1051.py` 的 `item_coordinates.bounds = (40,40,800,600)` 的 x 下限 40 过窄。修法：**`bounds = (0.0, 80.0, 800.0, 600.0)`**（x 到客户区左缘；y 到草坪上沿 `130 − 100/2 = 80` 以免点进种子栏 UI），只改常量、判定与点击点解析不变（R48）。第二项：Human 指出「植物的描述信息好像没在 jev state」—— 实测 `cards[]` 有 `description_en`/`role`、选项有 `plant_ability`，但 **`plants[]` 与 `catalog_context` 完全没有植物能力**（`catalog_context = {"zombie_abilities": []}`），mod 环境下模型看不出场上植物干什么；修法：`catalog_context.plant_abilities`（本样本手牌+已种类型去重、稳定排序、`{type_name, description_en, role}`，与 `zombie_abilities` 同构、不推断不在场类型）+ `plants[]` 每项 `role`，**不新增 state 顶层键**，Trace 投影同步（R49）。第三项 **collect 授权队列**：实测 `batch_superseded_by_newer_batch` **545 次** vs 实际 collect 动作 **116 次**（现行「只保留 1 个待执行批准」会丢弃尚未执行的旧批准）—— 记为 **Open Decision OD-59**（选项：先做等价合并去重（推荐）/ 多批 FIFO 上限 3 / 两者都做 / 维持现状），待 Human 明确后回填为 Task。新增 R48–R49、T31–T32、V73–V74，并**改写 V61** 的边界断言。**T31–T32 已实施完成（全量 414 tests OK；主 agent 独立验收：探针 20/20 PASS、变异回放 8/8 CAUGHT）。**

本次直接实施回填修订（2026-09-27，第 10 次，当前规范，待批准）：Human 在本 Iteration 中对若干行为改动作出「**不走 SDD、直接改**」的明确指示，主 agent 已直接实施并逐项独立验证；本次把它们**追认为正式需求与实现记录**，使 Plan 重新成为唯一事实来源。六项：① **威胁标签化 + 无攻击植物升档**（请求态不再含僵尸侧数字：`observed_lanes[] = {row, threat, crowd, composition, attacker_count, has_defender}`、`zombies[] = {type_name, row, proximity, armor}`；闭集 `threat = none|unknown|low|medium|high|critical|undefended`，**本行无攻击植物**时有僵尸 → `undefended`、无僵尸 → `high`；升档仅呈现，`urgency_band`/branch key 不变）；② **OD-59 闭环**（单槽 → **有界 FIFO 队列上限 3 + 等价合并去重**：超限记 `batch_queue_overflow`、重复成员记 `cohort_member_already_pending`，每批保留「自接受起算 5 s」窗口）；③ **管理答案校验**（仅 `replace` 要求类型答案，`keep`/`cancel` 缺省合法 —— 修掉基线 5 次误判）；④ **Trace `runtime_stop` 增 `final_phase`**（可区分通关与被推）；⑤ **目录 `engagement ∈ {ranged, melee, none}`**（49 项全标 18/6/25，**经济 = `role == "resource"`**）并下发到 plant 选项；⑥ **描述事实补全 + 经验策略**（手牌不再丢弃目录外新卡、`plants[]` 带 `description_en`、建造类型选项带能力文本；`configs/plant_experience.txt` 重写为 **10 条/784 字符**的标签驱动策略，含「远程植物提前种」「优先攻击植物而非防守植物」）。新增 R50–R55、T33–T38（均 `[x]`）、V75–V80。全量 **420 tests OK**。**T33–T38 已实施。**

**Human 接受声明（2026-09-27）**：Human 明确表示「006 已达到我的期望，我已经测出了 JEV 的能力上限，所以 006 可以 passed」。据此记录 006 的**当前状态由 Human 接受**；该声明不改变 `verify.md` 既有内容（仅 P01/P02/P05 为 Passed），P03/P04 的正式 `Verify Passed` 标注仍需显式 `$sdd-verify` 写入，且 V07（受控真实 API/游戏）与 V41（逐条人工审阅）仍未执行。

### Requirement Baseline

| Requirement ID | Requirement | Source | Verification tier | Reason for tier |
|---|---|---|---|---|
| R1 | 将当前恒为 false 的 decision_ready 改为有明确条件的 admission gate。jev_eligible 必须满足 state.valid、status == ok、phase == playing、未暂停，以及 board.cells/cards/zombies/items 均非 null；required field 还须符合已确认 evidence 门槛。 | 用户引用的“游戏状态与动作边界”对话、本次明确指定 Plan 01 及 2026-09-27 补充的 jev_eligible 表达式；用户选择接受合规 provisional；现有 State 契约。 | G1 | Admission 是每次 JEV 调用前的核心安全与可信度门槛。 |
| R2 | 官方 TypeSafe typed API 使用 model=jev-latest；P02 已有 Router/Action 是基础，P03 用 AsyncTypeSafeClient.system_one 实现分支局部意图和目标阶段；Noul、意图 Choice、目标 Choice 门槛独立，保留 typed answers/confidence/probabilities。 | 既有官方 API/SDK 需求与本次用户要求异步 Runtime、局部决策分层；已读本地 SDK async API。 | G1 | JEV 分支判断仍需真实 typed 来源与正确门槛。 |
| R3 | 默认连续capture→publish；collect/plant按相关语义key变化触发JEV、未变skip，独立wait；执行串行，暂停/退出关闭派发。--interval-ms可选观察限速，未指定/0无额外等待，正值不控制JEV调用间隔；API返回后消费最新相关变化，不额外sleep。 | 用户最新while-loop/状态变化/optional interval要求，2026-09-27。 | G1 | 新Runtime默认与触发语义是用户要求的核心行为。 |
| R4 | 显式 --trace-file，v2 JSONL 记录 job/branch/stage/execution 因果事件、样本/时延/confidence/usage/门槛、wait/discard/排队和 Boundary 结果；v1 writer 记录为历史格式，reader/UI 保持 v1/v2 兼容。 | 原 Timeline 要求及本次异步顺序/旧结果分析；P03 扩展现有 P04 Trace。 | G1 | 异步完成顺序与实际执行顺序必须可追溯。 |
| R5 | State 观察不自动授权动作；plant/shovel 保持 typed 目标；collect 每件必须属于 JEV 肯定回答的来源冻结批，具体目标由本地 ID 管理并经 Boundary/Executor 复核。 | 用户本次明确“JEV 这里只做到是否收集”及选择“整批收取”，取代原 collect 每件目标 Choice；其它动作原约束不变。 | G1 | 每件仍有可复核的 typed 授权来源，新 ID 不借旧回答。 |
| R6 | 当前 PLANTS 每种植物具有非空英文 description_en；植物选择阶段的 Choice.criteria 使用这些能力描述，若采用完整类型/位置候选，也包含对应植物能力。 | 用户要求补齐植物 criteria 描述且 config 使用英文；本次 P03 目标契约整合。 | G1 | 植物局部判断必须有可区别的能力上下文。 |
| R7 | 当前所有已知僵尸类型均有英文能力描述；TypeSafe request context 仅附加当前 sample 中出现的类型描述，不更改 JEV projection schema。 | 用户选择纳入 Zombie 能力目录，2026-09-27；EA 原版 Readme 指向 Almanac 作为僵尸能力来源。 | G1 | State 的 type/HP/armor/distance 无法完整表达部分僵尸专属移动或防御机制。 |
| R8 | 当前前端增加 JEV 导航页和简洁时间线卡片；Dashboard 与 Loop 独立运行，共读同一份 Human 显式指定的 JSONL Trace，页面只读显示最近周期，不触发游戏输入。 | 用户 2026-09-27 请求在现有前端增加 JEV 页面/card；本次选择共享同一 JSONL 文件、两个进程独立。 | G1 | 时间线卡片是用户要求的直接可见交付；若不能读取实际 Loop Trace，展示目标未完成。 |
| R9 | PlantBranch保留开局向日葵经济和未覆盖僵尸行防守，使用State确认余额/卡牌；没有可负担有效候选本地等待，余额或候选变化再判断。CollectBranch独立collect/wait；两者无完成回调/funding任务/预收入或资源预留。目标仍成立时低置信失败不当作完成。 | 既有开局/防守要求及用户最新取消收集与种植显式依赖的设计。 | G1 | 收集后新State自然解锁种植，避免钱不足反复请求或执行未到帐预算。 |
| R10 | 结合植物战略角色、逐行僵尸数量/最近房屋距离/现有战斗覆盖评估威胁；策略评估基于当前 sample 中可行动的植物类型与行列信息，是否将其收敛为 JEV 候选由 P03 的 OD-15 决定。 | 用户提议按行的僵尸数量和距离分析种植需求与列位置，并将资源植物与攻击植物分开处理。 | G1 | 逐行威胁与角色分类是运行时策略的依据；具体 typed Choice 方案须经过 OD-15 设计，避免把未确认的候选方案固化进需求。 |
| R11 | JSONL Trace 记录本轮策略目标、按行威胁摘要，以及 Router/Action 的真实 answer 与结果；策略字段采用白名单摘要，不保存额外原始 State。 | 用户要求把策略设计并入 006 P03 Runtime；现有 P04 JSONL Trace contract。 | G1 | 需要还原策略优先级与 JEV 实际选择/执行结果，判断目标、置信度或 Boundary 哪一层影响动作。 |
| R12 | 把 State 采集从“每样本重新发现并完整验证目标进程”改为“持有已验证目标会话”：会话建立时一次性定位与验证并持有目标句柄，每样本只做廉价守卫（存活 + 主模块路径 + 模块基址），使每样本固定采集开销从实测约 33 ms 降到约 5–6 ms。 | 用户 2026-09-27 指出“JEV runtime 需要 100ms 一次 loop、理论需要 100ms 刷新”，并选择先做采集路径优化；本次对 `locate_target_process`、磁盘 SHA-256、持有句柄守卫与单次 ReadProcessMemory 的直接实测，以及从既有 Trace 反推的约 33 ms/样本基线。 | G1 | 采集开销影响持续观察的吞吐；原100–250ms仅是历史规划场景，不是当前默认节奏，且可用确定性的调用计数而非机器相关的耗时来验证。 |
| R13 | 身份保证改为“会话建立时全量验证 + 每样本廉价守卫 + 每 1 s 磁盘身份重验证 + 每 30 s 进程唯一性重解析”；持有句柄消除 PID 复用；守卫失败使本样本 fail-fast 并作废会话、下一采样重新解析。 | 用户在本次 Plan 执行中先后确认“接受周期性歧义检测”、“身份 1s / 唯一性 30s”、“本样本 fail-fast，下样本重解析”；现有 003/004 身份契约与 `actions/executor.py` 的一致性检查。 | G1 | 该改动收窄了既有已验证的安全属性（歧义从每样本 fail-closed 放宽为不超过 30 s 的窗口），必须由证据与显式批准覆盖。 |
| R14 | State 的 `source` 增加 `identity_verified_at_utc`，显式记录该样本所依据的最近一次成功身份验证时间；additive，不改 `schema_version`，不进 JEV projection 与 Trace。 | 用户本次选择“加 identity_verified_at_utc”；现有 `source` 字段与 projection/Trace 的隔离契约。 | G1 | 放宽验证频率后，采集证据链仍必须能说明身份是在何时被验证的，否则 `source` 会被误读为“本样本刚被验证”。 |

| R15 | 两分支按决策相关key变化触发，全局2请求在途、每分支1，latest-only；比较排除序号/时间等元数据，不能按相邻采样漏掉在途变化。可靠wait未变不重复请求，错误/低分允许有界恢复；默认无固定分支sleep。 | 用户状态变化→JEV、未变skip及去掉默认100ms要求；OD-21既有选择。 | G1 | 变化驱动必须实质减少请求并及时消费最新可行动局面。 |
| R16 | 完整输入/确认串行，派发前检查当前实际余额/卡牌/格子、来源pair/episode/身份/目标和时效；晚到/失效结果零派发，不换模型目标。第一版不建跨分支DAG、resource claim或阳光预留。 | 用户最新独立分支/State衔接与已有动作互斥约束。 | G1 | 简化协作同时维持旧结果与实际资源的正确执行边界。 |
| R17 | v2 事件关联 branch/job/stage/request/execution，区分完成与执行、wait/discard和停止；旧 v1 JSONL 与 Dashboard 保持可读。 | 异步结果因果追踪与现有 P04 展示使用结果。 | G1 | 新运行记录能复核且旧运行记录不失去可用性。 |
| R18 | 同一次决策使用一次 fan-out 请求：所有该 state 的问题（含只有部分输入才用得上的推测性问题）在同一请求内；不采用逐问题串行调用。 | 用户 2026-09-27 要求按官方建议设计；官方 patterns/fan-out、cookbooks/parallel_questions。 | G1 | 直接决定请求拓扑，可用调用次数确定性断言。 |
| R19 | 问题原子化，代码机械合并typed答案/来源并执行合法性校验；原业务权重/重排不能替模型给策略答案，问题/技术阈值集中审阅。 | 原官方原子问题需求及本轮用户自主选择修订OD-40。 | G1 | 策略答案应来自JEV，代码不得隐蔽覆盖。 |
| R20 | 数值/计数/算术一律在代码完成；`state` 按问题裁剪；Noul 与 Choice 的语义与门槛不混用。 | 同上；官方 model-jaggedness/jev-1.13 的应避免清单与 "Common-sense structural invariants"。 | G1 | 违反会降低准确率或引入与官方结论相反的约束。 |
| R21 | collect 决策前提与目标身份分离：普通坐标下落不作废；ID 在本地绑定，当前修订由 R23/R24 进一步规定单 Noul/整批授权与 Boundary ID 请求；ID 不进 Trace。 | 既有 OD-32 及本轮用户明确 ID 策略，2026-09-27。 | G1 | 保持收集位移容忍并防止错收。 |
| R22 | `job_start` 记录**实际发给模型的裁剪 state**（而非 v1 摘要），且不含 `availability`/`source`/`raw_snapshot`/凭据。 | 同一次实机运行发现 `job_start.state` 是 v1 `summarize_jev_state` 摘要、无 items 坐标。 | G1 | Trace 是本次交付的可复核证据来源。 |

| R23 | 收集职能只问是否收集，一个typed Noul、无collect_target；items仅类型/代码计数，无物品坐标/ID/index。按R25扩展共享request时可同时包含经营问题与必要事实。 | 用户先确认收集单闸门，后要求经营并入同state/request，2026-09-27。 | G1 | 不恢复模型逐件选目标，明确共享问题边界。 |
| R24 | 一次肯定回答授权请求样本的全部有效 item ID，本地冻结整批逐件收取，不为同批每件重问；Boundary 按 ID 适配现有 Executor，新 ID 下一批询问；当前坐标即时读取，保持互斥/身份/停止/不确定结果不重放。 | 用户明确 ID 策略并在交互中选择整批收取，2026-09-27。 | G1 | 决定是否实际缓解逐件询问且不扩大授权。 |

| R25 | 现有collect worker的一次shared state/JEV请求同时评估收集与经营；空items不阻断经营相关变化，答案独立，保持两个worker与单执行器。 | 用户确认同state/output方式并显式要求经营加入P03，2026-09-27。 | G1 | 指定请求拓扑与经营活性。 |
| R26 | 提供实际生产/阵容/威胁/能力/预算卡牌/可信波次/已有模型意图；只算当前计数/费用/支付能力，sun与coin区分，unknown不补零，不含攻略目标缺口。 | 用户本轮自主经营要求与当前输入不足的源码证据。 | G1 | 模型输入应为真实事实。 |
| R27 | JEV自主选择、保持、替换或取消下一建设意图；撤回人工阵容方案/规模/布局/完成规则，代码持有意图与实际执行事实供后续判断。 | 用户本轮明确“应该让JEV选择，而不是我给一个答案”，修订OD-37并解决OD-39。 | G1 | 实验观察模型自主经营而非拟合攻略。 |
| R28 | PlantBranch忠实执行模型选择的完整合法目标；模型可选择等待指定建设、改用途或取消，代码不替换候补动作；派发核对真实余额/位置/类型。 | 用户自主选择原则与已确认OD-38的支出等待。 | G1 | 每件动作来自实际模型选择。 |
| R29 | 经营/collect独立key、epoch与内容版本；意图只是上下文，每件动作仍typed授权；无items经营活性、独立typed局部判断、共享输入到实际动作可追溯。 | shared请求与自主经营生命周期源码证据。 | G1 | 防止误失效、旧授权与不透明策略覆盖。 |

| R30 | 不给人工攻略答案，不通过本地phase/固定威胁档/候选重排覆盖模型；合法性/来源/预算/互斥等技术守卫保留并明示。 | 用户本轮明确自主选择，OD-40。 | G1 | 代码不能把模型策略错误偷偷纠正为人类策略。 |
| R31 | plant 的「要不要动手」由模型自己在完整目标 Choice 的弃选项里表达；代码不得设置绝对闸门决定能否动手。 | Human 确认 OD-41（删除 act-now Noul、弃选项作主），2026-09-27；实测绝对闸门 0.18–0.26 使开局 31 s 零种植。 | G1 | 直接决定冷启动能否种植；判据为零新增参数的相对规则（`best > none`）。 |
| R32 | collect 的「是否收集」使用固定锚点 0.5，与其它门槛解耦，且该锚点是人工可审阅的显式常量。 | Human 确认 OD-42，2026-09-27；实测 17/17 在 0.3 与 0.5 下结论相同。 | G1 | 收集是核心可用行为，门槛必须可审阅且不随 P02 配置漂移。 |
| R33 | 共享请求按事实裁剪：没有可收集物品时不再询问收集子问题，经营问题仍保留。 | Human 确认 OD-44，2026-09-27；实测 17 次 collect 请求中 9 次在空物品上白问。 | G2 | 当前表现为 token 浪费，不妨碍核心路径；若清理导致经营被饿死则升级 G1。 |
| R34 | 关卡尚未开始（`wave == 0`）时的僵尸分量不得使 PlantBranch 决策作废或被判为种植前提变化。 | Human 确认 OD-45（wave 守卫），2026-09-27；实测开局 9 僵尸 0.93 s 后归 0。 | G1 | 该瞬变实测吞掉了开局唯一一次通过闸门的种植决策。 |
| R35 | 掉落物点击区域必须覆盖游戏实际掉落范围（含列 0 左半与高处下落物）；被区域拒绝时必须给出坐标证据。 | Human 确认 OD-46 `(40,40,800,600)`，2026-09-27；实测 8/36（22%）派发因几何过窄被拒。 | G1 | 直接决定阳光能否被收（实测核心路径受阻）。 |
| R36 | 收集确认必须有有界超时（显著小于现状 10 s），且超时结果必须携带确认证据。 | Human 确认 OD-47 `timeout_ms=2500`，2026-09-27；实测成功确认 median 1091 / max 1431 ms，一次超时阻塞 10.2 s。 | G1 | 单次未确认点击会阻塞唯一执行 worker。 |
| R37 | 活跃批期间的收集授权不得静默丢失：必须保留一份 latest 未授权批并按既有 5 s 时效消费或记录丢弃。 | 补全已批准 OD-35（OD-48），2026-09-27；实测 46/72 次授权无动作也无记录。 | G1 | 授权与执行必须可追溯，且直接影响收集吞吐。 |
| R38 | 供模型使用的共享 state 必须包含每行己方构成、列方向语义与角色事实（仅事实与语义，不含推荐或配额）。 | Human 确认 OD-49/OD-50，2026-09-27；实测布局退化为单行堆叠与房屋侧坚果。 | G1 | 事实缺失使模型必须自行数行且缺乏方向语义。 |
| R39 | 每个已授权收集成员必须以 `executed` 或 `discarded(reason)` 收尾；批结束（TTL/覆盖/id 消失/停止/全部不可执行）逐条记录未执行成员。 | Human 确认 OD-51，2026-09-27；实测 16 个成员槽位只有 6 次派发 + 1 条记录。 | G1 | 授权与执行不可追溯，直接掩盖了漏收。 |
| R40 | 暂不可执行的队首成员不得阻止同批其他成员执行。 | Human 确认 OD-52；实测 2 件批只执行第 1 件，第 2 件直到暂停都没收。 | G1 | 队首阻塞是「太阳躺在草地上不收」的直接机制。 |
| R41 | 未执行/被延迟成员的记录必须能归因：含原因类别与该件 client 坐标，且不含 item ID。 | Human 确认 OD-53；现有 Trace 只有证据键名，无法区分 x<40 死带与 y<40 瞬时。 | G1 | 该证据是判断是否还需再调 `bounds` 的唯一手段。 |
| R42 | collect 成员的 `finished` 判据只能是「物品确实消失」（`success` / `postcondition_result == "met"`）；`unverified` 且物品仍在不得标 finished、不得永久排除。 | Human 确认 OD-54；实测一次 `unverified` 使可见太阳被永久拉黑，随后 8 次授权空手而归。 | G1 | 「大概率不捡、偶尔捡起来」的直接原因。 |
| R43 | 该情形之后必须把 collect 分支交回重评估，使同一物品能获得新的一次授权并被执行；不得重放同一 proposal。 | Human 确认 OD-54；只改 finished 判据不够 —— id 集合未变时分支会 skip 不重问。 | G1 | 否则重试永远不会发生。 |
| R44 | 一次肯定授权在过滤后没有任何可执行成员时，必须留下带 reason 的记录。 | Human 确认 OD-55；该路径此前完全静默（8 次授权在此消失）。 | G1 | 静默出口掩盖了误判 finished 的后果。 |
| R45 | 植物问题 `instructions` 用 `state.board.column_direction` 锚定方向语义，表达资源/防御倾向并让位给即时威胁；不写列号、不做区位过滤或配额。 | Human 确认 OD-56；`state` 侧 facts-only 边界（OD-49/OD-50）不变。 | G1 | 措辞反向会引导反向布局（Human 原话本身有前/后歧义）。 |
| R46 | run 级最小结果事实 `final_phase` + `lane_closest`（每行 `nearest_cells` run 最小值），经 run JSON 暴露；不预测不计分、不进模型输入、不新增 v2 事件、`status` 语义不变。 | Human 确认 OD-57；没有结果事实则布局改动无法验收。 | G1 | 后续策略改动的唯一可对照证据。 |
| R47 | 植物布局经验由手编文件 `configs/plant_experience.txt` 管理（UTF-8、`#` 注释、每行一条、入库）；加载器每次构建读取并追加到三处 `instructions`；运行时不因内容失败，预算与 `state.<字段>` 合法性只由测试守护。 | Human 追加要求「一个文件、手动加经验」；选定入库 + 测试守预算。 | G1 | 手加经验的唯一通道。 |
| R48 | 掉落物可点区域 = `(0.0, 80.0, 800.0, 600.0)`（x 到客户区左缘、y 到草坪上沿）；左缘/割草机条带上方可点、种子栏 UI 之后仍拒；只改常量。 | Human 报的边缘太阳 bug；26/29 实测丢弃落点可点却被拒。 | G1 | 直接造成「太阳凭空消失」。 |
| R49 | `catalog_context.plant_abilities`（本样本手牌+已种类型去重、稳定排序、`{type_name, description_en, role}`）+ `plants[]` 每项 `role`；不新增顶层键；Trace parity。 | Human 指出 state 无植物能力；mod 植物无法辨识。 | G1 | 铲除/补种缺事实依据。 |
| R50 | 请求态僵尸侧只给有序标签（含 `undefended` 升档）；无攻击植物的行至少 `high`；升档不改调度/键。 | Human 直接指示（数字不可靠）；已实施并验证。 | G1 | 让模型看到正确严重度。 |
| R51 | collect 肯定授权用有界 FIFO 队列（上限 3）+ 等价合并去重，超出/重复都记账，窗口不变。 | Human 直接指示（OD-59）；753 vs 302 基线。 | G1 | 提升授权→动作转化率。 |
| R52 | 管理答案仅 `replace` 要求类型答案；`keep`/`cancel` 缺省合法。 | Human 直接指示；基线 5 次误判。 | G1 | 不再丢弃合理答案。 |
| R53 | `runtime_stop` 携带 `final_phase`（stop 语义不变）。 | Human 直接指示；复盘需要。 | G2 | 每局可判胜负。 |
| R54 | `PlantInfo.engagement ∈ {ranged, melee, none}`（49 项全标）并下发到 plant 选项；经济 = `role == resource`。 | Human 直接指示；远程/近战放置策略。 | G1 | 让模型不必从描述猜射程。 |
| R55 | 手牌不因目录缺失而消失、`plants[]` 带 `description_en`、建造类型选项带能力文本；经验文件为标签策略（≤12 行/≤800 字符）。 | Human 直接指示；mod 环境事实缺口。 | G1 | 模型需要知道场上/手牌是什么。 |

## 3. Scope

### In scope

- 当前自主规范优先：不输入固定阵容/规模/布局/阶段公式，不本地重排或用phase/urgency覆盖JEV；本局仅保留最后模型意图与最近实际结果。下方既有Runtime描述中旧攻略规则已由OD-40取代，T1–T9历史证据保留不代表新规范已实现。

- 经营加入P03：R25–R29、T13–T15；扩展现有collect worker复用shared request，PlantBranch消费经营快照，不新增第三worker。OD-37/38确认模型自主意图与支出等待，OD-39不需攻略参数，OD-40取消策略覆盖；无需新依赖，修改既有strategy/questions/config/client/decision/loop/scheduler/trace、目录最小能力分类与UI/文档。

- 本轮仅收集增量：P03 R23/R24、T10–T12；Boundary 扩展 item_id 请求而 Executor.collect_item 点击/确认流程复用；Trace/README/架构按收集职责变化最小同步。无新依赖，不改 projection allowlist，不把 ID 发送 JEV 或落入 Trace。

- 按 P01 定义并实现 decision_ready，使用现有 All State 的 availability、errors、字段值和模式信息；JEV 投影仍只按现有 allowlist 输出。按已确认决定允许结构有效的 provisional。
- P02 的官方 SDK/typed 问题与英文目录保持基础能力；P03 使用已安装 AsyncTypeSafeClient，分支局部意图/目标按 OD-15 分层。配置一次初始化、代理在并发请求期间稳定，三个 .env confidence 门槛仍独立，默认各 0.6。
- 三种门槛分别校验并分别使用，配置缺失/留空默认 0.6；Trace 保存每次 Router 与 Action 决策实际采用的门槛。
- 补齐现有 49 个 PlantInfo 的 description_en，并为当前 34 种 ZombieInfo 增加 description_en；植物能力用于 plant_type Choice criteria，僵尸目录仅把本 sample 实际出现的类型附加到 TypeSafe request state。All State 与 project_jev_state schema 不变。
- P03默认连续观察，--interval-ms省略/0不加固定等待、正值只限观察；两个分支按相关key变化请求/未变skip，首个有效状态评估一次，latest-only，不丢在途变化；请求返回后没有额外默认sleep。全局2/分支1在途已确认，TTL/异常恢复/具体key与有界计数仍按OD-15/22。
- State capture 与 visible item 只提供事实；plant/shovel 来自 typed 意图/目标；collect 来自 typed 肯定回答的冻结 ID 批并经 Boundary。
- 复用 P04 JSONL/只读 Dashboard 基础，P03 增加 v2 分支/job/stage/execution 事件与新旧兼容；始终显式 --trace-file，不默认逐个高频 observation 全量落盘。
- 在现有 Dashboard 增加 JEV 导航页和简洁时间线卡片；`serve` 通过显式配置同一路径只读 JSONL，页面呈现最近完整周期、决策与结果。未配置时显示空闲状态，不允许通过 HTTP 请求指定任意文件路径。
- 对配置错误、SDK timeout/exception、Noul/Choice 不一致、低置信度、目录缺描述、拒绝动作、暂停、失效 State、关卡结束和用户中断定义 fail-closed 行为。
- P03按事实/派生特征/JEV局部判断分层；经济/防守基于当前确认资源。collect和plant无显式依赖、完成通知、预测阳光或资源预留；统一执行器只做原子输入、已就绪优先/公平性和派发前最新State校验。
- 已实现的 P05 建立“已验证目标会话”：会话建立时一次性执行 `locate_target_process` 与 `verify_target_identity` 并持有目标进程句柄；每样本只做廉价守卫（`main_module_base` 复核 PID 存活、主模块路径与模块基址）；磁盘身份验证与进程唯一性解析分别按 1 s 与 30 s 周期重跑，时间来源可注入以便测试。
- 已实现的 P05 把 `state/builder.py` 的默认采集路径从 `_capture_raw` 切换到会话；`capture_state(raw_reader=None, session=None)` 保持向后兼容，注入 `raw_reader` 时完全绕开会话；会话读取加锁以支持模块级默认调用。
- 已实现的 P05 区分身份类失败与数据读取类失败：身份/存活类失败（`TargetNotRunningError`、`AmbiguousTargetError`、`IdentityMismatchError`、`ProcessExitedError`）作废会话并在本样本按现有规则 fail-fast，下一采样重新解析；数据读取类失败不作废会话，沿用现有无效样本重试路径。
- 已实现的 P05 在 `source` 增加 `identity_verified_at_utc`，并更新 `docs/architecture.md` 的 runtime 与 State 契约说明，写明放宽后的身份保证与不超过 30 s 的歧义检测窗口。

### Out of scope

- 本轮允许有限、可审阅经营目标与本地支出等待；下方历史“长周期经济规划/长期记忆”排除项仅指无限期预测、跨局历史、自学习/最优通关，不排除本次R25–R29。不引入预收入、资金任务或阳光锁定。

- 完整自动通关策略、无边界的模型提示词搜索、长期记忆、训练、OCR/Vision、并行或多角色 Agent。
- 超出开局经济/未覆盖活动僵尸行/目标资金补充的一般通关策略、长周期经济规划、模型校准和任意 prompt 搜索；P03 仅规划由当前 State 驱动的有限策略规则与上下文。
- 新动作种类、改写 ActionExecutor 的既有点击/确认语义（本轮仅扩展 Boundary collect ID 请求适配）、内存写入、游戏暂停/冻结或自动启动游戏。
- 程序自动 collect visible suns、自动种植、自动铲除，或任何不经 JEV Decision/Action 的 housekeeping 动作。
- 修改 JEV State allowlist、引入 JEV HTTP 写路由、Trace 统计图/搜索/跨运行浏览、其他游戏版本及尚未支持的棋盘/模式。
- 不改 `actions/executor.py` 的动作路径身份验证与 `_capture_for_target` 一致性检查；不改数组/字段批量读取（实测收益上限不足 5 ms，会扩大 diff）；不改 `main.py probe` 与 `tests/capture_live_validation.py` 的既有验证调用点；不改 `win32process.EnumProcesses()` 的 pywin32 包装。
- P05 自身不改决策调度；异步观察/分支由 P03 规划且动作仍须 JEV typed 来源。本 Iteration 不承诺 100 ms 内完成远端判断或游戏动作。
- P05 按 OD-16 不新增采样会话关闭入口；P03 的 async client/worker 收尾和停止派发由本次 Runtime 范围负责，不改变 P05 的句柄身份决策。
- 本 Plan 阶段不调用真实 JEV API，不启动或操作游戏，不运行测试。

## 4. Plan Catalog

| Plan ID | Plan | Main outcome | Depends on | Status | Link |
|---|---|---|---|---|---|
| P01 | decision_ready gate | 让 State 对是否进入 JEV 决策给出可验证的布尔结果 | None | Approved | plans/01-decision-ready.md |
| P02 | TypeSafe Decision/Action 与机制目录 | 用官方 typed API 实现 Router + 按需 Action，补齐植物/僵尸英文描述 | None | Approved | plans/02-jev-api.md |
| P03 | T1–T38已实施（420 tests OK）；第8次修订（R45–R47、T28–T30、V70–V72：植物 instructions 方向锚定 + 手编经验文件 configs/plant_experience.txt + run 级结果事实）已实施；第9次修订（R48–R49、T31–T32、V73–V74：掉落物区域 (0,80,800,600) + 植物能力事实；OD-59 队列已闭环）；第10次修订（R50–R55：威胁标签化+undefended 升档、OD-59 队列、管理校验、Trace final_phase、目录 engagement、描述事实与经验策略）已直接实施、待批准 | T1–T15已实施；collect ID整批/shared自主经营/事实与意图来源校验/无本地重排/Trace证据完成；主agent350 tests OK | P01、P02、P05 | Approved; T1–T38 Implementation complete (T33–T38 implemented directly at Human request); 10th revision approved | plans/03-runtime-loop.md |
| P04 | Runtime Trace and JEV Timeline | 持久化 Router/Action 阶段 JSONL，并在 Dashboard JEV 页面只读呈现时间线 | P03 | Approved | plans/04-runtime-trace.md |
| P05 | 采样会话与目标身份 | 已实施T1–T3；capture默认使用持有句柄的TargetSession，身份时间明确；现场稳态中位3.49ms | None | Approved; Implementation complete; Verify Passed（仅P05） | plans/05-capture-session.md |

P01/P02提供准入与typed API基础，P04已提供v1 Trace/UI；P05采样会话已实施且仅其范围Verify Passed，P03直接复用当前capture/TargetSession接口。P03依赖P01/P02/P05，采集实现基线使用P05成果，Trace/UI扩展归P03；P03 T1–T9 已实施但未正式验证；新增 T10–T12 未实施。原P05独立于决策侧的身份规则保持不变，不再安排尚未发生的P05与P03并行实施。

## 5. Decision

### Open Decision

- 无阻塞性Open Decision。OD-37修订为自主经营，OD-39“不需业务攻略参数”解决，OD-40明确不覆盖模型策略；OD-34–40已确认。本次冷启动修订的六项选择（OD-41–OD-45 与 OD-37/OD-40 的延续）已由 Human 逐项确认并转入 §5.2；问题文本与两个门槛锚点（`COLLECT_ACT_THRESHOLD`、`best > none` 规则及 margin 证据）仍依 V41 人工审阅。P03 与 Iteration 的 Approval 因本次实质修订回到 Pending，等待 Human 审阅修订文本。 第 5 次修订（可用性与布局事实）的四项取值已由 Human 逐项确认并转入 §5.2：`bounds=(40,40,800,600)`（OD-46，G2→G1）、collect `timeout_ms=2500`（OD-47）、布局/列方向/角色事实进入共享 state（OD-49）、角色仅作事实暴露（OD-50）；OD-48 是补全已批准的 OD-35，不是新选择。V41 审阅面再次扩大（`lane_composition`、列方向语义、`cards[].role`）。 第 6 次修订（批成员账本与队首轮转）的三项选择已由 Human 逐项确认并转入 §5.2：OD-51 批成员终态账本（含 stop 路径与四个新 reason）、OD-52 队首轮转、OD-53 原因类别 + client 坐标证据；**OD-35 授权窗口语义明确保持不变**（排队等待仍计入 5 s 窗口）。V41 审阅面再增 reason 词表与证据字段。 第 7 次修订（finished 判据与重试）的三项选择已由 Human 逐项确认并转入 §5.2：OD-54 finished 只由「物品确实消失」判定 + 失败后重臂分支重新授权（只要物品还在允许无限重试）、OD-55 空批过滤记账；**OD-35 授权窗口语义明确保持不变**（每次重试都是新授权及其自己的窗口）。另留一条**非阻塞 G2 Open Decision**：是否为 `unverified` 的 collect 动作额外投影点击点与该物品点击时坐标（执行器 `details.item.client_point` 已存在但未进 Trace，纯数值无 ID），用于判断点击未生效是「点偏」还是「游戏忽略输入」。 第 8 次修订（布局经验与结果事实）的两项选择已由 Human 确认并转入 §5.2：OD-56 经验只进 `instructions`（方向锚定、不做区位过滤/配额、catalog 不动）、OD-57 结果事实取 run summary + run JSON（`final_phase` + `lane_closest`，不新增 v2 事件）。 随后 Human 追加要求并以两项选择确认 **OD-58**：经验文本改由入库手编文件 `configs/plant_experience.txt` 提供（加载器不缓存、运行时不校验，预算与字段合法性只由测试守护）。 **OD-59 已闭环**：Human 指示直接实施「有界 FIFO 队列（上限 3）+ 等价合并去重」（见 §5.2 与第 10 次修订）。

### Confirmed Decision

| Decision ID | Confirmed choice | Source/date | Reason |
|---|---|---|---|
| OD-01 | 接入 TypeSafe 官方 typed API，P02 sync 为基础、P03 使用已安装 AsyncTypeSafeClient.system_one；默认 base URL 为 https://api.typesafe.ai，model=jev-latest，POST /v1/systemone；历史 Router 使用 3 Noul + next_action；新分支 questions 按 P03 OD-15，目标使用有限 typed Choices；读取 SDK typed answers、confidence/probabilities、model 和 usage。 | 用户提供 TypeSafe 官方 API/SDK 细节并要求按其更新；已核对 TypeSafe OpenAPI 与 Python SDK 官方文档，2026-09-27。 | JEV 返回预定义 typed decisions；不使用通用 Prompt/任意 JSON 解析。 |
| OD-02 | required field 在结构校验通过且 availability 为 available 或 provisional 时可准入；unavailable/error 或结构不完整时不准入。 | 用户在本次 Plan 执行中选择，2026-09-27 | 与现有状态证据分级和 Boundary 对合规 provisional 的支持一致，同时保留错误/缺失时 fail-closed。 |
| OD-03 | 每次 Runtime Loop 都必须显式提供 --trace-file 路径；不设置仓库内或用户目录的隐式默认文件。 | 用户在本次 Plan 执行中选择，2026-09-27 | Trace 是运行数据，明确路径可避免意外持久化或污染工作区。 |
| OD-04 | P02 将 typesafe-sdk 与 python-dotenv 列为正式新增运行依赖；load_dotenv() 在 TypeSafeClient 初始化前加载 .env。 | 用户在本次 Plan 执行中明确批准，2026-09-27 | 使用官方 typed API，并避免手写 .env 解析器。 |
| OD-05 | Router Choice confidence 低于 `JEV_ROUTER_CONFIDENCE_THRESHOLD` 时本地 wait；专项 Action Choice confidence 低于 `JEV_ACTION_CONFIDENCE_THRESHOLD` 时不调用 ActionBoundary；两项默认各为 0.6。 | 用户在本次 Plan 执行中选择低于 0.6 转 wait，并于 2026-09-27 补充要求门槛各自可配置。 | 两阶段 Choice 独立配置，避免 Router 与 Action 共用一个运行时门槛。 |
| OD-06 | 旧全局 Router→唯一专项 Action、每周期两次请求为历史版本；P03 用独立分支局部判断与依赖 stages，预算按 OD-15/21/22。 | 用户本次要求基于异步分支分析修订 P03，2026-09-27。 | 避免统一 next_action 阻塞独立分支。 |
| OD-07 | zombie_catalog.py 为所有当前已知 zombie type 增加英文能力说明；每次请求只把当前 State 里出现的僵尸说明带给 TypeSafe，不改 JEV projection schema。 | 用户本次选择“纳入僵尸能力目录”，2026-09-27。 | 为特殊移动/防御僵尸提供 State 数值未表达的策略上下文，同时控制请求大小。 |
| OD-08 | 有 Noul candidate + Choice 的局部节点仍按 JEV_NOUL_CANDIDATE_THRESHOLD 做一致性检查，默认 0.6；旧 3 Noul + 全局 Choice 非新分支强制格式。 | 原候选门槛确认及本次 P03 异步分层修订。 | 保留安全检查而不强制全局 Router。 |
| OD-09 | capture/item/坐标不自动输入；每个动作由 JEV typed 分支意图和目标产生并通过 Boundary，取代旧全局 Router 必经要求。 | 既有 no-auto-action 约束及用户本次异步分支修订。 | 本地调度不代替 JEV 决策。 |
| OD-10 | Specialized JEV Action 用 typed Choice questions 选择目标参数；本地只把有限 typed answers 映射为同 sample Boundary request，不以确定性 selector 代替 JEV。 | 用户提供并认可 Decision → intent-specific Action 的两层模拟设计；P02/P03 实现计划采用此数据流，2026-09-27。 | 具体种植/收集/铲除目标由 JEV 决定；Boundary/Executor 仍做最终校验。 |
| OD-11 | JEV Loop 与 Dashboard 保持独立进程，共读同一份 Human 显式指定的 JSONL Trace；Loop 负责该路径的创建/更新，Dashboard 只读其显式配置路径。 | 用户本次在 Plan 阶段选择“共读同一 JSONL 文件，两个进程独立”，2026-09-27。 | JSONL 保持完整记录的单一来源；前端展示不与动作循环耦合，也不获得任意本机文件读取路径。 |
| OD-12 | 每次启动使用显式 `--trace-file`；若路径已有可识别的 JEV JSONL Trace，则启动时清空旧 Trace 并写入新 run；若现有内容不是 JEV Trace、是目录或链接则拒绝修改。 | 用户 2026-09-27 明确要求“直接干掉，然后使用新的”。 | 让重复使用同一显式路径可以启动新 run，同时避免覆盖非 Trace 内容；重用路径会丢弃此前 Trace 历史。 |
| OD-13 | 在 `.env` 中独立配置 `JEV_NOUL_CANDIDATE_THRESHOLD`、`JEV_ROUTER_CONFIDENCE_THRESHOLD` 与 `JEV_ACTION_CONFIDENCE_THRESHOLD`，分别控制 Noul 候选线、Router Choice confidence 与 Action Choice confidence；各自未设置或留空时默认 0.6，值须为 0–1 的有限数字。 | 用户 2026-09-27 明确要求置信度可在 `.env` 配置且门槛相互独立。 | 三类决策闸门用途不同，独立调参且每条 Trace 记录当次实际使用值。 |
| OD-14 | 开局向日葵/未覆盖行防守目标保留，已就绪防守不被可选collect长期挤占；资金不足等最新确认余额。原funding任务依赖由OD-27取代。 | 原策略目标与用户最新State自然衔接要求，2026-09-27。 | 保留策略目标，同时省去collect→plant任务耦合/资源预留。 |
| OD-17 | 接受把进程歧义的 fail-closed 检测从每样本放宽为周期性，窗口不超过 30 s；会话有效期内即使出现第二个同名同路径进程，Loop 也继续操作原本已验证并持有句柄的目标实例。 | 用户在本次 Plan 执行的交互提问中选择“接受周期性歧义检测”，2026-09-27。 | 每样本歧义检测必须枚举全部进程（实测 11–20 ms），是固定开销最大项；持有句柄保证读取始终指向原本已验证的进程，因此不会“读错进程”。 |
| OD-18 | 磁盘身份重验证周期为 1.0 s，进程唯一性重解析周期为 30.0 s，两者独立配置并各自记录触发时间。 | 用户在本次 Plan 执行的交互提问中选择“身份 1s / 唯一性 30s”，2026-09-27。 | 磁盘身份是锁定构建的可信来源需要较紧窗口；唯一性解析只覆盖低概率情形可更稀疏；100 ms 节奏下摊薄约 0.73 ms/样本。 |
| OD-19 | 守卫或重验证失败时本样本立即按现有规则输出 `status: "error"`/`"disconnected"` 并作废会话；下一个样本从头重新解析，不在同一次调用内静默重解析。 | 用户在本次 Plan 执行的交互提问中选择“本样本 fail-fast，下样本重解析”，2026-09-27。 | 与仓库既有 fail-fast 约定一致，并保持与今天相同的可观测性：瞬时身份失败仍产生一个可见的错误样本。 |
| OD-20 | State 的 `source` 增加 `identity_verified_at_utc`，记录该样本所依据的最近一次成功磁盘身份验证时间；additive，`schema_version` 保持 1。 | 用户在本次 Plan 执行的交互提问中选择“加 identity_verified_at_utc”，2026-09-27。 | 缓存身份后 `source` 的 `pid`/`sha256` 只证明“会话曾通过验证”；显式时间戳使采集证据链保持诚实。已核实该字段不进 JEV projection 也不进 Trace。 |
| OD-16 | Option A：不新增会话的显式关闭入口，也不修改 `main.py` 与 `dashboard/server.py` 的收尾路径；句柄只在会话作废或重解析时关闭旧句柄，进程退出时由操作系统释放。 | 用户在本次 Plan 执行的交互提问中回复“OD-16 A”，2026-09-27。 | 句柄持有即本 Plan 所需的身份保证语义，且重解析路径已经必须关闭旧句柄；显式关闭的资源收益不足以抵消多改两个入口与 `CloseHandle` 失败处理策略的成本。 |

| OD-21 | 全局最多 2 个 JEV 请求同时在途，collect/plant 各最多 1 个；分支内依赖判断顺序调用。 | 用户本次选择“全局2个，各分支1个”，2026-09-27。 | 允许两个分支同时等待网络，预算有界；无默认固定分支等待已确定，语义key/TTL/恢复细节仍待OD-22。 |
| OD-23 | 持续观察、独立 collect/plant 分支，各自 action/wait，共享最新 State。 | 用户要求基于异步分析修订 P03，2026-09-27。 | wait/API 延迟不停止整个 Runtime。 |
| OD-24 | 统一动作执行与资源/新鲜度协调；完整多点击动作及确认不交叉。 | 用户要求基于分析方案修订 P03，2026-09-27。 | 保护现有 Boundary/Executor 输入语义。 |

| OD-25 | 观察默认无额外固定等待，--interval-ms省略/0禁用限速、正值仅限制观察；JEV返回后不额外sleep。 | 用户最新去掉默认100ms/保留optional参数要求，2026-09-27。 | 默认由实际采集/网络工作形成节奏。 |
| OD-26 | 各分支相关语义key变化才调用JEV、未变skip；相对提交/可靠决定源key比较，在途latest-only；可靠wait等变化，错误/低置信有界恢复。 | 用户明确state变化true→JEV、false→skip及本次固化请求，2026-09-27。 | 避免元数据请求、漏掉在途变化或把本地异常当可靠wait。 |
| OD-27 | collect/plant无显式任务依赖、funding DAG、阳光预测/预留；确认资源通过最新State自然衔接，执行前仍复核当前资源并互斥完整动作。 | 用户提出下一State自然反映收集成功并要求同步，2026-09-27。 | 第一版仅plant消费阳光，无需resource reservation系统。 |
| OD-28 | 请求设计对齐 TypeSafe 官方 pattern：Speculative fan-out（一次决策 = 一次请求，含推测性问题）+ 问题原子化 + 代码加权合并；数值/算术在代码完成；`state` 按问题裁剪；questions 与 thresholds 集中一处；目标用「本地枚举完整候选 + 一次 Choice + 代码用完整 probabilities 做约束下重排」，仅候选爆炸时允许第二轮。 | 用户要求「按照官方的建议来设计」，2026-09-27；依据官方 patterns/fan-out、patterns/composite-scoring、cookbooks/parallel_questions、concepts/how-to-build-with-system-one、model-jaggedness/jev-1.13。 | 官方明确同 state 的问题应放一次请求、新增问题几乎不影响延迟，并把「原子问题 + 代码合并」列为最重要概念；N 轮深链被列为应避免的 System-2 任务。 |
| OD-29 | 资源层不预测：只用当前 `sun` + `affordable`，不计算产出速率、不预计未来阳光、不做阳光预留；OD-27 不变。 | 用户在本次 Plan 执行中交互选择，2026-09-27。 | 与官方「不让模型做算术」一致，并避免引入跨样本滚动历史。 |
| OD-30 | 行级威胁用有序档 `urgency ∈ none/low/medium/high/critical` + 显式分量；档位由代码按显式阈值映射，不输出浮点 threat score。 | 用户在本次 Plan 执行中交互选择，2026-09-27。 | 官方指出 jev-1.13 不做算术、数值表示弱于语义，且不要伪造精确 threat probability。 |
| OD-31 | 官方对齐在 P03 内完成（T3/T4/T7），包括 `build_typesafe_state` 改为按问题裁剪、替换并行 plant_type/cell 问题形态；P02 记为历史同步基线，其 Verify 结论保持历史范围，新接口证据由 P03 承担。 | 用户在本次 Plan 执行中交互选择，2026-09-27。 | 避免两套请求构造共存与语义漂移；P02 §1 已声明后续接口变更由 P03/T4–T5 承担。 |
| 修订 OD-08 | 撤销「Choice 必须落在 Noul 候选集合内」的一致性要求。Noul 作绝对闸门、Choice 作相对选择，门槛各自独立，不做跨类型候选一致性检查。 | 用户要求按官方建议设计，2026-09-27；依据官方 model-jaggedness（同一问题 Noul 0.22 / Choice 0.99）与 cookbooks/skill_suggestion 的分工示例。 | 官方明确两者不可互换、回答不同问题；保留旧检查会引入与官方相反的约束。 |
| OD-22（数值与口径） | 七组具体值：**分支 key**（PlantBranch = `affordable` 集合 + 每行 `(urgency 档, zombie_count, attacker_count, has_defender)` + 占用格集合；CollectBranch = item 实例集合；元数据/raw 距离/raw HP 不进 key）；**有序档阈值**（none/low=6–8/medium=4–5/high=2–3 或 count≥3/critical≤1 或 count≥3）；**TTL**（request 15 s 沿用、job 10 s、proposal 5 s、sample age ≤500 ms）与失效判定顺序（epoch → key 变化 → 派发前复核 → 最后才 TTL）；**恢复**（`low_confidence` 视为可靠结论不重试；仅 `api_error` 退避 1 s/×2/3 次/上限 8 s）；**公平性**（不可抢占、urgency 降序再 FIFO、collect 让位于 urgency ≥ high、超 TTL 即 discard）；**`--max-cycles`** 计终结 DecisionJob；**超 255** 时 L1 行 Choice → L2 行内「类型 × 格子」。 | 用户 2026-09-27 回复「同意」；另含对提案的一处修正：**HP 不进 branch key**，火力改用离散 `attacker_count`。 | 由真机模拟验证（冻结棋盘 16 样本各分支仅 1 次请求；脚本化 9 样本仅 Plant 5 次 / Collect 2 次，`sun 50→75` 跳过、`75→100` 触发、`d 5→4` 跳过、`4→3` 触发）；低置信不重试依据官方 "extremely consistent"；超 255 依据官方 255 上限与「chain Choice questions level by level」。 |
| OD-15（选择） | **Option C —— 全枚举、不截断、不排 shortlist**：候选 = 全部「空格且可种植」×「当前可负担」+ 显式弃选项，一次 Choice 承载；代码只做事实性过滤与 OD-28 的约束下重排。超过官方 255 上限时按官方「chain Choice questions level by level」逐层拆分，不引入截断算法。放弃 Option A（排序取前 24）。 | 用户 2026-09-27：「OD-15 C，因为官方已经推荐了，那没必要截断，而且你怎么保证你的截断算法符合期望呢？且没有超过 255 官方上限」。 | 官方 `primitives/choice` 明确「give the model the full list … rather than a shortlist」并给出 255 上限与超限正解；本地排序/截断两层无法被验证，属应移除的未经验证策略；今天 43 × 3 + 弃选项 = 130，未触上限。 |
| OD-32 | collect 语义 key 改为**类型 + 数量**（不含坐标/ID）；目标身份绑定为**同样本 All State 的物品 `id`**，派发时按 `id` 复核存在性/类型并**用当前坐标**点击；`id` 不写入 Trace。 | 用户在本次 Plan 执行中交互选择，2026-09-27。 | 实测同一太阳 x 恒定、y 在 263–507 ms 往返内跨 3 个 8px 桶；把坐标放进 key 等价于把「物品在动」误判为「局面变了」。`_review_collect` 的坐标精确相等要求也会在派发前挡住同一决策；同屏 3 个同类型太阳使容差匹配有歧义，故必须按 `id` 绑定。 |
| OD-33 | `job_start.state` 改为记录**实际发给模型的裁剪 state**，替代 v1 `summarize_jev_state` 摘要；保留无泄漏与 v1/v2 兼容。 | 同前，2026-09-27。 | 现有摘要不含 items 坐标，无法复核 collect 决策的实际输入，也无法核对 V31 的 state 裁剪。 |
| OD-22（方法） | Option A：语义 key + 行动前提 + 有界时效/恢复。比较排除 `sample_sequence`/时间戳/普通像素变动，按每分支相关字段与已定义信号判变；可靠决定记录源 key 并持续 skip；TTL 与退避只处理「失效」或「未形成可靠决定」。具体数值见 OD-22 的 Open 条目。 | 用户在本次 Plan 决策中回复「od-22 a」，2026-09-27。 | 避免元数据/普通坐标造成重复请求，同时避免可靠 wait 被定时器反复唤醒，并用有界 TTL 防止陈旧结果长期有效。 |

- OD-34（2026-09-27，用户确认）：CollectBranch 单 Noul；无坐标输入/目标 Choice，本地 ID 绑定，Boundary 直接 item_id，Executor 按即时 ID 坐标点击；经营策略不改。
- OD-35（2026-09-27，用户交互确认）：一次肯定回答覆盖来源样本冻结全部 ID；逐件消费，同批不重问，新 ID 下一批询问；授权最多 5 s，暂停/停止撤销，unverified 不重放，完整动作之间保留高紧急种植优先。

- OD-36（用户2026-09-27确认）：经营并入collect一次shared state/request；空items仍可因经营事实变化调用，两个worker/单执行器不变，结果独立校验。
- OD-37（用户本轮修订）：撤回前轮预定义方案，JEV自主选择/保持/替换/取消经营意图，代码只持有事实与模型意图。
- OD-38（保留）：JEV可选择等待指定建设资金，也可依据新局面改变/取消；代码不得自动强制应急改用途，无预测/资源锁定/资金任务。

- OD-39（本轮解决）：不设人工经济数量/布局/足够防守规则，不需模型方案参数或业务意图TTL；既有技术时效与即时复核保留。
- OD-40（本轮确认）：新Runtime不按本地phase/urgency或约束下重排覆盖JEV，合法目标保留原选择，冲突/非法只拒绝；紧急性来源typed模型判断。

- OD-41（本轮确认，plant 取消绝对闸门）：删除 plant 的 act-now 绝对 Noul，改由模型自己在 `plant_target`（或 L1/L2 链）的弃选项里表达「要不要动手」；判据仅为 `argmax ≠ none_of_the_above` 且 `best > none`（零新增可调参数），不使用绝对阈值或 confidence 门槛；`best`/`discard`/`margin` 记入 merge 与 Trace。实测同批数据下把「6 次请求 → 0 次种植」变为 5 次种植，唯一等待的那次正是模型自己选了弃选项；删除而非忽略该问题可避免 Trace 出现「模型说不要动手却动手」的矛盾证据。
- OD-42（本轮确认，collect 锚点）：`should_collect_now` 与显式常量 `COLLECT_ACT_THRESHOLD = 0.5` 比较（含义为「比一半更可能」），放 `jev/questions.py`，与 `JEV_NOUL_CANDIDATE_THRESHOLD` 解耦；后者只服务 P02。实测 17/17 完全二分，0.5 与 0.3 在本批数据等价；0.5 比现行 0.3 更严格，若模型「是」答案下漂到 0.45 会停止收集（记入 §8）。
- OD-43（本轮确认，删除冗余紧急信号）：删除 `needs_immediate_response`；`construction_intent`/`next_construction_type` 保留但从授权前提降级为上下文。实测该答案 7/17 为真却无任何消费者（`loop.py` 仅在意图存在时用它影响 urgency，而冷启动意图恒为 null）。
- OD-44（本轮确认，请求裁剪）：`items == []` 时共享请求只带经营问题，不再询问 `should_collect_now`；仍是一次请求、同一样本裁剪 state，两个 worker 与在途上限不变。
- OD-45（本轮确认，开局 wave 守卫）：`wave == 0` 时僵尸相关分量（`zombie_count`/`urgency`/`attacker_count`/`has_defender`）不进 PlantBranch key，`wave ≥ 1` 恢复正常；守卫只影响 key 灵敏度，不改变发给模型的事实。选它而非「已进场守卫」或「双样本一致」，因为最窄、直接对应证据，且不给连续观察引入额外等待（OD-25 保持）。
- 修订 OD-05（仅分支路径）：plant 侧「低于门槛即 wait」失去对象（OD-41）；collect 侧改为固定锚点（OD-42）；P02 历史同步路径及其门槛不变。
- 修订 OD-13（仅分支路径）：`JEV_NOUL_CANDIDATE_THRESHOLD` 在分支路径上不再有任何消费者，与另两个门槛一并只服务 P02。
- 修订 OD-22（`model_wait` 语义）：失效顺序、TTL/deadline 数值、恢复退避与公平性全部不变；仅把可靠结论中的 `model_wait` 含义更新为「模型选择了弃选项（plant）或 collect 锚点未过 / 无候选」。

- OD-46（本次确认，掉落物点击区域）：`item_coordinates.bounds` 由 `(80,80,800,600)` 改为 **`(40,40,800,600)`**（x 下限 = 首列中心 − 半间距；y 下限放宽允许高处下落物）。该常量只被 `ActionExecutor._resolve_item_point` 消费，种植/铲除不受影响。实测 8/36 收集派发因几何过窄被拒且未发输入 → 按 §8 既有升级条件 **G2→G1**。
- OD-47（本次确认，收集确认超时）：collect 请求显式带 `timeout_ms=2500`，`DEFAULT_TIMEOUT_MS` 保持 10000 不动；`unverified` 补 `last_observation`。实测成功确认 median 1091 / max 1431 ms；一次超时阻塞 worker 10.2 s。
- OD-48（本次确认，OD-35 补全）：活跃批期间的 `selected` 存入**一份 latest 未授权批**并记录事件；当前批结束/取消/过期后按**既有 5 s 授权时效**消费，超时丢弃并记录原因；已消费 ID 不重复。不改变 OD-35 的授权粒度与时效。
- OD-49（本次确认，布局与列方向语义事实）：共享 state 新增 `lane_composition`（每行 resource/attacker/defender 计数）与 `board` 的列方向语义（col 0 = 房屋侧、col 8 = 僵尸来向），同步 `PLANT_STATE_FIELDS` 与 V31/V44 断言；只给事实与语义，不给推荐/配额。
- OD-50（本次确认，角色仅作事实）：`role` 只作事实与呈现（选项文本已有，另加入 `cards[]`）；**不拆角色问题、不按角色过滤候选**（沿用 OD-37/OD-40 的 A 档）。

- OD-51（本次确认，批成员终态账本）：每个已授权成员以 `executed` 或 `discarded(reason)` 收尾；批结束（TTL 过期/被更新的批覆盖/id 消失/停止/全部不可执行）逐条记录未执行成员，`stop_dispatch` 清批前必须记账；新增 `cohort_member_id_gone` / `cohort_member_deferred_never_executable` / `cohort_authorization_expired` / `cohort_stopped_before_execution`；复用既有 action-discard 通道（不新增事件类型）。实测 16 个成员槽位只有 6 次派发 + 1 条记录。
- OD-52（本次确认，队首轮转）：`_blocked_collect` 命中的队首成员移到队尾，兄弟成员先执行；该成员保留离散条件恢复语义，条件未变前不反复排队首。实测「2 件批只执行 1 件、第 2 件直到暂停未收」即由此产生。
- OD-53（本次确认，不可执行证据）：延迟/丢弃记录附带原因类别（`outside_region` / `not_finite` / `unresolved_interpretation` / `items_unavailable`）与该件 client 坐标（两个数），**不含 item ID**；用于区分 x<40 永久死带与 y<40 瞬时。

- OD-54（本次确认，finished 判据与重试）：`finished` 只由 `status == "success"`（= `postcondition_result == "met"`，物品消失）判定；`unverified` 且 `same_item_present == true` → 不写 finished，并通过重臂入口（清该分支 `last_decided_key` + `request_recheck()`）让分支为同一物品重新授权；**只要物品还在允许无限重试**，每次重试都是一次**新授权**（不是重放同一 proposal），点击前仍按 id 从最新样本取坐标。其它状态（含「可能已发送输入后的 rejected」）保持既有保守语义。
- OD-55（本次确认，空批过滤记账）：`decision.cohort` 非空但按 `_finished_ids` 过滤后为空时必须记录一条带 reason 的丢弃（`cohort_members_all_finished`），不得静默跳过；使「授权成员数 = 执行数 + 丢弃数」在误判场景下也成立。

- OD-56（本次确认，布局经验只进 instructions）：不写进 `state`、不改 `configs/plant_catalog.py`；植物三处 instruction 文本以 `board.column_direction` 锚定方向、只表达倾向并显式让位给即时威胁；候选保持 OD-15 全枚举。「除非是近战」暂由模型读 `description_en` 判断，可靠性记为已知限制。
- OD-57（本次确认，最小结果事实的形态与归属）：`JevLoopSummary.final_phase`（最后一次观测到的 `game.phase` 事实，`status` 语义不变）+ `lane_closest`（run 内每行 `nearest_cells` 最小值），经 `main.py` run JSON 输出；样本数用既有 `observations`。**不新增 v2 Trace 事件类型**，逐样本接近度用已有 `observed_lanes[].nearest_cells` 离线交叉校验。
- OD-58（本次确认，经验文本由手编文件管理）：`configs/plant_experience.txt`（入库、UTF-8、`#` 注释、每行一条）提供经验行；`jev/questions.py` 的加载器每次构建读取、不缓存、缺文件为空；固定方向锚定句留在代码；**运行时不因内容失败**，预算（≤12 行/≤800 字符）与 `state.<字段>` 合法性仅由测试守护。

## 6. Task

- 当前结论：P03 T10–T15本轮Implementation已完成，主agent350 tests OK；以下待实施顺序只作原规划历史保留。具体Taskbackfill/evidence见P03。

- P01/T1：定义准入字段与证据门槛，更新 State 构造、测试和架构说明。
- P02/T1–T2：加入 typesafe-sdk/python-dotenv、Plant/Zombie 英文能力目录、3 Noul + 1 Choice Router 和 typed intent-specific Action requests。
- P03/T1–T9 已实施，旧证据保留；本轮 T10（collect 子职能单Noul）/T11（Boundary ID）、T13（观察事实/模型意图）→T14（shared请求/经营快照）→T12（整批生命周期）→T15（忠实目标/模型等待/Trace/UI）**均已实施**（主agent 350 tests OK，证据见 P03 §7 与各 Task backfill）；冷启动修订 T16–T19 未实施，待本次修订批准后显式 Implementation。
- P04/T1–T3：定义分阶段 JSONL 事件并接入 Loop；为 Dashboard 增加同文件只读 API 与 JEV 时间线卡片；验证事件完整性、凭据隔离和页面对照。
- P05/T1–T3已完成：runtime/session.py、默认会话capture及source.identity_verified_at_utc、架构文档；verify.md仅R12–R14为Passed，148项/现场3.49ms是既有证据，非本次重跑。
- P03 本次新增 T10–T12 待审批；OD-34–40已确认，OD-39参数前提已撤回且不再阻塞；本次增加T13–T15。P05保持Approved、Implementation complete、Verify Passed（仅其范围），不得将其结论扩展为整Iteration通过。
- P03依赖P01/P02 typed/准入与P05已实现采集，扩展既有P04 Trace/UI；P05没有反向依赖P03。检查ID必须带Plan前缀：P03/V25异步隔离与P05/V25真机采集是不同检查。


- P03 二次修订（官方对齐）：新增 R18–R20 与 OD-28–OD-31，修订 OD-08，重写 OD-15（收窄为问题集/阈值/候选规则）；T3 增补四类决策信号（资源不预测、全局阶段、行级有序档、可行动位置），T4 改为一次 fan-out 请求 + 原子问题 + 代码加权合并 + `state` 裁剪 + `jev/questions.py`，T7 记录原子答案与合并结论。
- P03 十次修订（直接实施回填 + Human 接受）：把 Human 指示「不走 SDD、直接改」的六项追认为 R50–R55 与 **T33–T38**（均 `[x]`）及 V75–V80；OD-59 移入 Confirmed（已闭环）；并记录 **Human 接受声明**（006 已达期望、已探明 JEV 能力上限）。全量 420 tests OK。
- P03 九次修订（掉落物区域 + 植物能力事实）：新增 R48–R49、T31–T32、V73–V74（区域 `(0,80,800,600)`；`catalog_context.plant_abilities` + `plants[].role`），并**改写 V61**；另有 **OD-59**（collect 授权队列）Open。T31–T32 **已实施完成**（全量 414 tests OK；探针 20/20 PASS、变异 8/8 CAUGHT）。
- P03 八次修订（布局经验 + 结果事实）：新增 R45–R46、OD-56–OD-57 与 **T28–T29**（T28 = 三处植物 `instructions` 方向锚定措辞；T29 = `JevLoopSummary.final_phase` + `lane_closest` 与 run JSON 输出）及 V70–V72；并新增 **T30**（手编 `configs/plant_experience.txt` + `load_plant_experience` 加载器，T28 改为「固定锚定句 + 文件经验行」）；`state` 键集、catalog、候选枚举、stop 行为均不变。T28–T30 **已实施完成**（406 tests OK）。
- P03 七次修订（finished 判据与重试）：新增 R42–R44、OD-54–OD-55 与 **T26–T27**（T26 = finished 只在确认收走后写入 + 失败后重臂重新授权并更新既有 `unverified` 用例；T27 = 空批过滤记账）及 V68–V69；**OD-35 不变**。T1–T25 保持 `[x]`，T26–T27 **已实施完成**（391 tests OK，主 agent 独立验收）。
- P03 六次修订（批成员账本与队首轮转）：新增 R39–R41、OD-51–OD-53 与 **T24–T25**（T24 = 批成员终态账本含 stop 路径与四个 reason；T25 = 队首轮转 + 原因类别与 client 坐标证据）及 V65–V67；**OD-35 不变**。T1–T23 保持 `[x]`，T24–T25 未实施。
- P03 五次修订（可用性与布局事实）：新增 R35–R38、OD-46–OD-50 与 **T20–T23**（T20 = 掉落物区域 `(40,40,800,600)`；T21 = collect `timeout_ms=2500` 与超时证据；T22 = 补全 OD-35 latest 未授权批与丢弃记录；T23 = `lane_composition`/列方向语义/`cards[].role` 进入共享 state）及 V61–V64；OD-46 升 G1；同步改写 V31/V44 字段集断言与 collect 请求键集断言。T1–T19 保持 `[x]`，T20–T23 未实施。
- P03 四次修订（冷启动/闸门）：新增 R31–R34、OD-41–OD-45 与 **T16–T19**（T16 = plant 删除 act-now Noul、弃选项作主并按 `best > none` 派发；T17 = collect 闸门铆定 `COLLECT_ACT_THRESHOLD = 0.5`；T18 = 删除 `needs_immediate_response` + 空 items 不问收集子问题；T19 = `wave == 0` 时僵尸分量不进 PlantBranch key）及 V57–V60，并据连带结论修订 OD-05/OD-13/OD-22；V33/V38/V45/V50/V53/V55 的闸门断言随本修订改写。T1–T15 保持 `[x]`，T16–T19 未实施。
- P03 三次修订（collect 身份分离 + Trace 输入）：新增 R21/R22、OD-32/OD-33 与 **T8/T9**（T8 = collect key 改类型+数量、目标按同样本 `id` 绑定并用当前坐标点击；T9 = `job_start.state` 记录模型实际裁剪输入）及 V42–V44；**T1–T9 全部 `[x]`（T8/T9 已实施）**。
## 7. Validation

### Current delivery boundary

- 本轮经营最小证据：P03/V50–V56（G1）验证shared请求调用次数、无items经营触发、当前事实/阳光与金币分类、模型意图保持/修改/取消、忠实合法目标与模型等待资金、独立结果有效性/紧急typed fallback、来源版本/Trace/UI与V41人工问题审阅。不按人工理想阵容验收模型策略，不将示例值当默认；T10–T15未实施不得预写通过。
- 模型策略质量/长局表现属G2实验结果；若系统不能提供真实事实或忠实执行模型合法选择则升级G1。完整关卡胜负须记录为实测结果，不预保证模型获胜，最优收益/精确未来预测不作为实现验收条件。现有P05通过证据不代替新增经营链路。

- 本轮收集修订最小证据：P03/V45–V49（G1）证明单 Noul 无坐标输入、每件来源于肯定授权 ID 批、同批不逐件请求、连续位移不失效、同数量 ID 替换不漏问、新 ID 不借授权、串行确认/高紧急种植优先、TTL/拒绝/停止与不确定结果不重放，以及 Trace 实际输入/授权关联/不泄漏 ID；后续受控现场由 V07 取证。本轮 Plan 未运行测试或真实 API/游戏。
- 当前已知左侧 x<80 与 Executor.bounds 拒绝关联作为 G2 风险记录；若现场必要收集受此影响则升级 G1，需另行明确区域修订。本次按 ID 不代表放宽点击区域。本轮新增模型自主持续经营意图；资源锁定/未来产出预测/整体关卡吞吐仍不验收。

- 本次产物与实际用途：由 Human 明确启动的本地 JEV Runtime Loop、可复核 JSONL Trace 和 Dashboard 的 JEV 时间线页；Loop 周期性决策并经现有 ActionBoundary 执行，页面只读显示。
- 最小成功条件：固定State/fake async SDK/clock/Executor证明默认无固定sleep、相关变化才请求/未变skip、无在途变化丢失、两个分支独立/无跨任务依赖或资源预留；typed来源与门槛、2/1在途上限、完整输入互斥、当前资源及失效目标校验、停止后零新派发、v1/v2 Trace/UI对照。后续Human有界真实API/游戏验证两个来源样本/分支；P05现有Passed只说明R12–R14，不代替P03真实链路证据。
- 不作为本次交付门槛的场景：完整关卡通关、长时间无人值守、所有游戏模式、训练/策略优劣比较、Trace 统计图/搜索/跨运行浏览和非标准布局。
- P05 部分的交付成功最小条件：确定性的调用计数证据证明稳态每样本不再执行进程枚举与磁盘身份验证，且 1 s / 30 s 周期重验证、身份类失败的 fail-fast 与下一采样重解析、以及 `source.identity_verified_at_utc` 的字段与隔离全部成立。现场每样本实测耗时为 G2，不作为门槛。 已有verify.md记录该范围Passed：148项、现场稳态中位3.49ms/p95 4.13ms；僵尸冻结场景的采集观测不作为动态玩法证据。

### Verification tiers

| Tier | Meaning | Handling in Verify |
|---|---|---|
| G1 核心路径 | 连续观察/可选限速、相关key变化触发与skip、latest-only、独立分支/无funding依赖、typed分层与门槛、单执行/当前资源/旧结果校验、停止/v1v2；P05采集会话原契约 | P03/V06–V08、V14–V17、V25–V28按新版自动化条件获取证据；P03/V07/P04/V13后续实机；P03/V18质量为G2。P05/V19–V25既有验证Passed，不重写成P03已通过。 |
| G2 当前风险 | API 服务临时不可用、模型延迟超过 5 秒、运行期间暂停/短时读取错误、Trace 文件增长和浏览器最近事件窗口限制 | 测试/现场记录 fail-closed 与展示边界；Human 接受剩余运行风险。若错误使核心动作边界失效、Trace 无法区分结果或事件读取阻塞 Loop，升为 G1。 |
| G3 后续场景 | 自动通关、长时间无人值守、特殊模式/布局、模型质量比较、统计图/搜索/跨运行 Trace 浏览 | 本次不验证；后续需要历史分析或海量 Trace 浏览时再评估。 |

P05已完成Implementation与仅R12–R14 Verify Passed，既有证据保留；本次不重跑其检查或改verify.md历史结论。P03新验证覆盖变化触发/skip、无限默认/可选interval、在途变化不丢失、独立分支无资源预留、单执行和v1/v2，对P01/P02/P04/P05接口做必要回归。真实JEV/动态游戏由后续显式Verify获取，不能用P05的冻结局面测量替代。

P03 二次修订新增 G1 检查 V29–V34：请求拓扑一次性（V29）、问题原子性与代码合并（V30）、数值与 `state` 裁剪（V31）、候选合法性与约束下重排（V32）、Noul 与 Choice 语义分离（V33）；另 **V34（G2）** 用 Human 提供的 API 实测全枚举候选量（今天 130）下的延迟、token 量与 top-1 稳定性；若超过 OD-22 选定的 TTL/deadline 则升级为 G1。 本轮新增 **V35–V40**：key 稳定性与灵敏度（V35）、OD-30 档位表（V36）、失效判定顺序（V37）、恢复策略（V38）、公平性与计数口径（V39）均为 G1；超 255 的层级拆分（V40）为 G2。**V41（G1）** 为 Human 逐条审阅 `jev/questions.py` 的问题措辞与阈值常量（官方要求）。本轮新增 **V42–V44（均 G1）**：collect key 稳定性（坐标位移不得触发）、collect 目标身份（按 `id` 复核 + 当前坐标点击、同类多件不歧义、`id` 消失即 discard、`id` 不进 Trace）、Trace `job_start.state` 等于模型实际裁剪输入且无泄漏。本轮冷启动修订新增 **V57–V60**：V57（G1）plant 无绝对闸门且 `best > none`、merge 事实字段可复核；V58（G1）collect 固定锚点 0.5 且与 P02 门槛解耦；V59（G2）空 items 请求裁剪与 `needs_immediate_response` 无残留；V60（G1）`wave == 0` 僵尸分量不进 plant key 而 `wave ≥ 1` 仍进。V33/V38/V45/V50/V53/V55 的 plant/collect 闸门断言按本修订改写，不得沿用旧通过结果。第 5 次修订新增 **V61–V64（均 G1）**：掉落物区域覆盖性（边界坐标可点击、界外仍拒且带坐标证据、种植几何回归）、collect 超时与证据（请求恰带 `timeout_ms=2500`、`unverified` 含 `polls`/`waited_ms`/`last_observation`）、latest 未授权批不丢授权（决策数 = 消费 + 记录丢弃）、布局/列方向/角色事实一致性（含「无推荐类字段」负向断言）。V31/V44 的 state 字段集断言与 collect 请求键集断言随本修订改写，不得沿用旧通过结果。第 6 次修订新增 **V65–V67（均 G1）**：V65 批成员终态账本（五条路径下「授权成员数 = 执行数 + 丢弃数」，含 `stop_dispatch` 之后）、V66 队首轮转（兄弟不被饿死、条件变化后可重试、无热循环）、V67 不可执行证据（原因类别 + client 坐标，且任何 v2 事件都不含 item ID）。第 10 次修订新增 **V75–V80**（V75 标签与升档、V76 队列/去重/溢出、V77 管理缺省类型、V78 `final_phase` 为 G2、V79 engagement、V80 描述事实与经验预算；均随直接实施完成）。第 9 次修订新增 **V73–V74（均 G1）**（V73 区域常量 + 左缘可点/UI 条带仍拒；V74 `plant_abilities` 去重排序/`plants[].role`/顶层键不变/Trace parity）并**改写 V61** 的边界断言为 `(0,80,800,600)`；**OD-59 已由第 10 次修订闭环**（有界 FIFO 队列 + 去重）。第 8 次修订新增 **V70–V72（均 G1）**：（均 G1）**（V72 = 经验文件注释/编码/顺序/缺文件语义 + 入库文件预算与 `state.<字段>` 合法性；运行时只读不校验）：V70 三处植物 `instructions` 的方向锚定/无列号无铁律 + 既有 `state.<field>` 引用校验 + `PLANT_STATE_FIELDS` 键集未变；V71 多帧样本下 `lane_closest` 逐行 min 与 `final_phase` 正确、`status == "level_finished"` 语义不变、两事实不进模型请求 state。第 7 次修订新增 **V68–V69（均 G1）**：V68 finished 判据与重试（`unverified` + 物品仍在 → 不写 finished、分支重臂、出现第二次授权与同 id 派发、无无授权重放、重试节奏有界）、V69 空批过滤记账（恰好一条带 reason 的记录、守恒式成立、无 item ID）。P03 的检查 ID 均属 P03 作用域。

## 8. Risks

- TypeSafe SDK 与 python-dotenv 已在 P02 Implementation 阶段安装并写入 pyproject.toml/uv.lock；后续升级仍应审阅 API typed response 与代理兼容性。
- .env 只有在 TypeSafeClient 创建前 load_dotenv() 才会进入进程环境；API Key 必须在错误、日志、Trace 和 Git 中保持秘密。
- P02/V03 已验证 `.env`/进程代理配置进入 TypeSafe SDK transport，并处理继承的 SOCKS `ALL_PROXY` fallback；Human-controlled V07 仍需确认到官方 endpoint 的端到端连通性。
- Choice 的 choice 是最高概率选项，不代表一定高 confidence；Router 与 Action 分别使用 `.env` 门槛判定是否本地 wait，Noul 候选线独立配置；Trace 记录三项当次实际门槛及各 answer confidence/probabilities。
- Router 中 Noul questions 与 next_action Choice 同时并行回答，Choice 不会读取 Noul 结果；Runtime 按 OD-08 后置检查，next_action 与候选信号不一致时 wait。
- 植物/僵尸描述是策略上下文，不是当前局的观测事实；僵尸目录仅附加当前出现类型，未知类型不推测其能力。
- .env 值不能进入异常、console、测试失败快照、JSONL 或 Git；代理和凭据处理要覆盖异常路径。
- JEV 请求可能长于观察周期；P03 通过 async SDK 保持观察/另一分支可运行，限制在途/速率，旧回答经 TTL/epoch/目标前提失效；不并发执行游戏输入。
- JEV 等待期间 State 会变化：来源 All/JEV pair 仍同 sample，派发前另用最新可靠 State 检查身份、目标及资源，再由 Executor 即时验证；不修改来源 pair 或偷换目标。
- decision_ready 若将候选字段误判为充分，会让模型基于不可靠数据决策；若过严，则 Loop 可能永不启动。OD-02 已确定接纳结构有效的 provisional，但必需字段和结构规则仍要在 P01 明确。
- Trace 的位置必须由调用者明确提供；程序不在仓库或用户目录创建隐式运行记录。复用路径会替换可识别的旧 JEV Trace；需要保留旧 run 时应另选路径。
- `serve` 与 `jev-loop` 是独立进程，必须显式配置同一路径；路径不一致时页面只能显示无数据/读取错误，不得回退读取其他文件或 All State。
- 真实模型调用可能产生费用；仅在后续 Verify 中由 Human 启动有界验证，本 Plan 阶段不发起调用。
- P03 的状态策略使用角色和行威胁摘要，不保证模型策略最优；若距离、类别或植物覆盖证据为 null/未知，按获批降级方式处理，不依据目录描述伪造当前局面。
- OD-15/22仅剩种植stages/语义key/时效/异常恢复/公平性与有界计数；默认连续观察、相关变化触发及无任务依赖已确认。旧串行证据与P05采集证据都不能证明新Runtime；源码中代理逐请求环境修改仍需由P03迁移。
- P05 把进程歧义的 fail-closed 检测从每样本放宽为不超过 30 s 的窗口（OD-17）；持有句柄保证读取仍指向原本已验证的进程，但“出现第二个实例时拒绝操作”这一 003/004 既有策略被放宽，须由该批准覆盖。
- P05 使 `source` 中的 `pid`/`sha256` 不再隐含“本样本刚被验证”；`identity_verified_at_utc` 与 `docs/architecture.md` 是缓解手段，后续 Verify 与现场证据必须按新语义解释，否则会得出错误结论。
- P05原33ms历史基线与组件测量已在其Verify对账；现场中位3.49ms/p95 4.13ms为一次受控采集证据。连续观察可能增加CPU/读取负载，使用受控worker/await协作，分支未变挂起并可显式interval限速；不承诺固定采样/动作耗时。
- P05 只改善采集侧；P03 async 分支可解除本地等待互相阻塞，但远端 latency 与多点击执行仍限制真实反应，不能把观察频率当成动作频率。
- P05 改变的 `capture_state` 是 `jev/loop.py`、`dashboard/server.py`、`actions/executor.py`、`main.py` 与 `tests/capture_live_validation.py` 的公共默认值；`raw_reader` 注入路径保持不变是控制回归面的关键。`actions/executor.py` 的 `_capture_for_target` 依赖于 `source` 身份字段，会话重解析产生 PID 差异时会 fail closed，需与真实身份不一致区分。
- P05已提供带锁TargetSession、惰性默认会话与reset_default_session，raw_reader注入绕过会话已有测试；P03复用而不另造会话。连续Observer与Executor采集的公平性/发布顺序仍需P03回归。
- P05 按 OD-16 Option A 不新增 CLI 收尾关闭入口，因此长驻进程（`serve`、`jev-loop`）会在整个运行期保持一个目标进程句柄，只有在会话作废或重解析时才关闭旧句柄；反复重启目标进程时必须确认旧句柄被关闭，否则累积泄漏。

- 官方 jaggedness 约束（jev-1.13）：不做算术/计数、数值表示弱于语义表示、多级间接（System Two）与深链是弱项、`state` 过大会造成 context rot；因此 P03 禁止 N 轮串行推导、数值全部在代码、行级信号用命名档位、`state` 必须裁剪。
- Noul 与 Choice 无结构不变性（官方同一问题 Noul 0.22 / Choice 0.99）：不得互套门槛，也不得把 Noul 概率当 Choice 候选集；OD-08 已据此修订。
- 官方延迟 70–500 ms 为其基准机数据，本项目实测 Router 往返中位 676 ms（走代理）；「一次请求」降低往返次数与请求级失败面，不构成 100 ms 级实时承诺。
- P02 已实现且已 Verify 的请求构造将被 P03/T4 替换；P02 的结论只对应其历史同步接口，不得当作新接口证据。
- 问题措辞与阈值需人工审阅（官方警告 agents 不擅长写问题）；`jev/questions.py` 不能只靠测试通过来验收。
- HP 不进 branch key：raw HP 虽离散，但在多株植物射击下每 ~1.4 s 即变一次，进 key 会把请求退化为准周期请求；本修订把火力改为离散的 `attacker_count`。若未来需要「接近击杀」信号，必须引入显式且可测的档位，不得把 raw HP 放回 key。
- 档位是硬阈值：边界抖动会让相邻帧落在不同档并多一次请求（可接受）；`zombie_count` 与 `attacker_count` 仍留在 key 中，保证档内实质变化仍触发。
- `low_confidence` 不重试的残余：若某 key 的低置信实为「信息不足」，仅等 key 变化可能长期等待；由 TTL 与 Human 调参兜底，不得改为对同一 key 反复重试。
- TTL 不是正确性装置：正确性来自 key 比对与派发前复核，TTL 只防无界延迟。
- 问题措辞需人工逐条审阅（官方：questions 与 thresholds 是最需要人工 review 的部分，且 agent 不擅长写问题）；由 V41 承担，不得只靠测试通过验收。

- collect 分支活锁（2026-09-27 实机运行发现，**已由 T8 修复**）：25.9 秒内 67 次请求、48 次模型已 `selected`、46 次被判 `superseded`，仅 1 次成功收集。根因是 collect key 含坐标（下落阳光每往返跨 8px 桶）且 `_review_collect` 要求坐标精确相等。修复后 key 只表达类型+数量、目标按同样本 item `id` 绑定并用当前坐标点击。**残留风险：现场是否真的收集成功仍未验证（V07），Verify 不得把未做的现场确认记为通过。**
- Trace 证据缺口（同因，**已由 T9 修复**）：`job_start.state` 从 v1 摘要改为模型实际裁剪输入（collect 含 items 与坐标；未发请求的 job 记 `None`）。**残留：T8 之前产生的历史 Trace 仍是旧摘要。**

- 取消 plant 绝对闸门会如实放大模型自己的策略错误（把阳光花在错误位置/类型）。这是 OD-37/OD-40 的既定实验目的；前提是 Trace 能区分「模型选了 A」与「代码改成 B」——任何合法选择必须原样执行。
- `best > none` 只是相对判据，不保证分布不平：45+ 选项下概率可能摊平，此时 argmax 在近似并列的选项间带任意性。由派发前复核与 V41 审阅 `margin` 事实兜底；若实机出现大面积 `margin ≈ 0` 的种植，升级为 G1 并考虑恢复**显式且可测**的判据（不得悄悄调回绝对阈值）。
- collect 铆定 0.5 比现行 0.3 更严格：本批实测两者等价，但若模型「是」答案下漂到 0.45 会停止收集；由 V41 审阅该常量、V07 观察收集成功率，必要时按证据显式调整（不得隐式耦合回 P02 门槛）。
- `wave == 0` 守卫的边界：若某关在 `wave == 0` 期间确有真实威胁，该期间僵尸分量不改变 key（威胁事实仍进入模型输入，其余字段变化仍可触发）。若实机出现「开局不响应真实威胁」，升级为 G1 并改判守卫形态。
- 删除 `needs_immediate_response` 会移除唯一与意图无关的紧急信号，`urgency` 因此只由机械调度规则决定；当前该信号本就无消费者，净收益为正，但将来若需紧急插队必须新增**有消费者**的 typed 问题并给出 V41 审阅面。
- 本次修订不解除 `x<80` 点击区域限制（G2 保持），仍无法覆盖列 0 附近掉落的阳光。

- 掉落物区域放宽的安全边界：`(40,40,800,600)` 的下限由几何推导，仍保留解释方式/origin/坐标有限性/唯一匹配/同 sample 校验；现场若出现误点必须回 Plan 重定，不得在实现里再放宽。
- collect 超时 2500 ms 的余量约 1.7×（实测 max 1431 ms）；若游戏侧偶发更慢会多一次 `unverified` 后的重新决策。不得与 `DEFAULT_TIMEOUT_MS` 合并修改以免动到种植/铲除语义。
- latest 未授权批沿用 OD-35 的 5 s 时效（自接受起算、不续期），等待期间可能整批过期需新决策；这是有界授权的既定语义，不得为实现「不漏」而无界延长授权。
- 共享 state 字段扩张会增加 token 并改变 `job_start.state` 字段集（V31/V44 与 V41 审阅面必须同步）；任何「推荐数量/布局答案」字段都违反 OD-40。
- `x<80` 的 G2 已升为 G1：V61 通过前 P03 收集路径不得宣称可用；现场是否仍有区域外掉落需在新一轮受控运行复核（V07）。

- 批成员记录量有界性：逐条记账把粒度从「每批一条」变为「每成员一条」（最坏 = 冻结件数）；需断言只取决于授权件数与路径。
- 停止路径记账不得妨碍停止：`stop_dispatch` 是同步路径，必须复用同步 `_record_action`，不得引入 IO 等待或重试；停止后仍须零新派发。
- 轮转只允许改变**同一批内部**的尝试顺序，不得越过 scheduler 的优先级门（`collect` 仍让位于 urgency ≥ high）；同一成员在离散条件未变时不得反复占用单槽。
- 证据字段必须是纯数值/枚举，不得携带 `item_id`/`object_id`/raw 内存或凭据；`assertNotIn` 是硬门槛。
- **OD-35 不变意味着「排队计入 5 s 窗口」这一类合法过期仍会发生**，但从此是**有记录**的 `cohort_authorization_expired`；若其占比过高需另开 Plan 讨论队列化。

- 无限重试的请求量：只要物品仍在，每次确认失败都会带来一次新的 JEV 授权往返（约 2.5 s 一次，受单执行器与确认窗口自然限流）。若现场显示请求量显著上升，应先把 G2 的点击点证据补上判断根因，再考虑收紧策略 —— 不得改回「一次失败永久拉黑」。
- 保守语义保持不变的一类：「可能已发送输入后的 rejected」仍写 finished 不重试；与 OD-54 的区别是执行器**明确报告物品仍在**时才重试，无法判断时不重试。
- 重臂不等于重放：第二次尝试必须是新的一次肯定授权（新 proposal + 新窗口），不得复用旧 proposal 或旧 `created_monotonic`。
- `_finished_ids` 职责收窄为「确认已收走的物品」，仍须保证迟到/持批不会重复点击刚收走的物品（靠确认窗口期间的 id 移除 + 单槽调度）。
- OD-35 未变：排队等待仍计入 5 s 窗口，长队仍会有有记录的 `cohort_authorization_expired`。
- V07/V41 仍未执行：即使 T26/T27 完成，P03 也不得宣称正式 Verify Passed。

- 未走 SDD 的追认（G2）：R50–R55 由 Human 即时指示直接实施，未经常规闸门；本次以文档追认 + 420 项测试 + 变异回放补齐证据。
- 队列放宽接受面（G2）：最多 3 批待执行，长队列尾部可能超窗（逐成员记 `cohort_authorization_expired`，不静默）。
- `undefended` 仅呈现层升档：调度优先级不变；若需调度层优先须另开修订。
- 经验文件接近预算（784/800 字符）：再加策略条当前需压缩既有行。
- 区域放宽副作用（G2）：x 下限放到 0 后，草坪左缘/割草机条带内落点会被点击；这些位置在场地内、游戏可点，割草机不响应点击，预期无害；若现场出现「点了边缘但没反应」或误碰 UI，回 Plan 重定（不得在实现里再放宽或缩小）。
- y 下限 80 的依据是几何常量（`first_cell_center_y 130 − vertical_spacing/2 50`）；若 mod 的 UI 高度不符需按现场截图微调并同步 V73。
- `plant_abilities` 体积（G2）：只列本样本出现的类型并去重，已是最小形式；若请求过大优先砍 `plants[].role`，而不是取消事实。
- OD-59 未定稿：队列/去重方案未定，本次不含 Task，单槽丢弃仍会继续（有记录、不静默）。
- 手写经验内容不在工程可控范围（G3）：工程只保证格式/预算/字段引用合法；文件入库 ⇒ 请勿写敏感信息；缺文件或清空后退化为「仅固定锚定句」。
- 加载器每次构建读文件（「改文件立即生效」的代价，一次小文件读取/植物决策；不加缓存或监听器）。
- 布局经验的**建议质量本身不可验证（G3）**：`final_phase`/`lane_closest` 只是让以后的改动可对照，本轮不把「模型是否遵守倾向」设成门槛。
- 过度遵守倾向：模型可能为「资源植物靠房屋侧」而忽视某行即时威胁；文本用 "an immediate threat … outranks any long-term layout preference" 缓解，不引入代码侧优先级覆盖。
- 三处文本各加 2 句，链式植物问题（>255 选项）会带同样文本两次；保持精简，不再追加经验句。
- `lane_closest` 是「最佳值（min）」不是「最新值」，文档须写清；`final_phase` 与 `status`（仍为 `level_finished`）不得互相替代。
- 「近战例外」不可靠（无结构化射程/耐久）；若现场证明常判错，再单独开修订加闭集字段。
- V07/V41 仍未执行：本轮完成也不构成 P03 的正式 Verify Passed。

## 9. Approval

- Status: Approved
- Approved by: Human
- Approval date: 2026-09-27 2026-09-27 2026-09-27 2026-09-27
- Notes: P01/P02/P04基础批准与历史实现保留；P05已Approved、T1–T3完成、Verify Passed（仅R12–R14，见verify.md）。P03本次同步默认连续观察、相关变化→JEV/未变skip、latest-only、无collect→plant依赖/资源预留；旧T1/T2历史，新T3–T7未实施。OD-21/25/26/27已确认；OD-15/22剩余细节待定，Iteration整体仍Pending human review/未验证。 2026-09-27 二次修订（P03）：按用户指令对齐 TypeSafe 官方 pattern，新增 R18–R20、OD-28–OD-31，修订 OD-08，重写 OD-15，扩展 T3/T4/T7 与 V29–V33；P02 记为历史同步基线；Approval 因实质范围修订回到 Pending。 追加：OD-22 方法已确认（Option A，来源用户「od-22 a」，2026-09-27），仅剩余 key/阈值/TTL/恢复/计数数值待定；OD-15 更新推荐为 C（全枚举 + 显式上限）并附三个条件与 V34 实测门槛，A 仍为可接受保守选择，OD-15 保持 Open。 追加：OD-15 已由 Human 选定 **Option C（全枚举、不截断、不排 shortlist）**，依据官方 `primitives/choice` 的 255 上限与「give the model the full list … rather than a shortlist」；超 255 改用官方「chain Choice questions level by level」；V34 降为 G2；OD-22 的 Open 列表增收「问题措辞与门槛数值」与「层级拆分顺序」。仅 OD-22 剩余待定。 OD-22 七项数值与口径已确认并转入 Confirmed；§5.1 无阻塞性 Open Decision；「问题措辞」改由 V41 在 Implementation 后由 Human 审阅；新增 V35–V41。P03 等待 Human 明确批准。 2026-09-27 Human 批准 P03 后，全部具体 Plan（P01–P05）均已 Approved 且无阻塞性 Open Decision，故按规则把 Iteration 级 Status 置为 Approved。Implementation 尚未开始；P03 的 T3–T7 未实施，P05 的实现未提交。 2026-09-27 三次修订：按实机运行发现新增 R21/R22、OD-32/OD-33 与 T8/T9（collect 决策前提与目标身份分离；Trace 记录模型实际输入），Approval 依规则回到 Pending。Iteration 级因此恢复 Pending。 追加：2026-09-27 Human 明确批准 P03 三次修订；P01–P05 全部 Approved、§5.1 无阻塞 Open Decision，Iteration 恢复 **Approved**。T8/T9 未实施。

- 2026-09-27 收集修订：R23/R24、OD-34/35、T10–T12、V45–V49，P03 与 Iteration Approval 回到 Pending；P01/P02/P04/P05 的既有批准与历史验收不改。未实施；该条记录此前收集阶段，最新经营修订见下一条。

- 2026-09-27 经营修订：R25–R29、OD-36–38已确认、OD-39目标参数/完成条件开放，T13–T15与V50–V56已加入；R23/V45单问题规则仅指collect职能。P03/Iteration仍Pending，T10–T15未实施，未运行测试/真实游戏/API。

- 2026-09-27 自主经营修订：R26–R29/T13–T15/V51–V56改为观察事实与模型意图，新增R30；OD-37撤回预定义方案、OD-39解决参数阻塞、OD-40不覆盖模型。T1–T9历史不改，T10–T15未实施，Pending；未改生产代码/测试/游戏/API。

- 2026-09-27 Human回复“approved”，批准P03当前ID收集与自主经营修订；P01–P05均Approved且无阻塞性Open Decision，Iteration恢复Approved。T10–T15尚未实施；历史Pending记录保留，下一阶段须显式Implementation。

- 2026-09-27 冷启动修订（本次 `$sdd-plan`）：依据两次受控实机 Trace（收集已恢复但新开局 31 s 零种植）新增 R31–R34、OD-41–OD-45 与 T16–T19、V57–V60，并据连带结论新增「修订 OD-05/修订 OD-13/修订 OD-22（`model_wait` 语义）」；V33/V38/V45/V50/V53/V55 的闸门断言随本修订改写。同步修正 §6 中已失效的「T10–T15 均未实施」表述。这是实质范围修订，P03 与 Iteration 的 Approval 依规则回到 Pending，等待 Human 审阅；本次未改任何生产代码、未运行测试、未访问真实 API/游戏。

- 2026-09-27 Human 明确批准 P03 冷启动修订（R31–R34、OD-41–OD-45 与 OD-05/OD-13/OD-22 修订、T16–T19、V57–V60）；P01–P05 全部 Approved 且无阻塞性 Open Decision，P03 与 Iteration 的 Approval 恢复 **Approved**。T16–T19 未实施；V07/V41 未执行。

- 2026-09-27 五次修订（可用性与布局事实）：依据受控运行 `run 92f9a6ac`（8/36 收集派发被区域拒绝、1 次 10.2 s 超时阻塞、46/72 次授权无记录、布局退化为单行堆叠与房屋侧坚果）新增 R35–R38、OD-46–OD-50 与 T20–T23、V61–V64；OD-46 把掉落物区域从 G2 升为 **G1**；同步改写 V31/V44 的 state 字段集断言与 collect 请求键集断言。P03 与 Iteration 的 Approval 依规则回到 Pending，等待 Human 审阅；本阶段未改生产代码、未运行测试、未访问真实 API/游戏。

- 2026-09-27 Human 明确批准 P03 第 5 次修订（可用性与布局事实：R35–R38、OD-46–OD-50、T20–T23、V61–V64）；P01–P05 全部 Approved 且无阻塞性 Open Decision，P03 与 Iteration 的 Approval 恢复 **Approved**。OD-46 已升 G1。T20–T23 未实施；V07/V41 未执行。

- 2026-09-27 六次修订（批成员账本与队首轮转）：依据受控运行 `run 94a40c3c`（13 次 selected / 16 个成员槽位，仅 6 次 collect 派发与 1 条丢弃记录；坐标拒绝 0，T20/T21 生效）新增 R39–R41、OD-51–OD-53 与 T24–T25、V65–V67；**OD-35 授权窗口语义保持不变**。P03 与 Iteration 的 Approval 依规则回到 Pending，等待 Human 审阅；本阶段未改生产代码、未运行测试、未访问真实 API/游戏。

- 2026-09-27 Human 明确批准 P03 第 6 次修订（批成员账本与队首轮转：R39–R41、OD-51–OD-53、T24–T25、V65–V67；OD-35 保持不变）；P01–P05 全部 Approved 且无阻塞性 Open Decision，P03 与 Iteration 的 Approval 恢复 **Approved**。T24–T25 未实施；V07/V41 未执行。

- 2026-09-27 七次修订（finished 判据与重试）：依据受控运行 `run e6c84636`（12 次 selected / 15 个成员槽位 → 仅 4 次派发、0 条丢弃记录；8 次空手而归全在唯一一次 `unverified` 之后）新增 R42–R44、OD-54–OD-55 与 T26–T27、V68–V69；**OD-35 保持不变**；另留一条非阻塞 G2 Open Decision（点击点证据）。P03 与 Iteration 的 Approval 依规则回到 Pending，等待 Human 审阅；本阶段未改生产代码、未运行测试、未访问真实 API/游戏。

- 2026-09-27 第 7 次修订（finished 判据与重试）获 Human 明确批准（「approved」）：无阻塞性 Open Decision（仅一条非阻塞 G2：是否投影点击点证据）→ P03 与 Iteration 的 Approval 恢复 Approved，P01–P05 全部批准；**T26–T27 待 `$sdd-implementation` 实施**。

- 2026-09-27 八次修订（布局经验+结果事实）：据 Human 的「写几条经验」提议讨论后定案 —— 不写进 `state`（facts-only 边界），改为 R45–R46、OD-56（经验只进植物 `instructions`，方向锚定 `board.column_direction`、不做区位过滤/配额、catalog 不动）与 OD-57（run 级结果事实 `final_phase` + `lane_closest`，经 run JSON 暴露、不新增 v2 事件），以及 T28–T29、V70–V71。P03 与 Iteration 的 Approval 依规则回到 Pending，等待 Human 审阅；本阶段未改生产代码、未运行测试、未访问真实 API/游戏。

- 2026-09-27 八次修订补充（手编经验文件）：Human 追加「经验最好由一个文件管理，便于手动新增」，并选定 `configs/plant_experience.txt` 入版本库 + 「只由测试守预算/引用合法性」⇒ 新增 R47、OD-58 与 T30（文件 + `load_plant_experience`）及 V72；T28 目标改为「固定锚定句 + 文件经验行」、V70 增补「逐条包含文件内容」。当时 Approval 仍为 Pending human review，**随后 Human 于 2026-09-27 明确批准**。

- 2026-09-27 第 8 次修订（布局经验 + 手编经验文件 + 最小结果事实）获 Human 明确批准（「approved」）：无阻塞性 Open Decision（仅一条非阻塞 G2：collect 点击点证据）→ P03 与 Iteration 的 Approval 恢复 Approved，P01–P05 全部批准；**T30/T28/T29 待 `$sdd-implementation` 实施**。

- 2026-09-27 九次修订（掉落物区域 + 植物能力事实）：据受控运行 `run d8a00084`（82 条 `outside_region` / 去重 29 落点 / 26 个在 x∈[10,36] 且可点；`batch_superseded_by_newer_batch` 545 次 vs 实际动作 116 次）新增 R48–R49、T31–T32、V73–V74 并改写 V61（区域 → `(0,80,800,600)`；`catalog_context.plant_abilities` + `plants[].role`）；collect 授权队列记为 **Open Decision OD-59**（含推荐方案，待 Human 明确后回填 Task）。P03 与 Iteration 的 Approval 当时依规则回到 Pending，**随后 Human 于 2026-09-27 明确批准（OD-59 仍 Open、不阻塞）**；本阶段未改生产代码、未运行测试、未访问真实 API/游戏。

- 2026-09-27 第 9 次修订（掉落物区域 + 植物能力事实）获 Human 明确批准（「approved」）：R48/R49 与其验证路径 V73/V74（含改写 V61）已定稿，**T31/T32 待 `$sdd-implementation` 实施**；**OD-59（collect 授权队列/去重）仍为 Open 且不阻塞**（R48/R49 不依赖它，Human 明确选择后回填为 T33）；非阻塞 G2（collect 点击点证据）保留。

- 2026-09-27 九次修订实施（T31/T32，`$sdd-implementation`+`$sdd-agents` 单波 2 代理）：T31 = `bounds` `(0,80,800,600)` + V61 改写（`test_action_boundary.py` 22→25，另授权改 `test_jev_loop.py` 3 处 fixture 与 `test_live_validation.py` 1 处）；T32 = `catalog_context.plant_abilities` + `plants[].role` + Trace parity（`test_jev_client.py` 75→79、`test_jev_trace.py` 28→29，另改 `jev/strategy.py` —— `plants[]` 实际装配处）。全量 **406 → 414 OK**；主 agent 独立验收：探针 20/20 PASS、变异回放 8/8 CAUGHT 且逐字节还原。残留：`docs/architecture.md` 旧区域文字待同步；OD-46 现场闭环与 OD-59 仍 Open；未 commit。

- 2026-09-27 十次修订（直接实施回填 + Human 接受）：把 Human「不走 SDD、直接改」的六项改动追认为 R50–R55 与 T33–T38（均 `[x]`）及 V75–V80（全量 420 tests OK），OD-59 从 Open 移入 Confirmed（已闭环）；并如实记录 **Human 接受声明**（「006 已达到期望、已测出 JEV 能力上限，006 可以 passed」）——不改变 `verify.md` 既有内容，P03/P04 正式 Verify 仍需显式 `$sdd-verify`，V07/V41 仍未执行。P03 与 Iteration 的 Approval 依规则回到 Pending。

- 2026-09-27 第 10 次修订（直接实施回填 + Human 接受）获 Human 明确批准（「approved 改下状态」）：无阻塞性 Open Decision → P03 与 Iteration 的 Approval 恢复 **Approved**；该修订为追认型（T33–T38 均 `[x]`），实现状态未变。
