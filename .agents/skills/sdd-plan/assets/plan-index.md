# Plan Index

Use this file as the human reading view for an Iteration. Keep implementation
details, symbols, Task checklists, and backfill fields in the linked concrete
Plans under `plans/`.

## 1. Metadata

- Iteration: `<NNN-short-title>`
- Created at:
- Status: Planned
- Owner:

## 2. Goal

用一段话说明整个 Iteration 要完成什么。

### Requirement Baseline

把原始需求写成后续阶段无需聊天上下文也能理解的可验证条目。

| Requirement ID | Requirement | Source | Mandatory |
|---|---|---|---|
| R1 | TBD | User conversation / issue / document | Yes |

## 3. Scope

### In scope

### Out of scope

## 4. Plan Catalog

| Plan ID | Plan | Main outcome | Depends on | Status | Link |
|---|---|---|---|---|---|
| P01 | TBD | TBD | None | Planned | `plans/01-<short-name>.md` |

## 5. Decision

- Open Decision：具体选项在各 Plan 中列出。
- Confirmed Decision：用户确认后从 Open Decision 回填，并记录来源、日期和理由。

## 6. Task

- 列出各 Plan 的 Task 顺序和跨 Plan 依赖。
- 每条 Task 的目标、影响文件、Implementation backfill 和计划验证详见具体 Plan。

## 7. Validation

说明整个 Iteration 的验证顺序，以及哪些验证属于自动化、手工或浏览器检查。

## 8. Risks

列出跨 Plan 的技术、合规、运行和验证风险。

## 9. Approval

- Status: Pending human review
- Approved by:
- Approval date:
- Notes:

实质修改 Requirement Baseline、Scope、Decision、Task 或 Validation 后，将 Status
恢复为 Pending，直到用户再次明确批准。
