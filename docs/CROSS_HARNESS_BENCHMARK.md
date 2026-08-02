# Cross-harness benchmark contract

`cross_harness_benchmark/v1` is an agent/operator-facing deterministic comparison contract. It evaluates explicit submitted machine facts against a frozen metadata corpus. It does not launch an executor, call a network service, inspect a local skill directory, read or mutate an OMH runtime store, write persistent state, or prove general live executor quality.

This is not the normal human OMH workflow. Normal users ask Hermes for an outcome; operators use this surface to validate, score, and report bounded benchmark artifacts.

## Contract boundary and input

The checked-in corpus is [manifest.json](../benchmarks/cross-harness/v1/manifest.json). It has the exact `cross_harness_benchmark/v1` schema, ten fixed dimensions, and 15 fixtures. CLI input is one object:

```json
{
  "schema_version": "cross_harness_benchmark_cli_input/v1",
  "corpus": { "schema_version": "cross_harness_benchmark/v1" },
  "submission": {
    "schema_version": "cross_harness_benchmark_submission/v1"
  }
}
```

The evaluator derives result status; an input cannot self-report a pass or score. Each fixture result binds its exact `adapter_id` and `capability_id`, source metadata and source digest, and command binding and binding digest. A command binding fixes the harness, argv, working-directory class, source id and commit, expected exit, and expected semantic result. Changed pins, digests, argv, or harness ids are rejected instead of scored.

Production code hardcodes both the `v1` manifest digest and a digest of the parsed corpus identity as independent trust anchors. A caller cannot replace fixture predicates, source pins, commands, corpus ids, or metadata and make that replacement trusted by recomputing co-located digests. Parsing requires the declared digest to equal the built-in manifest anchor and the supplied payload to hash to that value. Evaluation and scoring then require the parsed corpus identity to match the second built-in anchor.

`cross_harness_benchmark/v1` is immutable. Any corpus content change requires a new versioned benchmark directory and schema such as `v2`, new examples, and newly reviewed production trust anchors for that version. Never update the `v1` anchors to bless changed `v1` content in place.

CLI JSON is bounded to 1,000,000 UTF-8 bytes, 64 levels, 10,000 containers, and 50,000 total nodes. The decoder rejects `NaN`, `Infinity`, and `-Infinity` as invalid JSON, converts decoder recursion failures to structured exit-2 errors, and applies the same byte limit to files and stdin. Oversize input returns `input_too_large`; excessive depth or structure returns `input_too_complex`.

A result also contains `child_results`. Any child with `result: "fail"` makes that fixture fail even when the parent command says `observed_exit: 0`. Child aggregation is therefore stronger than a parent exit-code claim.

## Corpus

All fixture data is synthetic metadata. `prompt.intent` and `prompt.constraint` are category labels, never raw user prompts.

| Dimension | Fixture id | Priority | Dynamic |
| --- | --- | --- | --- |
| Model selection | `model-explicit-selection` | P1 | no |
| Model selection | `model-neutral-fallback` | P1 | no |
| Routing | `routing-machine-decision` | P1 | no |
| Routing | `routing-unsupported-script` | P1 | no |
| Ralplan | `ralplan-consensus-artifact` | P1 | no |
| Ultragoal | `ultragoal-stop-contract` | P1 | no |
| Ultrawork | `ultrawork-observed-runtime` | P1 | yes |
| Ultrawork | `ultrawork-child-propagation` | P0 | yes |
| Installed skill | `installed-skill-parity` | P1 | no |
| Safety | `safety-prepared-boundary` | P0 | no |
| Safety | `safety-no-secret-material` | P0 | no |
| Evidence | `evidence-runtime-observation` | P0 | yes |
| Evidence | `evidence-command-binding` | P0 | yes |
| Reproducibility | `reproducibility-source-pin` | P0 | no |
| Reporting | `reporting-coverage-separation` | P1 | no |

A P0 fixture with status `fail` adds `p0_failure` and blocks certification. An unsupported P0 fixture is a coverage gap, not a successful P0 check.

## Evidence, scoring, and coverage

Evidence classes are ordered `prepared`, `static`, `test`, then `runtime`. A matching result below the fixture's required class is `partial`. For a dynamic fixture, `runtime` evidence with `runtime_observation: "prepared_not_observed"` is also partial with `runtime_not_observed`. Prepared metadata is never execution, review, CI, merge, or observed-runtime evidence.

Each dimension weighs 10 points (100 total). A dimension earns 10 when all its fixtures pass, 5 when its fixtures are only pass or partial, and 0 otherwise. The report keeps coverage separate: `coverage_supported` counts non-unsupported outcomes and `coverage_total` is 15. Missing results or unavailable adapters/capabilities are `unsupported`: they do not earn points and cannot improve quality.

