# Project Memory

OMH project memory is a local, reviewed control plane for one project. Normal
users use natural-language Hermes chat: ask Hermes to remember a bounded fact,
review existing memory, or clean up old project context. The commands in this
document are for agents, wrappers, and operators implementing that flow; they
are not normal-user setup.

OMH does not read, patch, or mutate opaque Hermes internal memory.

## V2 Model

New OMH-owned artifacts use versioned, replay-gated records:

- `project_memory_candidate/v2` is a bounded candidate with source class,
  canonical scope, retention choice, and safety result.
- `project_memory_record/v2`, `omh_memory_scope/v2`, and
  `omh_memory_block/v2` carry an opaque identity, positive revision, source
  class, admission, retention, and revalidation data.
- `project_memory_review_record/v2` is immutable admission evidence. Its
  states are `pending_review`, `approved_manual`, `approved_auto_safe`,
  `blocked`, and `rejected`. `approved_auto_safe` is a local policy result,
  not a human-review claim.
- `omh_memory_replay_evaluation/v1` records why an immutable revision was or
  was not eligible for a particular replay boundary. Preparation is not proof
  that a model, provider, or executor used it.

A current v2 record must pass the same deterministic evaluator before project
recall, handoff context, provider prefetch/pre-compression, block rendering, or
an explicit block read. Unsupported schema, missing review linkage, safety
failure, expiry, stale review, scope mismatch, conflict, supersession, or a
legacy v1 artifact fails closed with a reason code.

## Admission: Remember, Refuse, or Defer

For a new fact, Hermes asks for source class, target store, canonical scope,
retention class, and an explicit decision:

- **Remember** creates only one bounded **durable** candidate. It remains
  pending review until OMH-local approval and a target write are separately
  observed.
- **Refuse** covers secrets, raw logs, transcripts, prompt-injection-shaped
  instructions, and temporary task progress.
- **Defer** sends uncertain source, scope, target, retention, and external
  provider/vector material to review rather than retaining it.

Hermes-native and external provider/vector context is `not_omh_reviewed`. It
may nominate a candidate but never inherits OMH admission. OMH-local processing
does not promise no egress: a configured Hermes runtime may transmit rendered
OMH prefetch content in its model request.

## Retention and Replay

Retention is additive to record type:

| Class | Rule |
| --- | --- |
| `volatile` | Explicit only; admission starts its 1-7 day TTL, defaulting to seven days. It is ineligible at the exact UTC expiry boundary. |
| `standard` | Preserves current type behavior. An `episode` defaults to 30 days; other records keep explicit TTL/staleness behavior. |
| `durable` | Has no TTL. It receives a revalidation deadline only when explicitly configured. |

Expiry removes influence only; it does not move an artifact or prove any
absence. A stale revalidation deadline requires fresh review or a bounded,
identity-specific confirmation.

## Recall Ranking and Delivery Usage

Recall packs order eligible records relevance-first: keyword relevance rank
(term and tag overlap) is the primary sort key, and deterministic reciprocal
rank fusion over relevance, recency (`approved_at`), and delivery usage
orders records that share a relevance rank. A weaker keyword match can never
displace a stronger one, including across the budget cut; without a query all
relevance ties and recency plus usage decide the order. Each included record
carries a `ranking` block with its per-signal ranks and an integer
`rrf_score_micro`, so the order is always explainable from the pack itself.
The usage signal ranks on saturating buckets (0, 1-2, 3-9, 10+ deliveries) so
delivery counts cannot compound into a permanent head start.

Delivery usage counts only recall packs that were actually attached to a
prepared handoff payload — building a pack is speculative, so a delegation
that ends without a handoff, or rejects the pack, counts nothing. A CLI
`omh memory recall` is an inspection and does not count. Counters live in
`.omh/memory/usage.json` (`omh_memory_recall_usage/v1`); a missing or corrupt
usage store reads as empty and never blocks recall, and usage is a ranking
hint plus a retirement-report annotation, never an eligibility input.
Retirement reports annotate each expired or expiring row with `recall_usage`
so an operator can see whether a record was ever delivered before archiving
it. Lifecycle receipts list `recall_usage_counters` under their exclusions: a
prune deletes the manifest targets, not the delivery counters.

This ranking design is a deterministic reinterpretation of the hybrid-search
rank fusion and per-observation usage tracking popularized by memory servers
such as Honcho; OMH keeps the bookkeeping and drops the model calls.

## Provenance and Lineage

A capture may declare which approved records a new fact was derived from:

```sh
# Agent/operator only: capture a conclusion with explicit provenance links.
omh memory capture "Always purge cache before deploy" --derived-from <record-id>

# Agent/operator only: trace where a record came from and what built on it.
omh memory lineage <record-id>
omh memory lineage <record-id> --depth 5
```

