# Delivery Agent Input

Use this contract only when the user explicitly invokes `$sdd-agents` together
with `$sdd-delivery`. The delivery agent prepares the report; it does not
perform Git delivery actions.

## Execution profile

- Fresh context without the parent conversation:
- Inherit the current main-agent model and reasoning effort:
- Do not change provider/model or delegate further:

## Identity and approved baseline

- Repository root and exact Iteration path/ID:
- Plan Index and concrete Plan paths/revisions:
- Approved goal, scope, and completed/incomplete Task state:
- `verify.md` path, overall result, and evidence summary:

## Actual result

- Current Git status/diff and relevant revision:
- In-scope changed files and behavior:
- Plan deviations, known risks, and follow-up items:
- Current branch and commit type/subject supplied by the main agent:
- Files explicitly excluded as unrelated:

## Write and action boundary

- Allowed write: target `delivery.md` only:
- Read-only inputs: Plans, `verify.md`, source diff/status, and repository
  instructions:
- Do not modify code, tests, Plans, Verify, memory, or unrelated files.
- Do not stage, commit, push, switch branches, create a PR, or change remotes.

## Result required

Draft the Delivery report from supplied evidence. Identify any mismatch between
the approved scope, actual diff, Verify result, or proposed Git scope. Report
the written file and unresolved discrepancies to the main agent, which owns the
final review, memory update, commit, and push.
