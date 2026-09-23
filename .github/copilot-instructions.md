# GitHub Copilot Instructions

This repository uses a conversation-first SDD workflow. Requirement discussion,
repository exploration and design comparison do not create or advance an
Iteration.

Before the first repository-specific response in a new session, read
`.memory/context.md` and `.memory/project-map.md`. Before an SDD stage reads
or writes either file, it must fully load
`.agents/skills/sdd-memory/SKILL.md` and follow that stage's memory contract.

The four explicit stage definitions live under `.agents/skills/`:

- `sdd-plan`
- `sdd-implementation`
- `sdd-verify`
- `sdd-delivery`

When the user explicitly requests one of these stages, follow only that skill's
`SKILL.md` and stop at its boundary. Never infer a stage, chain stages, create
`spec.md` or `implement.md`, or select an existing Iteration by recency.
Iterations live directly under `.sdd/` as `<NNN-short-title>` directories;
stage-specific artifact templates live in the owning skill's `assets/` folder.

For direct non-SDD work, prefer the existing project structure and minimal
changes. Do not create business files at the repository root or add dependencies
without explicit approval. Preserve unrelated working-tree changes.
