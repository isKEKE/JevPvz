# Project Map

## Technology Stack

| Area | Technology | Purpose |
|---|---|---|
| 游戏目标 | Windows x86 PE，Plants vs. Zombies 1.0.0.1051 | `.game/` 中固定身份的本地只读采集对象 |
| Python 环境 | Python 3.12.13、uv、`pyproject.toml`、`uv.lock` | 环境与 `pywin32` 依赖管理 |
| 进程与内存 | pywin32、ctypes、Win32 ReadProcessMemory | 目标进程发现、身份校验与只读内存访问 |
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
.python-version
pyproject.toml
uv.lock
README.md
main.py
configs/{pvz_1051.py,plant_catalog.py,zombie_catalog.py,item_catalog.py}
runtime/{process.py,memory.py}
game/{arrays.py,reader.py}
state/{schema.py,builder.py}
dashboard/{server.py,static/index.html,static/app.js,static/style.css}
tests/{test_memory.py,test_reader.py,test_state.py,test_web.py}
docs/{architecture.md,memory-map.md}
```

## Path Descriptions

| Path | Description |
|---|---|
| `.agents/skills/` | 仓库五个 SDD 技能与模板。 |
| `.codex/hooks/` | Iteration 和仓库结构检查脚本。 |
| `.game/` | 本地目标游戏程序；被 Git 忽略。 |
| `.memory/` | 跨会话上下文和已实现项目地图。 |
| `.sdd/` | 001 原迭代及 002 关卡/僵尸 HP 新方案。 |
| `configs/` | 固定目标身份、静态偏移与植物/僵尸/掉落物目录。 |
| `runtime/` | 通用 Windows 进程定位、身份校验与只读内存原语。 |
| `game/` | PvZ 容器与原始对象读取。 |
| `state/` | 版本化 State 快照、证据与可用性归一化。 |
| `dashboard/` | 本机只读 HTTP 服务及浏览器界面。 |
| `tests/` | 内存读取、实体、State 和页面接口测试。 |
| `docs/` | 当前架构和内存字段说明。 |
| `main.py` | `probe`、`snapshot` 和 `serve` 统一入口。 |
| `pyproject.toml`、`.python-version`、`uv.lock` | Python 版本与依赖配置。 |
| `README.md` | 安装、运行与测试命令。 |
