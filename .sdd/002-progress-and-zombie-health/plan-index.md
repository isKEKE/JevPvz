# Plan Index

这是 `002-progress-and-zombie-health` 的阅读入口；三个具体 Plan 分别见 `plans/`。本 Iteration 基于当前工作区已有的只读采样器与网页，不替代尚未完成的 001 验证。P01/P02 已按原批准范围完成 Implementation；P03 是用户本次新增的范围。

## 1. Metadata

- Iteration: `002-progress-and-zombie-health`
- Created at: 2026-09-24
- Status: Approved
- Owner: 本仓库维护者

## 2. Goal

让场景、模式、关卡和波次成为含义清楚、可核验的 State；复核僵尸本体与装备分层血量；并修复合法同格植物叠放导致草坪整块显示为空的问题。保持目标版本 1.0.0.1051、只读内存、现有目录与本地网页架构。

### Requirement Baseline

| Requirement ID | Requirement | Source | Mandatory |
|---|---|---|---|
| R1 | 读取并命名游戏场景与模式，区分“正在游玩”等场景和“冒险模式”等模式；未知枚举保留原始码 | 用户报告阶段/模式未获取；2026-09-24 公开结构检索 | Yes |
| R2 | 读取关卡编号、场地类型、已生成波数和总波数；冒险关卡可经确认后显示如 `1-5`，其他模式不套用冒险公式 | 用户报告关卡未获取；现有候选偏移与实机读数 | Yes |
| R3 | 暂停与关卡完成字段按单字节布尔值读取；不得把相邻字节组成的四字节值当作状态 | 公开 Board 结构；实机暂停原始值 `473956353` | Yes |
| R4 | 僵尸血量分别保留本体、头盔、盾牌和气球字段；页面清楚显示分层值及数值合计，不把本体 HP 称为整只僵尸 HP | 用户的铁桶僵尸截图与实机复现 | Yes |
| R5 | 从原始读数到 State、`/api/state` 和网页保持一致，缺失/未知值及 `provisional` 证据状态可辨 | 既有 State 契约与用户观察方式 | Yes |
| R6 | 用固定样本和只读现场采样验证各 Task；人玩关卡的动态观察仍由用户决定，不用写内存或操控游戏制造场景 | 用户已确认的只读与 human 验证边界 | Yes |
| R7 | 同一格多株植物必须保留所有活实体，不能因为高坚果与南瓜头叠放而清空全部草坪 | 用户 2026-09-24 游戏/网页截图与实机 raw 50 株、6 个叠放格 | Yes |
| R8 | 5×9 网格逐格展示叠放植物的全部名称；普通植物、空格、可种性未知及读取失败要能区分 | 用户报告草坪全空；现有 `renderBoard` 单株字段路径 | Yes |
| R9 | 固定样本和同帧只读现场对照植物实体数、占用格数、叠放格数；真正越界或容器计数错误仍显式失败 | 用户截图；修复前 `Multiple plants occupy row 0, column 6`，修复后 50/44/6 单帧 | Yes |

## 3. Scope

### In scope

- P01/T1：核对 `Root+0x7FC/+0x7F8` 场景/模式、`Board+0x554C/+0x5550/+0x5564/+0x557C` 场地/关卡/波数，并更正 `Board+0x164/+0x55FC` 布尔值读取；在 State 和网页展示有证据的名称与数值。
- P02/T1：审查当前已写入但尚未纳入 SDD 验证的 `Zombie+0xC8/+0xD0/+0xDC/+0xE4` 分层 HP 代码，补足路障、铁桶和带盾实例的回归覆盖与网页显示证据；保留 `hp` 的旧字段兼容语义为本体 HP。
- P03/T1：检查 `state.builder.build_state` 的同格植物聚合和 `dashboard/static/app.js::renderBoard` 的多名称呈现；保存本次[游戏叠放画面](evidence/001-layered-plants-game.png)与[草坪全空故障画面](evidence/002-empty-board-bug.png)为故障参照。现有直接修复已使单帧 State 读到 50 株、44 个占用格、6 个叠放格且 32 项测试通过，仍须按新 Plan 核验与回填。
- 两项均沿用 Python 3.12.13、`uv`、`pywin32`、`ctypes` 和原生网页；预计零新增依赖、零新抽象，改动限制在既有 `configs/`、`game/`、`state/`、`dashboard/static/`、`tests/` 与字段文档。
- 已检查：`configs/pvz_1051.py`、`game/reader.py`、`state/builder.py`、`state/schema.py`、`dashboard/static/app.js`、`dashboard/static/style.css`、`tests/test_reader.py`、`tests/test_state.py`、`tests/test_web.py`、`README.md`、`docs/memory-map.md`、`pyproject.toml`、001 的 P02–P04 Plan 和 `verify.md`。P01/P02 的原实施证据保留在各自 Plan 中；本次追加的植物叠放现场和当前代码基线见 P03。

### Out of scope

