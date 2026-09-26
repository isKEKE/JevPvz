# Agent Instructions

This repository uses an explicitly invoked Spec-Driven Development (SDD)
workflow implemented by four explicit stage skills:

- `$sdd-plan` — create, revise, or approve an Iteration Plan.
- `$sdd-implementation` — implement one approved Iteration.
- `$sdd-verify` — verify one implemented Iteration.
- `$sdd-delivery` — write Delivery, commit, and push one verified Iteration.

## Stage execution defaults

- Plan, Implementation, Verify, and Delivery run in the current main-agent
  context by default. Invoking a stage skill alone never starts sub-agents.
- `$sdd-agents` is the separate, explicit opt-in for sub-agent execution,
  explanation, and role input contracts. For execution, pair it with exactly
  one supported stage and Iteration name or ID. It owns delegation mechanics;
  the selected stage skill continues to own stage requirements and lifecycle.
- Main-agent stages use the maximum context length supported by the selected or
  inherited model. Optional sub-agent model, effort, isolation, and budget rules
  belong to `.agents/skills/sdd-agents/`.

## Session bootstrap

Before the first repository-specific response in every new session, read
`.memory/context.md` and `.memory/project-map.md` if they exist. If both files
are already present in the active context, do not reread them on every turn.

`.agents/skills/sdd-memory/SKILL.md` is the single authority for how these two
files are populated, pruned, and updated. Every SDD stage must load it before
touching memory. A direct non-SDD task loads it only when the task materially
changes the implemented technology stack, directory structure, or SDD operating
state.

## Default conversation

Before `$sdd-plan`, help the user expand the requirement in conversation:
inspect relevant files when useful, test feasibility, compare implementation and
validation paths, consult relevant documentation, and surface open decisions.
Do not create an Iteration or SDD artifact merely because a requirement is being
discussed. A direct non-SDD edit remains a direct task when the user explicitly
asks for it. SDD stages also run directly in the main agent by default. Use
`$sdd-agents` for explicit delegation, usage explanations, or role-input
questions; only its delegation mode starts sub-agents.

Never infer an SDD stage or advance to the next stage. Each stage requires its
own explicit skill invocation. Do not create standalone `spec.md` or
`implement.md` files.

## Shared boundaries

- Iterations live directly at `.sdd/<NNN-short-title>/`, for example
  `.sdd/001-user-login/`. Stage skills own identity resolution, artifact
  templates, and lifecycle details.
- Do not create business files at repository root unless they are recognized
  root-level configuration files.
- Prefer existing modules and minimal changes. New dependencies require
  explicit human approval.
- Plan artifacts are written in Chinese unless the user requests another
  language.
- Preserve unrelated working-tree changes and never include them in an SDD
  commit.
