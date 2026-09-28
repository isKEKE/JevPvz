# 详细使用说明

Windows 下《植物大战僵尸》1.0.0.1051 的状态监视、受控界面动作执行，以及基于 TypeSafe JEV 的异步决策循环：读取游戏进程内存得到标准化 State，可选地由 JEV 分支决策并在严格校验后执行鼠标动作，全程可落盘为 JSONL Trace 并在本机网页仪表盘复核。

> 仅支持 `1.0.0.1051` x86 版本。内存接口保持只读；`action` 与 `jev-loop` 会在严格窗口检查后向目标 HWND 投递鼠标消息，也就是**会真的操作游戏**。游戏可在后台运行，执行器不会激活游戏或改变前台焦点。

## 快速开始

1. **装环境**：Windows、Python 3.12.13、[uv](https://docs.astral.sh/uv/)。
2. **装依赖**：

   ```powershell
   uv sync
   ```

3. **放好并启动游戏**：目标程序为 `.game/PlantsVsZombies.exe`（该目录已被 Git 忽略）。版本与 SHA-256 必须与 `configs/pvz_1051.py` 中的锁定值完全匹配；不匹配时命令会直接报身份错误，不会继续读取。**先启动游戏**再运行下面的命令，并保持它运行且未暂停。
4. **按用途选一条命令**（详见下方「命令一览」）。只读观察不需要任何凭据；`jev-loop` 额外需要 `.env`（见「JEV 决策循环」）。

```powershell
uv run python main.py probe                                   # 校验身份并读一次
uv run python main.py snapshot --once                          # 看一次 State
uv run python main.py serve                                    # 开网页仪表盘
```

## 命令一览

| 命令 | 作用 | 需要 `.env` | 会操作游戏 |
|---|---|---|---|
| `probe` | 校验目标进程与可执行身份，输出一次原始读取结果 | 否 | 否 |
| `snapshot` | 输出一次或持续输出标准化 State JSON | 否 | 否 |
| `serve` | 启动本机只读仪表盘（状态页与 JEV 时间线页） | 否 | 否 |
| `action` | 按一个语义 JSON 请求执行**一次**界面动作 | 否 | **是** |
| `jev-loop` | 运行 TypeSafe JEV 异步决策循环并执行动作 | **是** | **是** |

## 前置条件

- Windows
- Python 3.12.13
- [uv](https://docs.astral.sh/uv/)
- 目标程序：`.game/PlantsVsZombies.exe`

目标程序需要与配置中的版本和 SHA-256 完全匹配；`.game/` 已被 Git 忽略。

`jev-loop` 还需要项目根目录下的 `.env`，其中必须提供 `TYPESAFE_API_KEY`、`HTTP_PROXY` 与 `HTTPS_PROXY`；**两个代理必须同时配置**，只配一个会在启动时失败并返回退出码 2，此时不会创建 Trace、不会发请求、也不会进入错误重试。

## 观察状态

```powershell
# 检查目标进程并输出一次原始读取结果
uv run python main.py probe

# 输出一次标准化状态 JSON
uv run python main.py snapshot --once

# 输出 JEV 精简字段集；省略 --profile 时仍输出完整 All State
uv run python main.py snapshot --once --profile jev

# 需要持续输出 JSON 时（间隔不低于 50 毫秒）
uv run python main.py snapshot --interval-ms 500
```

`snapshot --profile all|jev` 选择 JSON 字段集（默认 `all`），两个 profile 都来自**同一次**采样。JEV State 保留决策相关字段，但省略字段级 `availability`、进程身份、原始内存数据与仅供诊断的细节；缺失值一律为 `null`。All State 保留完整记录，含 availability 与 evidence。JEV zombies 自带房屋距离字段，lanes 提供按行的数量摘要；JEV items 带英文类型名。

State JSON 的游戏标签与实体类型使用英文标识；网页仪表盘会把已知标识映射为中文显示。Zombie `hp` 是 body-HP 的别名，装备 HP 单独报告。卡牌费用与冷却状态带有 evidence 限制；未经验证的冷却就绪状态与未标定的草坪距离不会被猜测。当前字段证据见 [`memory-map.md`](memory-map.md)，State 契约见 [`architecture.md`](architecture.md)。

## 网页仪表盘

```powershell
uv run python main.py serve
```

打开 <http://127.0.0.1:8765/> 查看状态。主页的“原始 JSON”视图与结构化视图使用同一采样快照。`/state` 页默认查看 JEV State，可切换至完整 All State；复制操作始终对应当前显示的 profile，并以可折叠、带语法着色的 JSON 树呈现。两页的普通导航链接会在当前标签页切换。`/api/state` 保持完整 State，`/api/jev-state` 返回显式 allowlist 投影，两者共享同一个后台采样器。

`/jev` 页只读呈现 JEV Trace 时间线，**不会**启动或停止 Loop、也不会发送游戏输入；它只显示显式配置的 Trace 路径，不接受通过 HTTP 参数指定任意路径。

## 语义动作（会操作游戏）

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

## JEV 决策循环（会操作游戏）

先启动受支持的 PvZ 对局，并在项目 `.env` 中配置 `TYPESAFE_API_KEY`、`HTTP_PROXY` 和 `HTTPS_PROXY`（**三者都必需，两个代理缺一即启动失败**）。三个决策门槛可独立配置；未设置或留空时分别默认为 `0.6`：

```dotenv
JEV_NOUL_CANDIDATE_THRESHOLD=0.6
JEV_ROUTER_CONFIDENCE_THRESHOLD=0.6
JEV_ACTION_CONFIDENCE_THRESHOLD=0.6
```

它们分别控制 Noul 候选线、Router Choice 置信度和 Action Choice 置信度（后两者只作用于 P02 的历史同步 Router/Action 路径；当前异步 Runtime 的目标 Choice 取 argmax、不使用 confidence 门槛），取值范围为 `0` 到 `1`。调整其中一项不会改变另外两项。Loop 使用官方 TypeSafe SDK；只读取 `.env` 变量，不在控制台或 Trace 输出密钥。`python-dotenv` 不覆盖已设置的进程环境变量，SDK HTTP transport 使用环境代理。

```powershell
# 默认无限运行：持续观察且不加任何固定等待
$trace = ".log/test_05.jsonl"
uv run python main.py jev-loop --trace-file $trace

# 可选：只给观察限速（250 ms 最小观察间隔），不影响 JEV 请求节奏
uv run python main.py jev-loop --interval-ms 250 --trace-file $trace

# 可选：以「已终结的 DecisionJob」数收尾
uv run python main.py jev-loop --max-cycles 20 --trace-file $trace

# 在另一个终端显式配置 Dashboard 读取同一份 Trace
uv run python main.py serve --jev-trace-file $trace
```

Runtime 默认持续观察：每次采样完成立刻继续，不加 100 ms/5 s 固定等待。`--interval-ms` 是可选的**观察限速**：省略或传 `0` 表示不引入额外观察等待；正整数值只限制观察的最小开始间隔（用 monotonic 计时，耗时已超间隔则不补睡，也不在 JEV 请求返回后再睡同样时长）；负值或非整数值属于启动失败，直接以退出码 2 结束，不会创建 Trace、不会发请求、也不会进入错误重试。网络超时仍由 SDK 配置决定，采样间隔不控制网络超时。

两个 worker 共用单执行器。收集 worker 的 shared 请求同时询问是否收集、建设意图（保持/替换/取消）与下一建设类型，空 items 仍可判断经营。输入只含当前事实、实际余额/卡牌、计数、能力、模型意图与最近实际结果，不预给阵容方案、规模或布局；其中 `lane_composition` 是每行的己方构成计数（`resource`/`attacker`/`defender`，空行显式为 0，`plants` 不可用时整字段为 null），`board.column_direction` 只陈述列方向事实（列 0 = 房屋侧，最高列 = 僵尸来向，与 executor 的 `first_cell_center + col * horizontal_spacing` 几何一致），`cards[].role` 取自目录、未知为 null —— 三者都只是事实与语义，不含推荐、配额或布局答案。收集只用一个 typed Noul，模型只见物品类型/代码/数量；肯定回答授权来源样本冻结的全部有效 ID，本地逐件经 Boundary 按 ID 校验，Executor 获取即时坐标。新 ID 必须重新询问。若肯定回答在上一批仍在消费时到达，它保存为**一份 latest 未授权批**（后到覆盖先到）；当前批结束/取消/过期后按同一条 5 s 授权时效（自**被接受**时刻起算，不因出队或等待续期）消费，已消费/已完成的 ID 不再被选，超过时效或被他批覆盖都有丢弃记录，绝不静默丢失。PlantBranch 只问一个完整合法目标 Choice，由模型自己的弃选项（`none_of_the_above`）表达「不动手」，**没有绝对闸门、没有 confidence 门槛**，代码不重排、不替换目标。Choice 使用 argmax；收集 Noul 使用 `questions.py` 的显式锚点 `COLLECT_ACT_THRESHOLD = 0.5`，与 P02 的 `JEV_NOUL_CANDIDATE_THRESHOLD` 解耦。保留来源意图版本、真实预算/卡牌/位置、TTL、身份、停止与完整动作确认守卫；不预留阳光或预测收入。

Trace 是 **schema v2** 的 JSONL 运行时事件：`job_start`、`request_result`、`proposal_discarded`、`action_result`、`job_end`、`runtime_stop`，由单一 writer 写出且 `event_sequence` 单调递增，用 `job_id`/`request_id`/`stage_id`/`execution_id`/`branch_id` 关联。每个任务记录样本年龄、API 延迟、排队时间、wait/discard 原因，以及**一次请求内的原子答案**（收集 `should_collect_now` 概率、目标 Choice 的完整分布）与**代码合并结论**（plant 的 `best_option`/`best_probability`/`discard_probability`/`margin`/`chosen_option`/`selected_option`/`target_choice_rule`，collect 的 `should_collect_probability`/`authorized_count`），用于复核「为什么动手或不动手」；它按任务写入，不为每个高频 observation 落盘，也不写原始 All State、原始 SDK 响应或凭据。Dashboard 同时识别旧 v1 周期文件与新 v2 事件文件：v1 仍按周期时间线呈现，v2 按分支/请求/执行事件呈现，并分别显示**决策完成顺序**与**实际执行顺序**（两者可能不同）；旧 v1 cycle 不会被伪装成分支事件。

停止语义：暂停、关卡结束、目标进程退出/状态断连、连续三轮「重试预算耗尽的错误 job」、`--max-cycles` 达成、Ctrl+C 或 Trace 写入失败都会先关闭提交与派发闸门，作废在途 job 与 pending proposal；迟到回答不再派发，停止后零新请求，每个已启动的 job 都会写出 terminal/cancelled 的 `job_end`（停止时仍未处理的 proposal 记在 `runtime_stop.pending_proposals`）。正常 skip 与 `model_wait` 不计入错误。

每次 Loop 都必须显式指定 `--trace-file`。若路径已有本应用的 JEV Trace（v1 或 v2），启动时会清空旧内容并写入新 run；这会丢失该路径之前的运行历史。若需要保留历史，请使用新路径。若路径指向非 Trace 文件、目录或符号链接，程序会拒绝覆盖并给出具体提示。Dashboard 只在显式设置相同的 `--jev-trace-file` 后显示该文件最近 100 个完整事件，且**不会**通过 HTTP 参数读取任意路径。Loop 与 Dashboard 可在不同终端独立运行。

省略 `--max-cycles` 时 Loop 不设上限，会持续运行直到上述停止条件之一。需要有界演示或检查时才传入 `--max-cycles N`：它计的是**已终结的 DecisionJob** 数（观察、请求、动作分别统计，不参与该上限）。收尾时 stdout 单独输出四类计数，便于区分采样、请求与真实动作：

```json
{"status":"stopped","observations":412,"requests":37,"actions":9,"terminated_jobs":31}
```

## Python API：决策侧 ActionBoundary

调用者可通过 `actions.ActionBoundary` 将 JEV 可见的语义请求转换成现有 `ActionExecutor` 调用；它不接入 JEV/LLM、策略循环或 HTTP 写接口，也不改变低层 JSON CLI。传入的两个 State 必须来自同一采样：

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

上述边界面向 Python 调用者；`main.py action` 仍直接接受低层请求（1 基 `card_slot` 或 All State `item_id`），不自动经过 `ActionBoundary`。

## 测试

```powershell
uv run python -m unittest discover -s tests -p "test_*.py"
```

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

## 相关文档

- [`architecture.md`](architecture.md)：当前架构、State 契约、Runtime 与 Trace 职责划分。
- [`memory-map.md`](memory-map.md)：内存字段与当前证据等级。
