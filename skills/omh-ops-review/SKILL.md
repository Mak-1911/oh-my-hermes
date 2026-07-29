---
name: omh-ops-review
description: [omh] Hermes Ops Review workflow: status, risks, blockers, priorities, and follow-ups. Use when the user says: ops-review, ops review, weekly ops review, status review, operating review, release risks, risks and blockers, priorities.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, operations]
    category: operations
    phase: status-review
    role: operator
    quality_tier: status-gated
---

# Ops Review

This is a Hermes-native `ops-review` workflow skill.

## Why This Exists

`ops-review` exists to keep `operations` work explicit, evidence-backed, and inside the Hermes/executor boundary instead of relying on ad hoc chat narration.

## Do Not Use When

- The request is casual chat, a status-only acknowledgement, or another workflow has stronger routing evidence.
- The user needs implementation, review, CI, merge, or external publishing evidence that has not been delegated or observed.

## Examples

Good example:

- Prompt: ops-review: summarize this week’s support queue, release blockers, owner status, and next operating risks.
- Expected behavior: Create an operations status review with owners, blockers, evidence gaps, and next actions.
- Why: The request is an operating review rather than a one-off plan or coding handoff.

Bad example:

- Prompt: ops-review: treat casual chat or unaccepted work as if this workflow already produced verified results.
- Expected behavior: Ask a clarification question or route to a narrower workflow instead of forcing `ops-review`.
- Why: The request lacks the required inputs or would overclaim work that Hermes did not observe.

## Completion Checklist

- Confirm the workflow target, evidence boundary, and stop condition are named.
- Report which outputs are prepared, observed, blocked, or missing.
- Name the smallest next verification or handoff instead of claiming completion from narration.

## Recovery Notes

- If required context is missing, ask one blocking question or route back to the narrower workflow.
- If runtime or wrapper evidence is unavailable, keep the status as not_observed and expose the next observable action.

## OMH Context Rail

- This skill is part of OMH's Hermes workflow layer, not a standalone executor.
- Product context: OMH is a Hermes-native workflow pack: choose skills, shape work, prepare artifacts, show status, and hand off with evidence boundaries.
- Current lane: **Research and company ops** (`source-finder`, `web-research`, `best-practice-research`, `autoresearch-goal`, `research-brief`, `strategy-brief`, `feedback-triage`, `research-department`, `+12 more`) - research, signals, ops, and briefings.
- If intent belongs to another lane, hand back to `oh-my-hermes` or name the adjacent workflow.
- Cross-skill context: every OMH skill: match lane; generic tool can render or execute.
- Generic-tool checkpoint: image->img-summary; frontend->frontend/a11y/visual-qa; paper->paper-learning; content->content-operator; media->media-input-operator; file->materials-package; search->web-research; live->live-info-operator; audit->workspace/production/security; failures->build-failure; verify->verification-gate; code->codegraph/onboarding/ultraprocess.
- Coverage: Every generated workflow skill carries this rail.
- Normal users talk to Hermes; OMH CLI is infra.
- Boundary: Prepared OMH routing/cards/handoffs/artifacts are not observed execution, image generation, delivery, review, CI, merge-readiness, or merge evidence.

## Use When

Use when Hermes should summarize observed status, risks, blockers, priorities, and follow-up actions for recurring operating work.

    Strong routing signals: `ops-review`, `ops review`, `weekly ops review`, `status review`, `operating review`, `release risks`, `risks and blockers`, `priorities`, `weekly status`, `운영 리뷰`, `주간 운영`, `상태 리뷰`, `리스크`, `블로커`, `우선순위`, `릴리즈 리스크`

## Catalog Metadata

Category: `operations`
Phase: `status-review`
Hermes role: `operator`
Quality tier: `status-gated`

Quality bar:

- Tie every status claim to observed evidence or mark it as unknown.
- Separate risks, blockers, priorities, and follow-up owners.
- Keep code fixes as explicit follow-up handoffs, not implicit ops-review output.

Handoff policy:

Keep operating review and status narration in Hermes; delegate code fixes only from explicit accepted follow-up items.

Required inputs:

- status evidence
- scope
- time window
- known risks

Expected outputs:

- status summary
- risks
- blockers
- priorities
- follow-up actions

Artifact expectations:

- ops review record or status artifact when a wrapper captures it

Safety rules:

- Do not infer status from missing evidence.
- Separate observed facts, risks, blockers, decisions, and follow-up actions.
- Do not report review, CI, release, or merge readiness from an ops summary alone.

## Runtime Evidence

Preferred harness for this skill: `ops-review`.

```sh
omh runtime record --skill ops-review --harness ops-review --status started
```

Record observed delegation results; otherwise return `not_available` or `not_observed`.

## Hermes Compatibility Contract

- Preserve workflow intent and stop conditions; verify before claiming completion.
- Use Hermes-native tools, file operations, and subagent/delegation features when available; do not require unavailable runtime tools, role prompts, or overlays. If a capability is unavailable: native subagents -> Hermes delegation when available, otherwise sequential lanes.
- Respect `omh_target_topology/v1`: bind state to the current target/thread, use single-target behavior when `active_agent_count` is one, and name a one-to-many or many-to-one change before treating it as persistent.
- Treat wrapper memory/context summaries as advisory local context, not proof of opaque Hermes memory reads or changes.
- Shared rail: `omh-routing/references/skill-common-rail.md` has harness discipline, runtime translations, the delegation command, and execution checklist. Load it when applicable; otherwise name an unavailable capability.
