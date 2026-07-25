---
name: omh-skill
description: [omh] Hermes adaptation for managing local skills.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, operator]
    category: operator
    phase: skill-management
    role: tracker
    quality_tier: evidence-gated
---

# Skill

This is a Hermes-native `skill` workflow skill.

## Why This Exists

`skill` exists to keep `operator` work explicit, evidence-backed, and inside the Hermes/executor boundary instead of relying on ad hoc chat narration.

## Do Not Use When

- The request is casual chat, a status-only acknowledgement, or another workflow has stronger routing evidence.
- The user needs implementation, review, CI, merge, or external publishing evidence that has not been delegated or observed.

## Examples

Good example:

- Prompt: $skill list installed OMH skills and show the catalog metadata for each workflow.
- Expected behavior: Manage or inspect the skill catalog without claiming runtime execution or external evidence.
- Why: The request is operator skill management, not a user workflow run.

Bad example:

- Prompt: skill: treat casual chat or unaccepted work as if this workflow already produced verified results.
- Expected behavior: Ask a clarification question or route to a narrower workflow instead of forcing `skill`.
- Why: The request lacks the required inputs or would overclaim work that Hermes did not observe.

## Completion Checklist

- The local command, managed path, config surface, and state artifact inspected are named.
- Blocking issues, warnings, and optional surfaces are separated.
- The next repair action is explicit and does not claim a reload or runtime observation.

## Recovery Notes

- If a managed path or config key is missing, route to setup/update repair instead of editing hidden state.
- If a reload or plugin load was not observed, keep the diagnostic result as local health evidence only.

## OMH Context Rail

- This skill is part of OMH's Hermes workflow layer, not a standalone executor.
- Product context: OMH is a Hermes-native workflow pack: choose skills, shape work, prepare artifacts, show status, and hand off with evidence boundaries.
- Current lane: **Automation and status** (`achievements`, `workspace-audit`, `production-audit`, `automation-blueprint`, `github-event-ops`, `agent-board`, `gateway-intent-card`, `voice-operator`, `+29 more`) - schedules, status, health, and ops review.
- If intent belongs to another lane, hand back to `oh-my-hermes` or name the adjacent workflow.
- Cross-skill context: every OMH skill: match lane; generic tool can render or execute.
- Generic-tool checkpoint: image->img-summary; frontend->frontend/a11y/visual-qa; paper->paper-learning; content->content-operator; media->media-input-operator; file->materials-package; search->web-research; live->live-info-operator; audit->workspace/production/security; failures->build-failure; verify->verification-gate; code->codegraph/onboarding/ultraprocess.
- Coverage: Every generated workflow skill carries this rail.
- Normal users talk to Hermes; OMH CLI is infra.
- Boundary: Prepared OMH routing/cards/handoffs/artifacts are not observed execution, image generation, delivery, review, CI, merge-readiness, or merge evidence.

## Use When

Use for local skill listing, search, add, remove, or edit tasks.

    Strong routing signals: `skill`, `$skill`, `skills`, `manage skills`

## Catalog Metadata

Category: `operator`
Phase: `skill-management`
Hermes role: `tracker`
Quality tier: `evidence-gated`

Quality bar:

- Name the workflow target, constraints, validation evidence, and stop condition.
- Separate Hermes guidance from executor or wrapper behavior unless evidence proves the step happened.

Handoff policy:

Use Hermes for inventory and guidance; delegate only repository code changes to the selected coding executor.

Required inputs:

- skill action
- target skill name or directory

Expected outputs:

- skill inventory or mutation result
- verification note

Artifact expectations:

- manifest update when managed skills change

Safety rules:

- Do not imply hidden Hermes runtime behavior.
- Use the smallest verification that can prove the claim.

## Runtime Evidence

Preferred harness for this skill: `docs-specialist`.

```sh
omh runtime record --skill skill --harness docs-specialist --status started
```

Record observed delegation results when Hermes or the wrapper exposes them. If delegation is unavailable, keep the result explicit as `not_available` or `not_observed`.

## Hermes Compatibility Contract

- Preserve the workflow intent, stop conditions, and verification discipline; verify with the smallest relevant test or inspection before claiming completion.
- Use Hermes-native tools, file operations, and subagent/delegation features when available, and do not require runtime tools, role prompts, or overlays that Hermes Agent does not expose. If Hermes cannot provide a required runtime capability, say so and fall back: native subagents -> Hermes delegation when available, otherwise sequential lanes.
- Respect `omh_target_topology/v1` when a wrapper reports it: bind state to the current target/thread, fall back to single-target behavior when `active_agent_count` is one, and give one concise setup-change comment before treating a one-to-many or many-to-one change as persistent.
- Treat wrapper-supplied memory/context summaries as advisory local context, not proof that opaque Hermes memory was read or changed.
- Shared rail: `oh-my-hermes/references/skill-common-rail.md` carries harness discipline, the runtime-mechanism translation table, the delegation-record command, and the execution-rule checklist. Load it when one of those applies; if it is not installed, name the unavailable capability instead of assuming it.
