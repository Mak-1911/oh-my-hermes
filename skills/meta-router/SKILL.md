---
name: meta-router
description: [omh] Meta-routing guidance for a leading /omh command: reason over the imperative task, consult the live workflow catalog, and select or chain the right workflow(s).
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, router]
    category: router
    phase: meta-routing
    role: guide
    quality_tier: routing-gated
---

# Meta Router

This is a Hermes-native `meta-router` workflow skill.

## Why This Exists

`meta-router` exists to turn a leading /omh command into a live catalog lookup: it reasons over the imperative task, selects or chains concrete workflows, and keeps the decision inside the observed/prepared evidence boundary instead of guessing from memory.

## Do Not Use When

- The /omh token is not the leading command token.
- The message is a bare picker alias or an OMH catalog/entrypoint question — those belong to oh-my-hermes.

## Examples

Good example:

- Prompt: /omh migrate this service off the deprecated API and add tests
- Expected behavior: Consult `omh recommend` on the remainder, then chain the recommended plan and executor workflows with explicit observed-vs-prepared evidence boundaries.
- Why: A leading /omh command with an imperative remainder is a meta-routing request that reasons over the live catalog rather than a memorized list.

Bad example:

- Prompt: omh add dark mode
- Expected behavior: Do not meta-route; a bare `omh` alias without a leading slash command is a picker/other-lane signal.
- Why: Meta-routing triggers only on a leading /omh or ./omh command token, not on a bare alias.

## Completion Checklist

- The selected workflow, confidence reason, evidence boundary, and user-facing next action are named.
- Low-confidence or conflicting signals return a picker or clarification instead of forced routing.
- Catalog answers are rendered without shell approval when wrapper metadata is sufficient.

## Recovery Notes

- If routing signals conflict, show the compact picker or ask one clarifying question.
- If wrapper metadata is unavailable, keep the recommendation advisory and avoid runtime claims.

## OMH Context Rail

- This skill is part of OMH's Hermes workflow layer, not a standalone executor.
- Product context: OMH is a Hermes-native workflow pack: choose skills, shape work, prepare artifacts, show status, and hand off with evidence boundaries.
- Current lane: **Intent -> plan** (`oh-my-hermes`, `meta-router`, `deep-interview`, `plan`, `ralplan`, `codebase-onboarding`, `codegraph-refresh`, `ultragoal`, `+4 more`) - clarify, plan, ship, or loop goals.
- If the user intent belongs to another OMH lane, hand back to `oh-my-hermes` or name the adjacent workflow instead of force-fitting this skill.
- Cross-skill context: every OMH skill: match lane; generic tool can render or execute.
- Generic-tool checkpoint: image->img-summary; frontend->frontend/a11y/visual-qa; paper->paper-learning; content->content-operator; media->media-input-operator; file->materials-package; search->web-research; live->live-info-operator; audit->workspace/production/security; failures->build-failure; verify->verification-gate; code->codegraph/onboarding/ultraprocess.
- Coverage: Every generated workflow skill carries this rail.
- Normal users talk to Hermes; OMH CLI is infra.
- Boundary: Prepared OMH routing, cards, handoffs, or artifacts are not observed execution, image generation, delivery, review, CI, merge-readiness, or merge evidence.

## Use When

Use when the user opens a message with the /omh or ./omh command followed by an imperative task; reason over the task, consult the live OMH catalog, and select or chain the right workflow(s).

    Strong routing signals: `/omh`, `./omh`

## Catalog Metadata

Category: `router`
Phase: `meta-routing`
Hermes role: `guide`
Quality tier: `routing-gated`

Quality bar:

- Route only from a leading `/omh` or `./omh` command token with a task remainder, never from a bare alias.
- Consult the live catalog on every decision instead of a memorized or embedded skill list.
- Exclude `meta-router` from its own recommendation output and choose the next best concrete workflow or chain.
- Report the routing decision as prepared guidance, not execution, review, CI, or merge evidence.

Handoff policy:

Reason over the /omh remainder, select or chain concrete workflows from the live catalog, and prepare a selected executor/runtime handoff only when the chosen chain requires code edits; do not execute code.

Required inputs:

- leading /omh or ./omh command with an imperative remainder
- live OMH catalog via bounded `omh recommend --json` queries
- available shell/CLI or plugin tool surface

Expected outputs:

- selected workflow or chain with rationale
- consulted catalog evidence from the bounded recommend output
- observed-vs-prepared evidence boundary for the routing decision

Artifact expectations:

- runtime run record when a wrapper can observe the meta-routing decision

Safety rules:

- Trigger only on a leading `/omh` or `./omh` command token with a task remainder; bare `/omh`, `./omh`, or `omh` without a slash is a picker/other-lane signal, not meta-routing.
- Shortlist candidates from the installed `references/catalog-index.md` (name plus one-line description per skill) when it is available, then confirm with `omh recommend "<remainder>" --json --limit 3` — the recommend output stays authoritative for the selection and its policy metadata; when the remainder spans multiple stages or the top recommendation is low-confidence, re-query `omh recommend` once per stage with a rephrased stage description instead of dumping the full catalog. Never run `omh docs workflows --json` or `omh list --json` in chat context — their full-catalog output does not fit a chat budget — and never rely on a memorized or embedded skill list; the catalog changes after `omh update`.
- Never select `meta-router` itself from the recommendation output; exclude it and route to the next best concrete workflow or chain.
- Report the selected workflow(s), why, and the observed-vs-prepared evidence boundary; a routing decision is not execution, review, CI, or merge evidence.
- If no shell/CLI surface is available, ask the wrapper to run the bounded `omh recommend` queries or use the plugin tool surface; never guess the catalog from memory — say the catalog is unavailable and offer the workflow picker instead.

## Runtime Evidence

Preferred harness for this skill: `coding-handling`.

```sh
omh runtime record --skill meta-router --harness coding-handling --status started
```

Record observed delegation results when Hermes or the wrapper exposes them. If delegation is unavailable, keep the result explicit as `not_available` or `not_observed`.

## Hermes Compatibility Contract

- Preserve the workflow intent, stop conditions, and verification discipline; verify with the smallest relevant test or inspection before claiming completion.
- Use Hermes-native tools, file operations, and subagent/delegation features when available, and do not require runtime tools, role prompts, or overlays that Hermes Agent does not expose. If Hermes cannot provide a required runtime capability, say so and fall back: native subagents -> Hermes delegation when available, otherwise sequential lanes.
- Respect `omh_target_topology/v1` when a wrapper reports it: bind state to the current target/thread, fall back to single-target behavior when `active_agent_count` is one, and give one concise setup-change comment before treating a one-to-many or many-to-one change as persistent.
- Treat wrapper-supplied memory/context summaries as advisory local context, not proof that opaque Hermes memory was read or changed.
- Shared rail: `oh-my-hermes/references/skill-common-rail.md` carries harness discipline, the runtime-mechanism translation table, the delegation-record command, and the execution-rule checklist. Load it when one of those applies; if it is not installed, name the unavailable capability instead of assuming it.
