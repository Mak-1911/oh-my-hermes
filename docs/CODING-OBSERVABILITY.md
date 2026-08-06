# Seeing What Coding Work Is Running

Multi-session coding work used to be invisible in three specific ways. Each is
now fixed, and each fix has a boundary worth knowing.

## What you get

```
Running work — 3 unit(s), 2 running

unit              runtime            model              status     elapsed   tokens       session
research-sweep    claude-code        opus xhigh         running    35m       10,000,000   sess_9f2c4a
api-ratelimit     codex              gpt-5.6-sol xhigh  running    4m        128,400      019a7b3e
docs-pass         omo-runtime (pi)   glm-4.6            completed  12m       unknown      unknown
```

Ask in chat — "what's running", "지금 뭐 돌고 있어", "what models are running" —
or run the command directly:

```sh
omh coding status-board [--limit N] [--json]
```

## What was actually broken

**The model was dropped.** The runtime (`codex` / `claude_code`) was tracked
end to end, but no progress surface carried the model. `_safe_signal` was a
closed key allow-list with no model key. So OMH knew *which CLI* was running
and could not say *which model* it was running on.

**Token counts had no write site.** `omh coding fanout brief` already read
`tokens_total` and `session_ref` and rendered columns for them. Nothing in
`src/` ever wrote either key, so both columns printed `unknown` on every row,
forever.

**A running unit could not report itself.** Dispatch is blocking —
`subprocess.run` inside a thread pool — so the dispatching process cannot
narrate its own progress. There was no way for a second session to see that a
unit was mid-flight, which is exactly the multi-session case that matters.

## The honesty contract

This is the part that makes "100% reliable" true rather than aspirational.

**Runtime and model are always exact when present.** OMH itself chose them and
put them on the command line, so there is nothing to infer.

**Tokens, session refs, and elapsed-for-unfinished-units are observed or
explicitly unknown.** They are never estimated, and never derived from the
Hermes conversation's own token budget — that belongs to a different actor and
using it would be a category error. A number on the board is a number an
executor reported. An absent count renders as the literal `unknown`, never as
`0`, because a zero reads as an observation.

**A start marker cannot prove liveness.** In-flight markers carry
`liveness: "unknown"` on purpose. A marker left by a process that died looks
identical to one left by a process still working, so the board reports an
observed start without an observed end rather than claiming the unit is alive.

**Runtimes without structured output report `unknown` and say so.** The
omo-runtime lane (pi / senpi / opencode) has no structured token surface, so
its token columns stay unknown by design rather than being filled with a guess.

## Why the token number is a sum, and what that means

Neither CLI reports a total. Verified by capturing real output:

```
claude  usage: {input_tokens: 2, cache_creation_input_tokens: 14441,
                cache_read_input_tokens: 15273, output_tokens: 4}
codex   usage: {input_tokens: 27305, cached_input_tokens: 6912,
                cache_write_input_tokens: 0, output_tokens: 5,
                reasoning_output_tokens: 0}
```

Two things follow. Reporting `input_tokens` alone would have shown **2** for a
claude run that consumed roughly **29,700** input tokens. And reading only
`total_tokens` — which neither CLI emits — would have left the column `unknown`
on every real run.

So the board shows `tokens_billable`: the sum of the components the CLI itself
printed, carrying `tokens_billable_source: "summed_reported_components"` in the
record. Summing numbers a provider stated is aggregation. It is not the
estimation this system refuses to do, and a provider-reported `total_tokens`
still wins when one exists.

The two CLIs also name the same categories differently
(`cache_read_input_tokens` vs `cached_input_tokens`,
`cache_creation_input_tokens` vs `cache_write_input_tokens`), so the parser
normalizes both vocabularies onto one set of keys.

## Where the data comes from

| Source | Provides |
| --- | --- |
| `~/.omh/coding/fanout/<id>/inflight/<unit>.json` | mid-flight `running` state and start time |
| `dispatch_summary.json` | owner, model, effort, status, duration, tokens, session |
| executor progress bindings | live cross-unit state and latest observed event |

