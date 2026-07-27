---
name: omh-ai-slop-cleaner
description: [omh] Hermes AI slop cleaner workflow: delete AI-generated slop, dead code, and duplication while observable behavior stays identical.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, maintenance]
    category: maintenance
    phase: cleanup
    role: handoff-guide
    quality_tier: regression-gated
---

# Ai Slop Cleaner

This is a Hermes-native `ai-slop-cleaner` workflow skill.

## Why This Exists

`ai-slop-cleaner` exists to keep `maintenance` work explicit, evidence-backed, and inside the Hermes/executor boundary instead of relying on ad hoc chat narration.

## Do Not Use When

- The goal is new or changed behavior rather than removing existing code; a plain refactor, feature, or fix request belongs to `ultraprocess`.
- The cleanup would change architecture, module boundaries, or carry regression risk that needs a reviewed plan first; use `ralplan`.
- The user wants existing code judged rather than changed; use `code-review` for a bug-first review and `failure-signal-audit` for swallowed failures.

## Examples

Good example:

- Prompt: $ai-slop-cleaner remove duplicated router branches and lock behavior with regression tests before refactoring.
- Expected behavior: Plan cleanup, preserve behavior, delete or simplify code, and prove it with targeted tests.
- Why: The request is maintenance cleanup with regression risk.

Bad example:

- Prompt: ai-slop-cleaner: treat casual chat or unaccepted work as if this workflow already produced verified results.
- Expected behavior: Ask a clarification question or route to a narrower workflow instead of forcing `ai-slop-cleaner`.
- Why: The request lacks the required inputs or would overclaim work that Hermes did not observe.

## Completion Checklist

- The selected coding or runtime owner is named before any implementation claim.
- Prepared handoff, dispatch, execution, verification, review, CI, and merge states are separated.
- The final status cites observed runtime evidence or keeps the work prepared_not_observed.
- When Hermes is the selected coding owner, use `hermes_coding_harness/v1` to keep builder, verifier, reviewer, docs, and PR lanes separate.
- Report the current harness stage, owner, next action, and missing evidence without claiming PR creation, review, CI, merge-readiness, or merge until matching runtime observations exist.

## Recovery Notes

- If the selected executor is unavailable, ask for Codex, Claude Code, Hermes, or another runtime before retrying.
- If dispatch or result evidence is missing, keep the handoff prepared_not_observed and expose the next observable action.

## OMH Context Rail

- This skill is part of OMH's Hermes workflow layer, not a standalone executor.
- Product context: OMH is a Hermes-native workflow pack: choose skills, shape work, prepare artifacts, show status, and hand off with evidence boundaries.
- Current lane: **Coding handoff** (`idea-to-deploy`, `cto-loop`, `deploy-and-monitor`, `code-review`, `build-failure-triage`, `verification-gate`, `security-safety-review`, `ultrawork`, `+7 more`) - coding owners, handoffs, review, CI, and merge evidence.
- If intent belongs to another lane, hand back to `oh-my-hermes` or name the adjacent workflow.
- Cross-skill context: every OMH skill: match lane; generic tool can render or execute.
- Generic-tool checkpoint: image->img-summary; frontend->frontend/a11y/visual-qa; paper->paper-learning; content->content-operator; media->media-input-operator; file->materials-package; search->web-research; live->live-info-operator; audit->workspace/production/security; failures->build-failure; verify->verification-gate; code->codegraph/onboarding/ultraprocess.
- Coverage: Every generated workflow skill carries this rail.
- Normal users talk to Hermes; OMH CLI is infra.
- Boundary: Prepared OMH routing/cards/handoffs/artifacts are not observed execution, image generation, delivery, review, CI, merge-readiness, or merge evidence.

## Use When

Use when the goal is removing existing low-quality, duplicated, or AI-generated code and the observable behavior must not change; lock behavior with tests before and after the edits.

    Strong routing signals: `ai-slop-cleaner`, `$ai-slop-cleaner`, `cleanup`, `deslop`, `refactor`, `risky`, `behavior-preserving refactor`, `risk analysis`, `refactor workflow`, `legacy refactor`, `리팩터링`, `리팩토링`, `위험 분석`, `변경 범위 제한`, `회귀 테스트`

## Catalog Metadata

Category: `maintenance`
Phase: `cleanup`
Hermes role: `handoff-guide`
Quality tier: `regression-gated`

Quality bar:

- Lock current behavior with regression checks before non-trivial cleanup.
- Prefer deletion, reuse, and boundary repair over new abstractions.
- Rerun verification after cleanup before claiming behavior is preserved.

Handoff policy:

Use Hermes to define cleanup scope and regression checks; route behavior-preserving edits to the selected coding runtime once tests are clear.

Executor readiness:

- When accepted work mutates code, check `executor_readiness/v1` for the selected Codex, Claude Code, Hermes, or oh-my runtime path before first dispatch.
- If readiness is `missing` or `blocked`, ask the user to choose another coding agent, configure PATH, continue in Hermes, or keep a prompt/runtime handoff; retry only after that state changes.
- A readiness probe is not dispatch, implementation, verification, review, CI, merge-readiness, or merge evidence.

Required inputs:

- target smell
- current behavior
- regression checks

Expected outputs:

- small cleanup diff
- before/after verification
- residual risk

Artifact expectations:

- cleanup plan and regression evidence for non-trivial work

Safety rules:

- Lock behavior with tests before risky cleanup.
- Prefer deletion and existing utilities over new layers.
- Do not add dependencies for cleanup unless explicitly requested.

## Runtime Evidence

Preferred harness for this skill: `coding-handling`.

```sh
omh runtime record --skill ai-slop-cleaner --harness coding-handling --status started
```

Record observed delegation results when Hermes or the wrapper exposes them. If delegation is unavailable, keep the result explicit as `not_available` or `not_observed`.

## Hermes Compatibility Contract

- Preserve the workflow intent, stop conditions, and verification discipline; verify with the smallest relevant test or inspection before claiming completion.
- Use Hermes-native tools, file operations, and subagent/delegation features when available, and do not require runtime tools, role prompts, or overlays that Hermes Agent does not expose. If Hermes cannot provide a required runtime capability, say so and fall back: native subagents -> Hermes delegation when available, otherwise sequential lanes.
- Respect `omh_target_topology/v1` when a wrapper reports it: bind state to the current target/thread, fall back to single-target behavior when `active_agent_count` is one, and give one concise setup-change comment before treating a one-to-many or many-to-one change as persistent.
- When wrapper metadata includes `memory_review_card/v1` or `handoff_context_pack/v1`, treat it as reviewed OMH-local or wrapper-supplied context only. Use conflict-free context summaries to shape plans and handoffs, but do not claim Hermes internal memory was read or changed.
- Shared rail: `oh-my-hermes/references/skill-common-rail.md` carries harness discipline, the runtime-mechanism translation table, the delegation-record command, and the execution-rule checklist. Load it when one of those applies; if it is not installed, name the unavailable capability instead of assuming it.
