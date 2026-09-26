# Implementation Agent Orchestration

Read this reference only when `$sdd-agents` is explicitly used to delegate an
Implementation stage.

## Assignment map

Before dispatch, read the Plan Catalog, Task dependencies, and Impact Surface.
For each agent, provide:

- Exclusive Plan/Task IDs and allowed write files;
- Expected outcome, acceptance checks, dependencies, and prohibited changes;
- Task width, effort, local budget, and remaining global budget;
- Relevant repository facts, key symbols, and focused validation commands.

Tasks in the same Plan, writing the same files, or depending on one another must
go to one agent or run in serial waves. Keep one of four slots for the main
agent; dispatch no more than three agents concurrently.

## Agent isolation

- Use fresh context without the parent conversation. Inherit the current model
  and do not change provider/model.
- Use `medium` for narrow/standard work; use `high` for broad cross-file work,
  difficult debugging, or a narrowed repair after failure. Use `max` only when
  the user explicitly overrides it or a documented exception requires it.
- The agent reads `AGENTS.md`, read-only `.memory/context.md` and
  `.memory/project-map.md`, Plan Index, assigned Plan, Git status, and relevant
  source/tests. The assignment envelope locates and bounds the work; it does not
  replace those repository facts.
- Agents must not create or delegate to further agents. The main agent alone
  writes memory.

Default local limits:

| Scope | Effort | maxTurns | maxWallTime | maxCost |
|---|---:|---:|---:|---:|
| Narrow/standard | medium | 20 | 10 minutes | USD 0.02 |
| Broad/debug/repair | high | 20 | 15 minutes | USD 0.04 |

If runtime cost telemetry is unavailable, record `unknown`, not zero; still
enforce turn and wall-time limits.

## Global limits and waiting

One Implementation stage has at most three dispatch waves (initial plus two
repair waves), 30 minutes, and USD 0.10 total cost. Reserve the worst-case local
cost before dispatch; do not start a wave that exceeds the remaining global
budget.

After every agent in a wave is created successfully, the main agent waits
without running commands or inspecting diffs until all finish, an agent fails or
requests attention, or the user sends a new message. On an unchanged timeout,
wait again without progress noise.

## Agent result contract

Each implementation agent must:

1. Keep a Task `[ ]` until complete, then mark it `[x]`.
2. Fill its Implementation notes and Actual/Changed files.
3. Record Plan Validation commands, results, and evidence with Task IDs.
4. Report changed files, checks, risks, blockers, and observable turns/time/cost.

After the wave, the main agent checks combined scope, file conflicts, Plan
invariants, and evidence, then runs only the minimum deterministic acceptance
checks needed for the Tasks.

Classify failures before repair:

- **Implementation defect:** dispatch a narrowed repair with the failure
  evidence, one behavior to fix, pass condition, and unchanged boundaries.
- **Plan contradiction, ambiguity, or scope expansion:** stop for Human Review.
- **Provider, infrastructure, or budget:** stop and report the operational
  blocker and usage.

Do not use "try again", "continue", or the original broad assignment as a
repair prompt. A first narrow repair may reuse the agent when the approach is
sound. If the same acceptance item fails a second time, use a fresh agent at
`high` effort. Stop after the third wave or any global limit; do not extend the
budget.
