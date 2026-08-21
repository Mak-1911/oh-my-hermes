# Model Optimization Guidance

What OMH does differently per model, how it actually works at runtime, and —
for every family-specific prompt guideline — exactly why it exists and where
it came from. This document is a reader's map; the source of truth is the code
it cites, and a drift test (`tests/test_unit_prompt_protocol.py`) fails when a
calibrated family disappears from this file.

Boundary first: OMH never calls a model. Every optimization below is prepared
text or prepared configuration — calibration blocks ride prepared unit
prompts, routing rides Hermes config keys, and execution evidence always comes
from the runtime that actually ran the model.

## How it works, end to end

1. **A lane gets a model.** The mixture chains (shipped defaults plus your
   `~/.omh/routing/model-chains.json` overrides) pick a model and reasoning
   effort per category; `omh_delegate_route` writes them as explicit Hermes
   delegation keys. Any token-shaped model id is accepted — if the provider
   cannot serve it, the error comes back as a normal result and the chain
   falls over to its next entry (Hermes itself has no provider-side fallback).
2. **The model id is classified into a family.** `model_family()` in
   `src/coding/model_routing.py` strips a provider prefix
   (`opencode/kimi-k3` → `kimi-k3`) and matches by prefix. Unknown ids get
   family `unknown` — never an error, just generic discipline.
3. **The prepared prompt is assembled.** Every dispatched unit prompt carries
   the universal protocols (goal echo-back, numbered completion criteria,
   bounded verification). If the routed effort is `high`/`xhigh`/`max`, one
   family-specific calibration paragraph is appended for the subagent; the
   composer writing the split follows the calibration for its *own* model
   (`omh coding composition-guide --model <id>` prints it).
4. **The model runs it.** Tool calling, todo rendering, and parallel
   execution are Hermes runtime capabilities — OMH's ULW behaviors
   (`todo init`, phase checklists, parallel evals, interjection-resume) live
   in skill contracts and prepared handoffs, so they apply identically to
   every lane regardless of which model the chain routed there.

So "optimizing for a model" in OMH means exactly one thing: a short,
evidence-backed paragraph of counter-guidance appended to an otherwise
identical prompt. Nothing else about the pipeline changes per model.

## How a model is recognized

| Family | Matched by | Example ids |
| --- | --- | --- |
| `gpt` | `gpt-` | `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` |
| `claude` | `claude-`, bare tiers `opus`/`sonnet`/`haiku` | `claude-fable-5`, `claude-opus-5` |
| `gemini` | `gemini-` | `gemini-3.1-pro` |
| `kimi` | `kimi-` | `kimi-k3`, `kimi-k3-ultrafast` |
| `glm` | `glm-` | `glm-5.2`, `glm-5.2-ultrafast` |
| `grok` | `grok-` | `grok-code-fast-1` |
| `qwen` | `qwen-`, alias `qwen3-` | `qwen3-coder` |
| `deepseek` | `deepseek-` | versioned DeepSeek ids |
| `mistral`, `llama`, `codestral` | own prefixes | — (recognized, not yet calibrated) |
| `openai`, `anthropic` | bare-vendor prefixes | rarely-seen ids (not yet calibrated) |
| `unknown` | anything else | e.g. `solar-*` today |

## Universal protocols (every model, every family)

`src/coding/unit_prompt_protocol.py` attaches three deterministic blocks to
every dispatched unit prompt, regardless of model:

- **Goal echo-back** — before the first tool use, the subagent restates the
  goal, its deliverable, and the numbered criteria, and reports (never
  guesses) if its reading conflicts with the declared boundary. *Why:* a
  misread boundary is cheapest to catch before any edit exists.
- **Pre-declared completion criteria** — "done" is a numbered list derived
  from the frozen unit contract before work starts. *Why:* completion must be
  a check against stated criteria, not a feeling.
- **Bounded verification** — exactly one full verification pass is both the
  floor (never skipped) and the ceiling (once criteria pass, re-verifying is
  forbidden; at most two fix-and-verify cycles before reporting the failing
  criterion). *Why:* the two dominant agent failure modes are opposites —
  skipping verification, and looping on it — and one bounded rule counters
  both. Review-role units add criterion-bound blocking with a two-round cap.

