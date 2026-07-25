---
name: team
description: [omh] Hermes Team workflow: coordinated parallel or sequential work lanes.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, execution]
    category: execution
    phase: coordination
    role: handoff-guide
    quality_tier: coordination-gated
---

# Team

This is a Hermes-native `team` workflow skill.

## Why This Exists

`team` exists to keep `execution` work explicit, evidence-backed, and inside the Hermes/executor boundary instead of relying on ad hoc chat narration.

## Do Not Use When

- The request is casual chat, a status-only acknowledgement, or another workflow has stronger routing evidence.
- The user needs implementation, review, CI, merge, or external publishing evidence that has not been delegated or observed.

## Examples

Good example:

- Prompt: team: coordinate parallel agents for frontend polish, copy polish, and QA with worker ACKs.
- Expected behavior: Assign lanes, require worker ACK/result evidence, and keep integration verification separate.
- Why: The work benefits from multiple coordinated workers with disjoint ownership.

Bad example:

- Prompt: team: treat casual chat or unaccepted work as if this workflow already produced verified results.
- Expected behavior: Ask a clarification question or route to a narrower workflow instead of forcing `team`.
- Why: The request lacks the required inputs or would overclaim work that Hermes did not observe.

## Completion Checklist

- Each lane has an owner, disjoint scope, expected output, and verification target.
- Worker ACK, dispatch, result, integration, and verification evidence are separated when wrappers record them.
- Hermes-owned coding teams use `hermes_coding_harness/v1` so builder, verifier, reviewer, docs, and PR lanes stay distinct even in solo mode.
- The integrated status names which lanes are observed, blocked, or still prepared_not_observed.

## Recovery Notes

- If two lanes are not independent, collapse them under one owner or re-plan before dispatch.
- If a worker has no ACK or result, mark that lane not_observed or blocked rather than infer progress.
- If integration reveals a shared-file conflict, stop lane fan-out and reassign ownership before continuing.

## OMH Context Rail

- This skill is part of OMH's Hermes workflow layer, not a standalone executor.
- Product context: OMH is a Hermes-native workflow pack: choose skills, shape work, prepare artifacts, show status, and hand off with evidence boundaries.
- Current lane: **Coding handoff** (`idea-to-deploy`, `cto-loop`, `deploy-and-monitor`, `code-review`, `build-failure-triage`, `verification-gate`, `security-safety-review`, `ultrawork`, `+7 more`) - coding owners, handoffs, review, CI, and merge evidence.
- If intent belongs to another lane, hand back to `oh-my-hermes` or name the adjacent workflow.
- Cross-skill context: every OMH skill: match lane; generic tool can render or execute.
- Generic-tool checkpoint: image->img-summary; frontend->frontend/a11y/visual-qa; paper->paper-learning; content->content-operator; media->media-input-operator; file->materials-package; search->web-research; live->live-info-operator; audit->workspace/production/security; failures->build-failure; verify->verification-gate; code->codegraph/onboarding/ultraprocess.
- Coverage: Every generated workflow skill carries this rail.
- Normal users talk to Hermes; OMH CLI is infra.
- Boundary: Prepared OMH routing/cards/handoffs/artifacts are not observed execution, image generation, delivery, review, CI, merge-readiness, or merge evidence.

## Use When

Use when multiple independent lanes materially improve throughput or verification.

    Strong routing signals: `team`, `$team`, `swarm`, `parallel agents`, `coordinated workers`

## Catalog Metadata

Category: `execution`
Phase: `coordination`
Hermes role: `handoff-guide`
Quality tier: `coordination-gated`

Quality bar:

- Split only independent lanes with explicit ownership and verification boundaries.
- Keep Hermes as coordinator and status narrator while coding lanes become runtime handoffs with explicit ownership.
- Integrate lane evidence before reporting combined progress.

Handoff policy:

Use Hermes for lane framing and status; implementation lanes should become selected runtime handoff tasks, including Hermes-owned coding when the user chooses that runtime.

Executor readiness:

- When accepted work mutates code, check `executor_readiness/v1` for the selected Codex, Claude Code, Hermes, or oh-my runtime path before first dispatch.
- If readiness is `missing` or `blocked`, ask the user to choose another coding agent, configure PATH, continue in Hermes, or keep a prompt/runtime handoff; retry only after that state changes.
- A readiness probe is not dispatch, implementation, verification, review, CI, merge-readiness, or merge evidence.

Required inputs:

- bounded lane definitions
- ownership boundaries
- verification target

Expected outputs:

- lane results
- integration summary
- combined verification evidence

Artifact expectations:

- delegation record only when separate participants are observed

Safety rules:

- Use parallel lanes only when work is independent.
- Keep shared-file edits under one owner.
- Record unobserved delegation as not_observed.

## Runtime Evidence

Preferred harness for this skill: `goal-execution`.

```sh
omh runtime record --skill team --harness goal-execution --status started
```

Record observed delegation results when Hermes or the wrapper exposes them. If delegation is unavailable, keep the result explicit as `not_available` or `not_observed`.

## Hermes Compatibility Contract

- Preserve the workflow intent, stop conditions, and verification discipline; verify with the smallest relevant test or inspection before claiming completion.
- Use Hermes-native tools, file operations, and subagent/delegation features when available, and do not require runtime tools, role prompts, or overlays that Hermes Agent does not expose. If Hermes cannot provide a required runtime capability, say so and fall back: native subagents -> Hermes delegation when available, otherwise sequential lanes.
- Respect `omh_target_topology/v1` when a wrapper reports it: bind state to the current target/thread, fall back to single-target behavior when `active_agent_count` is one, and give one concise setup-change comment before treating a one-to-many or many-to-one change as persistent.
- When wrapper metadata includes `memory_review_card/v1` or `handoff_context_pack/v1`, treat it as reviewed OMH-local or wrapper-supplied context only. Use conflict-free context summaries to shape plans and handoffs, but do not claim Hermes internal memory was read or changed.
- Shared rail: `oh-my-hermes/references/skill-common-rail.md` carries harness discipline, the runtime-mechanism translation table, the delegation-record command, and the execution-rule checklist. Load it when one of those applies; if it is not installed, name the unavailable capability instead of assuming it.
