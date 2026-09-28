# Project Map

## Technology Stack

| Area | Technology | Purpose |
|---|---|---|
| 游戏目标 | Windows x86 PE，Plants vs. Zombies 1.0.0.1051 | `.game/` 中固定身份的本地只读采集对象 |
| Python 环境 | Python 3.12.13、uv、`pyproject.toml`、`uv.lock`、python-dotenv | 环境、依赖与 `.env` 加载 |
| JEV 决策 | TypeSafe Python SDK (`typesafe-sdk`) | 通过 typed Noul/Choice 请求 Router 与专项 Action |
| 进程、窗口与内存 | pywin32、ctypes、Win32 ReadProcessMemory / User32 PostMessageW | 目标身份校验、只读内存采集、目标 HWND 鼠标消息 |
| 状态与展示 | Python 标准库 JSON/HTTP、原生 HTML/CSS/JavaScript | State 归一化、本机 Dashboard、JEV Runtime 控制与决策点阵 |
| Runtime Trace | Python 标准库 JSON Lines | JEV Loop 逐周期持久化、安全摘要和 Dashboard 只读读取 |
| 测试 | `unittest` | 读取、State 和 HTTP 接口回归 |
| 工作流 | Markdown、Python hooks | 仓库 SDD 阶段约定和 Iteration 名称检查 |

## Directory Tree

```text
AGENTS.md
.agents/skills/{sdd-plan,sdd-implementation,sdd-verify,sdd-delivery,sdd-memory}/
.codex/hooks/
.github/copilot-instructions.md
.game/PlantsVsZombies.exe
.log/            （JEV 逐周期 JSONL Trace 与真机对局日志，交付证据）
.memory/{context.md,project-map.md}
.sdd/
  001-memory-state-reader/
  002-progress-and-zombie-health/
  003-action-executor/
  004-game-state-observation/
  005-action-state-boundary/
  006-jev-runtime-loop/{plan-index.md,plans/01–05,verify.md}
  007-dashboard-jev-runtime/{plan-index.md,plans/01–02}
.python-version
pyproject.toml
uv.lock
README.md
README.zh-CN.md
main.py
configs/{pvz_1051.py,plant_catalog.py,zombie_catalog.py,item_catalog.py,plant_experience.txt}
runtime/{process.py,memory.py,session.py,window.py}
actions/{__init__.py,boundary.py,executor.py}
game/{arrays.py,reader.py}
state/{schema.py,builder.py,projection.py}
jev/{__init__.py,config.py,client.py,decision.py,loop.py,questions.py,scheduler.py,strategy.py,trace.py}
dashboard/{server.py,runtime_control.py,static/{index.html,viewmodel.js,recording.js,state.html,state-page.js,jev.html,jev-page.js,style.css}}
tools/{dev-view.mjs,fixtures/{recording-probe.js,verify-probe.js,narrow-probe.js}}
tests/{test_action_boundary.py,test_memory.py,test_reader.py,test_state.py,test_session.py,test_web.py,test_jev_client.py,test_jev_cli.py,test_jev_loop.py,test_jev_scheduler.py,test_jev_strategy.py,test_jev_trace.py,test_live_validation.py,capture_live_validation.py}
docs/{architecture.md,memory-map.md,usage.md}
```

## Path Descriptions

| Path | Description |
|---|---|
| `.agents/skills/` | 仓库 SDD 阶段技能、模板与记忆维护流程。 |
| `.codex/hooks/` | Iteration 和仓库结构检查脚本。 |
| `.game/` | 本地目标游戏程序；被 Git 忽略。 |
| `.log/` | 运行期产物：`jev-loop` 逐周期 JSONL Trace、真机对局日志与分析文档；作为交付验证证据入库（非源码）。 |
| `.memory/` | 跨会话上下文和已实现项目地图。 |
| `.sdd/` | SDD Iteration 001–007 的计划和阶段产物。 |
| `configs/` | 固定目标身份、静态偏移与植物/僵尸/掉落物目录；Plant/Zombie 能力描述供 JEV 使用。`plant_experience.txt` 是**可手编**的植物布局经验文本（每行一条，`#` 注释），由 `jev/questions.py` 的加载器读取后追加进植物问题文本。 |
| `runtime/` | Windows 进程定位/身份校验、只读内存原语、目标窗口校验和持有已验证目标的采样会话。 |
| `actions/` | 决策侧语义校验/适配，以及目标 HWND 定向动作执行和同进程 State 结果确认。 |
| `game/` | PvZ 容器与原始对象读取。 |
| `runtime/session.py` | 持有已验证目标进程句柄的采样会话：每样本廉价守卫（存活/主模块路径/基址）与 1 s 磁盘身份、30 s 唯一性周期重验证；身份失败作废会话并可重解析。 |
| `state/` | 版本化 All State 快照、证据/可用性归一化及 JEV State 显式 allowlist 投影；默认采集路径经由采样会话，`source` 携带 `identity_verified_at_utc`。 |
| `jev/` | TypeSafe typed异步API；collect/自主经营shared请求、本局最后模型意图/结果、变化驱动Runtime/单执行调度、受限Trace与v1/v2兼容。 |
| `jev/strategy.py` | 当前观察事实/预算/可信波次/observed_lanes、经营与collect语义key、完整合法候选；旧phase/urgency保留历史兼容，不用于自主策略覆盖。 |
| `jev/questions.py` | collect单Noul、共享自主经营意图/type/immediate问题与具体目标Choice的单一文本/技术门槛来源，供人工审阅；含固定方向锚定句 `PLANT_LAYOUT_ANCHOR` 与手编经验加载器 `load_plant_experience`（不缓存、缺文件为空、运行时不校验）。 |
| `jev/scheduler.py` | `ActionProposal` 与单执行调度：模型紧急性/FIFO、派发前意图来源版本/ID/实际资源复核、TTL交回；不本地改选模型目标。 |
| `dashboard/` | 本机 HTTP 服务、录制页（世界状态 + 800×600 游戏窗口 + JEV 决策空间）、State 观察、JEV Runtime 子进程控制。 |
| `tools/` | 开发期视觉与布局验证工具：`dev-view.mjs` 经 CDP 驱动本机 Edge 做无头截图与几何量测（Node，无 npm 依赖），`fixtures/` 存放录制页固定样本与窄屏量测探针。不参与运行时，不被 `STATIC_FILES` 服务。 |
| `dashboard/runtime_control.py` | Windows 单实例进程锁及 Dashboard 所启动 JEV 子进程的状态、START、STOP 生命周期。 |
| `actions/boundary.py` | 校验同样本语义请求；collect支持唯一item_id直接适配既有Executor，保留旧坐标接口，另两动作语义不变。 |
| `tests/` | 内存读取、采样会话、State、动作边界、JEV Client/Loop/策略/调度/JSONL Trace、Dashboard 和现场验证逻辑测试。 |
| `docs/` | 当前架构、内存字段和详细使用说明。 |
| `tests/test_action_boundary.py` | 固定 State 与 fake Executor 的动作边界、实体 ID、类型后置条件及隔离回归。 |
| `tests/test_jev_cli.py` | 验证 JEV Loop CLI 的安全配置预检和 fail-fast 行为。 |
| `main.py` | `probe`、`snapshot`、`serve`、`action` 与带显式 JSONL 路径的 `jev-loop` CLI 统一入口。 |
| `pyproject.toml`、`.python-version`、`uv.lock` | Python 版本与依赖配置。 |
| `README.md`、`README.zh-CN.md` | 中英文安装、运行、JEV Loop/Runtime/Dashboard 用法与测试命令。 |
