from __future__ import annotations

import unittest

from _local_package import load_local_package

load_local_package()
from omh.context_safety import (
    CODING_PROGRESS_REPORTABLE_EVENTS,
    build_progress_event as build_chat_progress_event,
)
from omh.executor_progress import (
    DEFAULT_MINIMUM_REPEAT_INTERVAL_SECONDS,
    PROGRESS_EVENT_TYPES,
    TERMINAL_EVENT_TYPES,
    build_progress_binding,
    build_progress_event,
    build_safe_progress_signal,
    infer_progress_event_type,
    reported_event_types,
    should_report_event,
    update_binding_reporter_state,
)
from omh.plugin_bundle.omh.runtime_reader import EXECUTOR_PROGRESS_EVENT_TYPES


CLAIM_MISMATCH_EVENT_TYPES = ("reported_change_not_observed", "reported_success_contradicted")


def _binding(**overrides: object) -> dict[str, object]:
    binding = build_progress_binding(
        target_type="run",
        target_id="run-quality-floor",
        executor_profile="codex",
        codex_session_ref="codex-session-1",
        now="2026-07-25T00:00:00Z",
    )
    binding.update(overrides)
    return binding


def _event(
    binding: dict[str, object],
    event_type: str,
    *,
    observed_at: str,
    summary: str = "",
) -> dict[str, object]:
    # `transition_fingerprint` hashes the summary, so a distinct summary is what
    # separates "the same state observed again" (duplicate_transition) from "the
    # same kind of thing happened again" (repeat_interval).
    return build_progress_event(
        binding,
        event_type=event_type,
        summary=summary or f"observed {event_type}",
        observed_at=observed_at,
    )


class SuppressionExemptFloorTests(unittest.TestCase):
    """The floor that volume control must never cut through.

    A long delegated coding session drowns its own signal: the observed incident
    ran twelve fix/test cycles and only surfaced "4 file(s) were NOT modified
    this turn despite any wording above that may suggest otherwise" at the very
    end. Claim/observation mismatches and first occurrences have to survive any
    suppression added for volume.
    """

    def test_claim_mismatch_types_are_registered_as_progress_events(self) -> None:
        for event_type in CLAIM_MISMATCH_EVENT_TYPES:
            with self.subTest(event_type=event_type):
                self.assertIn(event_type, PROGRESS_EVENT_TYPES)

    def test_claim_mismatch_types_are_suppression_exempt(self) -> None:
        for event_type in CLAIM_MISMATCH_EVENT_TYPES:
            with self.subTest(event_type=event_type):
                self.assertIn(event_type, TERMINAL_EVENT_TYPES)

    def test_claim_mismatch_reports_even_when_the_same_type_just_reported(self) -> None:
        for event_type in CLAIM_MISMATCH_EVENT_TYPES:
            with self.subTest(event_type=event_type):
                binding = _binding(
                    last_reported_event_type=event_type,
                    last_reported_at="2026-07-25T00:00:00Z",
                    report_count=9,
                    reported_event_types=[event_type],
                )
                event = _event(binding, event_type, observed_at="2026-07-25T00:00:01Z")
                should_report, reason = should_report_event(binding, event, now="2026-07-25T00:00:01Z")
                self.assertTrue(should_report, reason)
                self.assertEqual(reason, "terminal_or_blocker")

    def test_claim_mismatch_survives_the_chat_facing_event_builder(self) -> None:
        for event_type in CLAIM_MISMATCH_EVENT_TYPES:
            with self.subTest(event_type=event_type):
                event = build_chat_progress_event(event_type, "patch reported applied; no file changed")
                self.assertEqual(
                    event["event_type"],
                    event_type,
                    "unregistered types normalize to status_update, erasing the mismatch signal",
                )

    def test_claim_mismatch_types_are_declared_reportable_in_the_progress_policy(self) -> None:
        for event_type in CLAIM_MISMATCH_EVENT_TYPES:
            with self.subTest(event_type=event_type):
                self.assertIn(event_type, CODING_PROGRESS_REPORTABLE_EVENTS)


