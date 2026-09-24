# Plan 01 — 关卡与进度 State

## 1. Metadata

- Plan ID: P01
- Iteration: `002-progress-and-zombie-health`
- Status: Approved
- Depends on: 当前只读采样、State 与网页代码；不依赖 P02
- Requirement IDs: R1, R2, R3, R5, R6

## 2. Goal

把已有的场景/模式/关卡/波数候选读数核对为可解释的 State，并修正布尔字段读取宽度。页面直接显示有证据的中文含义和原始码；遇到未知枚举、菜单无 Board 或未经观察的动态语义时明确保留未知状态。

### Requirement Mapping

| Requirement ID | Outcome in this Plan | Acceptance signal |
|---|---|---|
| R1 | `scene` 和 `mode` 有明确字段名、已知枚举名称与原始码 | 实机 `scene=3` 显示“正在游玩”、`mode=0` 显示“冒险模式”；未知码不编造名称 |
| R2 | 关卡、场地类型、已生成/总波数独立输出 | 实机原始 5 和 3/20 与游戏画面、State、网页一致；只在冒险模式解释 1-5 |
| R3 | 暂停/完成按 `bool` 单字节读取 | 暂停现场读数为 0/1；不会再出现 `473956353` 一类混入邻字节的值 |
| R5 | 原始值、可用性、网页标签一致 | API 字段与 UI 同步；未核验值标 `provisional` 或 `unavailable` |
| R6 | 固定样本和现场只读检查 | 自动测试覆盖已知/未知/错误输入；现场不修改游戏 |

## 3. Scope

### In scope

