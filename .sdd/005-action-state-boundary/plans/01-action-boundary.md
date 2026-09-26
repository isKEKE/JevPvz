# Plan P01 — Action / State 边界收口

## 1. Metadata

- Plan ID: P01
- Iteration: 005-action-state-boundary
- Status: Approved
- Depends on: 003-action-executor；004-game-state-observation
- Requirement IDs: R1、R2、R3、R4

## 2. Goal

在接入 JEV 之前提供稳定、可测的语义动作边界：Validator 根据 JEV 决策可见的 State 拒绝不合法或不可判定的请求，Adapter 将植物名及 0 基卡槽转换成现有 ActionExecutor 请求，Executor 继续使用完整 All State 的实体 ID 和证据确认真实变化。三种动作保持 place_plant、collect_item 和 shovel_cell；不在本 Plan 接入 JEV 或增加 wait/no-op。

### Requirement Mapping

| Requirement ID | Outcome in this Plan | Acceptance signal |
|---|---|---|
| R1 | ActionExecutor 按 row/col 从 All State 的 plants 实体列表取得格内全部 ID，并为种植确认匹配的 type_name。 | 目标格的 ID 集合覆盖单株及叠层；缺失/重复/不可用数据不会误报成功；错类型不能得到 success。 |
| R2 | ActionValidator / ActionAdapter 校验三种动作并将植物名、卡槽及收取目标适配到当前 Executor。 | place 仅接受 usable 严格为 true 且 cell 严格为 null；shovel 接受 plant:<name> 后按 row/col 铲除一个格子；卡槽 0–9 正确转成 1–10；collect 使用 JEV 可见的 type_code、type_name、x、y，在同 sample_sequence 的 All State 中唯一找到当前 item。叠层格不承诺铲除特定层。 |
| R3 | All State 和 JEV State 保持独立；执行和验证继续使用 All State，决策前置条件只读 JEV State。 | 投影回归证明诊断/实体字段不会意外泄漏；Executor 不需要读取精简 JEV State。 |
| R4 | 将已选择的第 1–5 项固化为动作边界；排除第 6 项 wait/no-op 和 JEV 运行时集成。 | 公共接口只接受三种已有动作；没有新增 Controller、JEV 客户端或循环入口。 |

## 3. Scope

### In scope

- 修正 ActionExecutor._cell_ids 的 ID 来源：从顶层 plants 按 row/col 取得目标格实体，不把 board.cells 的内部对象结构当作 ID 的唯一来源；继续要求 plants 可用且 ID 完整、唯一。
- 对 place_plant 建立所选植物类型的后置条件：执行前将语义植物名与当前卡牌/slot 对应，执行后只在目标格出现的新实体 ID 的 type_name 与请求植物一致时确认成功。无法唯一解析所选卡牌时不发送输入。
- 新增 actions/boundary.py，提供独立 ActionValidator 和 ActionAdapter：校验当前 JEV State 的卡牌、cells 与动作请求；将 0 基 card slot 转成现有 Executor 接受的 1 基 card_slot；按 CD-04 用 (type_code, type_name, x, y) 在同 sample_sequence 的 All State 中唯一解析收取目标 ID；把通过校验的三种动作交给 ActionExecutor。
- Validator 对 unknown、null、false、结构不全、目标不唯一及两份 State 的 sample_sequence 不一致均 fail closed。种植要求 usable is True、目标 cell is None；铲除要求 cell 是 plant:<type_name>；收取要求目标在当前样本中仍存在。
- shovel_cell 是 cell-level 操作：JEV 以 row/col 选择格子，Executor 使用 All State 记录动作前该格所有 ID，动作后只把至少一个原有 ID 消失作为成功条件。单株格的目标明确；叠层格只能确认某一株消失，不保证移除 JEV 心中指定的那一层或 type_name。
- ActionExecutor 保持读取 All State；JEV projection 仍使用显式 allowlist，不增加 item ID。
- 在 actions/__init__.py 导出新边界；README 说明 API 的职责与三种请求形态，同时保留现有低层 JSON CLI。
- 使用固定样本和 fake executor 覆盖合法映射、无效请求拒绝、实体 ID 解析与 postcondition。无需新增依赖。

### Out of scope

