---
name: ulw-research
description: [omh] Web research with citation discipline on top of native search - every claim carries a live URL and unfetched claims stay not observed; for a decision-ready brief use research-brief, and for ongoing Scout/Analyst/Briefer coordination use research-department. Use when the user says: web-research, web research, web search, search the web, internet search, fresh sources, current sources, current web evidence.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, research]
    category: research
    phase: current-evidence
    role: researcher
    quality_tier: source-gated
---

# Web Research

This is a Hermes-native `web-research` workflow skill.

## Why This Exists

`web-research` exists to make Hermes a careful source-backed research operator: it routes web/current-source requests to evidence gathering, keeps retrieval gaps visible, and prevents search plans from being reported as observed facts.

## Do Not Use When

- The user asks for a full plan-to-PR delivery cycle; use `ultraprocess` or a planning workflow after research instead.
- The request is purely local repo inspection with no external, current, citation, or source-comparison need.
- The user needs coding execution, review, CI, or merge evidence rather than research synthesis.
- The requested output is a typed candidate list or acquisition status without factual synthesis; use `source-finder`.
- The user needs a market, customer, or pricing decision brief with evidence-versus-inference treatment; use `research-brief`.
- Correctness is a bounded, versioned official or upstream guidance question; use `best-practice-research`.

## Examples

Good example:

- Prompt: 웹서치해서 최신 자료와 출처를 정리해줘.
- Expected behavior: Run the Hermes web-research lane, ask for or state source boundaries and freshness, then summarize citations, confidence, and retrieval gaps.
- Why: The request explicitly asks for web search, current material, and sources without asking for implementation.

Bad example:

- Prompt: 웹리서치부터 계획, 구현, 리뷰, 문서, PR까지 한 사이클로 끝내줘.
- Expected behavior: Route to `ultraprocess` because the user asked for a bounded delivery cycle, not a research-only lane.
- Why: Research is only one stage of the requested delivery process.

## Completion Checklist

- The research question, source boundaries, recency assumptions, and confidence level are named.
- Observed sources, inference, synthesis, and unresolved retrieval gaps are separated.
- Follow-up planning or handoff uses the research summary without calling it execution evidence.

## Recovery Notes

- If sources cannot be accessed, state the retrieval gap and use only observed local context.
- If evidence is thin or one-sided, lower confidence and ask for a narrower source boundary.

## Workflow Lane

- Current lane: **Research and company ops** (`source-finder`, `web-research`, `best-practice-research`, `autoresearch-goal`, `research-brief`, `strategy-brief`, `feedback-triage`, `research-department`, `+12 more`) - research, signals, ops, and briefings.
- If intent belongs to another lane, hand back to `oh-my-hermes` or name the adjacent workflow.
- Shared product, routing, compatibility, and evidence rules: `omh-routing/references/skill-common-rail.md`.

## Use When

Use for current web evidence, links, citations, source diversity, or comparison before planning or handoff, including AI-agent usability research.

    Strong routing signals: `web-research`, `web research`, `web search`, `search the web`, `internet search`, `fresh sources`, `current sources`, `current web evidence`, `source-backed research`, `source search`, `find sources`, `find citations`, `citation check`, `evidence scan`, `source diversity`, `retrieval gap`, `look up`, `look up sources`, `latest sources`, `research plan`, `웹서치`, `웹 서치`, `웹 검색`, `인터넷 검색`, `검색해줘`, `검색해서`, `최신 자료`, `최신 출처`, `자료 찾아`, `조사`, `근거`, `출처`, `고객 피드백`, `literature review`, `research literature`, `review recent papers`, `문헌 검토`, `논문들 검토`

## Catalog Metadata

Category: `research`
Phase: `current-evidence`
Hermes role: `researcher`
Quality tier: `source-gated`
Reasoning demand: `standard`

Quality bar:

- Ask for the research question, source boundaries, freshness, jurisdiction, and version assumptions before retrieval.
- Use official or primary sources first when current or external facts matter, then add source diversity when the topic is contested.
- Revise the search plan when new evidence exposes a gap or contradiction instead of stopping at the first pass.
- For contested or consequential claims, run one counter-search for disconfirming sources and back the claim with a primary source or mark it unresolved.
- Separate direct evidence, citation links, retrieval dates, inference, confidence, and residual uncertainty.
- Name retrieval gaps when Hermes or the wrapper cannot access the web.
- For AI or usability research, separate target-user/task assumptions, measured or reported usability dimensions, and generalizability limits from the evidence.
- Summarize research before any coding handoff; research is not implementation evidence.

Handoff policy:

Run as a Hermes-side research lane when web access is available; summarize evidence before any coding handoff and never treat research as implementation.

Required inputs:

- research question
- target user/task if usability matters
- usability/quality dimension if applicable
- source boundaries
- freshness, jurisdiction, or version constraints

Expected outputs:

- source-backed synthesis
- links or citations
- source-quality notes
- confidence and residual uncertainty
- product_evidence_loop/v1

Artifact expectations:

- research notes with source URLs, retrieval dates, and source-quality notes when the wrapper captures them

Safety rules:

- Prefer official or primary sources when they can answer the question.
- Check source diversity and conflicts before summarizing contested or unstable topics.
- Separate quoted evidence from inference.
- State retrieval limits, dates, and missing-source gaps for unstable facts.
- product_evidence_loop/v1 is prepared-only opaque references, not observed evidence or execution.

## Runtime Evidence

Preferred harness for this skill: `research`.

```sh
omh runtime record --skill web-research --harness research --status started
```

Record observed delegation results; otherwise return `not_available` or `not_observed`.
Prepared OMH routing is not execution, review, CI, merge-readiness, or merge evidence.
- Treat wrapper memory/context summaries as advisory local context, not proof of opaque Hermes memory reads or changes.

Use Hermes-native subagent/delegation features when available: native subagents -> Hermes delegation when available, otherwise sequential lanes.

Shared product, compatibility, topology, memory, harness, and execution rules: `omh-routing/references/skill-common-rail.md`. Load it when applicable; otherwise name an unavailable capability.
