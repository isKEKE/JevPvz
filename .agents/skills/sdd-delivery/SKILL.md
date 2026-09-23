---
name: sdd-delivery
description: Deliver one explicitly named SDD Iteration whose formal verification passed by writing the delivery report, committing only in-scope changes, and pushing the current branch. Do not plan, implement, or repair.
---

# SDD Delivery

为已经正式验证通过的 Iteration 生成交付记录，并将属于该 Iteration 的变更安全地
commit、push。用户显式调用本 skill 即授权这两项 Git 操作，但不授权 force push
或夹带无关变更。

## 交付门槛

1. 用完整 Iteration 名称或唯一三位编号定位 `.sdd/` 的直接子目录；不能唯一定位时询问，不按最近时间
   猜测。
2. 必须完整读取 `.agents/skills/sdd-memory/SKILL.md`，并在本阶段执行其中的
   **Delivery** contract。
3. 读取 `AGENTS.md`、`.memory/context.md`、`.memory/project-map.md`、目标
   Plan Index、具体 Plans、`verify.md`、本 skill 的 `assets/delivery.md`、Git status/diff、当前
   分支与 remote/upstream。
4. 只有 `verify.md` 的总体结论明确为 `Passed` 才能继续。`Failed`、`Blocked`、
   缺失或证据自相矛盾都必须停止；Delivery 不补做 Verify 或修复。
5. 区分 Iteration 变更与既有/无关工作区变更。无法安全区分时，在 stage/commit
   之前停止并请用户决定；绝不 stash、丢弃或提交无关内容。

## Delivery 文档

复制本 skill 的 `assets/delivery.md` 结构创建或更新目标 `delivery.md`，记录：

- 已交付目标、完成与未完成的 Plan/Task；
- 实际变更文件和行为；
- Verify 结论及证据入口；
- 相对批准 Plan 的偏差；
- 已知风险与后续事项；
- 当前分支、提交类型和计划使用的 commit subject。

如果存在未完成项，明确写出；若它与 Passed 结论冲突则停止，不得交付。

在 stage/commit 之前完成已加载 `sdd-memory` 的 Delivery memory contract。

## Commit 与 push

只 stage 能归属于该 Iteration 的源码、测试、配置和 SDD artifact。提交类型使用：

- `docs`：仅文档或 SDD artifact 更新；
- `feat`：新增业务能力；
- `fix`：修复缺陷。

若类型不能从批准的 Goal/Scope 唯一判断，先询问用户。提交格式为两个 message：

```text
git commit -m "sdd(<NNN>): <type> <short description>" -m "<delivery description>"
```

其中 `<NNN>` 是 Iteration 的三位编号，description 概括实际交付内容。提交后记录 commit
hash，并使用当前分支的普通 `git push`；没有 upstream 时可使用
`git push -u origin <current-branch>`。禁止 force push、改写历史、切换分支或
自动创建 PR。凭据、remote、保护规则或网络导致 push 失败时，保留本地 commit，
报告准确状态和可重试命令，不伪称交付完成。

最后报告 Delivery 文件、commit subject/hash、push remote/branch 与剩余风险，
然后停止。
