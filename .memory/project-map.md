# Project Map

## Technology Stack

| Area | Technology | Purpose |
|---|---|---|
| 游戏目标 | Windows x86 PE，Plants vs. Zombies 1.0.0.1051 | `.game/` 中固定身份的本地只读采集对象 |
| Python 环境 | Python 3.12.13、uv、`pyproject.toml`、`uv.lock` | 环境与 `pywin32` 依赖管理 |
| 进程、窗口与内存 | pywin32、ctypes、Win32 ReadProcessMemory / User32 PostMessageW | 目标身份校验、只读内存采集、目标 HWND 鼠标消息 |
| 状态与展示 | Python 标准库 JSON/HTTP、原生 HTML/CSS/JavaScript | State 归一化、本机网页轮询与显示 |
| 测试 | `unittest` | 读取、State 和 HTTP 接口回归 |
| 工作流 | Markdown、Python hooks | 仓库 SDD 阶段约定和 Iteration 名称检查 |

## Directory Tree

```text
AGENTS.md
.agents/skills/{sdd-plan,sdd-implementation,sdd-verify,sdd-delivery,sdd-memory}/
.codex/hooks/
.github/copilot-instructions.md
.game/PlantsVsZombies.exe
.memory/{context.md,project-map.md}
.sdd/
  001-memory-state-reader/
  002-progress-and-zombie-health/
  003-action-executor/
  004-game-state-observation/
  005-jev-state-projection/
.python-version
pyproject.toml
uv.lock
README.md
main.py
configs/{pvz_1051.py,plant_catalog.py,zombie_catalog.py,item_catalog.py}
runtime/{process.py,memory.py,window.py}
actions/{__init__.py,executor.py}
game/{arrays.py,reader.py}
state/{schema.py,builder.py,projection.py}
dashboard/{server.py,static/index.html,static/app.js,static/state.html,static/state-page.js,static/style.css}
tests/{test_memory.py,test_reader.py,test_state.py,test_web.py,test_live_validation.py,capture_live_validation.py}
docs/{architecture.md,memory-map.md}
```

## Path Descriptions

| Path | Description |
|---|---|
| `.agents/skills/` | 仓库 SDD 阶段技能、模板与记忆维护流程。 |
| `.codex/hooks/` | Iteration 和仓库结构检查脚本。 |
| `.game/` | 本地目标游戏程序；被 Git 忽略。 |
| `.memory/` | 跨会话上下文和已实现项目地图。 |
| `.sdd/` | 001 State 读取、002 关卡/僵尸 HP、003 后台动作执行器、004 State 观察；005 为按用户指示取消后的编号保留记录。 |
| `configs/` | 固定目标身份、静态偏移与植物/僵尸/掉落物目录。 |
| `runtime/` | Windows 进程定位/身份校验、只读内存原语和目标窗口校验。 |
| `actions/` | 目标 HWND 定向鼠标消息、语义动作和同进程 State 结果确认。 |
| `game/` | PvZ 容器与原始对象读取。 |
| `state/` | 版本化 All State 快照、证据/可用性归一化及 JEV State 显式 allowlist 投影。 |
| `dashboard/` | 本机只读 HTTP 服务、草坪仪表盘和完整 State 观察页。 |
| `tests/` | 内存读取、实体、State、页面接口和现场验证逻辑测试。 |
| `docs/` | 当前架构和内存字段说明。 |
| `main.py` | `probe`、`snapshot`、`serve` 和 `action` JSON CLI 统一入口。 |
| `pyproject.toml`、`.python-version`、`uv.lock` | Python 版本与依赖配置。 |
| `README.md` | 安装、运行与测试命令。 |
