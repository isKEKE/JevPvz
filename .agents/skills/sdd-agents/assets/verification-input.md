# Verification Agent Input

Fill this envelope for the single fresh-context verifier. It must contain the
full evidence boundary and authority the verifier needs; do not depend on the
parent conversation for requirements or permissions.

## Execution profile

- Fresh context without the parent conversation:
- Inherit the current main-agent model and reasoning effort:
- Must differ from every implementation agent used for this Iteration:
- Do not change provider/model or delegate further:

## Identity and baseline

- Repository root and exact Iteration path/ID:
- Plan Index path, revision, and approval state:
- Concrete Plan paths and revisions:
- Original requirement source and self-contained requirement baseline:
- Current delivery goal and use:
- G1/G2/G3 boundary and reasons:
- Original user constraints and explicit Human decisions:

## Repository evidence

- Current Git diff/status and relevant revision:
- Relevant implementation files/symbols and tests:
- Required validation commands and expected evidence:
- Existing Human or automation evidence, with source/date:
- Runtime environment, current state, and access available:

## Authority and write boundary

- Actions the verifier may perform:
- Read-only memory inputs: `.memory/context.md` and `.memory/project-map.md`:
- Authorization source, scope, limits, and stop/recovery conditions for any
  state-changing or externally visible action:
- Sole writable file: target `verify.md`:
- Prohibited changes: production code, tests, Plans, Project Map, and unrelated
  files:
- Restrictions and their source; do not invent broad read-only limits:

## Result required

Check requirement-to-Plan-to-Task traceability, actual diff, acceptance, G1
coverage, and relevant omitted checks. Record every result and evidence,
including failures, `Not run`, or `Deferred` items; identify G1 delivery impact,
G2 Human decisions, G3 recheck triggers, and any execution omission. Do not
repair defects or delegate further.
