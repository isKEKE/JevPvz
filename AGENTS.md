# Agent Instructions

This repository uses an explicitly invoked Spec-Driven Development (SDD)
workflow implemented by four repository skills:

- `$sdd-plan` — create, revise, or approve an Iteration Plan.
- `$sdd-implementation` — implement one approved Iteration.
- `$sdd-verify` — independently verify one implemented Iteration.
- `$sdd-delivery` — write Delivery, commit, and push one verified Iteration.

## Stage runtime configuration

The repository does not pin a concrete model. Each stage uses the maximum
context length supported by its selected or inherited model.

### Implementation

- Execution: fresh-context worker sub-agents; no parent conversation transcript.
- Model: inherit the current main-agent model; a worker must not change it.
- Reasoning effort: `medium` for narrow/standard work; `high` for broad work,
  difficult debugging, or narrowed repair; `max` only when the user explicitly
  overrides it or a documented exception requires it.
- Context-Length: use the maximum supported by the inherited model.

### Verify

- Execution: one fresh-context verifier sub-agent; no Implementation worker or
  parent conversation transcript is reused.
- Model: inherit the current main-agent model unless explicitly overridden.
- Reasoning effort: inherit the current main-agent effort unless explicitly
  overridden.
- Context-Length: use the maximum supported by the inherited model.

### Delivery

- Execution: the current main agent; Delivery does not start a sub-agent.
- Model: use the current main-agent model.
- Reasoning effort: use the current main-agent effort.
- Context-Length: use the maximum supported by the current main-agent model.

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
asks for it.

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