- wait/no-op；未来 Controller 可在调用动作边界前直接跳过。
- JEV 调用、决策提示词、Controller、动作循环、pending 状态、节流或自动重试。
- 更改 sun_balance、cards.usable、board.cells、items 以外的 State 语义，或将 availability/evidence/source/raw_snapshot/进程身份暴露给 JEV。
- 修改现有 action CLI 的低层参数语义；不新增 HTTP 写入口。
- 真实游戏自动决策或关卡通关。
- 通过 plant ID 精确选择叠层格中的指定植物。添加该需求时，除 JEV identity 外还需确认游戏原生铲子是否能按层选择，并为 Executor 增加与目标实体一致的后置条件。

## 4. Impact Surface

### 4.1 File and Symbol Map

~~~text
actions/
  __init__.py
  executor.py
  boundary.py                 # new
tests/
  test_action_boundary.py     # new
README.md
~~~

~~~text
File: actions/executor.py
Module: guarded same-process semantic actions
Symbols:
  ActionExecutor._cell_ids — resolve every plant ID at a row/column from the entity list
  ActionExecutor._plant_ids — preserve availability and ID uniqueness checks
  ActionExecutor._execute_place — retain new-ID/target-cell confirmation and require expected type_name
  ActionExecutor._execute_shovel — perform one cell-target shovel and confirm at least one prior ID disappears
  ActionExecutor._validate_request — carry optional expected type context without breaking existing CLI requests
  ActionExecutor.place_plant — retain the existing 1-based low-level card_slot API
~~~

~~~text
File: actions/boundary.py (new)
Module: decision-facing validation and action adaptation
Symbols:
  ActionValidator.validate — validate action against current JEV State and matching All State
  ActionAdapter.dispatch — convert semantic plant/item target into the existing Executor call
  ActionBoundary — expose one entry point joining validation and dispatch
~~~

~~~text
File: actions/__init__.py
Module: public action package
Symbols:
  ActionExecutor, ActionResult — existing public low-level API
  ActionBoundary — new entry point for future decision callers
~~~

~~~text
File: tests/test_action_boundary.py (new)
Module: action contract regression
Symbols:
  ActionBoundaryTests — verify valid dispatch and fail-closed rejection using fixed State samples and a fake Executor
  ActionExecutorPostconditionTests — verify ID resolution by row/col and type-aware planting confirmation
~~~

~~~text
File: README.md
Module: local tool usage and public action boundary
Symbols:
  Semantic actions section — distinguish future decision-facing boundary from existing low-level CLI; document accepted requests and fail-closed checks
~~~

### 4.2 End-to-End Flow

~~~mermaid
flowchart LR
    A["capture_state"] --> B["project_jev_state"]
    A --> C["ActionValidator.validate"]
    B --> C
    C --> D["ActionAdapter.dispatch"]
    D --> E["ActionExecutor.place_plant / collect_item / shovel_cell"]
    E --> F["ActionExecutor._execute_place / collect / shovel"]
    F --> G["capture_state and State postcondition"]
~~~

ActionValidator 和 ActionAdapter 是本 Iteration 的边界，不包含未来 JEV 调用；All State 与 JEV State 必须来自同一 sample_sequence。ActionExecutor 仍自行采集 All State 并执行现有目标身份、窗口和动作后置检查。

## 5. Decision

### 5.1 Open Decision

- Open Decision：None。

### 5.2 Confirmed Decision

#### Confirmed Decision Record — CD-01

- Decision ID: CD-01
- Confirmed choice: 本 Iteration 采用引用建议第 1–5 项；不包含第 6 项 wait/no-op。
- Source: 用户 2026-09-26 的当前请求“1-5, 忽略6”。
- Date: 2026-09-26
- Reason: 用户要求先完成 State/Actions 接口收口，再进入 JEV 接入。

该确认的 shovel 契约是 cell-level：JEV 的 row/col 足以指示单株格；board.cells 的植物名称可作占用校验；ActionExecutor 内部 ID 用于动作前后核对。精确选择叠层中特定 plant entity 不属于本次契约。

#### Confirmed Decision Record — CD-02

