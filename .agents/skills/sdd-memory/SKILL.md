---
name: sdd-memory
description: Maintain the repository-scoped SDD context and project map when loaded by an SDD stage or explicitly requested. Defines schemas, ownership, pruning, and stage-specific update rules.
---

# SDD Memory

统一维护根目录 `.memory/context.md` 与 `.memory/project-map.md`。这两个文件用于
跨 Session 恢复必要上下文，但不是代码、Git 或 Iteration artifact 的事实权威；
内容与仓库证据冲突时，以当前仓库和对应 Iteration 为准。

SDD stage 在读取或写入任一 memory 文件前，必须完整读取本 skill。所有 memory
写入由主 agent 完成；delegated implementation/verifier agent 只能读取，不能并发修改。

## Context schema

`.memory/context.md` 固定保留以下标题，按需在标题下填写：

1. `Current Focus`：当前唯一主要目标；没有时写 `None`。
2. `Active Iteration`：Iteration ID、当前 stage、状态和一句话目标；没有时写
   `None`。
3. `Open Decisions and Blockers`：只保留仍未解决且会影响下一步的事项；记录
   Decision/issue ID（若有）、责任方和解除条件。解决后立即删除；没有时写
   `None`。
4. `Recent Activity`：按时间倒序保留最多八条。每条使用
   `YYYY-MM-DD — <stage/direct>: <outcome>; <evidence>`，只写可帮助下一
   Session 接手的结果，不复制完整日志、diff、Plan 或 Verify 内容。
5. `Next Action`：只写下一项可执行动作及其前置条件；没有时写 `None`。

每次更新都要合并重复事件、删除已解决或被新事实取代的内容，并把 Recent
Activity 裁剪到八条。不得写入密钥、凭据、个人数据、长日志、推测或只有当前
聊天才能解释的代词。

## Project Map schema

`.memory/project-map.md` 只描述当前已实现的仓库状态：

1. `Technology Stack`：使用 `Area | Technology | Purpose` 表格，仅列能从
   manifest、配置、源码或构建脚本确认的技术。
2. `Directory Tree`：使用精简的 fenced `text` tree，覆盖重要源码、测试、
   配置、文档和自动化入口；忽略 vendor、依赖缓存、构建产物和普通临时文件。
3. `Path Descriptions`：使用 `Path | Description` 表格，为 tree 中需要解释的
   目录或关键文件写一句职责说明。

不得把计划新增但尚未存在的文件、猜测的技术、逐文件实现细节、临时工作区状态
或 Iteration 进度写入 Project Map。更新时做最小事实修正，保留仍准确的内容；
删除已不存在的路径和已移除的技术。

## Stage contracts

### Plan

- 读取两个 memory 文件。
- 探索仓库时校对 Project Map；首次为空时按当前仓库初始化。只写当前事实，不写
  本 Plan 的预期结构。
- 更新 Context 的 active Iteration、Plan 状态、未决 Decision、blocker 和 next
  action；写入一条 Plan activity。

### Implementation

- Delegated Implementation agent 只读两个 memory 文件；主 agent 独占写入。
- 只有实现 acceptance 完成后，才按实际新增、删除、移动的结构及真实技术变化
  更新 Project Map；失败或未完成的计划内容不得进入地图。
- 每个 terminal outcome 都更新 Context 的完成 Task、实际变更摘要、测试结果、
  blocker 和 next action，并写入一条 Implementation activity。

### Verify

- Verify 阶段把 Project Map 当作只读输入；delegated verifier 同样只读。地图与仓库不一致时，将其
  写入 `verify.md` 的 issue/missing evidence，不在 Verify 阶段修正地图。
- Verify 结论确定后，由主 agent 更新 Context 的 Passed/Failed/Blocked、关键发现、
  blocker 和 next action，并写入一条 Verify activity。

### Delivery

- 在 commit 前按已验证的实际仓库最终对账 Project Map。
- 在 Context 中关闭已交付 Iteration，保留仍有效风险/follow-up，设置下一动作并
  写入一条 Delivery activity。
- 将本次相关 memory 变更与 Delivery 一起纳入 Iteration commit。push 失败时，
  Context 可记录精确重试 blocker；若该记录发生在 commit 后，明确它尚未提交。

### Direct non-SDD task

仅当直接任务实质改变技术栈、目录结构或 SDD 运行状态时加载本 skill：按实际结果
更新 Project Map，并在 Context 写入一条 `direct` activity。普通代码细节或无
结构变化的小修改不需要制造 memory 噪音。

## Completion check

写入后确认：两个文件仍保留规定标题；Context 最多八条 activity 且无已解决事项；
Project Map 只含当前事实；没有 delegated agent 写入冲突。最终响应只需概括 memory
变化，不复制全文。
