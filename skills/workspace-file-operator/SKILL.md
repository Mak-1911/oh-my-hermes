---
name: workspace-file-operator
description: [omh] Hermes workspace file operator workflow: scope local file/folder listing, search, organize, copy, move, rename, and delete tasks with path and destructive-action gates.
metadata:
  hermes:
    tags: [workflow, oh-my-hermes, filesystem]
    category: filesystem
    phase: file-task
    role: guide
    quality_tier: workflow-surface-gated
---

# Workspace File Operator

This is a Hermes-native `workspace-file-operator` workflow skill.

## Why This Exists

`workspace-file-operator` exists so Hermes users can ask for this workflow in chat and receive a structured, evidence-bounded OMH operating surface instead of ad hoc narration.

## Do Not Use When

- The request is already handled by a narrower explicit skill with stronger evidence.
- The user asks OMH to secretly run external platforms, connectors, schedulers, file exports, or runtime agents.
- The only safe answer is to ask for missing authority, credentials, target, or observed evidence first.

## Examples

Good example:

- Prompt: workspace-file-operator list files in the reports folder and move old PDFs into archive after confirmation.
- Expected behavior: Produce `prepare_workspace_file_operator_card` with required context, wrapper actions, and not-evidence boundaries.
- Why: The prompt names a real workflow surface that Hermes can orchestrate without hiding execution.

Bad example:

- Prompt: workspace-file-operator delete every matching file without path scope or confirmation.
- Expected behavior: Report the missing observed evidence or authority instead of claiming the external step happened.
- Why: Prepared OMH guidance is not platform, runtime, connector, file, memory, or delivery evidence.

## Completion Checklist

- The path root, allowed file operations, excluded paths, destructive-operation policy, and stop condition are explicit.
- Delete, overwrite, move, rename, permission change, archive mutation, upload, and download are gated or marked missing.
- Directory listings, file contents, hashes, diffs, and operation results are reported only from observed file evidence.

## Recovery Notes

- If the target path or folder is missing, ask for the smallest path scope needed before preparing the operation.
- If delete, overwrite, move, rename, chmod, or irreversible cleanup is requested, require an explicit confirmation gate.
- If the request is file conversion, deck/PDF export, or attachment delivery, route to materials-package or deliverable-package instead.

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

Use when Hermes should prepare or supervise local workspace/file-system operations such as listing, searching, organizing, copying, moving, renaming, archiving, or deleting files without claiming the operation ran.

    Strong routing signals: `workspace-file-operator`, `workspace file operator`, `file operator`, `file operation`, `file operations`, `filesystem task`, `filesystem operation`, `file system task`, `file system operation`, `list files`, `list folder`, `list directory`, `find local files`, `search files`, `organize files`, `organize folder`, `move file`, `move files`, `copy file`, `copy files`, `rename file`, `rename files`, `delete file`, `delete files`, `remove file`, `remove files`, `archive files`, `downloads folder`, `reports folder`, `folder cleanup`, `file cleanup`, `파일 작업`, `파일 조작`, `파일 정리`, `파일 검색`, `파일 찾아`, `파일 이동`, `파일 복사`, `파일 이름 변경`, `파일 삭제`, `폴더 정리`, `다운로드 폴더`, `디렉터리 목록`

## Catalog Metadata

Category: `filesystem`
Phase: `file-task`
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

- workspace_file_task_card/v1
- file_operation_scope/v1
- file_observation_manifest/v1 when observed
- file_confirmation_gate/v1 when destructive
- next action
- prepared-vs-observed boundary

Artifact expectations:

- workspace_file_task_card/v1 metadata-only wrapper card when prepared
- file_operation_scope/v1 with path root, allowed operations, excluded paths, and stop condition
- file_observation_manifest/v1 only when directory listings, file stats, hashes, diffs, or operation output are observed
- file_confirmation_gate/v1 for delete, overwrite, move, rename, chmod, archive mutation, or irreversible cleanup

Safety rules:

- A workspace file operator card is not file read, file write, copy, move, rename, delete, archive, upload, download, permission change, or destructive filesystem evidence unless observed file-operation output records it.
- Do not claim connector, gateway, runtime, file generation, memory mutation, or host automation evidence from prepared guidance.

## Runtime Evidence

Preferred harness for this skill: `workspace-file-operator`.

```sh
omh runtime record --skill workspace-file-operator --harness workspace-file-operator --status started
```

Record observed delegation results when Hermes or the wrapper exposes them. If delegation is unavailable, keep the result explicit as `not_available` or `not_observed`.

## Hermes Compatibility Contract

- Preserve the workflow intent, stop conditions, and verification discipline; verify with the smallest relevant test or inspection before claiming completion.
- Use Hermes-native tools, file operations, and subagent/delegation features when available, and do not require runtime tools, role prompts, or overlays that Hermes Agent does not expose. If Hermes cannot provide a required runtime capability, say so and fall back: native subagents -> Hermes delegation when available, otherwise sequential lanes.
- Respect `omh_target_topology/v1` when a wrapper reports it: bind state to the current target/thread, fall back to single-target behavior when `active_agent_count` is one, and give one concise setup-change comment before treating a one-to-many or many-to-one change as persistent.
- Treat wrapper-supplied memory/context summaries as advisory local context, not proof that opaque Hermes memory was read or changed.
- Shared rail: `oh-my-hermes/references/skill-common-rail.md` carries harness discipline, the runtime-mechanism translation table, the delegation-record command, and the execution-rule checklist. Load it when one of those applies; if it is not installed, name the unavailable capability instead of assuming it.
