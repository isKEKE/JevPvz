---
name: sdd-implementation
description: Implement one explicitly named and approved SDD Iteration through bounded implementation sub-agents and acceptance checks. Do not perform independent verification, delivery, commit, or push.
---

# SDD Implementation

根据已批准的具体 Plan 执行实现、测试和实现验收。用户调用本 skill 即授权启动
实现 sub-agent，但不授权扩大 Plan 范围。完成实现验收后停止。

## 前置条件

1. 用用户给出的完整 Iteration 名称或唯一三位编号定位 `.sdd/` 的直接子目录；不能唯一定位时
   询问，绝不按最近时间猜测。
2. 必须完整读取 `.agents/skills/sdd-memory/SKILL.md`，并在本阶段执行其中的
   **Implementation** contract。
3. 读取 `AGENTS.md`、`.memory/context.md`、`.memory/project-map.md`、目标
   `plan-index.md`、全部相关具体 Plan、当前 Git 状态以及受影响源码和测试。
4. 要求 Iteration 与相关 Plan 已 Approved，阻塞性 Open Decision 已解决。
   缺少批准、Plan 自相矛盾或实现需要扩展范围时，停止并返回 Human Review。
5. 必须完整读取 [实施编排规则](references/orchestration.md) 后再派发 worker。

## 执行边界

- 主 agent 负责分解、派发、等待和实现验收，不直接编写生产 Task。
- 使用平台原生 sub-agent；不得创建用户可见的新 task/thread。没有可用的
  sub-agent provider 时停止，不在主 agent 静默降级实现。
- 耦合工作使用一个 worker；只有依赖独立且写文件不重叠的工作流才并行。
- 每个 worker 仅修改被分配的源码、测试和其拥有的具体 Plan Task backfill。
  worker 必须编写/运行 Plan 要求的 unit/targeted tests，并报告证据。
- 实现中的测试和主 agent acceptance 属于 Implementation，不得写 `verify.md`
  或宣称正式 Verify 已通过。
- 不创建 `implement.md`，不执行 Delivery、Git commit 或 Git push。

## 完成条件

当所有已批准 Task 均完成、checkbox/backfill/实际文件/Validation evidence 已同步，
且最小确定性 acceptance checks 通过时，报告实现结果、变更文件、测试证据、
偏差与剩余风险，然后停止。正式验证必须由之后显式调用的 `$sdd-verify` 完成。

在最终响应前完成已加载 `sdd-memory` 的 Implementation memory contract。
