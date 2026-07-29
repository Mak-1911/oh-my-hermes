---
name: omh-design-orchestration
description: [omh] Hermes design orchestration workflow: prepare a bounded design direction, existing-lane composition, and executor-neutral handoff. Use when the user says: design-orchestration, design orchestration, design ownership, handle this product design, take on the design, 디자인 맡겨, 디자인 맡겨줘, 디자인 전체 맡겨.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, materials]
    category: materials
    phase: design-orchestration
    role: operator
    quality_tier: design-orchestration-gated
---

# Design Orchestration

This is a Hermes-native `design-orchestration` workflow skill.

## Why This Exists

`design-orchestration` lets Hermes users say that they want design handled without making them manually compose four specialist lanes or confusing preparation with completed visual work.

## Do Not Use When

- The request is directly about premium multi-format quality or publishing; use `design-quality-gate`.
- The request is directly about frontend implementation, layout, responsive behavior, or a design system; use `frontend`.
- The request is directly about WCAG, keyboard, screen-reader, or semantic accessibility; use `accessibility-audit`.
- The request is directly about screenshots, visual regression, pixel diff, rendered layout, or a verdict; use `visual-qa`.

## Examples

Good example:

- Prompt: 디자인 맡겨줘. 기존 프로젝트 맥락을 먼저 보고, 방향과 구현·검증의 다음 단계를 잡아줘.
- Expected behavior: Prepare design_orchestration/v1 with opaque context references, deliberate direction, existing-lane composition, executor_selection_required, and not_observed visual evidence requirements.
- Why: The request delegates broad design ownership while leaving implementation and observed QA to the appropriate owners.

Bad example:

- Prompt: design-orchestration already rendered and visually passed the new page.
- Expected behavior: Keep rendering and visual PASS not_observed; route the required capture and verdict work to visual-qa.
- Why: A prepared orchestration contract cannot create implementation or rendered evidence.

## Completion Checklist

- The bounded intent, opaque context references, direction vocabulary, and avoid patterns are explicit.
- The four downstream lanes retain their direct ownership and the executor is still selection-required.
- The visual evidence contract keeps visual_verdict not_observed until fresh captures are recorded by the visual-QA owner.

## Recovery Notes

- If only a raw brief exists, let Hermes retain it in chat and create an opaque user-supplied reference instead of storing the brief.
- If the request narrows to implementation, accessibility, or rendered QA, route to the existing specialist rather than expanding this orchestration surface.

## OMH Context Rail

- This skill is part of OMH's Hermes workflow layer, not a standalone executor.
- Product context: OMH is a Hermes-native workflow pack: choose skills, shape work, prepare artifacts, show status, and hand off with evidence boundaries.
- Current lane: **Materials and visual summaries** (`design-orchestration`, `design-quality-gate`, `frontend`, `accessibility-audit`, `visual-qa`, `content-operator`, `media-input-operator`, `materials-package`, `+4 more`) - web, accessibility, visual QA, files, and packages.
- If intent belongs to another lane, hand back to `oh-my-hermes` or name the adjacent workflow.
- Cross-skill context: every OMH skill: match lane; generic tool can render or execute.
- Generic-tool checkpoint: image->img-summary; frontend->frontend/a11y/visual-qa; paper->paper-learning; content->content-operator; media->media-input-operator; file->materials-package; search->web-research; live->live-info-operator; audit->workspace/production/security; failures->build-failure; verify->verification-gate; code->codegraph/onboarding/ultraprocess.
- Coverage: Every generated workflow skill carries this rail.
- Normal users talk to Hermes; OMH CLI is infra.
- Boundary: Prepared OMH routing/cards/handoffs/artifacts are not observed execution, image generation, delivery, review, CI, merge-readiness, or merge evidence.

## Use When

Use when Hermes should take broad ownership of a design problem before a narrower quality, frontend, accessibility, or visual-QA lane is known.

    Strong routing signals: `design-orchestration`, `design orchestration`, `design ownership`, `handle this product design`, `take on the design`, `디자인 맡겨`, `디자인 맡겨줘`, `디자인 전체 맡겨`, `프로덕트 디자인 맡겨`

## Catalog Metadata

Category: `materials`
Phase: `design-orchestration`
Hermes role: `operator`
Quality tier: `design-orchestration-gated`

Quality bar:

- Make the design job, context boundary, direction, downstream lane ownership, and visual evidence requirements readable before handoff.
- Reject generic default drift by naming hierarchy, palette, typography, layout, signature element, and avoid patterns deliberately.
- Require the selected executor and fresh visual evidence separately before any implementation or quality completion claim.

Handoff policy:

Keep design intent, opaque project context references, deliberate direction, and existing-lane composition in Hermes; prepare an executor-neutral handoff only. The selected executor owns implementation, while existing visual-QA and web-QA paths own observed rendered evidence.

Required inputs:

- bounded target surface, audience, and primary task
- at least one opaque project, user, or Hermes context reference
- direction vocabulary and avoid-pattern selection
- executor selection and observed visual evidence remain pending

Expected outputs:

- design_orchestration/v1
- design intent and opaque context-reference boundary
- prepared direction vocabulary
- downstream composition: design-quality-gate, frontend, accessibility-audit, visual-qa
- executor-neutral handoff with executor_selection_required
- visual evidence requirements with visual_verdict not_observed

Artifact expectations:

- design_orchestration/v1 with prepared_not_observed status
- no raw project source, prompt, asset, path, or URL retention
- no executor target, dispatch, implementation, render, QA PASS, review, CI, deployment, or merge claim

Safety rules:

- Preserve the existing direct owners: design-quality-gate for premium multi-format quality, frontend for web implementation/design-system work, accessibility-audit for semantic access review, and visual-qa for fresh rendered verdicts.
- Do not use a prepared direction to claim code, screenshots, browser QA, accessibility PASS, review, CI, deployment, or merge.
- Keep free-form briefs in Hermes conversation context; persist only closed vocabulary and opaque reference metadata in the deterministic artifact.
- Do not call Claude Design, Figma, Open Design, an image provider, browser, network service, daemon, or executor from OMH core.

## Runtime Evidence

Preferred harness for this skill: `design-orchestration`.

```sh
omh runtime record --skill design-orchestration --harness design-orchestration --status started
```

Record observed delegation results; otherwise return `not_available` or `not_observed`.

## Hermes Compatibility Contract

- Preserve workflow intent and stop conditions; verify before claiming completion.
- Use Hermes-native tools, file operations, and subagent/delegation features when available; do not require unavailable runtime tools, role prompts, or overlays. If a capability is unavailable: native subagents -> Hermes delegation when available, otherwise sequential lanes.
- Respect `omh_target_topology/v1`: bind state to the current target/thread, use single-target behavior when `active_agent_count` is one, and name a one-to-many or many-to-one change before treating it as persistent.
- Treat wrapper memory/context summaries as advisory local context, not proof of opaque Hermes memory reads or changes.
- Shared rail: `omh-routing/references/skill-common-rail.md` has harness discipline, runtime translations, the delegation command, and execution checklist. Load it when applicable; otherwise name an unavailable capability.