These originate from the stop-condition techniques the oh-my-openagent
research surfaced for high-effort models (terminal-condition rules,
criterion-bound blocking, capped re-review), generalized to every family.

## Per-family calibrations: what, why, and where each came from

Two tables in `src/coding/unit_prompt_protocol.py` carry the family-specific
guidance: `HIGH_EFFORT_CALIBRATIONS` for the **subagent executing a unit**,
and `MAIN_AGENT_COMPOSITION_CALIBRATIONS` for the **composer** splitting work
and writing unit prompts. A parity test forces the two tables to share one key
set — no family gets subagent discipline without composer discipline.

The governing rule, stated in the module docstring: a calibration counters a
family's *known* failure mode. No family carries richer guidance than another
without a stated reason, and no vendor is privileged. Provenance falls into
three buckets, each named per family below:

- **Adapted research** — stop-condition work from the oh-my-openagent
  project on how high-effort reasoning models over-verify.
- **Observed failure modes** — behavior seen in live OMH/Hermes usage of that
  family (recorded in the commits that introduced each block).
- **Provider-published model characteristics** — facts the vendor states
  about the model's design (e.g. a non-thinking architecture), which make
  certain prompt shapes actively harmful.

Validation is common to all: `benchmarks/live-model-tools/v1` runs
baseline-vs-calibrated prompt pairs where the *only* difference is the
calibration block, and `tests/test_omh_live_model_benchmark.py` pins that
pairing so a benchmark claim can never mix in other prompt changes.

### `gpt` (GPT-5.6 Sol / Terra / Luna)

- **Model trait:** a strong long-horizon reasoner. Its characteristic waste
  is spending depth on things that are already decided: re-deriving facts it
  established earlier, and re-running verification "for reassurance".
- **What OMH injects (subagent):** reasoning depth belongs to the hard parts
  of *this* unit; once the decisive fact is in view, act on it; a passed
  criterion is settled evidence, reopened only by contradicting output.
- **What OMH injects (composer):** compose outcome-first, but never compress
  the contract away — GPT's tight compositional style tends to drop stated
  boundaries and criteria while shortening a prompt, and a tighter prompt
  that loses an invariant is a worse prompt.
- **Source:** adapted research (oh-my-openagent stop-condition findings on
  high-effort models), one of the two original calibration entries.

### `claude` (Fable, Opus, Sonnet, Haiku)

- **Model trait:** conscientious to a fault. Left alone it grows the
  checklist mid-run ("while I'm here…"), adds just-to-be-sure verification
  passes, and — as a composer — fans out speculative subagents, including
  ones that only re-check its own work.
- **What OMH injects (subagent):** the numbered criteria are the *complete*
  checklist — do not grow it mid-run; deliberate deeply only where
  correctness is genuinely at risk, and let the single verification pass
  prove the mechanical steps.
- **What OMH injects (composer):** split only what the goal requires, no
  speculative units, and never spawn a subagent to double-check your own
  composition.
- **Source:** adapted research (same origin as `gpt`); the composer block was
  added after observing over-fan-out in live composition.

### `gemini` (Gemini 3.1 Pro)

- **Model trait:** fluent and confident narration. Its observed failure mode
  is asserting results from recall rather than from tool output, sounding
  "done" before verification has run, and creatively expanding beyond the
  declared boundary because the expansion seems like an improvement.
- **What OMH injects (subagent):** a claim without the tool output that
  proves it is not evidence — run the actual check and report from its
  output; done-sounding language before the mandatory verification pass is a
  failure, not optimism; expansion outside the boundary is a defect here.
- **What OMH injects (composer):** compose from tool-verified facts, not
  recall — run the inventory and readiness commands before naming owners or
  models; a unit is "prepared" only when the prepare command produced its
  artifact.
- **Source:** observed failure modes in live usage (authored in the
  per-family calibration commit; no upstream text existed for this shape).

