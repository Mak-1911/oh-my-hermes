---
name: deliverable-package
description: [omh] Hermes deliverable package workflow: track PPT, PDF, XLSX, DOCX, HWP, Markdown, and attachments through prepared, generated, QA, approved, and attached states.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, deliverables]
    category: deliverables
    phase: package-status
    role: operator
    quality_tier: workflow-surface-gated
---

# Deliverable Package

This is a Hermes-native `deliverable-package` workflow skill.

## Why This Exists

`deliverable-package` exists so Hermes users can ask for this workflow in chat and receive a structured, evidence-bounded OMH operating surface instead of ad hoc narration.

## Do Not Use When

- The request is already handled by a narrower explicit skill with stronger evidence.
- The user asks OMH to secretly run external platforms, connectors, schedulers, file exports, or runtime agents.
- The only safe answer is to ask for missing authority, credentials, target, or observed evidence first.

## Examples

Good example:

- Prompt: deliverable-package turn this research into PPT and PDF with attachment status.
- Expected behavior: Produce `prepare_deliverable_package` with required context, wrapper actions, and not-evidence boundaries.
- Why: The prompt names a real workflow surface that Hermes can orchestrate without hiding execution.

Bad example:

- Prompt: deliverable-package claim the PDF was attached without observed file evidence.
- Expected behavior: Report the missing observed evidence or authority instead of claiming the external step happened.
- Why: Prepared OMH guidance is not platform, runtime, connector, file, memory, or delivery evidence.

## Completion Checklist

- The deliverable type, audience, source inputs, QA ladder, and delivery boundary are named.
- Prepared generation, generated file, render QA, approval, attachment, and delivery are separate states.
- The next action says whether to generate, revise, QA, approve, attach, or deliver.

## Recovery Notes

- If generation tooling is missing, prepare a prompt or package handoff and mark file output not_observed.
- If QA or attachment evidence is missing, keep generated/delivered states separate and show the next check.

## OMH Context Rail

- This skill is part of OMH's Hermes workflow layer, not a standalone executor.
- Product context: OMH is a Hermes-native workflow pack: choose skills, shape work, prepare artifacts, show status, and hand off with evidence boundaries.
- Current lane: **Materials and visual summaries** (`design-orchestration`, `design-quality-gate`, `frontend`, `accessibility-audit`, `visual-qa`, `content-operator`, `media-input-operator`, `materials-package`, `+3 more`) - web, accessibility, visual QA, files, and packages.
- If the user intent belongs to another OMH lane, hand back to `oh-my-hermes` or name the adjacent workflow instead of force-fitting this skill.
- Cross-skill context: every OMH skill: match lane; generic tool can render or execute.
- Generic-tool checkpoint: image->img-summary; frontend->frontend/a11y/visual-qa; paper->paper-learning; content->content-operator; media->media-input-operator; file->materials-package; search->web-research; live->live-info-operator; audit->workspace/production/security; failures->build-failure; verify->verification-gate; code->codegraph/onboarding/ultraprocess.
- Coverage: Every generated workflow skill carries this rail.
- Normal users talk to Hermes; OMH CLI is infra.
- Boundary: Prepared OMH routing, cards, handoffs, or artifacts are not observed execution, image generation, delivery, review, CI, merge-readiness, or merge evidence.

## Use When

Use when Hermes should prepare, request generation, QA, and report attachment status for user-visible file deliverables.

    Strong routing signals: `deliverable-package`, `deliverable mode`, `file attachment`, `attach file`, `attachment status`, `file delivery`, `file deliverable status`, `generated file`, `자료`, `첨부`, `첨부 상태`, `전달 상태`

## Catalog Metadata

Category: `deliverables`
Phase: `package-status`
Hermes role: `operator`
Quality tier: `workflow-surface-gated`

Quality bar:

- Name the user-facing workflow objective, required context, next action, and stop condition.
- Separate prepared guidance from observed platform, runtime, connector, file, memory, or delivery evidence.
- Expose missing tools, credentials, targets, or observations as user-visible gaps.

Handoff policy:

Keep this as Hermes-facing orchestration guidance first. Prepare executor, connector, gateway, or host-runtime handoff only when the user accepts that next step and observed evidence can be recorded.

Required inputs:

- user request
- target context
- delivery or status expectation
- known missing evidence

Expected outputs:

- deliverable-package/v1 card or guidance
- next action
- prepared-vs-observed boundary

Artifact expectations:

- deliverable-package/v1 metadata-only runtime or wrapper card when recorded

Safety rules:

- A deliverable package card is not binary generation, render QA, formula recalculation, approval, upload, attachment, or delivery evidence.
- Do not claim connector, gateway, runtime, file generation, memory mutation, or host automation evidence from prepared guidance.

## Runtime Evidence

Preferred harness for this skill: `deliverable-package`.

```sh
omh runtime record --skill deliverable-package --harness deliverable-package --status started
```

Record observed delegation results when Hermes or the wrapper exposes them. If delegation is unavailable, keep the result explicit as `not_available` or `not_observed`.

## Hermes Compatibility Contract

- Preserve the workflow intent, stop conditions, and verification discipline; verify with the smallest relevant test or inspection before claiming completion.
- Use Hermes-native tools, file operations, and subagent/delegation features when available, and do not require runtime tools, role prompts, or overlays that Hermes Agent does not expose. If Hermes cannot provide a required runtime capability, say so and fall back: native subagents -> Hermes delegation when available, otherwise sequential lanes.
- Respect `omh_target_topology/v1` when a wrapper reports it: bind state to the current target/thread, fall back to single-target behavior when `active_agent_count` is one, and give one concise setup-change comment before treating a one-to-many or many-to-one change as persistent.
- Treat wrapper-supplied memory/context summaries as advisory local context, not proof that opaque Hermes memory was read or changed.
- Shared rail: `oh-my-hermes/references/skill-common-rail.md` carries harness discipline, the runtime-mechanism translation table, the delegation-record command, and the execution-rule checklist. Load it when one of those applies; if it is not installed, name the unavailable capability instead of assuming it.
