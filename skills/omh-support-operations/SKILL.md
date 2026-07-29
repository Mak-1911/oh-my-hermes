---
name: omh-support-operations
description: [omh] Turn a support case into a clear customer reply, severity path, and owned next step. Use when the user says: support escalation, customer support reply, ticket triage, 고객 지원 에스컬레이션, 고객 답변 초안, 지원 티켓 분류.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, triage]
    category: triage
    phase: support-operations
    role: operator
    quality_tier: triage-gated
---

# Support Operations

This is a Hermes-native `support-operations` workflow skill.

## Why This Exists

`support-operations` turns a bounded customer case into response and escalation guidance without treating drafts or recommendations as helpdesk actions.

## Do Not Use When

- The request clusters a backlog of customer signals to find product patterns or roadmap candidates; use `feedback-triage`.
- The user only needs a generic, non-support marketing or email rewrite with no case, severity, or escalation context; use `content-operator`.
- The request asks to send a reply, change ticket priority or status, issue a refund, modify an account, or update a helpdesk; use `connector-operator` with an explicit target and observed result.
- The request is an active reliability incident or postmortem rather than a support-case response; use `reliability-review`.

## Examples

Good example:

- Prompt: Draft a calm reply for this login-outage customer and tell me whether it needs an engineering escalation.
- Expected behavior: Prepare a customer-safe reply, severity matrix, engineering escalation recommendation, and owner handoff.
- Why: The request is one support case with reply and escalation decisions, not a feedback backlog or ticket mutation.

Bad example:

- Prompt: Cluster last quarter's support feedback into roadmap opportunities.
- Expected behavior: Route to `feedback-triage`, not `support-operations`.
- Why: A historical signal backlog needs product-pattern triage rather than case-level support guidance.

## Completion Checklist

- The source boundary, signal clusters, severity, and follow-up lane are named.
- Bug, feature, research, strategy, and coding handoff outcomes stay separate.
- The next workflow is recommended before any implementation claim.

## Recovery Notes

- If feedback lacks source or severity, ask for the missing signal before coding handoff.
- If the item is actually a plan or research request, route to that workflow instead of triage.

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

Use when one or a bounded set of support contacts needs response drafting, urgency classification, incident/escalation routing, and follow-up ownership.

    Strong routing signals: `support escalation`, `customer support reply`, `ticket triage`, `고객 지원 에스컬레이션`, `고객 답변 초안`, `지원 티켓 분류`

## Catalog Metadata

Category: `triage`
Phase: `support-operations`
Hermes role: `operator`
Quality tier: `triage-gated`

Quality bar:

- State issue, severity, impact, evidence gaps, owner, and next route.
- Draft a reply without treating it as a sent customer communication.

Handoff policy:

Keep domain framing, clarification, source/evidence synthesis, draft outputs, and next-work routing in Hermes. A prepared brief, review, reply, or plan is not an external action, approval, filing, send, publish, data mutation, implementation, review, CI, or merge claim. Prepare a connector, file, coding, or human-review handoff only when the user explicitly accepts that next step; report it only from observed evidence. Reply text is a draft, escalation is a recommendation, and no ticket state, message send, refund, account action, or customer outcome is claimed.

Required inputs:

- support case
- known facts
- customer impact
- available ownership or escalation path

Expected outputs:

- customer-safe reply draft with stated facts, unknowns, and tone
- issue/severity/impact/escalation matrix
- internal next-step and owner handoff brief
- missing repro, account, entitlement, or approval evidence list

Artifact expectations:

- prepared support case brief when a wrapper captures it

Safety rules:

- Keep customer-safe facts, unknowns, and escalation recommendations distinct.
- Do not claim ticket mutation, message send, refund, account action, or case outcome.

## Runtime Evidence

Preferred harness for this skill: `ops-review`.

```sh
omh runtime record --skill support-operations --harness ops-review --status started
```

Record observed delegation results; otherwise return `not_available` or `not_observed`.

## Hermes Compatibility Contract

- Preserve workflow intent and stop conditions; verify before claiming completion.
- Use Hermes-native tools, file operations, and subagent/delegation features when available; do not require unavailable runtime tools, role prompts, or overlays. If a capability is unavailable: native subagents -> Hermes delegation when available, otherwise sequential lanes.
- Respect `omh_target_topology/v1`: bind state to the current target/thread, use single-target behavior when `active_agent_count` is one, and name a one-to-many or many-to-one change before treating it as persistent.
- Treat wrapper memory/context summaries as advisory local context, not proof of opaque Hermes memory reads or changes.
- Shared rail: `omh-routing/references/skill-common-rail.md` has harness discipline, runtime translations, the delegation command, and execution checklist. Load it when applicable; otherwise name an unavailable capability.