Tokens and session ids are parsed from the spawned CLI's own structured output
by `parse_unit_telemetry`, which is pure: no file I/O, no clock, no network.
This does not reverse the privacy decision in `codex_progress` — that module
strips token fields from *visible text* collection, while this one reads the
same keys as integers into a metadata-only counter and emits no text.

## Rendering to a messenger

The board is deliberately plain: no bold, no italics, no links, no headings, no
tables. That means no Slack `mrkdwn` or Telegram MarkdownV2 escaping is needed
and there is nothing to over-saturate.

Fenced blocks now survive as a `code_block` body block with newlines and
leading whitespace preserved. Before that fix a fence collapsed into one
run-on paragraph on **both** render profiles, which destroyed the column
alignment the board is made of. On limited-markdown surfaces (Discord, Slack,
Telegram) the board renders as one bullet per unit instead of a table, since
all three render fences but none render tables well.

The chat envelope's `messenger_rendering` block now does the platform-shaping
work so adapters do not have to:

- **Deterministic chunking.** `chunked_body_texts` is an adapter-ready split
  of `body_text` under the resolved platform's
  `chunking.max_recommended_chars`: paragraph boundaries first, then line
  boundaries, then a hard character split as the last resort. A fenced block
  that must span chunks is closed at the chunk end and reopened at the next
  chunk start (same marker and run length, no language tag), so no chunk ever
  carries an unbalanced fence. A single element means the body fits one
  message.
- **Fence language tags are stripped on limited bodies.** Only Discord
  renders the language tag on a fence line; Slack and Telegram print it as
  literal text, so every `limited_markdown` `body_text` (and every
  `fallback_body_text`) drops fence info strings. Nothing is lost for
  adapters that can highlight: `body_blocks` still carries each
  `code_block.language`. Recorded as the `fence_language_tags_stripped`
  transform.
- **Slack gets its own dialect.** A resolved `slack` source converts Markdown
  to mrkdwn *outside* fences — headings become `*bold*` lines, `**bold**`
  becomes `*bold*`, `[text](url)` links become `<url|text>` — recorded as the
  `slack_dialect_markdown` transform. Fenced code and inline `` `code` ``
  spans stay byte-identical. The dialect applies to `body_text` and
  `chunked_body_texts` only: `body_blocks` stay canonical, dialect-neutral
  Markdown, and `transforms_applied` describes those text fields, not the
  blocks.
- **Telegram defaults to plain text.** The `telegram` platform hint says to
  post `body_text` without `parse_mode`; opting into MarkdownV2 means
  escaping every reserved character yourself.
- **Per-platform ceilings remain the source of truth.** The `chunking` hint
  carries `max_recommended_chars` / `hard_limit_chars` for the resolved
  platform (Discord 1700/1900, Slack 2700/2900, Telegram 3700/3900, generic
  1600/1800), and `chunked_body_texts` is computed against the recommended
  ceiling.

The plain-text `omh coding fanout brief` output respects the generic 1600
soft ceiling too: past it, the brief keeps the longest row prefix that fits
and states the omission as its own `… +N more units` line pointing at
`--json`, so a truncated brief is never mistaken for a complete one.

## External effects, and why a check row no longer prints a link

Everything above is activity *inside* this machine. The moment a status report
says something happened outside it — a message was sent, a review landed, CI
ran, a branch moved — the report is describing an effect OMH cannot perform and
therefore cannot vouch for on its own.

Those effects are tracked separately, as `external_effect_receipt/v1` records in
`~/.omh/runtime/journal/external_effect_receipts.jsonl`. A status report splits
them five ways:

| State | Means |
| --- | --- |
| `requested` | the run's own records say the effect is needed; nothing has started |
| `attempted` | the effect has started; no acting surface has reported an outcome |
| `succeeded` | a surface observed the effect complete, and named it |
| `failed` | a surface observed the effect not happen |
| `unknown` | a surface observed a terminal state it cannot classify, or a success it cannot name |

