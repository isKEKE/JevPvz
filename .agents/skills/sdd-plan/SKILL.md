---
name: sdd-plan
description: Create, revise, or approve an SDD Iteration Plan after the user explicitly invokes the planning stage. Do not use for implementation, verification, delivery, or ordinary requirement discussion.
---

# SDD Plan

把当前对话中已经展开的需求固化为可审阅、可实现、可验证的 Iteration
Plan。此 skill 只负责 Plan 阶段；完成后停止。

## 开始前

1. 必须完整读取 `.agents/skills/sdd-memory/SKILL.md`，并在本阶段执行其中的
   **Plan** contract。
2. 读取 `AGENTS.md`、`.memory/context.md`、`.memory/project-map.md`，以及本
   skill 的 `assets/plan-index.md` 和 `assets/plan.md`。
3. 检查相关源码、测试、配置、CI/脚本、相似实现和当前 Git 工作区。规划必须以仓库
   证据为依据，不能只复述用户的自然语言。
4. 把当前对话中的原始需求、约束、已确认选择和待决问题写进 Plan，使后续
   阶段无需依赖聊天记录也能正确执行。

## 定位 Iteration

- 新建：只扫描 `.sdd/` 的直接子目录中符合 Iteration 格式的目录，分配
  `max(existing NNN) + 1`；没有历史目录时从 `001` 开始。目录名称格式为
  `<NNN-short-title>`，其中 short title 是由标题生成、以小写字母开头的简短
  kebab-case slug。编号不得复用或重排。
- 修订或审批：使用用户给出的完整名称或唯一三位编号。若不能唯一定位，先
  询问，不按时间或“最近一次”猜测。
- Iteration 是追加式身份记录；取消时记录状态，不删除目录回收编号。

## 编写与修订

在 `.sdd/<NNN-short-title>/` 创建 `plan-index.md` 和 `plans/` 下一个或多个
具体 Plan。复制本 skill 的 `assets/plan-index.md` 与 `assets/plan.md` 作为
结构来源，仅替换占位符并填写实际内容；不要简化、重排或另行发明 Plan 结构。
默认使用中文。

- `plan-index.md` 是人类阅读入口：写清需求基线、目标、范围、Plan Catalog、
  依赖和执行顺序、跨 Plan 风险与审批状态。
- 每个具体 Plan 保持编号主章节：Metadata、Goal、Scope、Impact Surface、
  Decision、Task、Validation、Risks、Approval。
- 给可验证的原始需求分配 `R1`、`R2` 等 ID，并在 Validation 中将需求、Task、
  验证方法关联起来。不要把只有聊天上下文才知道的信息留在文档之外。
- Impact Surface 必须来自实际仓库检查，列出预期目录、文件、关键 symbol、
  职责和端到端流程；Plan 阶段不展开实现代码。
- 按独立结果或依赖边界拆 Plan，不为形式上的分层制造多余 Plan。
- Task 使用 `[ ] T1` 形式，包含目标、预期影响文件和待回填的 Implementation
  block。验收意图与验证方法放在 Plan/Validation，不在每个 Task 重复。
- Validation 命令从实际 package manifest、构建脚本、CI、测试配置和 README
  中发现并写入 Plan；没有可运行命令时明确记录替代检查，不依赖独立的全局
  validation 文件。
- 不创建 `spec.md`、`implement.md`，不修改生产代码。

## Plan gate

在允许审批前，Plan 必须包含：已检查文件与相似实现、目标与非目标、具体 Plan
拆分、预期新增/修改文件、symbol 级 Impact Surface、端到端流程、明确 Task、
依赖或配置变化、验证命令、风险和 acceptance intent。小改动默认以 1–3 个修改
文件、零新依赖和零无必要抽象为复杂度基线；超出时在 Scope/Risks 中解释。

## Decision 与审批

- 不替用户确认选择。未决项写入 Open Decision，包含问题、背景、选项含义、
  影响、优缺点、建议和需要用户确认的内容。
- 用户给出明确选择后，再次运行本 skill 时把选择移入 Confirmed Decision，
  记录来源、日期和理由，并同步受影响的 Scope、Task、Validation 与 Risks。
- 只有用户明确表示批准且没有阻塞性 Open Decision 时，才把 Iteration 和所有
  具体 Plan 的 Approval 标记为 Approved。任何实质范围修订都会使审批回到
  Pending，直到用户再次批准。

## 完成条件

在最终响应前完成已加载 `sdd-memory` 的 Plan memory contract。

报告创建或修改的 Iteration、Plan 列表、仍开放的 Decision、审批状态和主要
验证路径，然后停止。不要进入 Implementation、Verify 或 Delivery，也不要
执行 Git commit/push。
