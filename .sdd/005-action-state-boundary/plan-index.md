# Plan Index

## 1. Metadata

- Iteration: 005-action-state-boundary
- Created at: 2026-09-26
- Status: Approved
- Owner: 本仓库维护者

## 2. Goal

在后续接入 JEV 前，收敛现有三种游戏动作与当前 JEV State 契约之间的接口：让动作验证不依赖 JEV 内部格式之外的诊断字段，让植物实体 ID 查询独立于 board cell 的编码，并让种植结果确认植物类型。All State 继续提供执行器所需的实体与证据，JEV State 继续由显式投影生成；本 Iteration 不接入 JEV，也不添加 wait/no-op。

### Requirement Baseline

| Requirement ID | Requirement | Source | Verification tier | Reason for tier |
|---|---|---|---|---|
| R1 | 按植物实体列表中的 row/col 解析目标格的全部 plant ID；种植只有在目标格出现新 ID 且其 type_name 与所选植物一致时才能确认成功。 | 引用对话中的第 1、3 项；当前 ActionExecutor 与 State 结构。 | G1 | 植物实体定位和类型确认决定动作结果是否可信。 |
| R2 | 为 place_plant、collect_item、shovel_cell 提供薄的语义校验与适配边界：种植检查卡牌 usable 严格为 true 且格子为 null；铲除仅接受 plant:<name> 格并按 row/col 对该格执行一次原生铲除；卡槽由 State 的 0 基 slot 转换为 Executor 的 1 基 card_slot。collect_item 使用 JEV 可见的 item 属性，由 Adapter 在同 sample_sequence 的 All State 中唯一解析 item ID。 | 引用对话中的第 2、4 项及用户对 OD-01 的选择；当前 cards、board.cells、items 投影与 ActionExecutor 请求契约。 | G1 | 错卡、占用格、不可判定格、过期/歧义 item 不能触发动作；叠层格不保证移除指定的一层。 |
| R3 | All State 与 JEV State 保持不同职责；ActionExecutor 只使用包含 IDs、availability 和 evidence 的 All State，决策校验使用 JEV State。 | 引用对话中的第 5 项；004 的 State 投影契约。 | G1 | 合并诊断态和决策态会泄漏实现细节或削弱动作验证证据。 |
| R4 | 本次只收口上述三种现有动作接口，不接入 JEV、策略循环或 wait/no-op。 | 用户 2026-09-26 指定引用建议第 1–5 项并忽略第 6 项。 | G1 | 交付目标是接入 JEV 前的 State/Actions 接口准备；范围越界会改变阶段边界。 |

## 3. Scope

### In scope

- 一个 P01 计划，统一处理实体 ID 定位、类型后置确认、语义校验和 card slot 适配。
- ActionExecutor 的 cell ID 查询由 All State 顶层 plants 按 row/col 解析，不再假定 board.cells 中嵌套的 plants 列表是 ID 的唯一来源；保留 availability 与 ID 完整性检查。
- place_plant 后置条件关联本次选择的 type_name；只有目标格新增实体 ID 且实体类型匹配才报告确认成功。
- shovel_cell 是格级动作：JEV 提供 row/col，Executor 对该格执行一次原生铲除并确认该格至少有一个原有 plant ID 消失；单株格可对应唯一植物，叠层格不承诺精确选择某个实体或类型。
- 新增一个轻量 ActionValidator / ActionAdapter 边界，供未来 Controller 调用；验证三种已存在动作，拒绝缺失、未知、冲突或不唯一的输入；将 JEV 的 0 基 card slot 转换为 Executor 的 1 基 card_slot。
- 保留 All State 和 JEV State 两个表示，不把 availability、evidence、source、raw_snapshot、进程诊断或 item ID 塞入 JEV 投影；Adapter 按 CD-04 的当前 item 可见属性解析内部 ID。
- 用固定 State 样本及假 Executor 验证安全拒绝、语义映射和后置条件；更新 README 记录新边界的用途。
- 不新增依赖，不改变现有 JSON CLI 的低层动作语义。

### Out of scope

- 第 6 项 wait/no-op；它仍由未来 Controller 自行决定是否跳过调用。
- JEV/LLM 调用、策略、Controller、自动循环、重试、pending-action 管理或完整游戏策略。
- 改写 State v1 的一般字段或重做 004 已交付内容；不向 JEV items 投影添加 item ID。
- 改变游戏进程读取、目标窗口校验、鼠标输入机制、游戏版本或新增 HTTP 写接口。
- 按 plant ID 或 type_name 精确选择叠层格中的某一株；未来若需要该能力，须单独定义可选择的动作及匹配的后置条件。
- 让 ActionExecutor 直接消费精简 JEV State，或让 Validator 替代 Executor 现有的目标进程、输入发送和 State 后置确认职责。

