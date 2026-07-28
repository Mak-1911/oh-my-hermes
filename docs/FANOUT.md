# Fanout: Parallel Split, Dispatch Bridge, and Merge Contract

Audience: operators, wrappers, and coding agents. Normal users describe the
goal to Hermes in chat; these commands are the backend surface.

## Lifecycle

1. **Propose** — Hermes (the LLM) proposes the unit split in chat: unit ids,
   titles, owners, file boundaries, dependencies.
2. **Freeze** — `omh coding fanout prepare --goal <words> --units units.json
   --record` validates the split deterministically (boundary overlaps without
   a `depends_on` edge are hard errors; dependency cycles are hard errors) and
   freezes it as `fanout_contract/v1` under `~/.omh/coding/fanout/<id>/`. The
   goal is stored as a digest only.
3. **Dispatch (opt-in bridge)** — `omh coding fanout dispatch <id>
   --goal-file goal.txt` spawns each spawnable unit's local agent CLI in an
   isolated per-unit worktree, dependency-aware, with bounded concurrency.
4. **Observe** — `omh coding fanout show <id>` joins the frozen contract with
   per-unit run records; unit status is `not_observed` until real evidence
   exists. The board reads a bounded tail (last 20 events) of each unit's run
   history, so repeated checks cost the same context instead of growing with
   the run. `--limit N` changes the tail; `--full` reads everything and is
   expensive for agent context.
   For user-facing briefings, `omh coding fanout brief <id>` renders one
   line per unit in merge-plan order — unit, owner, `(model effort)` label
   (for example `(gpt-5-codex xhigh)`), status, elapsed seconds, token
   count, session ref, last observed summary — as plain text by default
   with `--json` for the `fanout_briefing/v1` payload. It joins the
   contract, the persisted dispatch summary, and a one-event journal tail;
   unknown fields stay the literal `unknown` rather than being inferred,
   and never-dispatched units keep `prepared_not_observed`. Without an id
   it lists known fanouts. Session refs and token counts are `unknown`
   until a structured-output dispatch contract lands (deliberate deferral
   — the current templates keep executor stdout as opaque bounded text);
   executor-progress bindings for `omh runtime progress-status` are
   deferred with that same follow-up.
5. **Merge (human/agent-gated)** — dispatch never merges. The summary lists
   merge-ready units in the contract's `merge_order`; merging and the final
   integration gate remain the operator's or reviewing agent's job.

## Dispatch bridge semantics

- **Spawnability is data.** `DISPATCH_COMMAND_TEMPLATES` in
  `src/coding/fanout_dispatch.py` maps profiles with a local headless CLI to
  fixed argv templates. Profiles without a template (hermes, omx/omo/omc
  runtimes, generic, unassigned) are reported
  `unsupported_for_local_dispatch` with the unit handoff as a prepared-prompt
  fallback — no profile is privileged.
- **Bridge dispatch is a separate axis from chat prompt-handoff.** Chat
  surfaces keep their prompt-only semantics for prompt-only profiles; the
  bridge is an operator-invoked command on a different surface.
- **Goal integrity.** `--goal-file` must hash to the digest frozen in the
  contract; a diverged goal is refused.
- **Worktrees.** One per unit at `<repo>-fanout-<unit>` on branch
  `agent/<unit>`, all branched from one SHA resolved at dispatch start
  (`--base-ref`, default HEAD). Pre-existing paths or branches are errors,
  never silently reused. Worktrees are never auto-deleted; reconcile with
  `git worktree list`.
- **Evidence.** Each dispatched unit gets a run named by its `run_ref`;
  spawn and exit are recorded as journal observations
  (`worker_dispatch`/`worker_result`, canonicalized to
  `executor_dispatch_observed`/`executor_result_observed`).
- **Dependency bar.** A satisfied dependency means only that the owner agent
  process exited 0. It is not verified, reviewed, or correct work. Failed
  units block their dependents, never their independents.