- Decision ID: CD-02
- Confirmed choice: 删除旧 005-jev-state-projection 取消记录；将本 Iteration 从 006-action-state-boundary 改为 005-action-state-boundary。
- Source: 用户 2026-09-26 明确指示“005删除，改006为005”。
- Date: 2026-09-26
- Reason: 按用户对此次编号的直接要求处理，作为仓库默认不复用已取消编号规则的显式例外。

#### Confirmed Decision Record — CD-03

- Decision ID: CD-03
- Confirmed choice: shovel_cell 通过 row/col 指定目标格；JEV 不需要 plant ID。All State 中的 plant IDs 仅由 ActionExecutor 内部用于核对动作前后的格内实体变化。
- Source: 用户 2026-09-26 明确说明“如果可以通过行和列铲除某个植物，这表示功能没问题，不需要具体某个id”。
- Date: 2026-09-26
- Reason: 当前铲除动作本来就是 cell-level；按格定位可满足用户要求，暴露实体 ID 不会增加该动作所需能力。叠层格只保证某株有变化，不承诺选中指定层。

#### Confirmed Decision Record — CD-04

- Decision ID: CD-04
- Confirmed choice: 采用 OD-01 Option A；不在 JEV items 中增加 item ID。collect_item 请求使用当前 JEV State 已有的 type_code、type_name、x、y；Adapter 只在同 sample_sequence 的 All State 中以这四项唯一匹配 item 并取出内部 ID。零个或多个匹配项都拒绝，不调用 Executor。
- Source: 用户 2026-09-26 明确选择“od-01 选A”。
- Date: 2026-09-26
- Reason: 复用已交付的 JEV item allowlist，同时满足低层 collect_item 对内部 ID 的要求；唯一性和样本序号约束避免猜测或使用过期实体。

## 6. Task

### Task

- [x] T1 — 解耦 plant ID 查询并按类型确认种植结果
  - Objective: 用 All State plants 实体列表按 row/col 解析完整 ID 集合；在发送 place_plant 前解析所选植物类型，并要求新建实体类型匹配后才报告 success。
  - Affected files:
    ~~~text
    Expected:
      actions/executor.py
      tests/test_action_boundary.py
    Actual:
      actions/executor.py
      tests/test_action_boundary.py
    ~~~
  - Implementation backfill:
    ~~~text
    Notes: ActionExecutor._cell_ids 已改为从 All State 顶层 plants 按 row/col 取得全部实体 ID，不再依赖 board.cells 的嵌套 plants；availability、ID 唯一性与完整性继续 fail closed，并拒绝无效行列。place_plant 在发送输入前从当前 All State 的 0 基 cards.slot 唯一解析 1 基 card_slot 对应 type_name；可选 expected_type_name 不匹配或卡牌缺失/歧义时不发送输入。后置条件要求目标格恰有一个新增 ID 且其 type_name 匹配所选卡牌；类型已知但不匹配时返回未确认，不会报告 success。保留原有低层 JSON 请求形态。
    Validation evidence: `uv run python -m unittest discover -s tests -p "test_action_boundary.py"` — 通过，6 项；初次运行仅因测试断言未匹配实际诊断措辞失败，修正断言后重跑通过。
    Changed files:
      - actions/executor.py
      - tests/test_action_boundary.py
    ~~~

- [x] T2 — 建立 fail-closed 语义校验与动作适配
  - Objective: 对三种动作执行 State 前置校验；完成 plant name 到当前唯一卡牌的映射、0 基 slot 到 1 基 card_slot 转换、shovel cell 判断及 CD-04 收取目标解析；仅通过校验后调用现有 ActionExecutor。
  - Affected files:
    ~~~text
    Expected:
      actions/boundary.py
      actions/__init__.py
      tests/test_action_boundary.py
    Actual:
      actions/boundary.py
      tests/test_action_boundary.py
    ~~~
  - Implementation backfill:
    ~~~text
    Notes: 新增 ActionValidator / ActionAdapter / ActionBoundary：要求 JEV 与 All State 有效 sample_sequence 一致；种植严格检查唯一已知卡牌、usable is True、目标 cells[row][col] 为 null，并校验 All State 目标格为空，将 State 0 基 slot 转换为 Executor 1 基 card_slot；铲除只接受 plant:<type_name> 格并要求 All State 同格实体/类型一致；收取仅用 (type_code, type_name, x, y) 在当前 JEV items 与 All State items 中唯一匹配，且检查 item availability、position、ID 完整唯一和有限坐标。未知、缺项、歧义、冲突及无效参数均在调用 Executor 前抛出 ActionValidationError。JEV 投影本身未改动且仍不含 item ID。
    Validation evidence: `uv run python -m unittest discover -s tests -p "test_action_boundary.py"` — 通过，14 项。
    Changed files:
      - actions/boundary.py
      - tests/test_action_boundary.py
    ~~~

