---
name: sdd-verify
description: Independently verify one explicitly named implemented SDD Iteration against its requirement baseline, approved Plans, code, and runtime evidence. Do not repair defects or deliver.
---

# SDD Verify

从原始需求与批准的 Plan 反向验证实现是否成立，并把可复查证据写入目标
Iteration 的 `verify.md`。此阶段验证而不修复。

## 前置条件

1. 使用用户提供的完整 Iteration 名称或唯一三位编号定位 `.sdd/` 的直接子目录；不能唯一定位时询问，
   不选择“最近”的 Iteration。
2. 必须完整读取 `.agents/skills/sdd-memory/SKILL.md`，并在本阶段执行其中的
   **Verify** contract。
3. 读取 `AGENTS.md`、`.memory/context.md`、`.memory/project-map.md`、目标
   Plan Index、全部具体 Plan、本 skill 的 `assets/verify.md`、当前 Git diff/status、
   相关实现和测试。
4. Plan 必须已批准。若 Implementation Task 或 backfill 明显未完成，仍可记录
   证据，但总体结果不能是 Passed。

## 独立验证

- 启动一个 fresh-context verifier sub-agent。它不能是先前的 implementation
  worker，也不能再委派。若 provider 不可用，停止并报告，不能由主 agent
  冒充独立验证。
- 给 verifier 的 envelope 包含：准确 Iteration 路径、Plan 中自包含的需求基线、
  当前对话仍提供的原始需求/约束、两个只读 memory 文件、允许写入的唯一 SDD
  文件 `verify.md`、验证命令和禁止修改生产代码/测试/Plan/Project Map 的边界。
- verifier 独立检查需求与 Plan 是否一致、每个 requirement/acceptance 是否有
  实现映射、实际 diff 与 Task backfill 是否一致、异常/边界路径是否覆盖，并运行
  具体 Plan 指定的检查，并从 package manifest、CI、构建脚本、测试配置和 README
  交叉发现缺失的最小充分检查。UI 行为应尽量使用 browser/DOM 证据，而非只读源码。
- 不因现有测试通过就推断需求通过；也不因实现与 Plan 一致就忽略原始需求。
  对每个结论给出文件、symbol、命令输出或手工检查等可定位证据。

## 结论与记录

复制 `assets/verify.md` 的结构生成或更新 `verify.md`，至少包含
requirement/Plan/Task 追踪矩阵、命令与
手工检查、发现的问题、未取得的证据和总体结论：

- `Passed`：所有强制需求和 acceptance 均有充分通过证据，且没有阻塞性偏差。
- `Failed`：发现实现缺陷、需求遗漏、越界变更或可复现失败。
- `Blocked`：由于环境、凭据或外部服务无法取得必要证据；未知不能记作 Passed。

Verify 不修改生产代码、测试或 Plan，不写“Fixes Applied”，不启动 repair，
不执行 Delivery、commit 或 push。主 agent 只审核 verifier 证据的完整性，并在
最终响应前完成已加载 `sdd-memory` 的 Verify memory contract。需要修复时要求
用户之后显式调用 `$sdd-implementation`。
