# JevPvz

Windows 下的《植物大战僵尸》1.0.0.1051 只读状态监视器：读取游戏进程内存，并提供 JSON 输出和本地网页仪表盘。

> 仅支持 `1.0.0.1051` x86 版本。程序只读内存，不写入游戏、不注入、不模拟操作。

## 环境

- Windows
- Python 3.12.13
- [uv](https://docs.astral.sh/uv/)
- 目标程序：`.game/PlantsVsZombies.exe`

目标程序需要与配置中的版本和 SHA-256 完全匹配；`.game/` 已被 Git 忽略。先启动游戏，再运行下面的命令。

## 使用

```powershell
uv sync

# 检查目标进程并输出一次原始读取结果
uv run python main.py probe

# 输出一次标准化状态 JSON
uv run python main.py snapshot --once

# 启动本地网页仪表盘
uv run python main.py serve
```

打开 <http://127.0.0.1:8765/> 查看状态。需要持续输出 JSON 时可运行：

```powershell
uv run python main.py snapshot --interval-ms 500
```

## 测试

```powershell
uv run python -m unittest discover -s tests -p "test_*.py"
```

详细架构和内存字段见 [`docs/architecture.md`](docs/architecture.md) 与 [`docs/memory-map.md`](docs/memory-map.md)。