- [x] T3 — 公开并记录动作边界
  - Objective: 让未来调用者能够使用新 ActionBoundary，同时明确它与当前低层 CLI 的分工、请求参数和拒绝条件。
  - Affected files:
    ~~~text
    Expected:
      actions/__init__.py
      README.md
    Actual:
      actions/__init__.py
      README.md
    ~~~
  - Implementation backfill:
    ~~~text
    Notes: 从 actions 包公开 ActionBoundary、ActionValidationError，保留现有 ActionExecutor / ActionResult 导出。README 新增 Python API、同样本 State 要求、三种语义请求形态、fail-closed 条件、返回/异常语义，以及其与未改变的低层 JSON CLI 的边界说明。
    Validation evidence: `uv run python -c "from actions import ActionBoundary, ActionExecutor, ActionResult, ActionValidationError; print('public action exports import successfully')"` — 通过；`uv run python -m unittest discover -s tests -p "test_action_boundary.py"` — 通过，14 项。
    Changed files:
      - actions/__init__.py
      - README.md
    ~~~

- [x] T4 — 增加动作契约回归
  - Objective: 用固定 State 与 fake Executor 覆盖三态 cells、card usable、卡槽转换、item 唯一性、plant IDs、植物类型和状态不一致场景。
  - Affected files:
    ~~~text
    Expected:
      tests/test_action_boundary.py
    Actual:
      tests/test_action_boundary.py
    ~~~
  - Implementation backfill:
    ~~~text
    Notes: 固定 State 与 fake Executor 覆盖空/不可种/占用 cells、usable 严格布尔、slot 0/9 到 1/10、collect 零/多匹配和样本不一致、实体 ID 完整与叠层、种植类型后置确认/不匹配、格级 shovel 至少一层 ID 消失、低层三种 CLI 请求兼容及 JEV item ID 隔离。
    Validation evidence: `uv run python -m unittest discover -s tests -p "test_action_boundary.py"` — 通过，16 项；`uv run python -m unittest discover -s tests -p "test_*.py"` — 通过，80 项（7.471 秒）。未运行真实游戏动作；V06 是 G2 非阻塞人工检查，留待后续 Human/Verify 处理。
    Changed files:
      - tests/test_action_boundary.py
    ~~~

## 7. Validation

### Traceability

| Check ID | Requirement ID | Task ID | Check | Tier and reason | Expected evidence | Delivery impact / escalation condition |
|---|---|---|---|---|---|---|
| V01 | R1 | T1、T4 | 固定 All State 样本验证按 row/col 取回单株和叠层 ID；验证缺失、重复 ID 或 plants 不可用时不误报；验证种植目标行列与新实体 type_name，并覆盖 cell-level shovel 只要求原有 ID 有变化。 | G1：实体跟踪与类型确认是动作后置结果可信的必要条件；叠层语义必须如实限制。 | 自动化用例证明 ID 集合完整；错误类型/错误格不能返回 success；叠层只证明至少一株消失，不声称精确选层。 | 任一失败阻塞交付。 |
| V02 | R2 | T2、T4 | 验证 place 的唯一 card、usable 严格为 true、目标 cell 严格为 null；验证 null/false/plant:* 和 unknown 均按定义处理；验证 slot 0/9 分别转换为 1/10。 | G1：动作发出前的基本防错门槛。 | 自动化用例覆盖接受、拒绝和 Executor 未被调用的情况，并断言正确 dispatch 参数。 | 任一错误请求触发 Executor 或转换错误阻塞交付。 |
| V03 | R2 | T2、T4 | 验证 collect 请求中的 type_code、type_name、x、y 在同 sample_sequence 的 All State 中唯一匹配当前 item；覆盖零匹配、多匹配及样本序号不一致时拒绝，并确认 JEV projection 不含 item ID。 | G1：收取目标须唯一且仍存在，不能依赖过期或猜测 ID。 | 固定样本自动化用例证明唯一匹配后只传入对应内部 ID，歧义时 Executor 未被调用；投影 allowlist 保持不变。 | 任一错误匹配、误调 Executor 或投影泄漏 ID 均阻塞交付。 |
| V04 | R3、R4 | T2、T3、T4 | 验证 Validator 仅使用 JEV 决策字段，ActionExecutor 仍读取 All State；确认 CLI 原有三种低层请求可回归，未新增 wait/no-op 或 JEV 循环。 | G1：State 隔离和限定动作面是本次接口目标。 | 自动化调用断言、投影 allowlist 回归及现有 CLI 测试。 | 数据层串用、字段泄漏或范围增加时阻塞交付。 |
| V05 | R1–R4 | T1–T4 | 运行新增动作边界测试与完整 unittest suite。 | G1：跨模块回归是动作接口变更的最小整体验证。 | 两条命令均通过的终端结果。 | 任一失败或未运行会阻塞交付。 |
| V06 | R1、R2 | T1、T2 | 在受控真实游戏窗口执行一次人工选卡种植，核对执行结果的类型和 row/col。 | G2：可发现仿真样本与实机 card slot 映射差异，但现有 G1 测试可以验证实现逻辑。 | 人工记录请求、State 前后样本及结果。 | 若出现错卡/错格或预期在无人工介入的实机中启用本接口，则升级为 G1。 |

