# JevPvz

Windows 下《植物大战僵尸》1.0.0.1051 的状态监视器与受控界面动作执行器：读取游戏进程内存，提供 JSON 输出、本地网页仪表盘，以及按语义请求执行的鼠标动作。

> 仅支持 `1.0.0.1051` x86 版本。内存接口保持只读；`action` 会在严格窗口检查后向目标 HWND 投递鼠标消息。游戏可在后台运行，执行器不会激活游戏或改变前台焦点。

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

# 单次语义动作：目标游戏需保持运行；动作消息会定向发送到已校验的目标 HWND
uv run python main.py action --action-json '{"action":"place_plant","card_slot":1,"row":0,"col":0}'
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

## 语义动作

`action` 每次只接收一个 JSON 对象，并输出一条 JSON 结果。动作参数只使用卡槽、行列或当前 State 中的 item ID，不接受调用者传入屏幕坐标：

```powershell
# 卡槽 1–10；row 为 0–4，col 为 0–8。放置后等待 State 确认新植物 ID；不检查或等待冷却。
uv run python main.py action --action-json '{"action":"place_plant","card_slot":1,"row":0,"col":0}'

# 将 3748399104 替换为当前 State.items 中的 ID；仅在候选坐标明确且映射有效时点击。
uv run python main.py action --action-json '{"action":"collect_item","item_id":3748399104,"timeout_ms":10000}'

# 每次只对该格执行一次原生铲除；仍有植物时由调用者再次明确请求。
uv run python main.py action --action-json '{"action":"shovel_cell","row":0,"col":0,"timeout_ms":10000}'
```

可配置项为 `timeout_ms`（点击后的 State 等待，100–120000 毫秒）和 `poll_interval_ms`（50–2000 毫秒），默认值分别为 10000 和 250 毫秒。种植不读取或等待卡槽冷却字段。输出 `status` 只有 `rejected`、`success`、`unverified`：只有 State 确认对应变化才是 `success`。退出码为 success `0`、rejected `2`、unverified `3`。

执行前由 Human 启动 PvZ 并确保目标游戏保持运行。V01 实机验收另由 Human 准备游戏在后台继续运行且不暂停、冻结僵尸、提供充足阳光并选好十张适用卡，同时让另一个非目标窗口保持前台；僵尸冻结是这项验收的准备条件，不是每个独立动作的前置条件。执行器验证固定程序身份、唯一可见且启用的 HWND、800×600 客户区、96 DPI 与单主显示器；每次点击前再次确认同一目标 PID/HWND 和窗口布局，并通过 `PostMessageW` 将客户区鼠标消息直接投递给目标 HWND。游戏可保持后台运行；执行器不会激活游戏或改变前台焦点。身份变化、布局不匹配或 State 证据不足时不发起后续输入。执行器不检查阳光余额/费用，也不选择植物与格子的策略；不会自动重试已发送但尚未确认的动作。

掉落物坐标目前仍是 State 的候选证据，须有有限、唯一可解释且落在支持范围内的坐标，否则拒绝点击。卡槽冷却字段不作为种植门槛。`shovel_cell` 每次只做一次原生铲除并返回实际消失的植物 ID，不承诺选择叠层中的某一株。窗口坐标只支持配置的固定布局；其他尺寸、缩放或多显示器布局会被拒绝。