class FirstOccurrenceGuaranteeTests(unittest.TestCase):
    def test_first_occurrence_of_a_non_terminal_type_always_reports(self) -> None:
        binding = _binding()
        event = _event(binding, "repo_exploration", observed_at="2026-07-25T00:00:01Z")
        should_report, reason = should_report_event(binding, event, now="2026-07-25T00:00:01Z")
        self.assertTrue(should_report, reason)
        self.assertEqual(reason, "first_occurrence")

    def test_repeat_inside_the_interval_is_still_suppressed(self) -> None:
        binding = _binding()
        first = _event(binding, "repo_exploration", observed_at="2026-07-25T00:00:01Z")
        binding = update_binding_reporter_state(
            binding, first, reported=True, reported_at="2026-07-25T00:00:01Z"
        )
        self.assertEqual(reported_event_types(binding), ["repo_exploration"])

        repeat = _event(
            binding,
            "repo_exploration",
            observed_at="2026-07-25T00:00:30Z",
            summary="observed repo_exploration in another directory",
        )
        should_report, reason = should_report_event(binding, repeat, now="2026-07-25T00:00:30Z")
        self.assertFalse(should_report)
        self.assertEqual(reason, "repeat_interval")

    def test_identical_state_observed_twice_is_suppressed_as_a_duplicate(self) -> None:
        binding = _binding()
        first = _event(binding, "repo_exploration", observed_at="2026-07-25T00:00:01Z")
        binding = update_binding_reporter_state(
            binding, first, reported=True, reported_at="2026-07-25T00:00:01Z"
        )
        same = _event(binding, "repo_exploration", observed_at="2026-07-25T00:00:30Z")
        should_report, reason = should_report_event(binding, same, now="2026-07-25T00:00:30Z")
        self.assertFalse(should_report)
        self.assertEqual(reason, "duplicate_transition")

    def test_reported_types_accumulate_without_duplicates(self) -> None:
        binding = _binding()
        for index, event_type in enumerate(("repo_exploration", "diff_started", "repo_exploration"), start=1):
            event = _event(binding, event_type, observed_at=f"2026-07-25T00:0{index}:00Z")
            binding = update_binding_reporter_state(
                binding, event, reported=True, reported_at=f"2026-07-25T00:0{index}:00Z"
            )
        self.assertEqual(reported_event_types(binding), ["repo_exploration", "diff_started"])

    def test_a_suppressed_event_does_not_consume_its_first_occurrence(self) -> None:
        binding = _binding()
        event = _event(binding, "repo_exploration", observed_at="2026-07-25T00:00:01Z")
        binding = update_binding_reporter_state(
            binding, event, reported=False, reported_at="2026-07-25T00:00:01Z"
        )
        self.assertEqual(reported_event_types(binding), [])

        retry = _event(binding, "repo_exploration", observed_at="2026-07-25T00:00:02Z")
        should_report, reason = should_report_event(binding, retry, now="2026-07-25T00:00:02Z")
        self.assertTrue(should_report, reason)
        self.assertEqual(reason, "first_occurrence")

    def test_legacy_bindings_without_the_field_keep_interval_behaviour(self) -> None:
        """A binding written before the field existed must not be re-opened.

        Treating an unknown history as "nothing reported yet" would un-suppress
        every type on a run already in flight.
        """
        binding = _binding(
            last_reported_event_type="repo_exploration",
            last_reported_at="2026-07-25T00:00:00Z",
            report_count=4,
        )
        binding.pop("reported_event_types")
        event = _event(binding, "repo_exploration", observed_at="2026-07-25T00:00:30Z")
        should_report, reason = should_report_event(binding, event, now="2026-07-25T00:00:30Z")
        self.assertFalse(should_report)
        self.assertEqual(reason, "repeat_interval")

    def test_repeat_after_the_interval_reports_again(self) -> None:
        binding = _binding(reported_event_types=["repo_exploration"], last_reported_event_type="repo_exploration")
        binding["last_reported_at"] = "2026-07-25T00:00:00Z"
        later = f"2026-07-25T00:{DEFAULT_MINIMUM_REPEAT_INTERVAL_SECONDS // 60 + 1:02d}:00Z"
        event = _event(binding, "repo_exploration", observed_at=later)
        should_report, reason = should_report_event(binding, event, now=later)
        self.assertTrue(should_report, reason)
        self.assertEqual(reason, "meaningful_transition")