### Commands

- 针对性测试（V01–V04）：uv run python -m unittest discover -s tests -p "test_action_boundary.py"
- 全量测试（V05）：uv run python -m unittest discover -s tests -p "test_*.py"
- 静态检查：仓库未配置独立 lint/type-check 命令；不新增工具。

### Implementation evidence

本阶段按 T1–T4 回填了各 Task 的实际文件与证据；这不是正式 verify.md 的替代。

- T1/T2/T3 targeted tests: `uv run python -m unittest discover -s tests -p "test_action_boundary.py"` — 最终 16 项通过；各 Task 完成时分别运行并记录了当时的 6、14、14 项结果。
- T3 public API smoke check: `uv run python -c "from actions import ActionBoundary, ActionExecutor, ActionResult, ActionValidationError; print('public action exports import successfully')"` — 通过。
- T4 full regression: `uv run python -m unittest discover -s tests -p "test_*.py"` — 80 项通过，耗时 7.471 秒。
- 未启动游戏或发送真实 UI 输入。V06 是 G2、默认非阻塞人工检查，本阶段未运行；正式 Verify 尚未执行。

### Manual checks

- V06 — Human 启动固定版本游戏，使用空且可种的标准日间格种植一株当前卡牌；核对成功结果中的新植物 type_name、row 和 col 与目标一致。此项为 G2，不作为默认交付阻塞。

## 8. Risks

- CD-04 的精确可见属性匹配依赖两份 State 来自同一 sample_sequence；即使序号一致，若可见属性不唯一也必须拒绝，不能退回猜测最近位置。
- JEV State 里的 usable 可能是 null；Validator 必须只接受真布尔值 true，未知不可被误当作可用。
- card slot 是两个层的不同编号体系，转换须使用唯一当前卡牌并覆盖首尾边界。
- ActionExecutor 会重新采集 All State；Validator/Adapter 输入需来自同一观察序列，且执行器需核对选中的预期植物，避免基于旧样本点击另一张卡。
- 同一格可有多株叠层植物；按 row/col 获取 ID 时不得仅取主植物，否则铲除后的实体变化确认可能错误。
- JEV 不看到 plant IDs，且现有 shovel_cell 只按格执行一次原生铲除、以任何一个旧 ID 消失为确认；因此它适用于格级清除，不支持保证移除某个指定叠层。
- JEV items 投影保持不含 ID；Adapter 使用 (type_code, type_name, x, y) 精确匹配当前 All State。若两个 item 无法唯一匹配，预期行为是拒绝收取而非任选一个。

## 9. Approval

- Status: Approved
- Approved by: User
- Approval date: 2026-09-26
- Notes: 用户明确批准 P01；CD-04 Option A、当前范围及 G1/G2 验证边界均已纳入批准基线。

