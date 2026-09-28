# JevPvz

[English](README.md) | 简体中文

在 Windows 上读取《植物大战僵尸》状态、查看本机仪表盘，并可通过语义动作或 TypeSafe JEV 决策循环操作游戏。

> 仅支持 x86 版 Plants vs. Zombies `1.0.0.1051`，程序身份须与 `configs/pvz_1051.py` 的版本和 SHA-256 一致。`action` 和 `jev-loop` **会操作游戏**；`probe`、`snapshot` 和 `serve` 只读。游戏可以在后台运行。

## 快速开始

1. 在 Windows 上安装 Python 3.12.13 和 [uv](https://docs.astral.sh/uv/)。
2. 将游戏放到 `.game/PlantsVsZombies.exe` 并启动。`.game/` 不纳入 Git。
3. 安装项目依赖：

   ```powershell
   uv sync
   ```

4. 按用途运行：

   ```powershell
   uv run python main.py snapshot --once   # 输出一次状态 JSON
   uv run python main.py serve              # 启动后访问 http://127.0.0.1:8765/
   uv run python main.py probe              # 校验游戏身份并读取一次
   ```

运行 `jev-loop` 前还需配置 `.env`，见下文。

## 命令速查

| 命令 | 用途 | 需要 `.env` | 操作游戏 |
|---|---|---|---|
| `probe` | 校验进程及程序身份，读取一次原始状态 | 否 | 否 |
| `snapshot` | 输出标准化 State JSON；`--profile jev` 输出精简字段 | 否 | 否 |
| `serve` | 启动本机只读状态页和 JEV Trace 时间线 | 否 | 否 |
| `action` | 执行一次语义动作 | 否 | **是** |
| `jev-loop` | 运行 JEV 异步决策循环并执行动作 | **是** | **是** |

完整参数与 State 字段说明见[详细使用说明](docs/usage.md)；架构与字段证据见[架构文档](docs/architecture.md)和[内存字段文档](docs/memory-map.md)。

## JEV 配置与运行

在项目根目录的 `.env` 中配置 `TYPESAFE_API_KEY`、`HTTP_PROXY` 和 `HTTPS_PROXY`。三个值均为必填，两个代理缺一时 `jev-loop` 会在启动阶段退出。

```powershell
$trace = ".log/jev-run.jsonl"
uv run python main.py jev-loop --trace-file $trace

# 另开终端，用仪表盘查看同一份 Trace
uv run python main.py serve --jev-trace-file $trace
```

Loop 默认持续运行，直到关卡结束、游戏断连、达到停止条件或按 Ctrl+C。可用 `--max-cycles 20` 限定已终结的决策任务数，用 `--interval-ms 250` 限制观察频率。每次都必须指定 `--trace-file`；**同一路径中已有的 JEV Trace 会在启动时被清空**，要保留历史请使用新路径。更多配置、停止条件及 Trace 说明见[详细使用说明](docs/usage.md#jev-决策循环会操作游戏)。

## 手动动作

每次 `action` 只执行一个请求。以下命令**会向游戏发送输入**：

```powershell
uv run python main.py action --action-json '{"action":"place_plant","card_slot":1,"row":0,"col":0}'
uv run python main.py action --action-json '{"action":"collect_item","item_id":3748399104,"timeout_ms":10000}'
uv run python main.py action --action-json '{"action":"shovel_cell","row":0,"col":0,"timeout_ms":10000}'
```

收集示例中的 `item_id` 须替换为当前 State 的物品 ID。结果 `status` 为 `success`、`rejected` 或 `unverified`；只有新 State 确认变化才返回 `success`。参数、校验规则与退出码见[详细使用说明](docs/usage.md#语义动作会操作游戏)。

## 测试与文档

```powershell
uv run python -m unittest discover -s tests -p "test_*.py"
```

- [详细使用说明](docs/usage.md)：状态观察、仪表盘、动作、JEV、Python API 与实机验收。
- [架构文档](docs/architecture.md)：模块职责、State 契约及 Runtime。
- [内存字段文档](docs/memory-map.md)：字段来源与证据等级。
