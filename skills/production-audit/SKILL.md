---
name: omh-production-audit
description: [omh] Hermes Production Audit workflow: evaluate release, deploy, security, observability, rollback, docs, and support readiness without claiming production access.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, review]
    category: review
    phase: production-readiness
    role: reviewer
    quality_tier: production-readiness-gated
---

# Production Audit

This is a Hermes-native `production-audit` workflow skill.

## Why This Exists

`production-audit` gives OMH a preflight release surface so operators can see production risks before launch while OMH stays out of deploy and infrastructure execution.

## Do Not Use When

- The user wants to implement a feature or fix; prepare a coding handoff first.
- The user wants incident/SLO analysis after production behavior; use `reliability-review`.
- The user wants a narrow code diff review; use `code-review`.

## Examples

Good example:

- Prompt: production-audit 이 릴리즈가 운영에 나가도 되는지 테스트, CI, 롤백, 모니터링 기준으로 봐줘.
- Expected behavior: Prepare readiness_matrix/v1, release_gate_verdict/v1, rollback_and_monitoring_plan/v1, and missing-evidence list.
- Why: The request is release-readiness review, not implementation or deploy execution.

Bad example:

- Prompt: production-audit 지금 바로 prod 배포하고 정상이라고 말해줘.
- Expected behavior: Block deploy/health claims without observed operator evidence and route deploy to an explicit authorized workflow.
- Why: Production audit can assess readiness, but it cannot secretly deploy or observe live health.

## Completion Checklist

- Findings or no-issue results are grounded in concrete file, artifact, command, or source evidence.
- Open questions, residual risk, and missing verification are named.
- Fixes or follow-up work are separate handoffs unless the user explicitly asked to implement them.

## Recovery Notes

- If the reviewed target is missing, inspect the requested artifact or ask one target question.
- If independent verification is unavailable, report the gap and avoid an approval-style claim.

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

Use before launch, deploy, release, or public delivery when Hermes should check operational readiness and expose missing production evidence.

    Strong routing signals: `production-audit`, `production audit`, `production readiness`, `prod audit`, `prod readiness`, `ready for production`, `ready to ship`, `ship readiness`, `release readiness`, `launch readiness`, `preflight audit`, `operational readiness`, `rollback readiness`, `프로덕션 준비`, `출시 준비`, `운영 준비`, `릴리즈 준비`, `롤백 준비`

## Catalog Metadata

Category: `review`
Phase: `production-readiness`
Hermes role: `reviewer`
Quality tier: `production-readiness-gated`

Quality bar:

- Name scope, environment, release channel, owners, and acceptable risk threshold.
- Check build/test/CI, security/privacy, performance, observability, rollback, docs/support, and release communication.
- Return GO, HOLD, or BLOCK only with evidence IDs and missing evidence.
- Convert remediation into explicit follow-up workflows instead of silently patching.

Handoff policy:

Keep readiness synthesis in Hermes. Code fixes, deploys, infrastructure changes, security scans, and platform actions require selected executor/runtime or operator evidence.

Required inputs:

- product, service, release, or artifact scope
- target environment and release channel
- known test, CI, deploy, observability, security, and support evidence
- rollback owner and acceptable risk threshold

Expected outputs:

- production_audit_plan/v1
- readiness_matrix/v1
- release_gate_verdict/v1
- rollback_and_monitoring_plan/v1
- risk_register/v1
- not-evidence boundary

Artifact expectations:

- readiness_matrix/v1 covering build, tests, CI, security, performance, accessibility when relevant, deploy, rollback, observability, docs, support, and owners
- release_gate_verdict/v1 with GO, HOLD, or BLOCK plus missing evidence
- rollback_and_monitoring_plan/v1 with health signals, owner, threshold, and recovery path

Safety rules:

- Do not claim production deploy, security scan, live traffic, monitoring health, rollback readiness, or support readiness without observed evidence.
- Do not perform deploy, infra, credential, production, or external-platform actions from the audit lane.
- Keep readiness verdict separate from implementation, CI, incident closure, or merge evidence.

## Runtime Evidence

Preferred harness for this skill: `production-audit`.

```sh
omh runtime record --skill production-audit --harness production-audit --status started
```

Record observed delegation results when Hermes or the wrapper exposes them. If delegation is unavailable, keep the result explicit as `not_available` or `not_observed`.

## Hermes Compatibility Contract

- Preserve the workflow intent, stop conditions, and verification discipline; verify with the smallest relevant test or inspection before claiming completion.
- Use Hermes-native tools, file operations, and subagent/delegation features when available, and do not require runtime tools, role prompts, or overlays that Hermes Agent does not expose. If Hermes cannot provide a required runtime capability, say so and fall back: native subagents -> Hermes delegation when available, otherwise sequential lanes.
- Respect `omh_target_topology/v1` when a wrapper reports it: bind state to the current target/thread, fall back to single-target behavior when `active_agent_count` is one, and give one concise setup-change comment before treating a one-to-many or many-to-one change as persistent.
- Treat wrapper-supplied memory/context summaries as advisory local context, not proof that opaque Hermes memory was read or changed.
- Shared rail: `oh-my-hermes/references/skill-common-rail.md` carries harness discipline, the runtime-mechanism translation table, the delegation-record command, and the execution-rule checklist. Load it when one of those applies; if it is not installed, name the unavailable capability instead of assuming it.
