---
name: omh-data-analysis
description: [omh] Hermes data analysis workflow: scope supplied data with provenance, causal-claim, and hallucination guards. Use when the user says: data-analysis, data analysis, dataset analysis, csv analysis, json analysis, log analysis, table analysis, analyze csv.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, analysis]
    category: analysis
    phase: data-task
    role: guide
    quality_tier: workflow-surface-gated
---

# Data Analysis

This is a Hermes-native `data-analysis` workflow skill.

## Why This Exists

`data-analysis` exists so Hermes users can ask for this workflow in chat and receive a structured, evidence-bounded OMH operating surface instead of ad hoc narration.

## Do Not Use When

- The request is already handled by a narrower explicit skill with stronger evidence.
- The user asks OMH to secretly run external platforms, connectors, schedulers, file exports, or runtime agents.
- The only safe answer is to ask for missing authority, credentials, target, or observed evidence first.

## Examples

Good example:

- Prompt: data-analysis analyze this CSV and summarize anomalies by segment.
- Expected behavior: Produce `prepare_data_analysis_card` with required context, wrapper actions, and not-evidence boundaries.
- Why: The prompt names a real workflow surface that Hermes can orchestrate without hiding execution.

Bad example:

- Prompt: data-analysis invent trends from an unavailable spreadsheet.
- Expected behavior: Report the missing observed evidence or authority instead of claiming the external step happened.
- Why: Prepared OMH guidance is not platform, runtime, connector, file, memory, or delivery evidence.

## Completion Checklist

- Dataset or corpus source, record scope, schema or extraction method, join assumptions, analysis question, method, and stop condition are explicit.
- Numeric claims, anomalies, trends, segments, and log patterns are reported only from observed data or supplied evidence.
- Causal claims require observed identification evidence.
- Source acquisition, file conversion, report generation, and code fixes are routed to the narrower workflow when stronger.

## Recovery Notes

- If the data itself is missing, ask for the smallest dataset sample, schema, or query output needed.
- If the user wants datasets found online, route to source-finder before analysis.
- If the user wants a PPT/PDF/XLSX report generated from data, route to materials-package or deliverable-package after analysis scope is clear.

## OMH Context Rail

- This skill is part of OMH's Hermes workflow layer, not a standalone executor.
- Product context: OMH is a Hermes-native workflow pack: choose skills, shape work, prepare artifacts, show status, and hand off with evidence boundaries.
- Current lane: **Research and company ops** (`source-finder`, `web-research`, `best-practice-research`, `autoresearch-goal`, `research-brief`, `strategy-brief`, `feedback-triage`, `research-department`, `+6 more`) - research, signals, ops, and briefings.
- If intent belongs to another lane, hand back to `oh-my-hermes` or name the adjacent workflow.
- Cross-skill context: every OMH skill: match lane; generic tool can render or execute.
- Generic-tool checkpoint: image->img-summary; frontend->frontend/a11y/visual-qa; paper->paper-learning; content->content-operator; media->media-input-operator; file->materials-package; search->web-research; live->live-info-operator; audit->workspace/production/security; failures->build-failure; verify->verification-gate; code->codegraph/onboarding/ultraprocess.
- Coverage: Every generated workflow skill carries this rail.
- Normal users talk to Hermes; OMH CLI is infra.
- Boundary: Prepared OMH routing/cards/handoffs/artifacts are not observed execution, image generation, delivery, review, CI, merge-readiness, or merge evidence.

## Use When

Use when Hermes should prepare supplied structured, unstructured, or mixed data analysis without unsupported numeric or causal claims.

    Strong routing signals: `data-analysis`, `data analysis`, `dataset analysis`, `csv analysis`, `json analysis`, `log analysis`, `table analysis`, `analyze csv`, `analyze this csv`, `analyze json`, `analyze logs`, `summarize anomalies`, `anomaly analysis`, `trend analysis`, `segment analysis`, `column analysis`, `schema check`, `table to chart`, `chart with an executive summary`, `spreadsheet delta analysis`, `cohort analysis`, `retention analysis`, `correlation analysis`, `causal analysis`, `causality check`, `데이터 분석`, `csv 분석`, `json 분석`, `로그 분석`, `이상치 분석`, `추세 분석`, `오류 패턴`, `컬럼 분석`, `전환율 델타`, `차트 요약`, `상관관계 분석`, `인과 분석`, `인과관계`

## Catalog Metadata

Category: `analysis`
Phase: `data-task`
Hermes role: `guide`
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

- data_analysis_task_card/v1
- dataset_scope/v1
- analysis_method_plan/v1
- operations_data_harness/v1
- product_evidence_loop/v1
- analysis_result_summary/v1 when observed
- next action
- prepared-vs-observed boundary

Artifact expectations:

- data_analysis_task_card/v1 metadata-only wrapper card when prepared
- dataset_scope/v1 with source, row/record scope, columns or schema, filters, and stop condition
- analysis_method_plan/v1 naming summary, anomaly, trend, segment, schema, or log-pattern methods
- operations_data_harness/v1 for relationship and causal boundaries
- product_evidence_loop/v1 for prepared opaque data reference metadata
- analysis_result_summary/v1 only from observed data, calculations, query output, or supplied evidence

Safety rules:

- A data analysis card is not file extraction, query execution, chart generation, statistical proof, data correctness, hallucination-safe numeric evidence, association, or causality unless observed data and method evidence records it.
- Do not claim connector, gateway, runtime, file generation, memory mutation, or host automation evidence from prepared guidance.

## Runtime Evidence

Preferred harness for this skill: `data-analysis`.

```sh
omh runtime record --skill data-analysis --harness data-analysis --status started
```

Record observed delegation results; otherwise return `not_available` or `not_observed`.

## Hermes Compatibility Contract

- Preserve workflow intent and stop conditions; verify before claiming completion.
- Use Hermes-native tools, file operations, and subagent/delegation features when available; do not require unavailable runtime tools, role prompts, or overlays. If a capability is unavailable: native subagents -> Hermes delegation when available, otherwise sequential lanes.
- Respect `omh_target_topology/v1`: bind state to the current target/thread, use single-target behavior when `active_agent_count` is one, and name a one-to-many or many-to-one change before treating it as persistent.
- Treat wrapper memory/context summaries as advisory local context, not proof of opaque Hermes memory reads or changes.
- Shared rail: `omh-routing/references/skill-common-rail.md` has harness discipline, runtime translations, the delegation command, and execution checklist. Load it when applicable; otherwise name an unavailable capability.