### `grok` (Grok Code Fast)

- **Model trait:** speed-first, search-heavy. The risk profile is the inverse
  of the deep reasoners: not over-verification but *under*-verification —
  fast answers that skip the proof, and repeated re-querying when a search
  surfaces many candidates.
- **What OMH injects (subagent):** speed is the default and the numbered
  criteria are the brake — a fast first answer never skips the single
  mandatory verification pass; pick from search results once, by the stated
  criteria, and act.
- **What OMH injects (composer):** run the overlap and dependency-cycle
  checks *before* recording the contract, not after dispatch fails;
  re-querying for a better split is re-verifying a settled decision.
- **Source:** written fresh for OMH — the calibration commit records that
  grok had no upstream precedent; the content encodes the family's publicly
  stated speed-first design plus observed search-churn behavior.

### `kimi` (Kimi K3, K3 Ultrafast)

- **Model trait:** a deep decompose-compare-verify reasoning loop. Excellent
  on genuinely hard problems; wasteful on low-entropy mechanical steps, where
  it enumerates alternatives that no stated criterion distinguishes.
- **What OMH injects (subagent):** reserve the decompose-compare-verify loop
  for the genuinely hard parts; mechanical steps are low-entropy — execute
  them directly; if you catch yourself listing options for a step no
  criterion distinguishes, stop analyzing and act.
- **What OMH injects (composer):** partitioning work is mostly low-entropy —
  decide the split once and freeze it; keep the deep reasoning for boundary
  overlaps and dependency cycles; if two partitions both satisfy the
  boundaries, take the first and move.
- **Source:** observed failure modes in live OMH usage of Kimi K3 (authored
  in the per-family calibration commit).

### `glm` (GLM 5.2, 5.2 Ultrafast)

- **Model trait:** an interleaved-reasoning style — thinking woven between
  tool calls. That style genuinely improves tool-result interpretation, but
  applied indiscriminately it plans mechanical steps that need no plan.
- **What OMH injects (subagent):** use interleaved reasoning only where it
  improves a tool decision — interpret each result, choose the next bounded
  action, preserve prior reasoning context when the runtime exposes it;
  mechanical steps need no extended plan.
- **What OMH injects (composer):** interleave reasoning to interpret evidence
  between contract-building tools; mechanical field assembly needs no extra
  planning; freeze the smallest split once boundaries are clean.
- **Source:** observed failure modes plus the family's documented
  interleaved-thinking design; the GLM guidance shipped with the
  baseline-vs-calibrated benchmark harness so its effect is measurable.

### `qwen` (Qwen3-Coder)

- **Model trait:** the current Qwen3-Coder is, per its own release
  documentation, a **non-thinking** coding-agent model — it does not emit
  reasoning traces, and prompting it for chain-of-thought or thinking tags
  degrades it rather than helping.
- **What OMH injects (subagent):** do not ask it to emit reasoning or
  thinking tags; give the exact goal, repository state, allowed boundaries,
  tool schemas, and completion criteria; follow one explicit plan; recover
  from failures using observed tool output; stop after one passing
  verification run.
- **What OMH injects (composer):** freeze one ordered split with exact
  owners, boundaries, tool contracts, dependencies, and verification
  commands instead of requesting reasoning output.
- **Source:** provider-published model characteristics (Qwen3-Coder's
  non-thinking architecture); shipped with the benchmark harness.

### `deepseek` (DeepSeek versioned line)

- **Model trait:** a heterogeneous family — some variants are reasoning
  models, some are not, and the split moved across versions. The common
  error in the wild is applying legacy R1-era reasoning prompts to every
  DeepSeek model, which is wrong on the non-reasoning variants.
- **What OMH injects (subagent):** treat the model version and its declared
  thinking mode as *contract fields*; preserve runtime-provided reasoning
  context across tool results only on a reasoning-capable route; otherwise
  use the same explicit goal/boundaries/criteria without thinking tags; make
  the smallest correct change, verify once, stop.