- **Blocked-by-design cascades.** An `unsupported_for_local_dispatch` or
  `executor_not_ready` dependency also blocks its dependents — dependents must
  never build on an unstarted base. Recovery: complete that unit manually (or
  via its owner's own tooling), record its observed result on the unit's
  `run_ref` run, then re-run `dispatch --unit <dependent>`; completed units
  satisfy dependencies even when not re-selected. Blocked entries carry a
  `blocked_on` list naming the offending units.
- **First-use validation note.** `codex exec` has in-repo precedent. The
  claude template was validated in a live dispatch (2026-07): `acceptEdits`
  alone let the agent create files but blocked the requested `git commit`,
  so the template additionally grants `--allowedTools
  "Bash(git add:*),Bash(git commit:*)"` — exactly those two git verbs,
  nothing broader. Template drift in either CLI surfaces as a clean
  readiness or exit-code failure recorded as observed evidence, and the fix
  is a one-line data edit in `DISPATCH_COMMAND_TEMPLATES`.
- **Model routing.** A unit may declare `model`, `reasoning_effort`, and/or
  `role` (brain, implementation, design_visual, review, docs). Prepare embeds
  the resolved `coding_model_route/v2` in the unit handoff, and dispatch
  turns it into argv fragments (`codex --model … --config
  model_reasoning_effort=…`; `claude --model … --effort …`). Resolution is a
  four-stage pure pipeline — requested model > role chain head > chain gap
  (explicit choice) > executor default — and every route records its
  `provenance` plus a per-stage `attempted[]` trail. Roles resolve against
  ordered per-profile chains (`ROLE_MODEL_CHAINS`); entries after the
  selected head are prepared next-candidate advice — omh never retries or
  switches models itself. A requested reasoning effort that a catalog-known
  model does not support steps down an ordered effort ladder with a typed
  `effort_change` record; for models the catalog has not met the request
  passes through untouched (the catalog is a default candidate list, not an
  allowlist, and it never adjudicates a model it does not know). No route
  means the argv stays byte-identical to the base template and the executor
  CLI default model applies. Model availability and entitlement are provider
  truth; a routed model that the CLI rejects surfaces as a normal observed
  exit failure. `omh coding model-route` previews a single route;
  `omh coding model-route --explain` renders the full profile × role
  resolution matrix with chains and provenance. Contracts frozen before the
  v2 bump may embed `coding_model_route/v1` routes — they are read verbatim
  (the brief annotates them `[schema v1]`), never rewritten.
- **Model inventory (reporting-only).** `omh coding model-inventory` reports
  which coding models the user has locally activated before any split or
  delegation is proposed: agent CLIs on PATH (codex, claude, opencode,
  gemini, grok, qwen), models named by the oh-my-openagent config
  (`~/.config/opencode/oh-my-openagent.json` — model/variant/fallback ids
  only), opencode provider-config and auth provider key NAMES
  (presence-only, values never read), and the existing executor login
  markers. Every identifier passes the opaque-metadata shape gate; rejects
  are counted, never echoed, and unreadable sources report a status without
  a path. The payload aggregates models with their `model_family()` and
  ships static domain-affinity notes (for example X-platform data work
  favors the grok family) under their own claim boundary: editorial
  defaults, not observed capability, no routing effect. The inventory never
  enters a model route, a frozen contract, or persisted state — it is
  read-time advisory context for the operator or wrapper proposing a split,
  and routing consumption is a recorded follow-up. A compact hint (families
  present, model count, the full-report command) rides the choose-executor
  context automatically, so Hermes proposes owners from what the user
  actually has instead of asking blind.
- **Unit prompt protocol.** Every dispatched unit prompt carries a fixed
  verification discipline (`src/coding/unit_prompt_protocol.py`): the
  subagent first echoes the goal, its deliverable, and the numbered
  completion criteria back before any tool use (and stops to report a
  conflict instead of guessing); "done" is pre-declared as numbered
  criteria derived from the frozen contract (boundary confinement, the
  unit's integration checks, committed work); and verification is
  mandatory-but-bounded — exactly one full pass is the floor, a finding
  blocks only when it violates a stated criterion, passing criteria are
  never re-verified, and a still-failing criterion is reported after two
  fix-and-verify cycles instead of looping. Review-role units add
  criterion-bound review with a two-round re-review cap. High-effort
  routes (high/xhigh/max) append a per-family calibration block countering
  over-verification inertia; unknown families get the generic block so no
  vendor carries richer guidance than another. Prompts are subprocess
  argv, so the assembled worst case is policy-gated under
  `UNIT_PROMPT_MAX_BYTES` in tests rather than trimmed at runtime.
- **Telemetry.** Each dispatched unit records `started_at`, `finished_at`,
  and `duration_seconds`, and the full dispatch summary persists to
  `~/.omh/coding/fanout/<id>/dispatch_summary.json` (latest wins,
  metadata only, skipped on `--dry-run`).
- **Limit signals.** A failed spawn whose bounded output matches a fixed,
  context-anchored limit-shape pattern (rate limit, usage limit, quota
  exceeded, HTTP 429, credits) is flagged `limit_shaped` with a pattern
  label; the last such failure per executor persists to
  `~/.omh/runtime/executor-limit-signals.json` (plus its transient `.lock`
  sibling) and surfaces as an advisory — with read-time `age_seconds` and
  a 6-hour `stale` marker — in `omh coding executor-readiness` and the
  choose-executor context, where candidates rank logged-in/no-fresh-limit
  first without ever removing an option. A later successful dispatch to
  the same executor clears its signal. Only the boolean and label persist
  — never the matched text, and stderr is matched in memory only.
- **Resume.** Re-running dispatch skips units whose runs already carry an
  observed successful result. `--unit <id>` selects subsets.
- **Never**: auto-merge, default-on execution, network calls by omh itself,
  raw-prompt persistence under `.omh`, Hermes-inline coding (coding-shaped
  work that cannot resolve an executor becomes an explicit user choice, not
  retained Hermes implementation).

## Command reference

```sh
omh coding fanout prepare --goal <words...> --units units.json [--record] [--source discord]
omh coding fanout validate --units units.json
omh coding fanout show <fanout-id> [--limit 20] [--full]
omh coding fanout brief [<fanout-id>] [--json]
omh coding fanout dispatch <fanout-id> --goal-file goal.txt \
  [--repo-root .] [--base-ref HEAD] [--concurrency 2] [--timeout 1800] \
  [--unit <id> ...] [--dry-run]
omh coding model-route [--executor <profile>] [--role <role>] [--model <id>] [--effort <level>] [--explain] [--json]
omh coding model-inventory [--json]
```

`--units` and `--goal-file` accept `-` for stdin. `--dry-run` resolves
readiness, planned argv, and worktree paths without spawning anything or
creating any runs.
