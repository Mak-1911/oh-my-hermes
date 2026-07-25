---
name: agent-board
description: [omh] Hermes agent board workflow: coordinate multiple Hermes profiles or agents with task, handoff, heartbeat, blocker, and completion states.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, agent-coordination]
    category: agent-coordination
    phase: board-status
    role: tracker
    quality_tier: workflow-surface-gated
---

# Agent Board

This is a Hermes-native `agent-board` workflow skill.

## Why This Exists

`agent-board` exists so Hermes users can ask for this workflow in chat and receive a structured, evidence-bounded OMH operating surface instead of ad hoc narration.

## Do Not Use When

- The request is already handled by a narrower explicit skill with stronger evidence.
- The user asks OMH to secretly run external platforms, connectors, schedulers, file exports, or runtime agents.
- The only safe answer is to ask for missing authority, credentials, target, or observed evidence first.

## Examples

Good example:

- Prompt: agent-board coordinate PM, CTO, QA, and release agents on this launch checklist.
- Expected behavior: Produce `prepare_agent_board_card` with required context, wrapper actions, and not-evidence boundaries.
- Why: The prompt names a real workflow surface that Hermes can orchestrate without hiding execution.

Bad example:

- Prompt: agent-board mark the other agent complete without an observed heartbeat or result.
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
- Current lane: **Automation and status** (`achievements`, `workspace-audit`, `production-audit`, `automation-blueprint`, `github-event-ops`, `agent-board`, `gateway-intent-card`, `voice-operator`, `+29 more`) - schedules, status, health, and ops review.
- If intent belongs to another lane, hand back to `oh-my-hermes` or name the adjacent workflow.
- Cross-skill context: every OMH skill: match lane; generic tool can render or execute.
- Generic-tool checkpoint: image->img-summary; frontend->frontend/a11y/visual-qa; paper->paper-learning; content->content-operator; media->media-input-operator; file->materials-package; search->web-research; live->live-info-operator; audit->workspace/production/security; failures->build-failure; verify->verification-gate; code->codegraph/onboarding/ultraprocess.
- Coverage: Every generated workflow skill carries this rail.
- Normal users talk to Hermes; OMH CLI is infra.
- Boundary: Prepared OMH routing/cards/handoffs/artifacts are not observed execution, image generation, delivery, review, CI, merge-readiness, or merge evidence.

## Use When

Use when multiple Hermes profiles, agents, or targets need a board-shaped status contract for collaborative work.

    Strong routing signals: `agent-board`, `agent board`, `kanban`, `multi-agent`, `multi agent`, `multi agent board`, `multiple hermes agents`, `multiple hermes profiles`, `hermes profiles`, `subagent`, `subagents`, `sub agent`, `sub agents`, `agent coordination`, `agent task board`, `task board`, `roles and board`, `role board`, `heartbeat`, `blocker`, `agent blocker`, `agent heartbeat`, `agent handoff`, `handoff board`, `interviewer reviewer builder`, `reviewer builder`, `칸반`, `멀티 에이전트`, `서브에이전트`, `서브 에이전트`, `여러 에이전트`, `Hermes agent 여러 명`, `여러 명이 같이 일`, `에이전트 보드`, `작업 배분`, `역할 배분`, `작업 보드`, `역할과 보드`, `역할 보드`

## Catalog Metadata

Category: `agent-coordination`
Phase: `board-status`
Hermes role: `tracker`
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

- agent-board/v1 card or guidance
- next action
- prepared-vs-observed boundary

Artifact expectations:

- agent-board/v1 metadata-only runtime or wrapper card when recorded

Safety rules:

- An agent board card is not proof that another Hermes agent accepted, executed, heartbeat-ed, or completed work unless target-specific evidence exists.
- Do not claim connector, gateway, runtime, file generation, memory mutation, or host automation evidence from prepared guidance.

## Runtime Evidence

Preferred harness for this skill: `agent-board`.

```sh
omh runtime record --skill agent-board --harness agent-board --status started
```

Record observed delegation results when Hermes or the wrapper exposes them. If delegation is unavailable, keep the result explicit as `not_available` or `not_observed`.

## Hermes Compatibility Contract

- Preserve the workflow intent, stop conditions, and verification discipline; verify with the smallest relevant test or inspection before claiming completion.
- Use Hermes-native tools, file operations, and subagent/delegation features when available, and do not require runtime tools, role prompts, or overlays that Hermes Agent does not expose. If Hermes cannot provide a required runtime capability, say so and fall back: native subagents -> Hermes delegation when available, otherwise sequential lanes.
- Respect `omh_target_topology/v1` when a wrapper reports it: bind state to the current target/thread, fall back to single-target behavior when `active_agent_count` is one, and give one concise setup-change comment before treating a one-to-many or many-to-one change as persistent.
- Treat wrapper-supplied memory/context summaries as advisory local context, not proof that opaque Hermes memory was read or changed.
- Shared rail: `oh-my-hermes/references/skill-common-rail.md` carries harness discipline, the runtime-mechanism translation table, the delegation-record command, and the execution-rule checklist. Load it when one of those applies; if it is not installed, name the unavailable capability instead of assuming it.