`requested` and `attempted` are the two states that matter most here, because
they are the ones a status board used to render as silence. Both are projected
from the *absence* of a receipt — from what the run's own records asked for and
how far they say it got — and neither is ever minted from a record nothing
observed. A gate recorded as `pending` writes `observed: false`, so it mints
nothing and shows as `attempted` because the run asked for it, not because
anyone saw it. Only `succeeded`, `failed`, and `unknown` come from a receipt.

A success claim carries its citation. `omh runtime delegation-status` names the
receipt id and the acting surface behind every `succeeded` effect, and
`safe_summary` prints the citation in the sentence that makes the claim. The
`ci_observed` and `merged` rungs need a receipt that observed *that* effect
*succeed* from the surface that gate is observed by: a `failed` or `attempted`
receipt satisfies neither, and one rung's receipt never satisfies another's.

### Runs recorded before receipts existed

A run written by an earlier version has no receipts, and that is not a fault.
`omh runtime validate` stays green for it, and it keeps every claim rung through
`review_observed` — handoff prepared, executor dispatched, execution observed,
verification observed, review observed all still hold, because none of them
describes anything outside this machine.

What such a run cannot do is claim `ci_observed` or `merged`. Both assert an
external effect, and nothing on record names the surface that saw it, so
`omh conformance check` blocks them with a reason that says exactly that. The
data is intact; the claim is refused.

#### The supported upgrade path

Record each already-observed gate again, in ladder order, with the result you
observed. Writing the record is what mints the receipt:

```sh
omh runtime ci    --run <id> --status passed --provider <provider> --check <name>:passed
omh runtime merge --run <id> --merged --target-branch <branch> --merge-commit <sha>
```

Nothing else is needed and nothing else is supported. Two properties make this
honest:

- **Every status you type is one the run already recorded.** The commands
  re-state `ci passed` and `merge merged`, which is what the run's own
  `ci.json` and `merge.json` already say. You never have to write a status you
  did not observe to get back to one you did.
- **Re-recording is allowed only from a completed gate.** These commands
  normally refuse a status the run has not reached — recording `merge merged`
  on a run still awaiting its executor stays refused, and says so. A run that
  has already passed the gate sits at `next_action: report_merged`,
  `report_merge_ready`, or `report_completion_with_evidence`, and from there
  recording the same gate again is a restatement rather than a transition, so
  the preflight admits it.

Recording the same observation twice still mints once, so running the sequence
again is harmless. Run `omh runtime delegation-status --run <id>` afterwards:
`merge.receipt.receipt_id` and `merge.receipt.acting_surface` are the citation,
and `safe_summary` carries it in the sentence that makes the claim.

There is deliberately no command that mints a receipt directly: a receipt an
operator can type is exactly the self-reported evidence this store exists to
replace.

Receipts are metadata-only, which is why `format_check_rollup` stopped printing
the URL from `gh pr checks` output. A check row now ends in a redacted receipt
reference (`ref-<digest>`) instead: stable, so rows still deduplicate and
correlate, and non-navigable, so a status report never republishes a link, a
credential embedded in one, or anything else the check output happened to
carry. The same guard covers every string field on a receipt, by class rather
than by name. Identifiers — `receipt_id`, `effect_id`, `run_id`, `observed_at`,
`external_ref`, `supersedes_receipt_ref`, and each `evidence_ref` — must be
opaque metadata references: bounded, non-navigable, and free of control
characters. `action`, `target_class`, `acting_surface`, and `observed_result`
are closed vocabularies. `summary` is bounded free text. Each class is enforced
in all three places a receipt is handled — when it is built, when it is
validated, and when it is rendered — so a hand-edited store line cannot reach a
citation: a link, a path, a secret, or anything with a newline or an ANSI escape
in it becomes `[redacted]` in free text and a `ref-<digest>` handle in an
identifier, and a value outside a closed vocabulary renders empty.

## Boundary

A status board is observed activity metadata. It is not result, verification,
review, CI, merge-readiness, or merge evidence, and a unit appearing as
`running` is not proof that it will finish.

A receipt is narrower still: it is one acting surface's observation of one
external effect, and it proves nothing about any other effect.
