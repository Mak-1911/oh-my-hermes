---
name: omh-decision-recall
description: [omh] Recall scoped reviewed rejected decisions without elevating them to approved memory.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, memory]
    category: memory
    phase: decision-recall
    role: memory-keeper
    quality_tier: workflow-surface-gated
---

# Decision Recall

This is a Hermes-native `decision-recall` workflow skill.

## Why This Exists

`decision-recall` exists so Hermes users can ask for this workflow in chat and receive a structured, evidence-bounded OMH operating surface instead of ad hoc narration.

## Do Not Use When

- The request is already handled by a narrower explicit skill with stronger evidence.
- The user asks OMH to secretly run external platforms, connectors, schedulers, file exports, or runtime agents.
- The only safe answer is to ask for missing authority, credentials, target, or observed evidence first.

## Examples

Good example:

- Prompt: Show rejected decisions for this project before we choose an alternative.
- Expected behavior: Produce `show_rejected_decision_recall` with required context, wrapper actions, and not-evidence boundaries.
- Why: The prompt names a real workflow surface that Hermes can orchestrate without hiding execution.

Bad example:

- Prompt: Claim the recalled rejected decision is an approved memory write or proof the replacement ran.
- Expected behavior: Report the missing observed evidence or authority instead of claiming the external step happened.
- Why: Prepared OMH guidance is not platform, runtime, connector, file, memory, or delivery evidence.

## Completion Checklist

- The query, scope, tags, stale policy, and match limit are explicit.
- Only reviewed rejected candidates are returned; expired candidates stay excluded.
- Recall output is not presented as approved memory, source freshness, or execution evidence.

## Recovery Notes

- If required context is missing, ask one blocking question or route back to the narrower workflow.
- If runtime or wrapper evidence is unavailable, keep the status as not_observed and expose the next observable action.

## OMH Context Rail

- This skill is part of OMH's Hermes workflow layer, not a standalone executor.
- Product context: OMH is a Hermes-native workflow pack: choose skills, shape work, prepare artifacts, show status, and hand off with evidence boundaries.
- Current lane: **Retained knowledge** (`memory-new`, `memory-sync`, `decision-recall`, `wiki`) - memory, rejected alternatives, wiki notes, retrieval, and staleness.
- If intent belongs to another lane, hand back to `oh-my-hermes` or name the adjacent workflow.
- Cross-skill context: every OMH skill: match lane; generic tool can render or execute.
- Generic-tool checkpoint: image->img-summary; frontend->frontend/a11y/visual-qa; paper->paper-learning; content->content-operator; media->media-input-operator; file->materials-package; search->web-research; live->live-info-operator; audit->workspace/production/security; failures->build-failure; verify->verification-gate; code->codegraph/onboarding/ultraprocess.
- Coverage: Every generated workflow skill carries this rail.
- Normal users talk to Hermes; OMH CLI is infra.
- Boundary: Prepared OMH routing/cards/handoffs/artifacts are not observed execution, image generation, delivery, review, CI, merge-readiness, or merge evidence.

## Use When

Use for scoped reviewed rejected-decision context; it is not approved memory or execution evidence.

    Strong routing signals: `decision-recall`, `rejected decision recall`, `rejected decisions`, `why was this rejected`, `previously rejected alternative`, `거절된 결정`, `기각된 대안`

## Catalog Metadata

Category: `memory`
Phase: `decision-recall`
Hermes role: `memory-keeper`
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

- rejected_decision_recall/v1
- scoped rejected-decision matches
- claim boundary

Artifact expectations:

- rejected_decision_recall/v1 metadata-only recall result

Safety rules:

- Rejected-decision context is reviewed OMH-local context, not approved memory, Hermes memory, or execution evidence.
- Do not claim connector, gateway, runtime, file generation, memory mutation, or host automation evidence from prepared guidance.

## Runtime Evidence

Preferred harness for this skill: `decision-recall`.

```sh
omh runtime record --skill decision-recall --harness decision-recall --status started
```

Record observed delegation results; otherwise return `not_available` or `not_observed`.

## Hermes Compatibility Contract

- Preserve workflow intent and stop conditions; verify before claiming completion.
- Use Hermes-native tools, file operations, and subagent/delegation features when available; do not require unavailable runtime tools, role prompts, or overlays. If a capability is unavailable: native subagents -> Hermes delegation when available, otherwise sequential lanes.
- Respect `omh_target_topology/v1`: bind state to the current target/thread, use single-target behavior when `active_agent_count` is one, and name a one-to-many or many-to-one change before treating it as persistent.
- Treat wrapper memory/context summaries as advisory local context, not proof of opaque Hermes memory reads or changes.
- Shared rail: `oh-my-hermes/references/skill-common-rail.md` has harness discipline, runtime translations, the delegation command, and execution checklist. Load it when applicable; otherwise name an unavailable capability.
