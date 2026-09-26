---
name: sdd-agents
description: Opt-in SDD sub-agent orchestration, usage explanations, and role input contracts for Implementation, Verify, and Delivery.
---

# SDD Agents

SDD stages run in the current main-agent context by default. This skill owns the
optional sub-agent path; it does not replace stage requirements or create a
second implementation, verification, or delivery workflow. A stage invocation
alone never authorizes sub-agent use.

## Choose the requested mode

1. **Delegate stage work.** Only when the user explicitly asks to use
   sub-agents, pair this skill with exactly one stage and Iteration:
   `$sdd-agents $sdd-implementation 001`,
   `$sdd-agents $sdd-verify 001`, or
   `$sdd-agents $sdd-delivery 001`. Read and follow that complete stage skill;
   this skill supplies only delegation, agent inputs, and result coordination.
   Use platform-native sub-agents only; do not create user-visible tasks or
   threads. If the agent provider is unavailable or dispatch fails, stop and
   report it instead of silently switching to main-agent execution.
2. **Explain sub-agents.** When asked how they work or when to use them, explain
   the opt-in rule, available roles, input boundaries, and which work remains
   with the main agent. Do not start an agent just to answer a question.
3. **Show or prepare role inputs.** When asked what an agent receives, use the
   corresponding input asset. Explain or fill the contract from repository
   evidence. Do not dispatch unless the user also asks to perform the stage with
   sub-agents.

If execution is requested without one clearly named stage and Iteration, ask
for the missing information; do not infer a stage or advance the lifecycle.
`$sdd-plan` is not delegated by this skill.

## Role contracts

- **Implementation:** Read [implementation input](assets/implementation-input.md)
  and [orchestration limits](references/implementation-orchestration.md). Assign
  bounded Plan Tasks and non-overlapping write ownership. Keep implementation
  acceptance and memory writes with the main agent.
- **Verify:** Read [verification input](assets/verification-input.md). Use one
  fresh-context verifier, distinct from every implementation agent. The agent
  may write only the target `verify.md`; the main agent reviews evidence and
  completes the Verify memory contract.
- **Delivery:** Read [delivery input](assets/delivery-input.md). An agent may
  prepare the Delivery report only. The main agent owns the final scope check,
  memory update, staging, commit, and push.

Do not let an agent delegate further or exceed the selected stage's approved
scope. Preserve stage-specific approval, evidence, risk, and stop conditions.
Report each delegated role, its result, and any unresolved issue; the main agent
remains responsible for the stage's completion decision.

All delegated agents inherit the current main-agent model and may not change
provider or model. Use the maximum supported context. Verify and Delivery agents
also inherit the current main-agent reasoning effort; Implementation effort and
time/cost limits follow the orchestration reference.
