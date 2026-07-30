---
name: omh-memory-sync
description: [omh] Audit what Hermes already remembers - reviews USER.md, MEMORY.md, and skill memories claim by claim and rewrites only after an approved diff; for a new fact use memory-new, and for retrieving a past decision use decision-recall. Use when the user says: memory-sync, memory curation, memory review, memory inspect, memory check, memory update, context cleanup, curate memory.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, memory]
    category: memory
    phase: curation-review
    role: memory-keeper
    quality_tier: workflow-surface-gated
---

# Memory Sync

This is a Hermes-native `memory-sync` workflow skill.

## Why This Exists

`memory-sync` exists so Hermes users can ask for this workflow in chat and receive a structured, evidence-bounded OMH operating surface instead of ad hoc narration.

## Do Not Use When

- The request is already handled by a narrower explicit skill with stronger evidence.
- The user asks OMH to secretly run external platforms, connectors, schedulers, file exports, or runtime agents.
- The only safe answer is to ask for missing authority, credentials, target, or observed evidence first.

## Examples

Good example:

- Prompt: memory-sync inspect stale project memories and ask me what to keep.
- Expected behavior: Produce `prepare_memory_sync` with required context, wrapper actions, and not-evidence boundaries.
- Why: The prompt names a real workflow surface that Hermes can orchestrate without hiding execution.

Bad example:

- Prompt: memory-sync silently delete all conflicting memories.
- Expected behavior: Report the missing observed evidence or authority instead of claiming the external step happened.
- Why: Prepared OMH guidance is not platform, runtime, connector, file, memory, or delivery evidence.

## Completion Checklist

- Confirm the workflow target, evidence boundary, and stop condition are named.
- Report which outputs are prepared, observed, blocked, or missing.
- Name the smallest next verification or handoff instead of claiming completion from narration.

## Recovery Notes

- If required context is missing, ask one blocking question or route back to the narrower workflow.
- If runtime or wrapper evidence is unavailable, keep the status as not_observed and expose the next observable action.

## Workflow Lane

- Current lane: **Retained knowledge** (`memory-new`, `memory-sync`, `decision-recall`, `wiki`) - memory, rejected alternatives, wiki notes, retrieval, and staleness.
- If intent belongs to another lane, hand back to `oh-my-hermes` or name the adjacent workflow.
- Shared product, routing, compatibility, and evidence rules: `omh-routing/references/skill-common-rail.md`.

## Interview Protocol

- **클레임 추출** — `~/.hermes/memories/USER.md`·`MEMORY.md`를 클레임으로 분해하고, 각 클레임은 원문 그대로 인용한다.
- **출처** — 출처를 추정하거나 지어내지 않는다; 세션에 실제 근거가 있을 때만 출처를 언급한다.
- **대상** — existing USER.md and MEMORY.md accumulated memories only; 새 프로젝트·제품 메모리 후보 추가는 `memory-new`로 라우팅한다.
- **우선순위** — stale, conflicting, duplicate, or overgeneralized 클레임을 우선한다("파이썬 한 번 개발"→"파이썬 선호").
- **턴 구성** — 4–5턴 × 턴당 2–3개 의심 클레임을 묶고, 전수가 아닌 의심 우선으로 메신저 친화 짧은 포맷을 쓴다.
- **분기** — 예=유지 / 아니요=삭제 / 수정 지시=수정.
- **마지막 턴** — 변경 요약 diff을 제시한다(유지 n / 삭제 n / 수정 n + 수정 전후).
- **쓰기 게이트** — 승인 전에는 어떤 파일도 수정하지 않는다; 승인 후 1회 일괄 쓰기로만 반영한다.
- **캡** — MEMORY.md ~2,200자 / USER.md ~1,375자를 넘기지 않는다.

## Boundary

The prepared artifact is `memory_curation_review/v1`. A memory-sync review is not MEMORY.md or USER.md modification evidence until the approved write gate is observed. Hermes itself reads and writes these files; OMH runtime never writes `~/.hermes` (DIRECTION Rule 5).

## Use When

Use when existing Hermes USER.md, MEMORY.md, or accumulated skill memories need human-approved audit and cleanup. Do not use for adding new project or product memory candidates. 캡: MEMORY.md ~2,200자 / USER.md ~1,375자.

    Strong routing signals: `memory-sync`, `memory curation`, `memory review`, `memory inspect`, `memory check`, `memory update`, `context cleanup`, `curate memory`, `stale memory`, `hermes remembers`, `conflicting memory`, `duplicate skill`, `MEMORY.md`, `USER.md`, `기억하고 있는`, `기억하고 있는 프로젝트 맥락`, `기억하는 맥락`, `현재 hermes가 기억하는 맥락`, `현재 헤르메스가 기억하는 맥락`, `헤르메스가 기억하는 맥락`, `오래된 맥락`, `오래된 기억`, `기억 점검`, `기억 정리`, `메모리 업데이트`, `메모리 검사`, `메모리 점검`, `메모리 정리`, `맥락 점검`, `맥락 정리`, `맥락 피드백`, `등록된 맥락`, `헤르메스 기억`, `중복 스킬`, `나에 대해 잘못 알고`, `저장된 내 정보`, `너한테 저장된`, `저장된 프로필`, `기억 바로잡`, `what you remember about me`, `your memory about me`

## Catalog Metadata

Category: `memory`
Phase: `curation-review`
Hermes role: `memory-keeper`
Quality tier: `workflow-surface-gated`
Reasoning demand: `light`

Quality bar:

- Name the user-facing workflow objective, required context, next action, and stop condition.
- Separate prepared guidance from observed platform, runtime, connector, file, memory, or delivery evidence.
- Expose missing tools, credentials, targets, or observations as user-visible gaps.
- 출처를 추정하거나 지어내지 않는다; 근거 없는 클레임은 의심 항목으로만 제시한다.

Handoff policy:

Keep this as Hermes-facing orchestration guidance first. Prepare executor, connector, gateway, or host-runtime handoff only when the user accepts that next step and observed evidence can be recorded.

Required inputs:

- user request
- target context
- delivery or status expectation
- known missing evidence

Expected outputs:

- memory-sync/v1 card or guidance
- next action
- prepared-vs-observed boundary

Artifact expectations:

- memory-sync/v1 metadata-only runtime or wrapper card when recorded

Safety rules:

- A memory curation review is not Hermes internal memory, MEMORY.md, USER.md, or skill-file modification evidence until an approved write is observed.
- Do not claim connector, gateway, runtime, file generation, memory mutation, or host automation evidence from prepared guidance.
- 각 클레임은 원문 그대로 인용한다; 세션에 실제 근거가 있을 때만 출처를 언급한다.
- 승인 전에는 어떤 파일도 수정하지 않는다; 승인 후 1회 일괄 쓰기로만 반영한다.

## Runtime Evidence

Preferred harness for this skill: `memory-sync`.

```sh
omh runtime record --skill memory-sync --harness memory-sync --status started
```

Record observed delegation results; otherwise return `not_available` or `not_observed`.
Prepared OMH routing is not execution, review, CI, merge-readiness, or merge evidence.
- Treat wrapper memory/context summaries as advisory local context, not proof of opaque Hermes memory reads or changes.
Preserve workflow intent and stop conditions; verify before claiming completion.

Use Hermes-native subagent/delegation features when available: native subagents -> Hermes delegation when available, otherwise sequential lanes.

Shared product, compatibility, topology, memory, harness, and execution rules: `omh-routing/references/skill-common-rail.md`. Load it when applicable; otherwise name an unavailable capability.