Levels are mechanical: 0 has no earned points; 1 is below 50; 2 is 50–69; 3 is 70–99 without all fixtures passing; 4 has every fixture passing; 5 has every fixture passing plus observed runtime for every dynamic fixture. The level-four input records dynamic work as test evidence with `prepared_not_observed`; it is an offline level-4 contract result, not observed runtime work. The passing input records runtime evidence and observed dynamic facts, so it reaches level 5.

`certified: true` means contract certification only: no P0 failure, every fixture passes, dimension minimums are met, and the level is at least 4. Neither level 4 nor level 5 proves general live executor quality. A live-quality claim needs a separately approved isolated runtime benchmark and observed evidence; this offline contract deliberately provides neither.

## Checked-in machine inputs

All examples are complete CLI envelopes and validate through the same corpus parser, submission evaluator, and scorer used by the production command. [tests/test_cross_harness_benchmark_docs.py](../tests/test_cross_harness_benchmark_docs.py) asserts only the machine structure and derived outcomes, never documentation prose.

| File | Derived state | Score behaviour |
| --- | --- | --- |
| [example-passing-submission.json](../benchmarks/cross-harness/v1/example-passing-submission.json) | all 15 fixtures pass with observed runtime facts | 100, level 5, contract-certified |
| [example-level-four-submission.json](../benchmarks/cross-harness/v1/example-level-four-submission.json) | all fixtures pass, dynamic facts are test-only and unobserved | 100, level 4, contract-certified but not live observation |
| [example-failing-child-submission.json](../benchmarks/cross-harness/v1/example-failing-child-submission.json) | `ultrawork-child-propagation` has a failing child while parent exit is zero | P0 failure; non-certified |
| [example-unsupported-submission.json](../benchmarks/cross-harness/v1/example-unsupported-submission.json) | an adapter is unavailable | unsupported coverage; never a quality pass |
| [example-partial-submission.json](../benchmarks/cross-harness/v1/example-partial-submission.json) | prepared evidence where static is required | partial; never full quality |

The diagnostic failing, unsupported, and partial files intentionally submit one fixture; the other 14 become unsupported. They make the coverage gap visible and score at level 0. They are diagnostic inputs, not complete submissions.

## Operator command surface

The benchmark command is available to agents and operators. These are its exact commands.

```sh
uv run python -m omh.cli benchmark validate \
  --input benchmarks/cross-harness/v1/example-passing-submission.json

uv run python -m omh.cli benchmark score \
  --input benchmarks/cross-harness/v1/example-passing-submission.json

uv run python -m omh.cli benchmark report \
  --input benchmarks/cross-harness/v1/example-passing-submission.json
```

Use exactly one of `--input PATH` or `--stdin`. `validate` exits zero when the JSON and benchmark contract are valid, even if a fixture evaluates to a semantic failure. It exits nonzero for missing input, unavailable files, malformed JSON, non-object JSON, conflicting input modes, stale corpus, or another contract error. `score` and `report` exit nonzero when the score is not contract-certified; the failed-child, unsupported, and partial inputs therefore have nonzero score and report exits while retaining structured JSON output for inspection.

```sh
uv run python -m omh.cli benchmark score --stdin \
  < benchmarks/cross-harness/v1/example-passing-submission.json
```

## Manual QA

Run from the repository root.

1. Validate the passing input; confirm exit 0 and `valid: true`.
2. Score it; confirm `total: 100`, `level: 5`, and `certified: true`.
3. Report it; confirm outcomes, dimensions, score, coverage, unknowns, and claim boundary.
4. Score the level-four input; confirm level 4 and preserve the distinction between test evidence and observed runtime.
5. Validate the child-failure input; confirm a `fail` despite parent exit zero. Score and report must exit nonzero and include `p0_failure`.
6. Report the unsupported input; confirm unsupported coverage and a nonzero exit. Do not report it as pass.
7. Score the partial input; confirm partial status and a nonzero exit.
8. Run `uv run python -m omh.cli harness validate`; it remains a separate generated-harness validation surface.

The benchmark command must create no `.omh` directory or runtime artifact in an isolated directory. It is pure input-to-output evaluation: no network calls, subprocess dispatch, executor launch, persistent runtime state, skill-body loading, or production-routing mutation belongs here.

## Privacy and reporting

Keep corpus, submissions, and reports metadata-only. Never include raw user prompts, transcripts, absolute local paths, home directories, secrets, API keys, private keys, credentials, skill bodies, PII, or untrusted instruction text. Caller-supplied corpus metadata is rejected before evaluation or reporting unless it passes both trust-anchor checks above. Submission metadata also rejects common secret, absolute-path, script, and prompt-injection markers, but these controls are guardrails rather than permission to include sensitive data. Benchmark validation rejections return reason codes and never echo the rejected value. Use stable ids, relative repository metadata, capability ids, digests, reason codes, and bounded machine facts.

Offline source inspection, static metadata, and tests establish only their stated evidence class. In dashboards, issue reports, and automation, report the level and coverage with that class; never invent execution observation or a live-quality claim.
