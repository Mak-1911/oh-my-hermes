---
name: omh-memory-new
description: [omh] Hermes new-memory capture workflow: add reviewed project, product, or durable context candidates through capture, review, and approve actions. Use when the user says: memory-new, new memory, project memory, product memory, remember this project, remember this product, memory capture, capture memory.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, memory]
    category: memory
    phase: candidate-capture
    role: memory-keeper
    quality_tier: workflow-surface-gated
---

# Memory New

This is a Hermes-native `memory-new` workflow skill.

## Why This Exists

`memory-new` exists so Hermes users can ask for this workflow in chat and receive a structured, evidence-bounded OMH operating surface instead of ad hoc narration.

## Do Not Use When

- The request is already handled by a narrower explicit skill with stronger evidence.
- The user asks OMH to secretly run external platforms, connectors, schedulers, file exports, or runtime agents.
- The only safe answer is to ask for missing authority, credentials, target, or observed evidence first.

## Examples

Good example:

- Prompt: memory-new capture this product decision as a project-memory candidate for review.
- Expected behavior: Produce `prepare_memory_new` with required context, wrapper actions, and not-evidence boundaries.
- Why: The prompt names a real workflow surface that Hermes can orchestrate without hiding execution.

Bad example:

- Prompt: memory-new claim Hermes already remembers this internally without an observed native-memory write.
- Expected behavior: Report the missing observed evidence or authority instead of claiming the external step happened.
- Why: Prepared OMH guidance is not platform, runtime, connector, file, memory, or delivery evidence.

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
- Current lane: **Retained knowledge** (`memory-new`, `memory-sync`, `decision-recall`, `wiki`) - memory, rejected alternatives, wiki notes, retrieval, and staleness.
- If intent belongs to another lane, hand back to `oh-my-hermes` or name the adjacent workflow.
- Cross-skill context: every OMH skill: match lane; generic tool can render or execute.
- Generic-tool checkpoint: image->img-summary; frontend->frontend/a11y/visual-qa; paper->paper-learning; content->content-operator; media->media-input-operator; file->materials-package; search->web-research; live->live-info-operator; audit->workspace/production/security; failures->build-failure; verify->verification-gate; code->codegraph/onboarding/ultraprocess.
- Coverage: Every generated workflow skill carries this rail.
- Normal users talk to Hermes; OMH CLI is infra.
- Boundary: Prepared OMH routing/cards/handoffs/artifacts are not observed execution, image generation, delivery, review, CI, merge-readiness, or merge evidence.

## Candidate Flow

- **capture -> review -> approve** — capture a new durable fact as `memory_new_candidate/v1`, review its scope, source, conflicts, duplicates, and target store, then approve or reject it.
- **Candidate first** — capture adds a candidate. It does not create an approved record until the review decision and target write are observed.
- **OMH project memory** — the default durable project/product/context store is reviewed OMH-local project memory under `.omh/memory/`.
- **Hermes native memory** — when the user also wants Hermes to remember the fact natively, prepare that as an optional second target with its own approval and observed write evidence.
- **Dual-store pattern** — one approved fact may target OMH project memory, Hermes native memory, or both; keep the two write states separate.
- **Stop condition** — stop once approval is recorded or the candidate is rejected; do not drift into existing-memory cleanup.

## Boundary

OMH project memory does not mutate Hermes internal memory. A `memory_new_candidate/v1` artifact is prepared context only, not an approved OMH project-memory record, Hermes native-memory write, or proof that either store changed. Record target writes only when observed: OMH project-memory approval is not Hermes native-memory evidence, and Hermes native-memory approval is not OMH project-memory evidence.

## Use When

Use when the user wants to add new durable project, product, or context memory as an OMH project-memory candidate, with optional separate Hermes native-memory capture after review.

    Strong routing signals: `memory-new`, `new memory`, `project memory`, `product memory`, `remember this project`, `remember this product`, `memory capture`, `capture memory`, `save project memory`, `save product memory`, `project context memory`, `product context memory`, `add memory candidate`, `프로젝트 메모리 저장`, `제품 메모리 저장`, `프로젝트 기억`, `제품 기억`, `새 기억`, `기억 추가`, `메모리 캡처`

## Catalog Metadata

Category: `memory`
Phase: `candidate-capture`
Hermes role: `memory-keeper`
Quality tier: `workflow-surface-gated`

Quality bar:

- Name the user-facing workflow objective, required context, next action, and stop condition.
- Separate prepared guidance from observed platform, runtime, connector, file, memory, or delivery evidence.
- Expose missing tools, credentials, targets, or observations as user-visible gaps.
- Name the durable fact, project or product scope, source context, target store, review decision, and duplication or conflict check.

Handoff policy:

Keep this as Hermes-facing orchestration guidance first. Prepare executor, connector, gateway, or host-runtime handoff only when the user accepts that next step and observed evidence can be recorded.

Required inputs:

- user request
- target context
- delivery or status expectation
- known missing evidence

Expected outputs:

- memory_new_candidate/v1
- capture/review/approve decision
- OMH project-memory and optional Hermes native-memory targets
- prepared-vs-observed boundary

Artifact expectations:

- memory_new_candidate/v1 metadata-only candidate when recorded

Safety rules:

- An OMH project-memory candidate is prepared local context only; it does not mutate Hermes internal memory, and optional Hermes native-memory capture requires separate observed approval and write evidence.
- Do not claim connector, gateway, runtime, file generation, memory mutation, or host automation evidence from prepared guidance.
- Add candidates before approval; do not present capture as an approved OMH project-memory record.
- Keep OMH project memory and Hermes native memory as separate stores with separate write evidence.

## Harness

- Use `memory-new` to keep candidate capture, review, approval, and observed writes distinct.
- Route stale, conflicting, duplicate, overgeneralized, or risky existing `USER.md`/`MEMORY.md` facts to `memory-sync`.
- Prefer one durable fact per candidate and preserve the project/product scope and source context.
- State the new durable fact, scope, source, target store, and review owner before capture; add the candidate before requesting approval, and verify target-specific write evidence before claiming persistence.

## Runtime Evidence

Preferred harness for this skill: `memory-new`.

```sh
omh runtime record --skill memory-new --harness memory-new --status started
```

Record observed delegation results; otherwise return `not_available` or `not_observed`.

## Hermes Compatibility Contract

- Preserve workflow intent and stop conditions; verify before claiming completion.
- Use Hermes-native tools, file operations, and subagent/delegation features when available; do not require unavailable runtime tools, role prompts, or overlays. If a capability is unavailable: native subagents -> Hermes delegation when available, otherwise sequential lanes.
- Respect `omh_target_topology/v1`: bind state to the current target/thread, use single-target behavior when `active_agent_count` is one, and name a one-to-many or many-to-one change before treating it as persistent.
- Treat wrapper memory/context summaries as advisory local context, not proof of opaque Hermes memory reads or changes.
- Shared rail: `omh-routing/references/skill-common-rail.md` has harness discipline, runtime translations, the delegation command, and execution checklist. Load it when applicable; otherwise name an unavailable capability.
