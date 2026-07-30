---
name: ulw-goal
description: [omh] Ultragoal - durable multi-session goal tracking: a checkpointed ledger survives context loss and resumes exactly where work stopped, with a final completion gate. Aliases: ulg. Use when the user says: ultragoal, durable goal, multi-goal, goal ledger, long running goal, 완료조건까지 계속, keep working until acceptance criteria pass, 장기 목표.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, execution]
    category: execution
    phase: durable-goals
    role: handoff-guide
    quality_tier: checkpoint-gated
---

# Ultragoal

This is a Hermes-native `ultragoal` workflow skill.

## Why This Exists

`ultragoal` exists for work that can outlive one chat turn: it turns ambition into durable stories, checkpoints, and completion gates so progress can resume without pretending a summary is evidence.

## Do Not Use When

- The request is a single-turn answer, quick diagnosis, or small edit that does not need a durable ledger.
- One concrete, already-scoped task only needs one owner to finish and verify; use `ralph`.
- The next work must be discovered or reframed repeatedly through research and feedback cycles; use `loop`.
- The request is a settings-only or single configuration change (for example a gateway channel policy, a mention rule, or one config key) that the wrapper or Hermes can apply directly; apply the configuration change, verify the new value, and report it instead of opening a goal ledger or preparing a coding handoff.
- Acceptance criteria, current checkpoint, and final gate expectations are too vague to make a goal inspectable.
- The user expects hidden Hermes code execution rather than explicit executor handoff and observed verification evidence.

## Examples

Good example:

- Prompt: $ultragoal turn OMH skill quality into a durable goal with rubrics, generated skill sync, tests, and a PR gate.
- Expected behavior: Create or update a goal ledger, split the story into verifiable checkpoints, and close only after generated docs, skills, and tests match.
- Why: The task has multiple milestones and a final quality gate that should be inspectable across interruptions.

Bad example:

- Prompt: $ultragoal what does this one error mean?
- Expected behavior: Route to diagnosis or a direct answer instead of creating a durable goal.
- Why: A narrow explanation does not need checkpointed long-running state.

## Completion Checklist

- The goal_ledger/v1 names the current criteria, checkpoints, blockers, and next action.
- The goal_completion_gate/v1 result passes from required evidence, not from a summary-only message.
- All explicitly linked coding milestones have matching observed runtime evidence or are still named as gaps.
- The final user-facing status says complete, blocked, or continue with the exact remaining checkpoint.
- Long-running or background executor milestones report observed handles, current state, changed-file summaries, missing checks, and prepared-vs-observed boundaries while work is running.
- When Hermes is the coding owner, use `hermes_coding_harness/v1` to separate builder, verifier, reviewer, docs, and PR lanes.
- Branch, PR, CI, review, and merge claims are verified against local HEAD, remote branch SHA, PR head SHA, and merge commit before saying a fix landed.

## Recovery Notes

- If the goal ledger is stale or missing, inspect .omh/goals and ask which checkpoint to resume before continuing.
- If a blocker checkpoint exists, keep the goal open and record the blocker plus the smallest unblock action.
- If linked runtime evidence is missing, keep coding milestones prepared_not_observed and do not close the goal.

## Workflow Lane

- Current lane: **Intent -> plan** (`oh-my-hermes`, `meta-router`, `deep-interview`, `plan`, `ralplan`, `codebase-onboarding`, `codegraph-refresh`, `ultragoal`, `+6 more`) - clarify, plan, ship, or loop goals.
- If intent belongs to another lane, hand back to `oh-my-hermes` or name the adjacent workflow.
- Shared product, routing, compatibility, and evidence rules: `omh-routing/references/skill-common-rail.md`.

## Use When

Use when work needs durable goal artifacts, checkpointed progress, and final quality gates.

    Strong routing signals: `ultragoal`, `$ultragoal`, `ulg`, `$ulg`, `durable goal`, `multi-goal`, `goal ledger`, `long running goal`, `완료조건까지 계속`, `keep working until acceptance criteria pass`, `장기 목표`, `오래 실행`, `완료 조건까지 계속`

## Catalog Metadata

Category: `execution`
Phase: `durable-goals`
Hermes role: `handoff-guide`
Quality tier: `checkpoint-gated`
Reasoning demand: `heavy`

Quality bar:

- Keep goal state durable, inspectable, and separate from chat narration.
- Checkpoint every success, blocker, and final quality gate with fresh evidence.
- Reject completion with a summary-only goal_completion_gate/v1 result until required criteria, blockers, and explicitly linked runtime runs are satisfied.
- Tell the user the next action through goal_status_card/v1 or goal_continuation/v1 instead of ending with vague follow-up copy.
- For coding milestones, use prepared runtime handoffs and observed runtime evidence rather than hidden execution claims.

Handoff policy:

Use Hermes to maintain .omh/goals goal_ledger/v1 state, show goal_status_card/v1 / goal_continuation/v1 next actions, and route coding milestones to the selected runtime profile with only observed runtime evidence.

Executor readiness:

- When accepted work mutates code, check `executor_readiness/v1` for the selected Codex, Claude Code, Hermes, or oh-my runtime path before first dispatch.
- If readiness is `missing` or `blocked`, ask the user to choose another coding agent, configure PATH, continue in Hermes, or keep a prompt/runtime handoff; retry only after that state changes.
- A readiness probe is not dispatch, implementation, verification, review, CI, merge-readiness, or merge evidence.

Required inputs:

- goal statement
- acceptance criteria
- current checkpoint or missing criteria

Expected outputs:

- goal_ledger/v1 updates
- checkpoint evidence
- goal_completion_gate/v1 result
- completion or blocker summary

Artifact expectations:

- metadata-only .omh/goals ledger
- goal_status_card/v1 or goal_continuation/v1 wrapper payload
- runtime run record only for explicitly linked coding milestones

Safety rules:

- Do not imply hidden Hermes runtime behavior.
- Use the smallest verification that can prove the claim.

## Runtime Evidence

Preferred harness for this skill: `goal-execution`.

```sh
omh runtime record --skill ultragoal --harness goal-execution --status started
```

Record observed delegation results; otherwise return `not_available` or `not_observed`.
Prepared OMH routing is not execution, review, CI, merge-readiness, or merge evidence.
- When wrapper metadata includes `memory_review_card/v1` or `handoff_context_pack/v1`, treat it as reviewed OMH-local or wrapper-supplied context only. Use conflict-free context summaries to shape plans and handoffs, but do not claim Hermes internal memory was read or changed.
Preserve workflow intent and stop conditions; verify before claiming completion.

Use Hermes-native subagent/delegation features when available: native subagents -> Hermes delegation when available, otherwise sequential lanes.

Shared product, compatibility, topology, memory, harness, and execution rules: `omh-routing/references/skill-common-rail.md`. Load it when applicable; otherwise name an unavailable capability.