- JEV 决策、自动玩游戏、注入/写内存、其他 PVZ 版本、修改游戏存档。
- 从 HP 合计推算精确击杀时间或不同攻击方式的伤害路径；合计只表示当前各部位数值之和。
- 在尚未发生的场景或模式上声称已经完成动态验证；001 尚缺的证据不由 002 文档代填。

## 4. Plan Catalog

| Plan ID | Plan | Main outcome | Depends on | Status | Link |
|---|---|---|---|---|---|
| P01 | 关卡与进度 State | 场景、模式、场地、关卡、波数和布尔状态的正确读取与显示 | 现有 001 代码 | Approved | [plans/01-game-progress.md](plans/01-game-progress.md) |
| P02 | 僵尸分层血量 | 本体和装备 HP 的实机核对、回归覆盖与清楚显示 | 现有 001 代码；与 P01 无互相依赖 | Approved | [plans/02-zombie-health.md](plans/02-zombie-health.md) |
| P03 | 同格植物叠放与草坪显示 | 保留同格多株，网页逐格展示并防止整域清空 | 现有植物读取、State 与网页；与 P01/P02 无逻辑依赖 | Approved | [plans/03-layered-plants.md](plans/03-layered-plants.md) |

## 5. Decision

- Open Decision：无阻塞性产品选择。P03 保留完整 `cell.plants` 列表和既有单株兼容字段；未来更完整的种植规则另行规划。
- Confirmed Decision：2026-09-24 用户先要求关卡与僵尸血量两个 Task，后提供叠放植物和草坪全空的对照截图，明确要求在 002 增加修复 Plan。既有只读内存、网页展示与用户亲自玩关卡的验证边界继续有效。

## 6. Task

- P01/T1：关卡与进度字段从内存经 State 到网页的核验和显示。
- P02/T1：僵尸本体/护甲分层 HP 的复核、必要修正与显示验证。
- P03/T1：同格植物叠放与草坪呈现的复核、必要修正及现场对照。
- P01/P02 的 T1 已在原批准范围实施并回填；P03/T1 已实施并回填为 `[x]`。P03 涉及 `state/builder.py`、`dashboard/static/app.js` 与 P01/P02 的历史改动同文件，已保留完成行为；各 Task 的实际文件及证据见具体 Plan。

## 7. Validation

1. 自动：`uv run python -m unittest discover -s tests -p "test_*.py"`、`uv run python -m compileall configs game state dashboard tests`、`node --check dashboard/static/app.js`（本机有 Node 时）、`python .codex/hooks/check_iteration_names.py`。
2. 现场：保持只读，运行 `uv run python main.py probe` 与 `uv run python main.py snapshot --once`，对照同一时刻的 raw、State、`GET /api/state` 和网页。当前铁桶样本期望本体 270、头盔 1100、合计 1370；关卡样本的 `scene=3/mode=0/level=5/wave=3/20` 只代表该次采样，不能写死。
3. 动态：若用户自行在游戏里经历开局、波次推进、暂停、结束，记录事件前后读数并升级对应字段证据；未发生的事件保留待核验。完成 002 验证不得掩盖 001 仍未关闭的事项。
4. P03：构造高坚果+南瓜头的两种数组顺序、承载植物和三株同格样本，核对 `plants` 总数与各格列表之和；在新启动的只读网页服务中对照游戏画面、raw/State/API/UI，空格与真实读取失败保持不同文案。旧版 8765 服务不作为新代码的验收依据。

## 8. Risks

- `Root` 场景字段在当前配置中误命名为 `root`，需迁移时兼顾原始快照可读性；菜单和关卡结束时 Board 指针可能变化。
- `mCurrentWave` 在 1051 公开表中称“已生成波数”，不等于屏幕上存活的僵尸批数；冒险 `mLevel` 的 `1-5` 格式只适用于经核对的模式。
- 当前 HP 合计已由直接修复产生，但不同部位受攻击机制不同；显示名称必须避免暗示合计就是统一伤害池。旧网页服务进程需重启才能加载新的 Python 读取逻辑。
- 001 的 P03/P04 回填和 Verify 证据仍未完成；002 是追加迭代，不改变 001 的批准或验证状态。
- P03 的叠放层级排序只是 State 展示约定，不能当作完整的游戏放置或铲除规则；50/44/6 为一次现场读数而非固定关卡常量。新增 P03 是实质范围变更，因此 002 的整体审批须重新确认；P01/P02 已完成的原范围与证据不回滚。

## 9. Approval

- Status: Approved
- Approved by: 用户（显式调用 `$sdd-implementation 002 plan-3`）
- Approval date: 2026-09-24
- Notes: 002 原 P01/P02 于 2026-09-24 获批并实施；用户在审阅新增 P03 后明确要求执行 `$sdd-implementation 002 plan-3`，据此批准扩展后的 002 及 P03 的当前范围。P01/P02 自身 Approval 记录保留为历史批准。

实质修改 Requirement Baseline、Scope、Decision、Task 或 Validation 后，将 Status 恢复为 Pending，直到用户再次明确批准。
