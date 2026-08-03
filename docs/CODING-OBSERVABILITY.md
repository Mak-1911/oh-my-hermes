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

## Boundary

A status board is observed activity metadata. It is not result, verification,
review, CI, merge-readiness, or merge evidence, and a unit appearing as
`running` is not proof that it will finish.
