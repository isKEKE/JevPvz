---
name: sdd-verify
description: Verify one explicitly named implemented SDD Iteration against its requirement baseline, approved Plans, code, and runtime evidence. Do not repair defects or deliver.
---

# SDD Verify

从原始需求与批准的 Plan 反向验证实现是否成立，并把可复查证据写入目标
Iteration 的 `verify.md`。默认由当前 main agent 执行；此阶段验证而不修复。

## 前置条件

1. 使用用户提供的完整 Iteration 名称或唯一三位编号定位 `.sdd/` 的直接子目录；不能唯一定位时询问，
   不选择“最近”的 Iteration。
2. 必须完整读取 `.agents/skills/sdd-memory/SKILL.md`，并在本阶段执行其中的
   **Verify** contract。
3. 读取 `AGENTS.md`、`.memory/context.md`、`.memory/project-map.md`、目标
   Plan Index、全部具体 Plan、本 skill 的 `assets/verify.md`、当前 Git diff/status、
   相关实现和测试。
4. Plan 必须已批准。若交付本次产物所需的 Implementation Task 或 backfill 明显
   未完成，仍可记录证据，但总体结果不能是 Passed。

## Verification

- 完成需求与 Plan 对照、实现映射、实际 diff/Task backfill、一致性和 G1
  异常/边界路径检查。检查范围、证据标准和结论规则不随执行者改变。
- 对照 package manifest、CI、构建脚本、测试配置和 README，发现可能推翻 G1
  结论的遗漏检查。新检查按其与当前目标的因果关系分级，不能仅因存在检查或
  潜在风险就自动升级为交付门槛。UI 行为应尽量使用 browser/DOM 证据，而非只读源码。
- 对可分解的 G1 检查，分别记录可独立观察的结果和步骤依赖。不能仅因完整门槛
  尚未满足，就跳过其中已获授权且可安全执行的部分；分项通过不降低整体 G1 门槛。
- 不因现有测试通过就推断需求通过；也不因实现与 Plan 一致就忽略原始需求。
  对每个结论给出文件、symbol、命令输出或手工检查等可定位证据。
- 若计划要求运行时或交互检查，记录当前运行环境及可访问状态、检查执行者和已有
  证据。对会改变目标系统状态或产生外部副作用的操作，必须有可追溯的授权来源与
  范围、操作限制及停止/恢复条件。不得从 Plan 标注 Manual、历史操作或禁止修改
  生产代码推断 agent 有权或无权执行动作。授权或安全条件不足时，不执行该操作，
  记录具体原因，并继续其它可独立执行的检查。
- 对操作的限制必须能追溯到当前用户约束、批准的 Plan、本 skill 或具体安全边界；
  不得自行添加笼统的只读限制。

## 分级与 Human 裁定

- `G1 核心路径`：直接影响本次目标或结果可信度。完成最小充分验证；实际失败
  是交付失败，必要证据无法取得是阻塞。Human 亲自完成的手工验证可作为证据，
  记录检查范围、操作/观察结果、来源和日期；不因当前执行者未重复操作就否认它。
  若它与其他证据冲突，先定位冲突，不能直接把失败改写为通过。
- `G2 当前风险`：保留检查的真实结果、影响范围和证据。已发现问题或未执行的
  检查可以由 Human 明确接受或暂缓，并记录决定、理由及适用边界；接受风险不
  等于声称检查通过。若没有预先批准的暂缓条件，也没有明确的 Human 裁定，
  不得自行假定当前相关风险已被接受。若裁定是总体结论的唯一待决条件，先保留
  `Not run` 草稿并请 Human 决定，不把 G2 未决项误写为 G1 的 `Blocked`。
- `G3 后续场景`：Plan 已明确排除在当前用途之外时，可记为 `Deferred`，附
  理由和未来重查条件；无需为了达到百分之百覆盖而运行。发现其实际影响 G1 时
  必须重新评估，不能沿用 G3 定级。
- 判断级别时以本次产物的用途和可证明的影响路径为准。仅有未来多人使用、长期
  部署或其他非本次场景的可能性，不构成当前阻塞。对 Plan 中误列为门槛的检查，
  Human 可明确裁定其对本次交付不适用或接受剩余风险；在 `verify.md` 记录原级别、
  新判断、依据、决定来源及范围，不修改 Plan 或抹去原始发现。这是本次交付的
  例外记录，不自动改变未来 Iteration 的需求基线。已观察到的核心目标失败不能
  仅靠接受风险改写为 Passed。
- 旧 Plan 没有 G1/G2/G3 标记时，先从原始需求、批准的 Goal/Scope 和当前用途
  重建交付边界；原有 `Mandatory` 需求先按 G1 审视，其余检查按影响路径分级。
  Human 对误设门槛的明确裁定按上述例外规则记录，不能因缺少新模板字段就默认
  所有旧检查都阻塞交付。

## 执行完整性与缺证据归因

- 执行完整性与产品结论分开记录。`Complete` 表示每项适用的 G1 检查均已执行，
  或有可接受的替代/Human 证据；不能执行的检查有具体、合理的限制说明。
  `Incomplete` 表示仍有可执行且已获授权的 G1 检查，因执行遗漏、误解或自加限制
  而未执行。后者是流程问题，不是产品失败。
- 每项 G1 `Not run` 都要注明原因类别和证据缺口。因检查遗漏而未运行的项目，标为
  Verify 执行遗漏，写明来源及影响；不能归因于 Verify 规则、外部环境或产品缺陷。
  补做遗漏检查前不能判为 Passed。
- G1 必要证据未取得且无替代证据时，总体结果为 `Blocked`。注明原因属于外部
  条件、授权/安全边界或 Verify 执行遗漏；流程遗漏同时标记执行完整性为
  `Incomplete`。这些原因都不自动证明产品失败。G2/G3 未知或未运行本身不构成
  总体 `Blocked`。

## 结论与记录

复制 `assets/verify.md` 的结构生成或更新 `verify.md`，至少包含
requirement/Plan/Task 与检查 ID 的追踪矩阵、各项真实结果及处置、命令与手工
检查、Human 裁定、发现的问题、未取得的证据和总体结论：

- `Passed`：本次交付的 G1 需求和核心路径有充分通过证据，没有影响核心目标的
  失败或阻塞；G2 问题已按批准条件或 Human 裁定接受，G3 暂缓项已记录。
- `Failed`：核心目标存在可复现的实现缺陷、需求遗漏或其他实质偏差。
- `Blocked`：G1 必要证据未取得，且没有可用的替代或 Human 手工证据。按
  **执行完整性与缺证据归因**记录具体原因；G2/G3 的未知或未运行本身不构成
  Blocked。

每项检查分别记录观察结果与交付处置；`Failed`、`Not run` 或 `Deferred` 的
单项检查不得伪写成通过。总体 `Passed` 可以带有明确记录的非核心保留项。

Verify 不修改生产代码、测试或 Plan，不写“Fixes Applied”，不启动 repair，
不执行 Delivery、commit 或 push。主 agent 负责最终 `verify.md` 和 memory
contract。需要修复时要求用户之后显式调用 `$sdd-implementation`。