- **What OMH injects (composer):** keep the DeepSeek version and thinking
  mode explicit in the prepared route; no synthetic thinking instructions on
  non-reasoning routes.
- **Source:** provider-published model characteristics (DeepSeek's
  reasoning/non-reasoning variant split); shipped with the benchmark
  harness.

### `generic` (mandatory fallback — solar and every unknown id today)

- **What OMH injects:** reserve extended reasoning for genuine ambiguity with
  materially different outcomes; decide once, act, verify once against the
  criteria, and stop — speed never skips the verification pass, and
  thoroughness never repeats it.
- **Why it exists:** an unknown family must never receive *weaker* discipline
  than a known one. The generic block carries the same core stop rules as
  every family block (a test asserts this), so putting `solar-pro2` or any
  unlisted model in a chain still yields a disciplined lane — what it misses
  is only the counter to its own family-specific failure mode.

### When the calibration is (and is not) applied

`calibration_for_route()` appends the family block **only when the routed
reasoning effort is `high`, `xhigh`, or `max`**. The calibrations exist to
counter the over-verification inertia of high-effort routes; low-effort
routes do not exhibit that inertia, and every byte rides a prepared prompt
whose worst-case assembled size is policy-gated in tests
(`UNIT_PROMPT_MAX_BYTES = 8000`) rather than truncated at runtime.

## Throughput overlays (per family, ULW-facing)

`build_throughput_overlay()` in `src/coding/throughput_prompting.py` gives
every family the base rules — batch independent tool calls and reads in one
shot, keep dependency-bound work sequential. Two advanced modes are gated to
the `gpt` family: `gpt_sol_codex_handoff` (a `*-sol` model on the codex
profile, adding single-eval-cell internal parallelism) and `gpt_hermes_ulw`
(gpt family on the hermes profile running ultrawork). *Why gated:* the
eval-batching behavior was designed and verified against GPT-5.6 Sol's
execution surface; extending an unverified throughput claim to other families
would be guidance without a stated reason, which the governing rule forbids.

## Routing, chains, and per-model bookkeeping

- **Mixture chains** — per-category ordered model chains (see the README
  model-routing section), user-editable via
  `~/.omh/routing/model-chains.json` (`mixture_chain_overrides/v1`).
- **Ultrafast variants are not a separate family** — `kimi-k3-ultrafast` and
  `glm-5.2-ultrafast` are the same base models served on OpenGateway's speed
  tier: same weights, same family (`kimi-` / `glm-` prefix match), and
  therefore exactly the same calibration — only serving speed differs. A
  `-ultrafast` variant the chains do not name still projects onto its base
  model's category for HUD labels (`mixture_category_for`), so speed tiers
  never unlabel a lane.
- **Cost approximation** — `APPROX_PRICE_PER_MTOK` in
  `src/plugin_bundle/omh/hermes_delegation.py` supplies `~$` estimates only
  when the host recorded no cost; models absent from the table show no
  approximation (never a fabricated number).
- **Fanout dispatch credentials** — `_PROVIDER_ENV` in
  `src/coding/hermes_child_dispatch.py` maps providers (anthropic, openai,
  gemini/google/vertex, qwen, deepseek, zai, opengateway, openrouter, nous,
  azure, bedrock, …) to the environment variables a dispatched child needs.

## Coverage matrix and known gaps

| Family | Recognized | Calibrated (both tables) | Status |
| --- | --- | --- | --- |
| `gpt`, `claude`, `gemini`, `grok`, `kimi`, `glm`, `qwen`, `deepseek` | yes | yes | full guidance, provenance above |
| `mistral`, `llama`, `codestral` | yes | no → `generic` | tracked in issue #1051 |
| `openai`, `anthropic` (bare-vendor prefixes) | yes | no → `generic` | tracked in issue #1051 |
| `solar` (Upstage) and other emerging families | no → `unknown` | no → `generic` | tracked in issue #1052 |

Gaps close by evidence, not by copywriting: a new calibration entry needs an
observed failure mode (or provider-stated characteristic) worth countering,
lands in both tables at once (parity-gated), and states its reason and source
in this document.
