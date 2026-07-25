---
name: wiki
description: [omh] Hermes adaptation for retained knowledge capture and destination-aware external knowledge connection guidance.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, knowledge]
    category: knowledge
    phase: capture
    role: memory-keeper
    quality_tier: knowledge-gated
---

# Wiki

This is a Hermes-native `wiki` workflow skill.

## Why This Exists

`wiki` exists to keep `knowledge` work explicit, evidence-backed, and inside the Hermes/executor boundary instead of relying on ad hoc chat narration.

## Do Not Use When

- The request is casual chat, a status-only acknowledgement, or another workflow has stronger routing evidence.
- The user needs implementation, review, CI, merge, or external publishing evidence that has not been delegated or observed.

## Examples

Good example:

- Prompt: wiki: capture the router decisions and prepare Obsidian vault retrieval hints without claiming a write happened.
- Expected behavior: Prepare retained knowledge guidance with source context, destination-aware structure, staleness notes, and observed-write boundaries.
- Why: The request is knowledge capture with an external destination preference, not connector execution.

Bad example:

- Prompt: wiki: treat casual chat or unaccepted work as if this workflow already produced verified results.
- Expected behavior: Ask a clarification question or route to a narrower workflow instead of forcing `wiki`.
- Why: The request lacks the required inputs or would overclaim work that Hermes did not observe.

## Completion Checklist

- The durable fact, source evidence, destination preference, retrieval hint, and staleness risk are recorded.
- Destination-specific guidance is prepared for the named store or the unknown destination gap is explicit.
- No output claims an external write, query, connector invocation, or memory mutation without observed evidence.
- Separate coding or connector tasks are extracted instead of buried in notes.

## Recovery Notes

- If source evidence conflicts, route to memory or knowledge review before writing durable guidance.
- If the destination is unknown, record the missing destination facts and keep the guidance vendor-neutral.
- If the fact may be stale, record the staleness warning and next refresh action.

## OMH Context Rail

- This skill is part of OMH's Hermes workflow layer, not a standalone executor.
- Product context: OMH is a Hermes-native workflow pack: choose skills, shape work, prepare artifacts, show status, and hand off with evidence boundaries.
- Current lane: **Retained knowledge** (`memory-new`, `memory-sync`, `wiki`) - new/curated memory, wiki notes, retrieval, and staleness.
- If intent belongs to another lane, hand back to `oh-my-hermes` or name the adjacent workflow.
- Cross-skill context: every OMH skill: match lane; generic tool can render or execute.
- Generic-tool checkpoint: image->img-summary; frontend->frontend/a11y/visual-qa; paper->paper-learning; content->content-operator; media->media-input-operator; file->materials-package; search->web-research; live->live-info-operator; audit->workspace/production/security; failures->build-failure; verify->verification-gate; code->codegraph/onboarding/ultraprocess.
- Coverage: Every generated workflow skill carries this rail.
- Normal users talk to Hermes; OMH CLI is infra.
- Boundary: Prepared OMH routing/cards/handoffs/artifacts are not observed execution, image generation, delivery, review, CI, merge-readiness, or merge evidence.

## Use When

Use to capture durable project knowledge and prepare destination-aware wiki guidance for markdown vaults, Obsidian, Notion, Google Drive/Docs, databases, local folders, or unknown external knowledge targets.

    Strong routing signals: `wiki`, `project wiki`, `memory`, `notes`, `external knowledge store`, `knowledge base`, `Obsidian`, `markdown vault`, `Notion knowledge base`, `Google Drive wiki`, `옵시디언`, `마크다운 볼트`, `노션 지식베이스`

## Catalog Metadata

Category: `knowledge`
Phase: `capture`
Hermes role: `memory-keeper`
Quality tier: `knowledge-gated`

Quality bar:

- Capture durable facts with source evidence and destination-aware retrieval hints.
- Treat Obsidian as one vendor hint under a broader external knowledge connection model.
- Never present prepared wiki guidance as an observed external write, query, connector, or memory mutation.
- Mark stale or uncertain knowledge instead of presenting it as permanent truth.
- Extract separate coding tasks instead of burying them in notes.

Handoff policy:

Run directly in Hermes as retained knowledge capture; prepare connector/runtime handoff only when a separate observed external write or coding task is explicitly required.

Required inputs:

- project fact
- source evidence
- target topic
- destination preference when supplied

Expected outputs:

- retained knowledge note guidance
- destination-aware organization and retrieval hint
- staleness warning when needed
- prepared-versus-observed external write boundary

Artifact expectations:

- repo-local markdown knowledge artifact or metadata-only destination guidance

Safety rules:

- Do not imply hidden Hermes runtime behavior.
- Use the smallest verification that can prove the claim.

## Runtime Evidence

Preferred harness for this skill: `docs-specialist`.

```sh
omh runtime record --skill wiki --harness docs-specialist --status started
```

Record observed delegation results when Hermes or the wrapper exposes them. If delegation is unavailable, keep the result explicit as `not_available` or `not_observed`.

## Hermes Compatibility Contract

- Preserve the workflow intent, stop conditions, and verification discipline; verify with the smallest relevant test or inspection before claiming completion.
- Use Hermes-native tools, file operations, and subagent/delegation features when available, and do not require runtime tools, role prompts, or overlays that Hermes Agent does not expose. If Hermes cannot provide a required runtime capability, say so and fall back: native subagents -> Hermes delegation when available, otherwise sequential lanes.
- Respect `omh_target_topology/v1` when a wrapper reports it: bind state to the current target/thread, fall back to single-target behavior when `active_agent_count` is one, and give one concise setup-change comment before treating a one-to-many or many-to-one change as persistent.
- Treat wrapper-supplied memory/context summaries as advisory local context, not proof that opaque Hermes memory was read or changed.
- Shared rail: `oh-my-hermes/references/skill-common-rail.md` carries harness discipline, the runtime-mechanism translation table, the delegation-record command, and the execution-rule checklist. Load it when one of those applies; if it is not installed, name the unavailable capability instead of assuming it.
