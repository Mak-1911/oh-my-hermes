---
name: doctor
description: [omh] Hermes adaptation for diagnosing oh-my-hermes installation health.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, operator]
    category: operator
    phase: diagnostics
    role: tracker
    quality_tier: evidence-gated
---

# Doctor

This is a Hermes-native `doctor` workflow skill.

## Why This Exists

`doctor` exists to turn confusing install/setup states into grouped, local health evidence and the next repair action without treating a check as a fix.

## Do Not Use When

- The user is asking for a general product explanation rather than local health diagnostics.
- The requested change is a repository bug fix, not an installed-environment check.
- The wrapper wants to claim Hermes reload, skill execution, or plugin behavior that was not observed.

## Examples

Good example:

- Prompt: doctor after omh update says setup is next but Hermes skills still look stale.
- Expected behavior: Inspect managed skills, Hermes registration, runtime state, and next repair action with explicit proof boundaries.
- Why: The issue is local installation health and needs grouped diagnostic evidence.

Bad example:

- Prompt: doctor implement a new uninstall command UX.
- Expected behavior: Route to planning or implementation instead of health diagnostics.
- Why: That is product development work, not a local health check.

## Completion Checklist

- Command availability, managed skills, Hermes registration, runtime state, and optional surfaces are grouped separately.
- Blocking issues and warnings are separated, with one next repair action named for each blocking area.
- Plugin install, plugin import/register smoke, and Hermes runtime load are not collapsed into one claim.
- The final status says whether setup/update/doctor repaired anything or only observed health.

## Recovery Notes

- If managed skills are stale, recommend omh update or omh setup depending on whether registration also needs repair.
- If skills.external_dirs or Hermes config is missing, route to setup repair rather than editing hidden runtime state.
- If plugin register smoke fails, reinstall the plugin bundle with setup --with-plugin --force before claiming plugin readiness.
- If omh is missing from PATH, use the installer-reported absolute command path and then re-run doctor.

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

Use to diagnose OMH installation and Hermes config registration.

    Strong routing signals: `doctor`, `$doctor`, `diagnose omh`, `installation health`

## Catalog Metadata

Category: `operator`
Phase: `diagnostics`
Hermes role: `tracker`
Quality tier: `evidence-gated`

Quality bar:

- Name the workflow target, constraints, validation evidence, and stop condition.
- Separate Hermes guidance from executor or wrapper behavior unless evidence proves the step happened.

Handoff policy:

Run directly as local health inspection; propose executor work only when a repo fix is required.

Required inputs:

- omh home
- Hermes home
- observed issue

Expected outputs:

- health checks
- fix guidance
- known proof boundary

Artifact expectations:

- doctor state summary when runtime artifacts are writable

Safety rules:

- Do not imply hidden Hermes runtime behavior.
- Use the smallest verification that can prove the claim.

## Runtime Evidence

Preferred harness for this skill: `qa-specialist`.

```sh
omh runtime record --skill doctor --harness qa-specialist --status started
```

Record observed delegation results when Hermes or the wrapper exposes them. If delegation is unavailable, keep the result explicit as `not_available` or `not_observed`.

## Hermes Compatibility Contract

- Preserve the workflow intent, stop conditions, and verification discipline; verify with the smallest relevant test or inspection before claiming completion.
- Use Hermes-native tools, file operations, and subagent/delegation features when available, and do not require runtime tools, role prompts, or overlays that Hermes Agent does not expose. If Hermes cannot provide a required runtime capability, say so and fall back: native subagents -> Hermes delegation when available, otherwise sequential lanes.
- Respect `omh_target_topology/v1` when a wrapper reports it: bind state to the current target/thread, fall back to single-target behavior when `active_agent_count` is one, and give one concise setup-change comment before treating a one-to-many or many-to-one change as persistent.
- Treat wrapper-supplied memory/context summaries as advisory local context, not proof that opaque Hermes memory was read or changed.
- Shared rail: `oh-my-hermes/references/skill-common-rail.md` carries harness discipline, the runtime-mechanism translation table, the delegation-record command, and the execution-rule checklist. Load it when one of those applies; if it is not installed, name the unavailable capability instead of assuming it.