## 4. Plan Catalog

| Plan ID | Plan | Main outcome | Depends on | Status | Link |
|---|---|---|---|---|---|
| P01 | Action / State 边界收口 | 语义动作校验、slot 转换、植物实体 ID 查询与类型确认，保留两种 State 职责 | 003-action-executor；004-game-state-observation | Approved | plans/01-action-boundary.md |

## 5. Decision

- Open Decision：None。
- Confirmed Decision：本 Iteration 范围采用引用建议第 1–5 项并排除第 6 项 wait/no-op；shovel_cell 按 row/col 定位，plant ID 只在 All State 内部用于结果核对；collect_item 采用 Option A，保持 JEV items allowlist 不变并由 Adapter 在同 sample_sequence 的 All State 中按可见 item 属性唯一解析内部 ID。用户另要求删除旧 005 取消记录并将本计划从 006 改为 005。来源均为用户 2026-09-26 的直接指令。

## 6. Task

- P01 的 T1 修正实体 ID 查询并增加种植类型确认。
- P01 的 T2 增加三种动作的语义校验与 Adapter，按 CD-04 实现 collect item 的唯一属性匹配。
- P01 的 T3 公开并记录该边界，保留原有 CLI。
- P01 的 T4 增加自动化契约测试并运行项目测试套件。
- 单一 P01 将这几项放在同一端到端契约内；详细依赖和文件回填见 P01。

## 7. Validation

### Current delivery boundary

- 本次产物与实际用途：未来 JEV Controller 可安全调用的动作前置校验与语义适配边界，以及能独立读取 All State 做结果确认的 ActionExecutor。
- 本次交付成功的最小条件：G1 检查证明 plant IDs 从实体列表解析正确；卡牌、cells 和收取目标校验 fail-closed；slot 转换正确；新植物类型匹配是 success 的必要条件；All State 与 JEV State 的既有 allowlist 隔离得到回归保护。
- 不作为本次交付门槛的场景：真实 JEV 决策与运行、其他 PvZ 版本/布局、无尽模式或特殊背景的种植规则、实际对局中完整动作循环。真实窗口动作可列为 G2；将来开始接入 JEV 时重新评估。

### Verification tiers

| Tier | Meaning | Handling in Verify |
|---|---|---|
| G1 核心路径 | 实体 ID 按格解析、动作 Validator/Adapter 的输入判定与映射、植物类型确认、当前 CLI/State 契约回归 | 必须取得自动化测试证据；失败或缺少必要证据影响交付。 |
| G2 当前风险 | 在真实游戏中核验选择植物与新植物类型的端到端确认 | 记录结果与风险；除非实施中发现模拟样本无法覆盖类型/slot 关联，否则不阻塞交付。 |
| G3 后续场景 | 真实 JEV 决策循环、wait/no-op、不同游戏版本和非标准棋盘 | 本次不执行；进入相应后续阶段时重查。 |

G1 的最小充分路径是 P01/V01–V04；完整单元测试套件用于发现跨模块回归。V03 按 CD-04 验证可见 item 属性在同样本 All State 中唯一解析且投影不泄漏 ID。所有检查均在实现阶段执行；当前 Plan 阶段不运行测试。

## 8. Risks

- State cards.slot 为 0–9，ActionExecutor.card_slot 为 1–10；重复或偏移错误可能选择错误卡牌，Adapter 必须严格转换并用测试锁定边界。
- 当前 JEV items 投影没有 item ID，而 collect_item 要求内部 ID；CD-04 要求使用当前投影提供的 type_code、type_name、x、y 精确匹配同样本 All State。缺项、不一致或不唯一均拒绝收取。
- All State 与 JEV State 若来自不同 sample_sequence，按可见坐标映射 item 或卡牌可能过期；Adapter/Validator 应拒绝不一致样本。
- 单格可能含多株植物；ID 查询必须保留该格全部实体，铲除仍依靠 Executor 的原生一次铲除语义和 State 回读。
- 当前工作区存在用户已有未提交改动和未跟踪的 004 evidence；实现与交付阶段必须保留，不纳入本 Iteration 变更。

## 9. Approval

- Status: Approved
- Approved by: User
- Approval date: 2026-09-26
- Notes: 用户明确批准 005/P01；OD-01 Option A 已记录为 CD-04。