- 核对 [PvZLib 1051 地址表](https://github.com/HenryJk/PvZLib/blob/main/include/pvz_reference/1_0_0_1051_en.h)的 `Root+0x7F8` 模式、`+0x7FC` 场景、`Board+0x554C` 场地、`+0x5564` 总波数、`+0x557C` 已生成波数，以及[公开 Board 结构](https://github.com/Electr0Gunner/PvZ-Reconstruction-BugFix/blob/main/Lawn/Board.h)的 `+0x5550` 关卡、`+0x164` 暂停与 `+0x55FC` 关卡完成。枚举数值按[公开定义](https://github.com/Patoke/re-plants-vs-zombies/blob/main/ConstEnums.h)作为候选，对目标 SHA-256 实机核验。
- 保留 `progress_raw` 作为诊断信息；规范化场景、模式、关卡、场地与波次时分别设置 `availability`，避免一个字段成功让整组误标已验证。`mCurrentWave` 的展示名称是“已生成波数”。
- 修正 `scene` 配置中把场景叫 `root` 的误名；需要时兼容旧采样 fixture。冒险关卡标签只对 mode=0 且 level 在合理范围内转换；其他模式保留原始编号或未获取。
- 在 `dashboard/static/app.js` 的进度区显示同一 State 的结果与证据标记，网页原始候选读数仍可查看。

### Out of scope

- 对所有挑战、生存模式的关卡编号猜统一转换公式；更改游戏进程；推算下一波倒计时。
- 没有画面/事件证据时把字段升级为 `available`。

## 4. Impact Surface

### 4.1 File and Symbol Map

```text
configs/
  pvz_1051.py
game/
  reader.py
state/
  builder.py
dashboard/static/
  app.js
tests/
  test_reader.py
  test_state.py
docs/
  memory-map.md
```

```text
File: configs/pvz_1051.py
Module: configs.pvz_1051
Symbols:
  CANDIDATE_OFFSETS — 版本化场景/模式、场地/关卡/波数与 bool 字段地址、字段名
```

```text
File: game/reader.py
Module: game.reader
Symbols:
  read_game_progress — 按字段实际宽度读取场景、模式、进度并保留逐项读错信息
  _candidate_u32_fields — 只处理四字节候选，布尔字段另行按字节读取
```

```text
File: state/builder.py
Module: state.builder
Symbols:
  build_state — 解析枚举和关卡/波数，独立设置 game.* availability 与 evidence
```

```text
File: dashboard/static/app.js
Module: browser renderer
Symbols:
  renderGame — 展示场景、模式、关卡、场地、已生成/总波数和字段状态
  FIELD_LABELS — 更新游戏进度字段的覆盖率名称
```

```text
File: tests/test_reader.py
Module: tests.test_reader
Symbols:
  FakeMemory/reader regression cases — 固定字节样本检验 bool 宽度和原始字段
```

```text
File: tests/test_state.py
Module: tests.test_state
Symbols:
  StateBuilderTests — 已知枚举、冒险关卡、未知模式和缺失值的 State 回归
```

```text
File: docs/memory-map.md
Module: memory field documentation
Symbols:
  progress field table — 记录来源、地址、宽度和实测证据等级
```

### 4.2 End-to-End Flow

```mermaid
flowchart LR
    A["CANDIDATE_OFFSETS"] --> B["read_game_progress"]
    B --> C["build_state"]
    C --> D["renderGame"]
```

## 5. Decision

### 5.1 Open Decision

无阻塞性 Open Decision。默认展示已确认的场景/模式名称和原始码；其他模式的关卡标签按原始编号处理，待实际样本出现后再扩展。

### 5.2 Confirmed Decision

#### Confirmed Decision Record

- Decision ID: CD-01
- Confirmed choice: 继续使用 1.0.0.1051 的只读内存采集和现有 State/本地网页；阶段、模式与关卡各自独立显示。
- Source: 用户 2026-09-24 对未获取字段的追问及本次 `$sdd-plan` 两 Task 指令
- Date: 2026-09-24
- Reason: 公开结构与实机已有原始数值，缺口位于字段类型核验及 State/UI 解释层。

## 6. Task

### Task

- [x] T1 — 关卡与进度字段核验、归一化及展示
  - Objective: 将原始场景/模式/场地/关卡/波数与单字节状态通过 State 和网页准确呈现，并保留未知与证据等级。
  - Execution hint:
    - Width: `standard`
    - Worker effort: `medium`
    - Budget override: None; uses `sdd-implementation` defaults
  - Affected files:
    ```text
    Expected:
      configs/pvz_1051.py
      game/reader.py
      state/builder.py
      dashboard/static/app.js
      tests/test_reader.py
      tests/test_state.py
      docs/memory-map.md
    Actual:
      configs/pvz_1051.py
      game/reader.py
      state/builder.py
      dashboard/static/app.js
      tests/test_reader.py
      tests/test_state.py
      docs/memory-map.md
    ```
  - Implementation backfill:
    ```text
    Notes: 已将 Root 场景字段改名为 scene 并兼容旧 root 原始样本；增加 Board 场地类型读取；暂停与关卡完成按单字节读取。State 对场景、模式、场地、关卡、已生成/总波数和布尔值分别输出字段、码值、availability/evidence；未知枚举保留原始码，冒险关卡按每十关换世界的规则生成 N-M 标签，菜单/加载/制作人员名单场景不显示 Board 进度。网页同步显示名称、原始码、逐字段证据和未知值。
    Changed files:
      configs/pvz_1051.py
      game/reader.py
      state/builder.py
      dashboard/static/app.js
      tests/test_reader.py
      tests/test_state.py
      docs/memory-map.md
    ```

## 7. Validation

### Traceability

| Requirement ID | Task ID | Check | Expected evidence |
|---|---|---|---|
| R1 | T1 | 固定枚举值与现场 `scene=3/mode=0` | 名称、原始码和状态一致；未知码原样保留 |
| R2 | T1 | `level=5`, `current_wave=3`, `total_waves=20` 样本，及现场画面 | 冒险关卡与已生成波数表述准确；其他模式不套冒险标签 |
| R3 | T1 | `+0x164/+0x55FC` 周围邻字节非零的固定样本 | 布尔字段只取目标字节，不读取邻域 |
| R5 | T1 | raw → State → API → 页面同次采样 | 逐字段证据标记与值一致，缺失与错误可区分 |
| R6 | T1 | 自动测试及用户游戏自然事件时的只读对照 | 不通过写入/操控游戏制造变化 |

### Commands

- 目标运行环境/测试命令：`uv run python main.py probe`；`uv run python main.py snapshot --once`；`uv run python main.py serve --port 8765`，浏览器看 `http://127.0.0.1:8765/` 和 `GET /api/state`。
- 静态检查：`uv run python -m compileall configs game state`；`node --check dashboard/static/app.js`（本机有 Node 时）。
- 针对性测试：`uv run python -m unittest discover -s tests -p "test_*.py"`；`python .codex/hooks/check_iteration_names.py`。

### Implementation evidence

Implementation evidence (T1):

- `uv run python -m unittest discover -s tests -p "test_reader.py"` 与 `... "test_state.py"`：分别 7、14 项通过；邻接非零字节样本确认两个 bool 只读首字节；菜单无 Board 样本仍保留 Root scene/mode。
- `uv run python -m unittest discover -s tests -p "test_*.py"`：30 项通过。`uv run python -m compileall configs game state dashboard tests`、`node --check dashboard/static/app.js`、`python .codex/hooks/check_iteration_names.py` 均通过。
- 只读同一帧 raw/State（2026-09-24T05:09:42.675Z）：scene/mode/background/level/current/total/pause/complete 原始值 `3/1/0/0/9/10/1/0`；State 分别显示正在游玩、普通生存第 1 阶段、白天、原始关卡 0、已生成 9/总计 10、暂停、未完成；进度 availability 均为 `provisional`，evidence 为 `observed_once`。
- 更新服务的 `GET /api/state` 返回新字段和 raw snapshot；首页与 `/static/app.js` 均 HTTP 200。既有 8765 服务仍是旧进程，返回旧 `root` 和宽读 pause 值；使用临时端口 8766 检查后已停止该临时服务，未触碰原进程。
- 未在游戏中制造场景切换；菜单/无 Board 与未知码由固定样本覆盖，未发生的动态事件仍保持 provisional。正式独立复核仍属于 Verify。
- Repair wave 2：Adventure 原始关卡按每十关换世界（`1..10 → 1-1..1-10`, `11..20 → 2-1..2-10`），保留 raw `level_number`；新增回归 `15 → 2-5`、`50 → 5-10`。修复后 `uv run python -m unittest discover -s tests -p "test_state.py"`：15 项通过。

### Manual checks

- 对当前游戏同次/相邻采样记录时间、PID、scene/mode/level/wave/pause 的 raw 与 State，页面不能继续把已有可信读数显示为“未获取”。
- 若用户自行经历暂停/恢复、波次前进或关卡结束，对照前后值；尚未出现的变化保留 `provisional`，不借用旧截图假称已验证。
- 若游戏处于菜单或 Board 无效，确认页面不沿用上一局的关卡/波数作为当前状态。

## 8. Risks

- 场景与模式存于 Root，关卡/波数存于 Board；Board 切换时需要避免跨场景拼接旧值。
- 当前 `pause_flag` 的四字节读数非 0/1，现有 `bool(raw)` 只是偶然得到正确结果；必须单字节读取。
- `mLevelComplete` 表示本关完成，不等同游戏整体胜利；`mCurrentWave` 是已生成波数，不代表当前还活着的僵尸波。
- 七个预计文件超过小改动基线，因为同一字段贯穿配置、读取、State、浏览器和已有测试/文档；零新增依赖。

## 9. Approval

- Status: Approved
- Approved by: 用户
- Approval date: 2026-09-24
- Notes: 随 002 Iteration 获用户明确审批。

若 Goal、Scope、Decision、Task 或 Validation 有实质修订，将 Approval 恢复为 Pending，并等待用户再次明确批准。
