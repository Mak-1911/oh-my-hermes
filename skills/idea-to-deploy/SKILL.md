---
name: idea-to-deploy
description: [omh] Hermes Idea-to-Deploy workflow: shape an app idea into decisions, delivery handoff, verification, release, and monitoring status.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, delivery]
    category: delivery
    phase: app-delivery-loop
    role: operator
    quality_tier: delivery-gated
---

# Idea To Deploy

This is a Hermes-native `idea-to-deploy` workflow skill.

## Why This Exists

`idea-to-deploy` exists to keep `delivery` work explicit, evidence-backed, and inside the Hermes/executor boundary instead of relying on ad hoc chat narration.

## Do Not Use When

- The request is casual chat, a status-only acknowledgement, or another workflow has stronger routing evidence.
- The user needs implementation, review, CI, merge, or external publishing evidence that has not been delegated or observed.

## Examples

Good example:

- Prompt: idea-to-deploy: turn this onboarding idea into a scoped plan, implementation handoff, QA gate, and release path.
- Expected behavior: Prepare the idea-to-release lane while keeping implementation, QA, and deploy evidence observed-only.
- Why: The request spans product shaping through deploy readiness instead of a single task.

Bad example:

- Prompt: idea-to-deploy: treat casual chat or unaccepted work as if this workflow already produced verified results.
- Expected behavior: Ask a clarification question or route to a narrower workflow instead of forcing `idea-to-deploy`.
- Why: The request lacks the required inputs or would overclaim work that Hermes did not observe.

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
- Current lane: **Coding handoff** (`idea-to-deploy`, `cto-loop`, `deploy-and-monitor`, `code-review`, `build-failure-triage`, `verification-gate`, `security-safety-review`, `ultrawork`, `+7 more`) - coding owners, handoffs, review, CI, and merge evidence.
- If intent belongs to another lane, hand back to `oh-my-hermes` or name the adjacent workflow.
- Cross-skill context: every OMH skill: match lane; generic tool can render or execute.
- Generic-tool checkpoint: image->img-summary; frontend->frontend/a11y/visual-qa; paper->paper-learning; content->content-operator; media->media-input-operator; file->materials-package; search->web-research; live->live-info-operator; audit->workspace/production/security; failures->build-failure; verify->verification-gate; code->codegraph/onboarding/ultraprocess.
- Coverage: Every generated workflow skill carries this rail.
- Normal users talk to Hermes; OMH CLI is infra.
- Boundary: Prepared OMH routing/cards/handoffs/artifacts are not observed execution, image generation, delivery, review, CI, merge-readiness, or merge evidence.

## Use When

Use when Hermes should carry a product or app idea through shaping, decision gates, plan acceptance, executor handoff, verification, release readiness, deploy, and monitoring boundaries.

    Strong routing signals: `idea-to-deploy`, `idea to deploy`, `from idea to deploy`, `plan to deploy`, `idea to launch`, `ship this idea`, `ship this feature`, `launch this feature`, `product delivery loop`, `app delivery loop`, `complete product loop`, `end-to-end app operation`, `완제품 루프`, `아이디어부터 배포`, `기획부터 배포`, `출시까지`, `앱 운영 루프`, `서비스로 만들어서 배포`, `아이디어를 서비스로`, `배포까지 가보자`, `ship this idea to production`

## Catalog Metadata

Category: `delivery`
Phase: `app-delivery-loop`
Hermes role: `operator`
Quality tier: `delivery-gated`

Quality bar:

- Name the idea, user value, decision owner, non-goals, and success metric before planning delivery.
- Expose idea, decision, plan, handoff, verification, release, deploy, and monitor stages as separate status steps.
- Prepare coding handoffs only after plan acceptance and selected executor/runtime choice.
- Mark deploy, monitoring, and rollback as unobserved until the wrapper or operator records evidence.

Handoff policy:

Keep idea shaping, decision gates, planning, release narration, and status in Hermes; prepare selected executor/runtime handoffs only for accepted code work and record deploy/monitoring only from observed operator or wrapper evidence.

Required inputs:

- product idea
- target user or customer signal
- success metric
- repo or app context

Expected outputs:

- stage rail
- decision gates
- executor handoff criteria
- verification and deploy/monitor status boundaries

Artifact expectations:

- app delivery loop status record when the wrapper captures stage acceptance or observations

Safety rules:

- Do not claim implementation, deploy, health checks, rollback, or monitoring happened from a prepared loop.
- Keep coding, release, and monitoring observations as separate evidence gates.
- Ask for missing success metric, release scope, or executor choice before preparing a handoff.

## Runtime Evidence

Preferred harness for this skill: `app-delivery-loop`.

```sh
omh runtime record --skill idea-to-deploy --harness app-delivery-loop --status started
```

Record observed delegation results when Hermes or the wrapper exposes them. If delegation is unavailable, keep the result explicit as `not_available` or `not_observed`.

## Hermes Compatibility Contract

- Preserve the workflow intent, stop conditions, and verification discipline; verify with the smallest relevant test or inspection before claiming completion.
- Use Hermes-native tools, file operations, and subagent/delegation features when available, and do not require runtime tools, role prompts, or overlays that Hermes Agent does not expose. If Hermes cannot provide a required runtime capability, say so and fall back: native subagents -> Hermes delegation when available, otherwise sequential lanes.
- Respect `omh_target_topology/v1` when a wrapper reports it: bind state to the current target/thread, fall back to single-target behavior when `active_agent_count` is one, and give one concise setup-change comment before treating a one-to-many or many-to-one change as persistent.
- When wrapper metadata includes `memory_review_card/v1` or `handoff_context_pack/v1`, treat it as reviewed OMH-local or wrapper-supplied context only. Use conflict-free context summaries to shape plans and handoffs, but do not claim Hermes internal memory was read or changed.
- Shared rail: `oh-my-hermes/references/skill-common-rail.md` carries harness discipline, the runtime-mechanism translation table, the delegation-record command, and the execution-rule checklist. Load it when one of those applies; if it is not installed, name the unavailable capability instead of assuming it.
