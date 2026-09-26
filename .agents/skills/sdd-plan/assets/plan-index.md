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

| Requirement ID | Requirement | Source | Verification tier | Reason for tier |
|---|---|---|---|---|
| R1 | TBD | User conversation / issue / document | G1 | TBD |

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

### Current delivery boundary

- 本次产物与实际用途：
- 本次交付成功的最小条件：
- 不作为本次交付门槛的场景：

### Verification tiers

| Tier | Meaning | Handling in Verify |
|---|---|---|
| G1 核心路径 | 直接决定本次目标能否实现或结果是否可信 | 必须取得充分通过证据；失败或缺少必要证据影响交付 |
| G2 当前风险 | 当前可能遇到，但不必然妨碍核心路径 | 如实记录影响；Human 明确接受的剩余风险不阻塞交付 |
| G3 后续场景 | 主要针对未来用途，不属于本次目标 | 可暂缓验证；记录理由和未来重查条件 |

说明整个 Iteration 的验证顺序，以及哪些检查属于自动化、手工或浏览器验证。
所有具体检查及其级别、证据和升级条件写在对应 Plan 的 Validation 中。若 G2/G3
的发现实际影响 G1，必须重新评估其级别，不能沿用非阻塞判断。

## 8. Risks

列出跨 Plan 的技术、合规、运行和验证风险。

## 9. Approval

- Status: Pending human review
- Approved by:
- Approval date:
- Notes:

实质修改 Requirement Baseline、Scope、Decision、Task 或 Validation 后，将 Status
恢复为 Pending，直到用户再次明确批准。
