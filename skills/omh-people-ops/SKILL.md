---
name: omh-people-ops
description: [omh] Turn hiring and people context into a fair, structured recruiting or people-operations brief. Use when the user says: recruiting plan, interview scorecard, candidate debrief, 채용 계획, 면접 평가표, 후보자 비교.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, operations]
    category: operations
    phase: people-operations
    role: operator
    quality_tier: evidence-gated
---

# People Ops

This is a Hermes-native `people-ops` workflow skill.

## Why This Exists

`people-ops` keeps recruiting and people-process guidance fair, structured, and evidence bounded before any human decision or external HR action.

## Do Not Use When

- The request asks for a jurisdiction-specific employment-law conclusion, policy compliance ruling, or contract interpretation; use `legal-compliance-review`.
- The user only needs a one-off job-ad, rejection, or interview-email rewrite; use `content-operator`.
- The user asks to create ATS records, send invitations, book interviews, change employment status, or modify HRIS settings; use `connector-operator` with explicit authorization and observed results.
- The prompt asks the workflow to make an unsupported candidate decision from protected characteristics or missing interview evidence; retain the process and evidence gap instead.

## Examples

Good example:

- Prompt: Create an interview scorecard and debrief plan for our first senior support hire.
- Expected behavior: Prepare role criteria, a structured scorecard, a debrief template, and decision-owner plan.
- Why: The request needs a fair hiring-process brief, not a claim that a candidate was evaluated or hired.

Bad example:

- Prompt: Send calendar invitations to every candidate for next Tuesday.
- Expected behavior: Route to `connector-operator`, not `people-ops`.
- Why: Sending invitations is an explicit external calendar action.

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

Use when a team needs a role brief, hiring plan, interview rubric, candidate-debrief structure, onboarding outline, or people-process decision support.

    Strong routing signals: `recruiting plan`, `interview scorecard`, `candidate debrief`, `채용 계획`, `면접 평가표`, `후보자 비교`

## Catalog Metadata

Category: `operations`
Phase: `people-operations`
Hermes role: `operator`
Quality tier: `evidence-gated`

Quality bar:

- Distinguish role outcomes from proxy criteria and missing evidence.
- Keep inclusion, privacy, policy, and decision-owner gaps visible.

Handoff policy:

Keep domain framing, clarification, source/evidence synthesis, draft outputs, and next-work routing in Hermes. A prepared brief, review, reply, or plan is not an external action, approval, filing, send, publish, data mutation, implementation, review, CI, or merge claim. Prepare a connector, file, coding, or human-review handoff only when the user explicitly accepts that next step; report it only from observed evidence. Hermes can prepare fair process guidance and interview artifacts; it cannot claim a candidate was contacted, evaluated, hired, rejected, or recorded in an HR system.

Required inputs:

- role or people-process outcome
- available evidence
- decision owner
- policy constraints

Expected outputs:

- role/outcome and must-have versus trainable-criteria brief
- structured interview scorecard and evidence-based debrief template
- hiring-process, interviewer, and decision-owner plan
- inclusion, privacy, policy, and missing-evidence flags with a next route

Artifact expectations:

- prepared people-operations brief when a wrapper captures it

Safety rules:

- Keep protected characteristics and missing interview evidence out of unsupported candidate recommendations.
- Do not claim HRIS, ATS, outreach, interview, or employment-status actions occurred.

## Runtime Evidence

Preferred harness for this skill: `ops-review`.

```sh
omh runtime record --skill people-ops --harness ops-review --status started
```

Record observed delegation results; otherwise return `not_available` or `not_observed`.

## Hermes Compatibility Contract

- Preserve workflow intent and stop conditions; verify before claiming completion.
- Use Hermes-native tools, file operations, and subagent/delegation features when available; do not require unavailable runtime tools, role prompts, or overlays. If a capability is unavailable: native subagents -> Hermes delegation when available, otherwise sequential lanes.
- Respect `omh_target_topology/v1`: bind state to the current target/thread, use single-target behavior when `active_agent_count` is one, and name a one-to-many or many-to-one change before treating it as persistent.
- Treat wrapper memory/context summaries as advisory local context, not proof of opaque Hermes memory reads or changes.
- Shared rail: `omh-routing/references/skill-common-rail.md` has harness discipline, runtime translations, the delegation command, and execution checklist. Load it when applicable; otherwise name an unavailable capability.