class ClaimMismatchDetectionTests(unittest.TestCase):
    """The exemption list is worthless if nothing ever emits the exempt types."""

    def _signal(self, **overrides: object) -> dict[str, object]:
        signal = build_safe_progress_signal(
            executor_profile="claude_code",
            profile_progress_summary={
                "status": "running",
                "observable_activity": ["Codex changed files."],
            },
        )
        signal.update(overrides)
        return signal

    def test_reported_change_with_clean_git_is_flagged(self) -> None:
        signal = build_safe_progress_signal(
            executor_profile="claude_code",
            profile_progress_summary={"observable_activity": ["Codex changed files."]},
            git_status_short="",
            git_diff_stat="",
        )
        self.assertTrue(signal["git_observed"])
        self.assertEqual(infer_progress_event_type(signal), "reported_change_not_observed")

    def test_reported_change_with_a_real_diff_is_not_flagged(self) -> None:
        signal = build_safe_progress_signal(
            executor_profile="claude_code",
            profile_progress_summary={"observable_activity": ["Codex changed files."]},
            git_status_short=" M src/coding/executor_progress.py",
            git_diff_stat="1 file changed, 2 insertions(+)",
        )
        self.assertEqual(infer_progress_event_type(signal), "diff_started")

    def test_no_git_observation_never_claims_a_mismatch(self) -> None:
        """Callers that do not collect git state must not trip the detector."""
        signal = build_safe_progress_signal(
            executor_profile="claude_code",
            profile_progress_summary={"observable_activity": ["Codex changed files."]},
        )
        self.assertFalse(signal["git_observed"])
        self.assertNotEqual(infer_progress_event_type(signal), "reported_change_not_observed")

    def test_clean_git_without_any_change_claim_is_not_a_mismatch(self) -> None:
        signal = build_safe_progress_signal(
            executor_profile="claude_code",
            profile_progress_summary={"observable_activity": ["Codex inspected the repo."]},
            git_status_short="",
        )
        self.assertEqual(infer_progress_event_type(signal), "repo_exploration")

    def test_clean_exit_with_observed_failure_is_flagged(self) -> None:
        signal = build_safe_progress_signal(
            executor_profile="claude_code",
            process_status="exited_zero",
            profile_progress_summary={"status": "failed_or_error_observed"},
        )
        self.assertEqual(infer_progress_event_type(signal), "reported_success_contradicted")

    def test_clean_exit_without_observed_failure_stays_completed(self) -> None:
        signal = build_safe_progress_signal(executor_profile="claude_code", process_status="exited_zero")
        self.assertEqual(infer_progress_event_type(signal), "executor_completed")

    def test_failing_exit_with_observed_failure_is_not_a_contradiction(self) -> None:
        signal = build_safe_progress_signal(
            executor_profile="claude_code",
            process_status="failed",
            profile_progress_summary={"status": "failed_or_error_observed"},
        )
        self.assertNotEqual(infer_progress_event_type(signal), "reported_success_contradicted")

    def test_an_explicit_event_type_still_wins(self) -> None:
        signal = build_safe_progress_signal(
            executor_profile="claude_code",
            explicit_event_type="tests_passed",
            profile_progress_summary={"observable_activity": ["Codex changed files."]},
            git_status_short="",
        )
        self.assertEqual(infer_progress_event_type(signal), "tests_passed")


class VendoredBundleParityTests(unittest.TestCase):
    def test_bundle_event_types_match_the_source_of_truth(self) -> None:
        """The plugin bundle keeps its own copy and cannot import from src.

        Nothing enforced parity before, so adding an event type in one place and
        not the other silently dropped it at the plugin read boundary.
        """
        self.assertEqual(EXECUTOR_PROGRESS_EVENT_TYPES, set(PROGRESS_EVENT_TYPES))


if __name__ == "__main__":
    unittest.main()
