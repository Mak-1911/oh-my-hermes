---
name: omh-deep-interview
description: [omh] Hermes Deep Interview workflow: one-question-at-a-time clarification.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, clarification]
    category: clarification
    phase: discovery
    role: planner
    quality_tier: clarity-gated
---

# Deep Interview

This is a Hermes-native `deep-interview` workflow skill.

## Why This Exists

`deep-interview` exists to stop Hermes from guessing through ambiguous product, workflow, or implementation intent; it converts uncertainty into a clarified brief before planning or handoff.

## Do Not Use When

- The request already has concrete scope, acceptance criteria, and verification commands.
- The missing information is discoverable from the repository or local artifacts without asking the user.
- The user asked for immediate read-only analysis and the ambiguity does not change the answer.

## Examples

Good example:

- Prompt: $deep-interview before planning Discord and Slack routing, ask what each channel owns and what evidence counts.
- Expected behavior: Ask one decision-changing question at a time, then produce goals, non-goals, and acceptance criteria.
- Why: The request explicitly rejects assumptions and needs product boundaries before implementation.

Bad example:

- Prompt: $deep-interview fix this failing test; the traceback and expected behavior are attached.
- Expected behavior: Proceed to diagnosis or implementation instead of interviewing.
- Why: The required facts are already available, so more questions would slow the workflow.

## Completion Checklist

- The clarified brief names goals, non-goals, constraints, and one next planning or handoff path.
- Remaining ambiguity is listed only when it changes the plan, risk, or stop condition.
- No implementation handoff is prepared until the blocking decision is resolved.

## Recovery Notes

- If the user answers with new ambiguity, ask the next decision-changing question instead of planning too early.
- If repo evidence can answer the question, inspect it before asking the user.

## OMH Context Rail

- This skill is part of OMH's Hermes workflow layer, not a standalone executor.
- Product context: OMH is a Hermes-native workflow pack: choose skills, shape work, prepare artifacts, show status, and hand off with evidence boundaries.
- Current lane: **Intent -> plan** (`oh-my-hermes`, `meta-router`, `deep-interview`, `plan`, `ralplan`, `codebase-onboarding`, `codegraph-refresh`, `ultragoal`, `+4 more`) - clarify, plan, ship, or loop goals.
- If intent belongs to another lane, hand back to `oh-my-hermes` or name the adjacent workflow.
- Cross-skill context: every OMH skill: match lane; generic tool can render or execute.
- Generic-tool checkpoint: image->img-summary; frontend->frontend/a11y/visual-qa; paper->paper-learning; content->content-operator; media->media-input-operator; file->materials-package; search->web-research; live->live-info-operator; audit->workspace/production/security; failures->build-failure; verify->verification-gate; code->codegraph/onboarding/ultraprocess.
- Coverage: Every generated workflow skill carries this rail.
- Normal users talk to Hermes; OMH CLI is infra.
- Boundary: Prepared OMH routing/cards/handoffs/artifacts are not observed execution, image generation, delivery, review, CI, merge-readiness, or merge evidence.

## Use When

Use before planning or execution when requirements are materially ambiguous.

    Strong routing signals: `deep-interview`, `$deep-interview`, `interview`, `don't assume`, `clarify`, `feature shaping`, `ambiguous product request`, `one question`, `온보딩`, `부드럽게`, `모호한 제품 요청`, `기획자`, `개발자 사이`

## Catalog Metadata

Category: `clarification`
Phase: `discovery`
Hermes role: `planner`
Quality tier: `clarity-gated`

Quality bar:

- Ask exactly one blocking question per turn unless the wrapper explicitly supports a structured batch.
- Tie each question to a missing decision that changes the plan, handoff, or stop condition.
- Emit a clarified brief with non-goals and acceptance criteria before planning or delegation.

Handoff policy:

Run directly in Hermes or the chat wrapper; produce a clarified brief before any coding handoff is prepared.

Required inputs:

- initial request
- known repo facts
- current ambiguity

Expected outputs:

- clarified brief
- non-goals
- decision boundaries

Artifact expectations:

- clarity summary or transcript when the wrapper supports it

Safety rules:

- Ask one question at a time.
- Gather discoverable repo facts before asking the user.
- Stop interviewing once ambiguity is low enough to plan.

## Runtime Evidence

Preferred harness for this skill: `deep-interview`.

```sh
omh runtime record --skill deep-interview --harness deep-interview --status started
```

Record observed delegation results when Hermes or the wrapper exposes them. If delegation is unavailable, keep the result explicit as `not_available` or `not_observed`.

## Hermes Compatibility Contract

- Preserve the workflow intent, stop conditions, and verification discipline; verify with the smallest relevant test or inspection before claiming completion.
- Use Hermes-native tools, file operations, and subagent/delegation features when available, and do not require runtime tools, role prompts, or overlays that Hermes Agent does not expose. If Hermes cannot provide a required runtime capability, say so and fall back: native subagents -> Hermes delegation when available, otherwise sequential lanes.
- Respect `omh_target_topology/v1` when a wrapper reports it: bind state to the current target/thread, fall back to single-target behavior when `active_agent_count` is one, and give one concise setup-change comment before treating a one-to-many or many-to-one change as persistent.
- Treat wrapper-supplied memory/context summaries as advisory local context, not proof that opaque Hermes memory was read or changed.
- Shared rail: `oh-my-hermes/references/skill-common-rail.md` carries harness discipline, the runtime-mechanism translation table, the delegation-record command, and the execution-rule checklist. Load it when one of those applies; if it is not installed, name the unavailable capability instead of assuming it.
