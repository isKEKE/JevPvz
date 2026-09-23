# Implementation orchestration

## Assignment map

派发前读取 Plan Catalog、Task 依赖与 Impact Surface，并为每个 worker 列出：

- 独占的 Plan/Task ID 与允许写入的文件；
- 结果、验收检查、依赖和不得修改的边界；
- task width、effort、局部预算与剩余全局预算；
- 需要读取的仓库事实、关键 symbol 和聚焦验证命令。

同一 Plan、同一写文件或存在依赖的 Task 必须交给同一 worker 或按 wave 串行。
在四槽环境中为主 agent 保留一槽，最多并发三个 worker。

## Worker isolation

- worker 使用 fresh context，不继承主对话；默认继承当前 model，不得自行更换
  provider/model。
- narrow/standard worker 默认 `medium`；广泛跨文件、困难调试或已失败的窄化
  repair 才使用 `high`。`max` 仅在用户明确覆盖或记录充分例外时使用。
- worker 自行读取仓库 `AGENTS.md`、只读的 `.memory/context.md` 与
  `.memory/project-map.md`、Plan Index、分配的 concrete Plan、Git 状态和相关
  源码/测试。实现 envelope 只是定位信息。两个 memory 文件始终由主 agent 独占。
- worker 不得继续委派或启动 sub-agent。

默认局部上限：

| Scope | Effort | maxTurns | maxWallTime | maxCost |
|---|---:|---:|---:|---:|
| Narrow/standard | medium | 20 | 10 minutes | USD 0.02 |
| Broad/debug/repair | high | 20 | 15 minutes | USD 0.04 |

运行时不能提供 cost telemetry 时记录 `unknown`，不能当作零成本；仍执行 turn 与
wall-time 上限。

## Global limits and waiting

一次 Implementation 最多三个 dispatch waves（初始 wave 加两个 repair waves）、
30 分钟、总成本 USD 0.10。派发前按 worker 最坏局部成本预留，不能启动会超过
剩余全局预算的 wave。

成功创建本 wave 的全部 worker 后，主 agent 立即进入静默等待，不运行命令、
检查 diff 或把正常 running 当作异常。仅在全部 worker 结束、某 worker 失败或
请求关注、或用户发来新消息时恢复实质处理。无变化的 wait timeout 只需重新
等待，不输出进度噪音。

## Worker result contract

worker 只能处理其 assignment，并且必须：

1. 未完成时保持 Task `[ ]`；完成后改为 `[x]`。
2. 回填 Implementation notes 与 Actual/Changed files。
3. 在 Plan Validation 中记录关联 Task ID 的命令、结果和证据。
4. 报告变更文件、验证结果、风险、阻塞，以及可观测的 turns/time/cost。

## Acceptance and repair

worker 全部结束后，主 agent 检查组合 diff 的范围、文件冲突、Plan invariants 与
证据，并只运行判断 Task 所需的最小确定性检查。

失败项必须先分类：

- **Implementation defect**：派发窄化 repair，只描述失败证据、单一待修行为、
  通过条件和不得改变的内容。
- **Plan contradiction / ambiguity / scope expansion**：停止并交回 Human Review。
- **Provider / infrastructure / budget**：停止并报告操作性阻塞与用量。

禁止用“再试一次”“继续”或原始宽任务作为 repair prompt。首次窄化 repair 可在
路线正确时复用原 worker；同一 acceptance item 第二次失败必须使用 fresh worker
和 `high` effort。达到第三个 wave 或任一全局上限后停止，不延长预算。
