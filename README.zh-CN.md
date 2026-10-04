# JevPvz

[English](README.md) | 简体中文

在 Windows 上读取《植物大战僵尸》状态、查看本机仪表盘，并可通过语义动作或 TypeSafe JEV 决策循环操作游戏。

**建议先读 [JEV 能力报告](docs/jev-capability-analysis.md)。** 它讲清楚了实机对局测出了什么、策略卡在哪里，以及 JEV 在整套系统中的位置。之后再按本 README 配置和运行项目。

> 仅支持 x86 版 Plants vs. Zombies `1.0.0.1051`，程序身份须与 `configs/pvz_1051.py` 的版本和 SHA-256 一致。`action`、`jev-loop` 和 JEV Runtime 的 START **会操作游戏**；状态观察页面仍只读。游戏可以在后台运行。

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
| `serve` | 启动本机状态页和 JEV Runtime 控制台 | 仅使用 START 时需要 | **通过 JEV Runtime START** |
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

直接运行 `uv run python main.py serve` 打开草坪主页，主页**内嵌 JEV Runtime HUD**，便于与游戏同屏录制；`/jev` 仍然提供同一 HUD 的独立页面。HUD 是霓虹科技风面板，除无障碍标签外不含文字：青色 ▶ 启动、洋红 ■ 强制结束，无状态文案（面板状态决定哪个按钮点亮）。游戏已连接并处于进行中时，START 启动一个 `jev-loop` 子进程；STOP 强制结束该子进程。第一个 Loop 未退出前，网页或命令行都不能启动第二个。暂停、关卡结束或离开游戏时，Loop 按原有规则自动停止。点阵按左右关系画成一张决策网络：左侧是由本周期实际问了哪些分支推导出的意图层（收集/种植/取消，进入的分支点亮），中间是连线，右侧是具体目标。收集层平铺本局该问题最近一次请求的**全部 option**（一个 option 一个点，点数随可收项动态变化）；种植层是**固定的 5×9 草坪矩阵**，45 格始终存在，只有被证实种植到该格的候选才点亮。页面不显示文字标签，每个节点与格子都用鼠标悬停/键盘焦点读出名称。只有摘要证明该 option 真的执行时才亮：`action_result` 与组内最新请求同源 `job_id`、`boundary.status == success`，且目标精确对应到该 option（成功种植的类型与行列，或成功收集对应的 `should_collect_now: true`）；已证实执行的点与格在本局内**一直保持点亮**，即使该问题被重新提问。失败、未确认、作废、仅模型选中以及旧 job 迟到的动作都保持暗点，`construction_intent` 等经营选择永不点亮，证据缺失一律显示暗点而不推断；模型概率不代表执行。新一局会清空旧点，刷新页面时由摘要恢复本局状态。历史 schema v1 Trace 没有完整问题 option，页面只给兼容提示，不伪造点。主页同步调整：僵尸行摘要跨整行，每只僵尸只显示名称、位置与血量；卡牌槽只有名称居中、下方一条由卡牌自身冷却计数驱动的进度条（就绪满格、冷却中按进度、状态未知为不确定）以及右下角的纯数值费用，宽屏一行放下全部十张。页面不再出现英文小标题与页脚注释，统一中文。网页 START 与命令行一样需要配置 `.env`；进程输出保存在 `.log/jev-dashboard-process.log`。

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

离线重放一份冻结的 schema-2 Trace：重建其中一次 plant 决策，对照「旧规则只留目标类型」与「新规则目标为上下文 + surplus」的候选。只读，不调模型、不访问游戏。

```powershell
uv run python tools/evidence-plan-economy.py --trace-file .log/jev-dashboard.jsonl
```

- [JEV 能力报告](docs/jev-capability-analysis.md)：实机实验的发现与边界，建议优先阅读。
- [详细使用说明](docs/usage.md)：状态观察、仪表盘、动作、JEV、Python API 与实机验收。
- [架构文档](docs/architecture.md)：模块职责、State 契约及 Runtime。
- [内存字段文档](docs/memory-map.md)：字段来源与证据等级。

## 许可证与使用边界

本项目以源码公开形式发布，采用 [PolyForm Noncommercial License 1.0.0](LICENSE)。

允许在许可证规定的用途范围内使用、学习、修改和分发本项目，包括非商业用途。商业用途不在本许可证的授权范围内。分发时须保留许可证文本或链接，以及规定的版权通知。具体授权条件以 `LICENSE` 完整正文为准。

本项目包含游戏进程内存读取与自动操作功能。使用者应自行合法取得游戏，并确认其使用方式符合适用法律及游戏相关条款。本仓库不提供游戏程序。

本项目许可证仅适用于作者有权许可的项目内容，不授予游戏本体、素材、商标或第三方组件的权利；第三方内容继续适用各自的许可。
