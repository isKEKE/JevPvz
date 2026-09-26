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

# 输出 JEV 精简字段集；省略 --profile 时仍输出完整 All State
uv run python main.py snapshot --once --profile jev

# 启动本地网页仪表盘
uv run python main.py serve

# 单次语义动作：目标游戏需保持运行；动作消息会定向发送到已校验的目标 HWND
uv run python main.py action --action-json '{"action":"place_plant","card_slot":1,"row":0,"col":0}'
```

打开 <http://127.0.0.1:8765/> 查看状态。主页的“原始 JSON”视图与结构化视图使用同一采样快照。进入 <http://127.0.0.1:8765/state> 后默认查看 JEV State，可切换至完整 All State；复制操作始终对应当前显示的 profile。`/api/state` 保持完整 State，`/api/jev-state` 返回显式 allowlist 投影，两者共享同一个后台采样器。两页的普通导航链接会在当前标签页切换。需要持续输出 JSON 时可运行：

```powershell
uv run python main.py snapshot --interval-ms 500
```

`snapshot --profile all|jev` selects the JSON field profile (default `all`);
both profiles come from one captured sample. JEV State keeps decision-facing
fields but omits field-level `availability`, process identity, raw memory data,
and diagnostic-only details. Missing values remain `null`; All State retains
the complete record, including availability and evidence. JEV zombies carry
their own house-distance fields while lanes contain row/count summaries; JEV
items include their English type name. The `/state` page
shows the selected profile as a collapsible, syntax-styled JSON tree and copies
the selected profile's JSON data.

State JSON uses English identifiers for game labels and entity types; the web
Dashboard maps known identifiers to Chinese for display. Zombie `hp` remains
the body-HP alias, with equipment HP reported separately. Card costs and
cooldown state include evidence limits; unverified cooldown readiness and
uncalibrated lawn distance are not guessed. See [`docs/memory-map.md`](docs/memory-map.md)
for current field evidence and [`docs/architecture.md`](docs/architecture.md)
for the State contract.

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

### 决策侧 ActionBoundary（Python API）

未来的调用者可通过 `actions.ActionBoundary` 将 JEV 可见的语义请求转换成现有 `ActionExecutor` 调用；它不接入 JEV/LLM、策略循环或 HTTP 写接口，也不改变下方的低层 JSON CLI。传入的两个 State 必须来自同一采样：

```python
from actions import ActionBoundary, ActionValidationError
from state.builder import capture_state
from state.projection import project_jev_state

all_state = capture_state()
jev_state = project_jev_state(all_state)
boundary = ActionBoundary()
result = boundary.dispatch(
    {"action": "place_plant", "type_name": "sunflower", "row": 0, "col": 0},
    jev_state=jev_state,
    all_state=all_state,
)
```

接受的语义请求为：

```json
{"action":"place_plant","type_name":"sunflower","row":0,"col":0}
{"action":"collect_item","type_code":4,"type_name":"sun","x":551.0,"y":448.0}
{"action":"shovel_cell","row":0,"col":0}
```

种植只接受当前 JEV `cards` 中唯一匹配且 `usable` 严格为 `true` 的植物，并要求目标 `board.cells[row][col]` 严格为 `null`；JEV 卡槽 0–9 会转换为 Executor 卡槽 1–10。Executor 会在输入前重新核对该卡槽的植物类型，且只有目标格出现新 ID、其 `type_name` 与请求植物一致时才报告成功。收取只使用 JEV 可见的 `type_code`、`type_name`、`x`、`y`，Adapter 必须在同 `sample_sequence` 的 All State 中唯一解析 item ID；JEV 投影仍不包含 ID。铲除只接受 `plant:<type_name>` 格，按 row/col 执行一次原生铲除；叠层格不保证移除某个指定实体。缺字段、未知值、不可用卡牌、空/不可种/占用格、样本序号不一致或目标歧义都会在调用 Executor 前 fail closed；拒绝时抛出 `ActionValidationError`，通过后返回 `ActionExecutor` 的 `ActionResult`。

上述边界只面向未来 Python 调用者；现有 `main.py action` 仍直接接受低层请求（1 基 `card_slot` 或 All State `item_id`），不自动经过 `ActionBoundary`。

## 实机 State 与截图证据

由维护者显式运行采集工具；它不会启动或关闭游戏，也不会调用 LLM。输出目录由调用者指定，内含 JSON 元数据和（有截图的场景）目标游戏窗口 PNG：

```powershell
# 仅在目标格确认为空，且 cost、cooldown_ready、usable 均有 available 证据时执行一次
uv run python tests/capture_live_validation.py plant --card-slot 1 --row 0 --col 0 --output-dir .sdd/004-game-state-observation/evidence

# 固定 10 秒 deadline；仅尝试安全定位且类型码为 4、5、6 的阳光物件
uv run python tests/capture_live_validation.py collect-sun --duration-seconds 10 --output-dir .sdd/004-game-state-observation/evidence

# 对截图前后 State 做稳定字段投影；比较明确排除 items
uv run python tests/capture_live_validation.py current --output-dir .sdd/004-game-state-observation/evidence
```

种植动作后等待 1 秒，再采集 State 与游戏窗口截图。卡槽冷却、空格、费用、余额、状态或身份无法确认时脚本 fail closed 并返回 inconclusive。阳光收集只接受 ActionExecutor 能安全校验的位置，动作超时不大于剩余 10 秒；余额增量必须严格大于 50，且需人工确认没有其他阳光来源。截图由本机目标 HWND 捕获，截图失败不会替换为网页或旧图。

将 JSON 与 PNG 一起交给多模态审阅。种植按“State 植物类型/目标行列、截图观察、结论”逐项报告 match、mismatch 或 not visible。current 场景只审阅截图可见且截图前后相同的字段；字段变化标 sample changed，items 不参与比较。采集状态不等于多模态验收通过。
