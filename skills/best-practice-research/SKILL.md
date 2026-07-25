---
name: best-practice-research
description: [omh] Hermes adaptation for bounded official/upstream best-practice research.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, research]
    category: research
    phase: evidence
    role: researcher
    quality_tier: source-gated
---

# Best Practice Research

This is a Hermes-native `best-practice-research` workflow skill.

## Why This Exists

`best-practice-research` exists to keep `research` work explicit, evidence-backed, and inside the Hermes/executor boundary instead of relying on ad hoc chat narration.

## Do Not Use When

- The request is casual chat, a status-only acknowledgement, or another workflow has stronger routing evidence.
- The user needs implementation, review, CI, merge, or external publishing evidence that has not been delegated or observed.

## Examples

Good example:

- Prompt: best-practice-research: check official docs and upstream examples before we choose the plugin packaging pattern.
- Expected behavior: Gather primary-source guidance, compare options, and separate evidence from recommendation.
- Why: The request needs citation-backed best-practice research before implementation.

Bad example:

- Prompt: best-practice-research: treat casual chat or unaccepted work as if this workflow already produced verified results.
- Expected behavior: Ask a clarification question or route to a narrower workflow instead of forcing `best-practice-research`.
- Why: The request lacks the required inputs or would overclaim work that Hermes did not observe.

## Completion Checklist

- The research question, source boundaries, recency assumptions, and confidence level are named.
- Observed sources, inference, synthesis, and unresolved retrieval gaps are separated.
- Follow-up planning or handoff uses the research summary without calling it execution evidence.

## Recovery Notes

- If sources cannot be accessed, state the retrieval gap and use only observed local context.
- If evidence is thin or one-sided, lower confidence and ask for a narrower source boundary.

## OMH Context Rail

- This skill is part of OMH's Hermes workflow layer, not a standalone executor.
- Product context: OMH is a Hermes-native workflow pack: choose skills, shape work, prepare artifacts, show status, and hand off with evidence boundaries.
- Current lane: **Research and company ops** (`source-finder`, `web-research`, `best-practice-research`, `autoresearch-goal`, `research-brief`, `strategy-brief`, `feedback-triage`, `research-department`, `+6 more`) - research, signals, ops, and briefings.
- If the user intent belongs to another OMH lane, hand back to `oh-my-hermes` or name the adjacent workflow instead of force-fitting this skill.
- Cross-skill context: every OMH skill: match lane; generic tool can render or execute.
- Generic-tool checkpoint: image->img-summary; frontend->frontend/a11y/visual-qa; paper->paper-learning; content->content-operator; media->media-input-operator; file->materials-package; search->web-research; live->live-info-operator; audit->workspace/production/security; failures->build-failure; verify->verification-gate; code->codegraph/onboarding/ultraprocess.
- Coverage: Every generated workflow skill carries this rail.
- Normal users talk to Hermes; OMH CLI is infra.
- Boundary: Prepared OMH routing, cards, handoffs, or artifacts are not observed execution, image generation, delivery, review, CI, merge-readiness, or merge evidence.

## Use When

Use when correctness depends on current official or upstream guidance.

    Strong routing signals: `best-practice-research`, `best practice`, `official docs`, `upstream guidance`

## Catalog Metadata

Category: `research`
Phase: `evidence`
Hermes role: `researcher`
Quality tier: `source-gated`

Quality bar:

- Use official or upstream sources first and name the version/environment assumptions.
- Map applicability to the user's local context before recommending action.
- Preserve residual uncertainty instead of overstating best practice.

Handoff policy:

Run as Hermes-side evidence gathering; hand coding to the selected executor/runtime only after source-backed guidance is summarized.

Required inputs:

- chosen technology
- question
- version or environment constraints

Expected outputs:

- source-backed guidance
- applicability notes
- residual uncertainty

Artifact expectations:

- research notes or citations when the wrapper captures them

Safety rules:

- Do not imply hidden Hermes runtime behavior.
- Use the smallest verification that can prove the claim.

## Runtime Evidence

Preferred harness for this skill: `research`.

```sh
omh runtime record --skill best-practice-research --harness research --status started
```

Record observed delegation results when Hermes or the wrapper exposes them. If delegation is unavailable, keep the result explicit as `not_available` or `not_observed`.

## Hermes Compatibility Contract

- Preserve the workflow intent, stop conditions, and verification discipline; verify with the smallest relevant test or inspection before claiming completion.
- Use Hermes-native tools, file operations, and subagent/delegation features when available, and do not require runtime tools, role prompts, or overlays that Hermes Agent does not expose. If Hermes cannot provide a required runtime capability, say so and fall back: native subagents -> Hermes delegation when available, otherwise sequential lanes.
- Respect `omh_target_topology/v1` when a wrapper reports it: bind state to the current target/thread, fall back to single-target behavior when `active_agent_count` is one, and give one concise setup-change comment before treating a one-to-many or many-to-one change as persistent.
- Treat wrapper-supplied memory/context summaries as advisory local context, not proof that opaque Hermes memory was read or changed.
- Shared rail: `oh-my-hermes/references/skill-common-rail.md` carries harness discipline, the runtime-mechanism translation table, the delegation-record command, and the execution-rule checklist. Load it when one of those applies; if it is not installed, name the unavailable capability instead of assuming it.