`--derived-from` is repeatable (at most 8 refs) and every ref must name an
existing approved record at capture time. The lineage report
(`omh_memory_lineage/v1`) walks ancestors and descendants breadth-first up to
`--depth` hops (clamped to 1-10), cuts cycles, and marks deeper unexplored
links as `truncated`. A parent that was later retired or pruned appears under
`unresolved_refs` rather than failing the report. Recall items expose each
record's `derived_from` list so an executor can ask for lineage when a
summary alone is not enough. Lineage is prepared-context traversal only; it
never claims the derivation itself was re-verified.

## Perspectives (Observer / Observed)

A record may optionally carry a perspective: which actor's view it is
(`observer`, defaulting to `hermes`) and which actor it is about
(`observed`). This is Honcho's peer paradigm reinterpreted deterministically:
no theory-of-mind inference, just bookkeeping that keeps one actor's lessons
out of another actor's context. An `observed` label that should reach
handoffs must be an executor target (`codex`, `claude-code`, `generic`,
`hermes`, `omx-runtime`, `omo-runtime`, `omc-runtime`); other labels such as
`operator` are inspection-only lenses that no handoff ever selects.

```sh
# Agent/operator only: capture a fact about one executor.
omh memory capture "codex needs the full test command spelled out" --observed codex

# Agent/operator only: recall through a lens; unscoped records always pass.
omh memory recall "test command" --observed codex

# Agent/operator only: list observer/observed pairs with record counts.
omh memory perspectives
```

Lens semantics: an unscoped record (no perspective) behaves exactly as
before and passes every lens. A scoped record surfaces only through a
matching lens; lens labels normalize like capture labels (lowercased,
trimmed). Handoff recall packs and handoff context packs automatically use
the selected executor target as their `observed` lens, so a record captured
about `codex` reaches codex handoffs — and never a `claude-code` or
`generic` handoff. While the executor target is still unresolved
(`choose`), handoffs carry unscoped records only. A plain recall with no
lens is an inspection surface and hides nothing. Recall packs echo the
active lens under `perspective`, each included record carries its own
`perspective` block, and context packs exclude mismatched records with
reason `perspective_mismatch`.

## Legacy Migration and Reactivation

Legacy v1 files remain readable in status and review surfaces as
`review_required_legacy`; they do not replay. The first operator step is always
a report:

```sh
# Agent/operator only: dry-run, source-by-source counts and review-required notice.
omh memory inventory

# Agent/operator only: persist the bounded inventory ledger when requested.
omh memory inventory --write-ledger

# Agent/operator only: re-scan and reactivate exactly one reviewed artifact.
omh memory reactivate <record-id> --revision <n> --apply
```

Inventory reports deterministic counts for active records, scope items, blocks,
archive/history, candidates/reviews, index references, declared-link journals,
corrupt or unknown artifacts, and external exclusions. It does not emit raw
values or content hashes. Reactivation is per artifact/revision, report-first,
under the store lock, and creates v2 review evidence. It never mass-promotes
legacy memory or silently grants replay eligibility.

## Exact Lifecycle Vocabulary

- **expire** removes influence only.
- **retire** archives a readable local revision recoverably.
- **restore** creates a new pending revision linked to the archived revision
  while preserving that archive. A newer live conflict remains review-blocked.
- **prune** hard-deletes only the manifest-declared OMH-local target set for an
  expired volatile revision, after report and explicit confirmation.

Restore and prune are report-first operator actions:

```sh
# Agent/operator only: inspect first, then apply a recoverable archive move.
omh memory retire
omh memory retire --apply

# Agent/operator only: inspect archive targets; a restore remains pending review.
omh memory restore <record-id> --revision <n>
omh memory restore <record-id> --revision <n> --apply

# Agent/operator only: inspect the local manifest, then explicitly hard-delete it.
omh memory prune <record-id> --revision <n>
omh memory prune <record-id> --revision <n> --apply --confirm-hard-delete-local
```

A prune receipt names attempted, observed, absent, unresolved, and excluded
local targets. It does not cover backups, filesystem snapshots, trash, synced
copies, Hermes-native memory, providers, vector stores, executors, or unlinked
artifacts. A tombstone blocks restore/retry of that exact opaque identity; it
does not block a newly captured fact.

## Batch Context Updates

Direct batch mutation is not a trust path. Agents and operators use a staged
sequence:

```sh
# Agent/operator only: validate into review-only candidates.
omh memory batch-stage --batch memory-update-batch.json

# Agent/operator only: create immutable review evidence for the staged set.
omh memory batch-review <batch-id>

# Agent/operator only: apply only the linked approved set under the store lock.
omh memory batch-apply <batch-id> --apply
```

Each stage is separate from replay eligibility. The compatibility
`omh memory apply --batch` path reports `review_required` rather than directly
writing unreviewed updates.

## Dreaming

Dreaming has only `off` and `reminder` modes. It prepares a reminder and
metadata-only evidence; it never invokes a model, consolidates, retires,
restores, or prunes. Standing reminder reasons include
`stale_review_required` and `expired_volatile_records`.

## Prepared Context Boundary

A prepared recall or handoff pack is OMH-local context, not proof that an
executor ran, a provider received content, a model used it, or review/CI/merge
happened. Keep source class, admission mode, retention class, revision, and
replay reason with the bounded preparation evidence.
