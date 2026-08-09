"""Contract for `run_health_summary/v1` (issue #834).

One test class per acceptance criterion, plus the guards that keep each
criterion from passing vacuously:

- AC1 is a real differential. Two owners narrating in entirely different words
  that normalize to the same stream must produce byte-identical summaries apart
  from the owner attribution block. The counter-case -- an owner whose evidence
  ceiling refuses one of those words -- must produce a DIFFERENT summary, or the
  equality would only prove that the projection ignores its input.
- AC2 needs three states to be genuinely three. A test that only checks
  "unavailable exists" would pass on an implementation that never reports
  `unknown` and never reports a real `0`.
- AC3 is checked on both the write path (the parser) and the read path (the
  validator), because a hand-edited record never goes through the parser.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from _cli_harness import run_cli
from _local_package import load_local_package

load_local_package()

from omh.coding.context_safety import coding_progress_policy_enforcement  # noqa: E402
from omh.coding.owner_progress_normalization import (  # noqa: E402
    OWNERS_WITH_PROGRESS_LANE,
    UNMAPPED_NORMALIZED_EVENT,
)
from omh.local_store import atomic_write_json  # noqa: E402
from omh.runtime.run_health import (  # noqa: E402
    MAX_RUN_HEALTH_EVENTS,
    RUN_HEALTH_CLAIM_BOUNDARY,
    RUN_HEALTH_METRICS,
    RUN_HEALTH_STALENESS_THRESHOLD_MS,
    RUN_HEALTH_SUMMARY_SCHEMA_VERSION,
    build_run_health_summary,
    parse_run_health_input,
    render_run_health_summary_text,
    run_health_digest,
    unphased_normalized_events,
    validate_run_health_summary,
)


def _input(
    owner: str,
    events: list[tuple[str, int | None]],
    *,
    observed_at_ms: int = 9_000,
    run_id: str = "run-834",
    direction: str = "unclaimed",
    baseline_ref: str = "",
    evaluator_ref: str = "",
) -> dict[str, object]:
    return {
        "schema_version": "run_health_input/v1",
        "run_id": run_id,
        "owner": owner,
        "observed_at_ms": observed_at_ms,
        "events": [{"source_event": word, "at_ms": at_ms} for word, at_ms in events],
        "efficiency_claim": {
            "direction": direction,
            "baseline_ref": baseline_ref,
            "evaluator_ref": evaluator_ref,
        },
    }


def _summary(owner: str, events: list[tuple[str, int | None]], **kwargs: object) -> dict[str, object]:
    return build_run_health_summary(parse_run_health_input(_input(owner, events, **kwargs)))  # type: ignore[arg-type]


def _without_owner(summary: dict[str, object]) -> dict[str, object]:
    stripped = dict(summary)
    stripped.pop("owner_attribution")
    return stripped


def _metric(summary: dict[str, object], name: str) -> dict[str, object]:
    metrics = summary["metrics"]
    assert isinstance(metrics, dict)
    value = metrics[name]
    assert isinstance(value, dict)
    return value


# The same three positions in the run, said in two owner-native dialects that
# share no word: codex stream words on the left, Claude Code stream envelope
# types on the right. Both normalize to
# executor_dispatched / progress_observed / executor_completed.
_CODEX_NATIVE = [("dispatch_to_executor", 1_000), ("item.completed", 1_500), ("turn.completed", 2_400)]
_CLAUDE_NATIVE = [("system", 1_000), ("assistant", 1_500), ("result", 2_400)]


class AcceptanceCriterionOneCrossOwnerTests(unittest.TestCase):
    """AC1: the same normalized events produce the same health summary across owners."""

    def test_two_owners_with_no_shared_source_word_produce_one_summary(self) -> None:
        codex = _summary("codex", _CODEX_NATIVE)
        claude = _summary("claude-code", _CLAUDE_NATIVE)

        self.assertEqual(
            [observation["normalized_event"] for observation in codex["observations"]],  # type: ignore[union-attr]
            ["executor_dispatched", "progress_observed", "executor_completed"],
        )
        self.assertEqual(codex["observations"], claude["observations"])
        self.assertEqual(codex["health_digest"], claude["health_digest"])
        self.assertEqual(_without_owner(codex), _without_owner(claude))
        self.assertEqual(codex["owner_attribution"], {"owner": "codex", "owner_supported": True, "evidence_ceiling": "verified"})
        self.assertEqual(
            claude["owner_attribution"],
            {"owner": "claude-code", "owner_supported": True, "evidence_ceiling": "verified"},
        )

    def test_every_lane_owner_agrees_on_the_shared_dialect(self) -> None:
        shared = [("dispatch_to_executor", 1_000), ("diff_started", 2_000), ("workflow_completed", 4_000)]
        digests = {owner: _summary(owner, shared)["health_digest"] for owner in OWNERS_WITH_PROGRESS_LANE}

        self.assertEqual(len(set(digests.values())), 1, digests)
        self.assertEqual(len(digests), 4)

    def test_owner_aliases_fold_onto_the_same_summary(self) -> None:
        self.assertEqual(_summary("claude", _CLAUDE_NATIVE), _summary("claude_code", _CLAUDE_NATIVE))

    def test_an_owner_whose_ceiling_refuses_the_word_gets_a_different_summary(self) -> None:
        """The counter-case that keeps the equality above from being vacuous.

        `omo-runtime` has no readable structured stream, so its evidence ceiling
        stops at `result_claimed` and `full_tests_passed` cannot become
        `tests_passed`. A different normalized stream must project a different
        health summary -- with the refusal counted as an evidence gap, not
        rounded to the neighbouring verified event.
        """
        words = [("dispatch_to_executor", 1_000), ("full_tests_passed", 2_000)]
        codex = _summary("codex", words)
        omo = _summary("omo-runtime", words)

        self.assertEqual(codex["observations"][1]["normalized_event"], "tests_passed")  # type: ignore[index]
        self.assertEqual(omo["observations"][1]["normalized_event"], UNMAPPED_NORMALIZED_EVENT)
        self.assertNotEqual(codex["health_digest"], omo["health_digest"])
        self.assertNotEqual(_without_owner(codex), _without_owner(omo))
        self.assertEqual(_metric(codex, "evidence_gap_count")["value"], 0)
        self.assertEqual(_metric(omo, "evidence_gap_count")["value"], 1)

    def test_the_projection_is_deterministic(self) -> None:
        self.assertEqual(_summary("codex", _CODEX_NATIVE), _summary("codex", _CODEX_NATIVE))

    def test_the_digest_ignores_owner_and_the_now_dependent_fields(self) -> None:
        early = _summary("codex", _CODEX_NATIVE, observed_at_ms=3_000)
        late = _summary("codex", _CODEX_NATIVE, observed_at_ms=800_000)

        self.assertEqual(early["health_digest"], late["health_digest"])
        self.assertEqual(early["staleness"], "fresh")
        self.assertEqual(late["staleness"], "stale")
        self.assertNotEqual(_metric(early, "idle_duration_ms"), _metric(late, "idle_duration_ms"))

        moved = _summary("codex", [("dispatch_to_executor", 1_000), ("item.completed", 1_500), ("turn.completed", 2_401)])
        self.assertNotEqual(early["health_digest"], moved["health_digest"])

    def test_the_module_never_reads_a_clock(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "src" / "runtime" / "run_health.py").read_text(encoding="utf-8")

        for forbidden in ("import time", "from time", "import datetime", "from datetime", "monotonic(", "time()"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


class AcceptanceCriterionTwoUnavailableTests(unittest.TestCase):
    """AC2: unavailable metrics are shown as unavailable rather than estimated."""

    def test_unknown_unavailable_and_zero_are_three_distinguishable_states(self) -> None:
        summary = _summary(
            "codex",
            [("dispatch_to_executor", 1_000), ("diff_started", 1_000), ("progress_observed", None)],
        )

        genuine_zero = _metric(summary, "dispatch_phase_duration_ms")
        never_observed = _metric(summary, "verification_phase_duration_ms")
        no_clock = _metric(summary, "total_duration_ms")

        self.assertEqual(genuine_zero, {"state": "observed", "value": 0, "reason": ""})
        self.assertEqual(never_observed, {"state": "unknown", "value": None, "reason": "phase_not_observed"})
        self.assertEqual(
            no_clock,
            {"state": "unavailable", "value": None, "reason": "boundary_event_carried_no_timestamp"},
        )
        self.assertEqual(len({genuine_zero["state"], never_observed["state"], no_clock["state"]}), 3)
        self.assertIsNotNone(genuine_zero["value"])
        self.assertIsNone(never_observed["value"])
        self.assertIsNone(no_clock["value"])
        self.assertEqual(validate_run_health_summary(summary), [])

    def test_a_missing_bound_is_never_replaced_by_the_observation_instant(self) -> None:
        """The one estimate a projection like this is tempted to make.

        An execution phase that nothing later closed has a plausible "duration"
        available -- `observed_at_ms` minus the phase start. Substituting it
        would make an in-flight run look measured. Moving the observation
        instant must therefore move `idle_duration_ms` and `staleness` and
        nothing else.
        """
        early = _summary("codex", [("dispatch_to_executor", 1_000), ("diff_started", 2_000)], observed_at_ms=2_500)
        late = _summary("codex", [("dispatch_to_executor", 1_000), ("diff_started", 2_000)], observed_at_ms=900_000)

        execution = _metric(early, "execution_phase_duration_ms")
        self.assertEqual(
            execution,
            {"state": "unknown", "value": None, "reason": "phase_not_closed_by_a_later_observed_phase"},
        )
        for name in RUN_HEALTH_METRICS:
            if name == "idle_duration_ms":
                continue
            with self.subTest(metric=name):
                self.assertEqual(_metric(early, name), _metric(late, name))
        self.assertEqual(_metric(early, "idle_duration_ms")["value"], 500)
        self.assertEqual(_metric(late, "idle_duration_ms")["value"], 898_000)

    def test_a_missing_phase_never_leaks_its_time_into_a_neighbour(self) -> None:
        closed = _summary(
            "codex",
            [("dispatch_to_executor", 1_000), ("diff_started", 2_000), ("tests_started", 5_000)],
        )
        unclosed = _summary("codex", [("dispatch_to_executor", 1_000), ("diff_started", 2_000)])

        self.assertEqual(_metric(closed, "execution_phase_duration_ms")["value"], 3_000)
        self.assertIsNone(_metric(unclosed, "execution_phase_duration_ms")["value"])
        self.assertEqual(
            _metric(closed, "dispatch_phase_duration_ms"),
            _metric(unclosed, "dispatch_phase_duration_ms"),
        )
        self.assertEqual(_metric(closed, "total_duration_ms")["value"], 4_000)
        self.assertEqual(_metric(unclosed, "total_duration_ms")["value"], 1_000)

    def test_no_metric_in_any_shape_carries_a_value_it_did_not_observe(self) -> None:
        shapes = [
            [],
            [("dispatch_to_executor", None)],
            [("dispatch_to_executor", 1_000)],
            [("dispatch_to_executor", None), ("diff_started", 2_000)],
            [("dispatch_to_executor", 1_000), ("workflow_started", 1_100), ("turn.completed", 4_000)],
            [("targeted_tests_started", 1_000), ("targeted_tests_failed", 2_000), ("targeted_tests_started", 3_000)],
        ]
        for events in shapes:
            summary = _summary("codex", events)
            with self.subTest(events=events):
                self.assertEqual(validate_run_health_summary(summary), [])
                for name in RUN_HEALTH_METRICS:
                    metric = _metric(summary, name)
                    if metric["state"] == "observed":
                        self.assertIsNotNone(metric["value"])
                        self.assertEqual(metric["reason"], "")
                    else:
                        self.assertIsNone(metric["value"])
                        self.assertNotEqual(metric["reason"], "")

    def test_nothing_observed_leaves_every_metric_unknown_rather_than_zero(self) -> None:
        summary = _summary("codex", [])

        for name in RUN_HEALTH_METRICS:
            with self.subTest(metric=name):
                self.assertEqual(_metric(summary, name), {"state": "unknown", "value": None, "reason": "no_observed_events"})
        self.assertEqual(summary["staleness"], "unknown")

    def test_the_validator_refuses_a_number_attached_to_an_absent_metric(self) -> None:
        summary = _summary("codex", [("dispatch_to_executor", 1_000), ("diff_started", 2_000)])
        summary["metrics"]["execution_phase_duration_ms"] = {  # type: ignore[index]
            "state": "unknown",
            "value": 1_500,
            "reason": "phase_not_closed_by_a_later_observed_phase",
        }

        errors = validate_run_health_summary(summary)
        self.assertTrue(any("must be null unless the metric is observed" in error for error in errors), errors)

    def test_the_validator_keeps_the_two_absence_vocabularies_apart(self) -> None:
        summary = _summary("codex", [("dispatch_to_executor", 1_000), ("diff_started", 2_000)])
        summary["metrics"]["execution_phase_duration_ms"] = {  # type: ignore[index]
            "state": "unknown",
            "value": None,
            "reason": "boundary_event_carried_no_timestamp",
        }

        errors = validate_run_health_summary(summary)
        self.assertTrue(any("not a declared unknown reason" in error for error in errors), errors)

    def test_the_text_surface_names_the_absence_instead_of_printing_a_blank(self) -> None:
        summary = _summary(
            "codex",
            [("dispatch_to_executor", 1_000), ("diff_started", 1_000), ("progress_observed", None)],
        )
        text = render_run_health_summary_text(summary)

        self.assertIn("- dispatch: 0 ms", text)
        self.assertIn("- verification: unknown (phase_not_observed)", text)
        self.assertIn("Total duration: unavailable (boundary_event_carried_no_timestamp)", text)


class AcceptanceCriterionThreeEfficiencyClaimTests(unittest.TestCase):
    """AC3: no efficiency claim without a named baseline and a named evaluator."""

    def test_the_parser_refuses_a_comparative_direction_with_a_name_missing(self) -> None:
        for direction in ("improved", "regressed", "unchanged"):
            for baseline, evaluator in (("", ""), ("baseline-a", ""), ("", "evaluator-a")):
                with self.subTest(direction=direction, baseline=baseline, evaluator=evaluator):
                    with self.assertRaisesRegex(ValueError, "named baseline_ref and evaluator_ref"):
                        parse_run_health_input(
                            _input(
                                "codex",
                                _CODEX_NATIVE,
                                direction=direction,
                                baseline_ref=baseline,
                                evaluator_ref=evaluator,
                            )
                        )

    def test_a_named_baseline_and_evaluator_admits_the_claim(self) -> None:
        summary = _summary(
            "codex",
            _CODEX_NATIVE,
            direction="improved",
            baseline_ref="run-833-baseline",
            evaluator_ref="omh-run-health-differential",
        )

        self.assertEqual(
            summary["efficiency_claim"],
            {
                "direction": "improved",
                "baseline_ref": "run-833-baseline",
                "evaluator_ref": "omh-run-health-differential",
                "gate": "named_baseline_and_evaluator",
            },
        )
        self.assertEqual(validate_run_health_summary(summary), [])

    def test_the_validator_refuses_a_hand_edited_improvement_claim(self) -> None:
        summary = _summary("codex", _CODEX_NATIVE)
        summary["efficiency_claim"]["direction"] = "improved"  # type: ignore[index]
        summary["health_digest"] = run_health_digest(summary)

        errors = validate_run_health_summary(summary)
        self.assertEqual(
            [error for error in errors if "named baseline_ref and evaluator_ref" in error],
            [
                "run_health_summary.efficiency_claim.direction other than unclaimed requires a named "
                "baseline_ref and evaluator_ref"
            ],
        )

    def test_the_gate_cannot_be_hand_set_to_agree_with_the_claim(self) -> None:
        summary = _summary("codex", _CODEX_NATIVE)
        summary["efficiency_claim"].update({"direction": "improved", "gate": "named_baseline_and_evaluator"})  # type: ignore[union-attr]
        summary["health_digest"] = run_health_digest(summary)

        errors = validate_run_health_summary(summary)
        self.assertTrue(any("gate must be derived from" in error for error in errors), errors)
        self.assertTrue(any("named baseline_ref and evaluator_ref" in error for error in errors), errors)

    def test_an_unclaimed_summary_states_the_shut_gate(self) -> None:
        summary = _summary("codex", _CODEX_NATIVE)

        self.assertEqual(summary["efficiency_claim"]["gate"], "no_named_baseline_and_evaluator")  # type: ignore[index]
        self.assertIn("named baseline and a named evaluator", str(summary["claim_boundary"]))


class RunHealthDerivationTests(unittest.TestCase):
    def test_every_normalized_word_has_a_phase_except_the_unmapped_one(self) -> None:
        self.assertEqual(unphased_normalized_events(), (UNMAPPED_NORMALIZED_EVENT,))

    def test_a_repeated_verification_counts_as_a_retry(self) -> None:
        summary = _summary(
            "codex",
            [
                ("dispatch_to_executor", 1_000),
                ("tests_started", 2_000),
                ("targeted_tests_failed", 3_000),
                ("tests_started", 4_000),
                ("targeted_tests_passed", 5_000),
                ("turn.completed", 6_000),
            ],
        )

        self.assertEqual(_metric(summary, "retry_count")["value"], 1)
        self.assertEqual(_metric(summary, "verification_phase_duration_ms")["value"], 1_000)
        self.assertEqual(_metric(summary, "unobserved_phase_count")["value"], 1)

    def test_an_unmapped_word_neither_retries_nor_closes_a_phase(self) -> None:
        summary = _summary(
            "codex",
            [("dispatch_to_executor", 1_000), ("workflow_started", 2_000), ("diff_started", 3_000)],
        )

        self.assertEqual(summary["observations"][1]["normalized_event"], UNMAPPED_NORMALIZED_EVENT)  # type: ignore[index]
        self.assertEqual(_metric(summary, "retry_count")["value"], 0)
        self.assertEqual(_metric(summary, "evidence_gap_count")["value"], 1)
        self.assertEqual(_metric(summary, "dispatch_phase_duration_ms")["value"], 2_000)

    def test_failure_class_reports_the_highest_severity_observed(self) -> None:
        cases = {
            "no_failure_observed": [("dispatch_to_executor", 1_000), ("turn.completed", 2_000)],
            "claim_not_corroborated": [("reported_change_not_observed", 1_000)],
            "executor_blocked": [("blocker_encountered", 1_000), ("reported_change_not_observed", 2_000)],
            "verification_failed": [("blocker_encountered", 1_000), ("targeted_tests_failed", 2_000)],
            "executor_failed": [("targeted_tests_failed", 1_000), ("failure_discovered", 2_000)],
        }
        for expected, events in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(_metric(_summary("codex", events), "failure_class")["value"], expected)

    def test_staleness_turns_over_exactly_at_the_declared_threshold(self) -> None:
        events = [("dispatch_to_executor", 1_000), ("diff_started", 2_000)]
        at_threshold = _summary("codex", events, observed_at_ms=2_000 + RUN_HEALTH_STALENESS_THRESHOLD_MS)
        past_threshold = _summary("codex", events, observed_at_ms=2_001 + RUN_HEALTH_STALENESS_THRESHOLD_MS)

        self.assertEqual(at_threshold["staleness"], "fresh")
        self.assertEqual(past_threshold["staleness"], "stale")
        self.assertEqual(at_threshold["staleness_threshold_ms"], RUN_HEALTH_STALENESS_THRESHOLD_MS)

    def test_an_unclocked_last_event_makes_staleness_unavailable(self) -> None:
        summary = _summary("codex", [("dispatch_to_executor", 1_000), ("diff_started", None)])

        self.assertEqual(summary["staleness"], "unavailable")
        self.assertEqual(_metric(summary, "idle_duration_ms")["reason"], "boundary_event_carried_no_timestamp")

    def test_the_claim_boundary_denies_every_downstream_evidence_class(self) -> None:
        for denied in ("execution", "verification", "review", "CI", "merge-readiness", "merge"):
            with self.subTest(denied=denied):
                self.assertIn(denied, RUN_HEALTH_CLAIM_BOUNDARY)
        self.assertIn("metadata-only", RUN_HEALTH_CLAIM_BOUNDARY)


class RunHealthInputBoundsTests(unittest.TestCase):
    def test_the_parser_refuses_an_inexact_key_set(self) -> None:
        extra = _input("codex", _CODEX_NATIVE)
        extra["notes"] = "extra"
        with self.assertRaisesRegex(ValueError, "exact run_health_input/v1 fields"):
            parse_run_health_input(extra)

        missing = _input("codex", _CODEX_NATIVE)
        missing.pop("owner")
        with self.assertRaisesRegex(ValueError, "exact run_health_input/v1 fields"):
            parse_run_health_input(missing)

    def test_the_parser_refuses_a_backwards_clock_and_a_stale_observation_instant(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not move backwards"):
            parse_run_health_input(_input("codex", [("diff_started", 2_000), ("tests_started", 1_000)]))
        with self.assertRaisesRegex(ValueError, "must not precede the last observed event"):
            parse_run_health_input(_input("codex", [("diff_started", 2_000)], observed_at_ms=1_999))

    def test_the_parser_bounds_the_event_list(self) -> None:
        too_many = _input("codex", [("diff_started", 1_000)] * (MAX_RUN_HEALTH_EVENTS + 1))
        with self.assertRaisesRegex(ValueError, "at most 100 items"):
            parse_run_health_input(too_many)

    def test_the_parser_refuses_secret_shaped_references(self) -> None:
        for secret in ("AKIAIOSFODNN7EXAMPLE", "gho_12345678901234567890", "AIzaSyDUMMYABCDEFGHIJKLMNOPQRSTUVWX123"):
            with self.subTest(secret=secret):
                with self.assertRaisesRegex(ValueError, "safe opaque metadata reference"):
                    parse_run_health_input(
                        _input(
                            "codex",
                            _CODEX_NATIVE,
                            direction="improved",
                            baseline_ref=secret,
                            evaluator_ref="omh-run-health-differential",
                        )
                    )
                with self.assertRaisesRegex(ValueError, "safe opaque metadata reference"):
                    parse_run_health_input(_input("codex", [(secret, 1_000)]))

    def test_the_parser_refuses_an_event_missing_its_clock_key(self) -> None:
        payload = _input("codex", [])
        payload["events"] = [{"source_event": "diff_started"}]
        with self.assertRaisesRegex(ValueError, "exactly source_event and at_ms"):
            parse_run_health_input(payload)


class RunHealthValidatorTests(unittest.TestCase):
    def test_the_validator_checks_the_key_set_in_both_directions(self) -> None:
        summary = _summary("codex", _CODEX_NATIVE)

        extra = dict(summary)
        extra["notes"] = "hand added"
        self.assertEqual(
            validate_run_health_summary(extra),
            ["run_health_summary has an unsupported key: notes"],
        )

        missing = dict(summary)
        missing.pop("staleness")
        self.assertEqual(
            validate_run_health_summary(missing),
            ["run_health_summary is missing a required key: staleness"],
        )

    def test_the_validator_rederives_a_hand_edited_metric(self) -> None:
        summary = _summary("codex", _CODEX_NATIVE)
        summary["metrics"]["total_duration_ms"] = {"state": "observed", "value": 12, "reason": ""}  # type: ignore[index]
        summary["health_digest"] = run_health_digest(summary)

        self.assertEqual(
            validate_run_health_summary(summary),
            ["run_health_summary.metrics.total_duration_ms must match the value derived from observations"],
        )

    def test_the_validator_rederives_the_owner_attribution(self) -> None:
        summary = _summary("omo-runtime", [("dispatch_to_executor", 1_000)])
        summary["owner_attribution"]["evidence_ceiling"] = "verified"  # type: ignore[index]

        errors = validate_run_health_summary(summary)
        self.assertIn(
            "run_health_summary.owner_attribution.evidence_ceiling must match the owner's declared evidence ceiling",
            errors,
        )

    def test_the_validator_rederives_the_digest(self) -> None:
        summary = _summary("codex", _CODEX_NATIVE)
        summary["run_id"] = "run-999"

        errors = validate_run_health_summary(summary)
        self.assertIn("run_health_summary.health_digest must match the derived health digest", errors)

    def test_the_validator_refuses_a_word_outside_the_normalized_vocabulary(self) -> None:
        summary = _summary("codex", _CODEX_NATIVE)
        summary["observations"][0]["normalized_event"] = "targeted_tests_passed"  # type: ignore[index]

        errors = validate_run_health_summary(summary)
        self.assertTrue(
            any("not in the normalized progress vocabulary" in error for error in errors),
            errors,
        )

    def test_the_validator_refuses_a_staleness_verdict_that_contradicts_the_idle_metric(self) -> None:
        summary = _summary("codex", _CODEX_NATIVE)
        summary["staleness"] = "stale"
        summary["health_digest"] = run_health_digest(summary)

        errors = validate_run_health_summary(summary)
        self.assertIn(
            "run_health_summary.staleness must match the verdict derived from idle_duration_ms",
            errors,
        )

    def test_the_validator_accepts_every_summary_this_module_builds(self) -> None:
        for owner in OWNERS_WITH_PROGRESS_LANE:
            for events in ([], _CODEX_NATIVE, [("full_tests_passed", 1_000)]):
                with self.subTest(owner=owner, events=events):
                    self.assertEqual(validate_run_health_summary(_summary(owner, events)), [])


class RunHealthCommandTests(unittest.TestCase):
    def _write_input(self, root: Path, payload: dict[str, object]) -> Path:
        path = root / "run_health_input.json"
        atomic_write_json(path, payload)
        return path

    def test_the_command_defaults_to_plain_text(self) -> None:
        with TemporaryDirectory() as tmp:
            path = self._write_input(Path(tmp), _input("claude-code", _CLAUDE_NATIVE))
            status, stdout, stderr = run_cli(["runtime", "health-summary", "--input", str(path)], output_json=False)

        self.assertEqual(status, 0, stderr)
        self.assertIn("Run health summary (OMH projection)", stdout)
        self.assertIn("Owner: claude-code (progress lane: yes, evidence ceiling: verified)", stdout)
        self.assertIn("Efficiency claim: unclaimed", stdout)
        self.assertIn("For machine-readable output, rerun with `--json`.", stdout)
        self.assertNotIn("\"schema_version\"", stdout)

    def test_the_command_opts_into_the_machine_payload(self) -> None:
        with TemporaryDirectory() as tmp:
            path = self._write_input(Path(tmp), _input("codex", _CODEX_NATIVE))
            status, stdout, stderr = run_cli(
                ["runtime", "health-summary", "--input", str(path), "--json"],
                output_json=False,
            )

        self.assertEqual(status, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["schema_version"], RUN_HEALTH_SUMMARY_SCHEMA_VERSION)
        self.assertEqual(payload["health_digest"], _summary("codex", _CODEX_NATIVE)["health_digest"])
        self.assertEqual(validate_run_health_summary(payload), [])

    def test_the_command_refuses_an_efficiency_claim_with_nobody_named(self) -> None:
        with TemporaryDirectory() as tmp:
            payload = _input("codex", _CODEX_NATIVE, direction="improved", baseline_ref="run-833")
            path = self._write_input(Path(tmp), payload)
            status, _stdout, stderr = run_cli(["runtime", "health-summary", "--input", str(path)], output_json=False)

        self.assertEqual(status, 2)
        self.assertIn("named baseline_ref and evaluator_ref", stderr)

    def test_the_command_is_declared_a_bounded_polled_surface(self) -> None:
        self.assertIn("omh runtime health-summary", coding_progress_policy_enforcement()["bounded_surfaces"])

    def test_the_documented_example_is_the_output_the_renderer_produces(self) -> None:
        """The doc block in `docs/CODING-OBSERVABILITY.md` is real output, not a sketch.

        Read in text mode, so a CRLF checkout compares the same as an LF one.
        """
        events = [
            ("system", 1_000),
            ("assistant", 2_000),
            ("tests_started", 3_000),
            ("targeted_tests_failed", 4_000),
            ("tests_started", 5_000),
            ("targeted_tests_failed", 6_000),
        ]
        rendered = render_run_health_summary_text(_summary("claude-code", events))
        # The doc elides the two trailing lines, which are constant boilerplate.
        documented = "\n".join(rendered.splitlines()[:-2])
        doc = (Path(__file__).resolve().parents[1] / "docs" / "CODING-OBSERVABILITY.md").read_text(encoding="utf-8")

        self.assertIn(documented, doc)


if __name__ == "__main__":
    unittest.main()
