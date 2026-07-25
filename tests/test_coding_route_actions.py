from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from _local_package import load_local_package

load_local_package()

from omh.paths import resolve_paths
from omh.plugin_bundle.omh.awareness import awareness_route_hint
from omh.profiles.setup import write_setup_profile
from omh.routing.action_copy import NEXT_ACTION_LABELS
from omh.routing.coding_route_actions import (
    CODING_ROUTE_LANE_NEXT_ACTION,
    CODING_ROUTE_NEXT_ACTIONS,
    COMPATIBLE_ROUTE_NEXT_ACTION,
    NAMED_EXECUTOR_NEXT_ACTION,
    RECORDED_OWNER_NEXT_ACTION,
    USER_CHOICE_NEXT_ACTION,
    named_coding_agent_phrase_parity,
    resolve_coding_route_decision,
)
from omh.routing.localization import normalized_phrase
from omh.wrapper.contract import build_chat_interaction_payload


# One message per coding-delivery route-hint site. Direct `ultraprocess`, broad
# `coding_delivery`, and `test_until_pass_delivery` have to answer the coding-owner
# question the same way, so they are asserted together rather than one by one.
CODING_DELIVERY_SITE_MESSAGES: tuple[tuple[str, str], ...] = (
    ("direct_workflow_invocation", "Use OMH ultraprocess for: improve README and open PR"),
    ("coding_delivery", "implement the dark mode toggle and open a pr"),
    ("test_until_pass_delivery", "테스트 통과할때까지 고쳐줘"),
)

# Overroute guards: advisor, customer-signal, and executor-comparison requests. None of
# them is an unambiguous delivery request, so none of them may auto-select a coding owner.
NON_CODING_DELIVERY_MESSAGES: tuple[tuple[str, str], ...] = (
    ("advisor", "ask claude for a second opinion on this plan"),
    ("customer_signal", "users report a bug in the checkout page"),
    ("customer_signal_ko", "고객들이 결제 실패 이슈를 계속 제보해요"),
    ("executor_comparison", "should i use codex or claude code for this?"),
)

# Customer-signal work stays on the feedback lane, so it never reaches a coding-owner
# decision at all. Kept separate because awareness has no advisor lane of its own.
CUSTOMER_SIGNAL_MESSAGES: tuple[str, ...] = (
    "users report a bug in the checkout page",
    "고객들이 결제 실패 이슈를 계속 제보해요",
)


def _decision(message: str, **kwargs: str):
    return resolve_coding_route_decision(normalized_phrase(message), **kwargs)


class CodingRouteActionVocabularyTests(unittest.TestCase):
    def test_four_states_resolve_to_four_distinct_next_actions(self) -> None:
        named = _decision("use codex to fix the login bug")
        recorded = _decision("implement the dark mode toggle and open a pr", recorded_owner="claude-code")
        automatic = _decision("implement the dark mode toggle in a worktree with parallel workers")
        fallback = _decision("implement the dark mode toggle and open a pr")

        self.assertEqual(named.next_action, NAMED_EXECUTOR_NEXT_ACTION)
        self.assertEqual(recorded.next_action, RECORDED_OWNER_NEXT_ACTION)
        self.assertEqual(automatic.next_action, COMPATIBLE_ROUTE_NEXT_ACTION)
        self.assertEqual(fallback.next_action, USER_CHOICE_NEXT_ACTION)

        actions = {named.next_action, recorded.next_action, automatic.next_action, fallback.next_action}
        self.assertEqual(len(actions), 4)
        self.assertEqual(actions, set(CODING_ROUTE_NEXT_ACTIONS))

    def test_every_coding_route_action_has_a_route_label(self) -> None:
        for action in CODING_ROUTE_NEXT_ACTIONS:
            with self.subTest(action=action):
                self.assertIn(action, NEXT_ACTION_LABELS)
                self.assertTrue(NEXT_ACTION_LABELS[action].strip())
        self.assertIn(CODING_ROUTE_LANE_NEXT_ACTION, NEXT_ACTION_LABELS)

    def test_owner_phrase_groups_still_cover_the_policy_executor_names(self) -> None:
        self.assertTrue(named_coding_agent_phrase_parity())

    def test_automatic_route_carries_source_reason_and_confidence(self) -> None:
        automatic = _decision("implement the dark mode toggle in a worktree with parallel workers")

        self.assertEqual(automatic.source, "request_capability_match")
        self.assertEqual(automatic.confidence, "medium")
        self.assertEqual(automatic.selected_route_family, "runtime_handoff")
        self.assertTrue(automatic.reason.strip())
        self.assertTrue(automatic.matched_cues)
        self.assertFalse(automatic.choice_required)
        # An automatic route names a compatible handoff shape, never a vendor to dispatch.
        self.assertEqual(automatic.selected_owner, "")

    def test_named_and_recorded_states_report_the_owner_and_its_source(self) -> None:
        named = _decision("codex로 이 버그 고쳐줘")
        recorded = _decision("implement the dark mode toggle and open a pr", recorded_owner="omx-runtime")

        self.assertEqual(named.selected_owner, "codex")
        self.assertEqual(named.source, "request_named_executor")
        self.assertEqual(named.confidence, "high")
        self.assertEqual(recorded.selected_owner, "omx-runtime")
        self.assertEqual(recorded.source, "recorded_setup_preference")
        self.assertEqual(recorded.confidence, "high")

    def test_caller_fixed_executor_target_is_a_named_executor_state(self) -> None:
        decision = _decision("implement the dark mode toggle and open a pr", requested_owner="claude-code")

        self.assertEqual(decision.next_action, NAMED_EXECUTOR_NEXT_ACTION)
        self.assertEqual(decision.selected_owner, "claude-code")
        self.assertFalse(decision.choice_required)


class CodingRouteActionGuardTests(unittest.TestCase):
    """Negative guards: the explicit user-choice path must survive every unsafe case."""

    def test_unset_recorded_owner_is_not_a_preference(self) -> None:
        for recorded_owner in ("", "choose", "  ", "CHOOSE"):
            with self.subTest(recorded_owner=recorded_owner):
                decision = _decision("implement the dark mode toggle and open a pr", recorded_owner=recorded_owner)
                self.assertEqual(decision.next_action, USER_CHOICE_NEXT_ACTION)
                self.assertTrue(decision.choice_required)

    def test_two_named_executors_stay_a_user_choice(self) -> None:
        decision = _decision("use codex or claude code to fix the login bug")

        self.assertEqual(decision.next_action, USER_CHOICE_NEXT_ACTION)
        self.assertTrue(decision.choice_required)
        self.assertEqual(decision.selected_owner, "")

    def test_two_route_families_stay_a_user_choice(self) -> None:
        decision = _decision("give me the prompt and also run parallel workers in a worktree")

        self.assertEqual(decision.next_action, USER_CHOICE_NEXT_ACTION)
        self.assertEqual(decision.selected_route_family, "")

    def test_merge_and_production_authority_outranks_a_named_executor(self) -> None:
        for message in (
            "use codex to implement this and merge to main",
            "codex로 고치고 프로덕션에 배포해줘",
            "have claude code fix this and force push the branch",
        ):
            with self.subTest(message=message):
                decision = _decision(message)
                self.assertEqual(decision.next_action, USER_CHOICE_NEXT_ACTION)
                self.assertTrue(decision.choice_required)

    def test_authority_cue_outranks_a_recorded_preference(self) -> None:
        decision = _decision("implement this and merge to main", recorded_owner="codex")

        self.assertEqual(decision.next_action, USER_CHOICE_NEXT_ACTION)
        self.assertTrue(decision.choice_required)

    def test_authority_cue_outranks_a_caller_fixed_executor_target(self) -> None:
        decision = _decision("implement this and merge to main", requested_owner="codex")

        self.assertEqual(decision.next_action, USER_CHOICE_NEXT_ACTION)
        self.assertTrue(decision.choice_required)


class CodingRouteHintTests(unittest.TestCase):
    def test_every_coding_delivery_site_reports_the_same_lane_and_decision_shape(self) -> None:
        for site, message in CODING_DELIVERY_SITE_MESSAGES:
            with self.subTest(site=site, message=message):
                hint = awareness_route_hint(message)
                decision = hint["primary_coding_route_decision"]

                self.assertEqual(hint["primary_workflow"], "ultraprocess")
                self.assertEqual(hint["primary_next_action"], CODING_ROUTE_LANE_NEXT_ACTION)
                self.assertEqual(hint["hints"][0]["coding_route_decision"], decision)
                self.assertEqual(decision["schema_version"], "coding_route_decision/v1")
                self.assertIn(decision["next_action"], CODING_ROUTE_NEXT_ACTIONS)
                self.assertEqual(decision["lane_next_action"], CODING_ROUTE_LANE_NEXT_ACTION)
                self.assertEqual(decision["user_choice_next_action"], USER_CHOICE_NEXT_ACTION)
                self.assertIn("not executor dispatch", decision["claim_boundary"])

    def test_named_executor_request_reports_the_named_executor_state(self) -> None:
        hint = awareness_route_hint("claude code로 이 이슈 해결해줘")
        decision = hint["primary_coding_route_decision"]

        self.assertEqual(hint["primary_next_action"], CODING_ROUTE_LANE_NEXT_ACTION)
        self.assertEqual(decision["next_action"], NAMED_EXECUTOR_NEXT_ACTION)
        self.assertEqual(decision["selected_owner"], "claude-code")
        self.assertFalse(decision["choice_required"])

    def test_unresolved_request_keeps_the_explicit_user_choice_path(self) -> None:
        hint = awareness_route_hint("테스트 통과할때까지 고쳐줘")
        decision = hint["primary_coding_route_decision"]

        self.assertEqual(decision["next_action"], USER_CHOICE_NEXT_ACTION)
        self.assertTrue(decision["choice_required"])
        self.assertEqual(hint["hints"][0]["fallback_action"], "choose_coding_agent_or_runtime")

    def test_route_hints_stay_prepared_and_never_claim_execution(self) -> None:
        for _site, message in CODING_DELIVERY_SITE_MESSAGES:
            with self.subTest(message=message):
                hint = awareness_route_hint(message)

                self.assertTrue(hint["hints"][0]["not_evidence_yet"])
                self.assertIn("not workflow execution", hint["claim_boundary"])

    def test_non_delivery_requests_never_auto_select_a_coding_owner(self) -> None:
        for guard, message in NON_CODING_DELIVERY_MESSAGES:
            with self.subTest(guard=guard, message=message):
                for item in awareness_route_hint(message)["hints"]:
                    decision = item.get("coding_route_decision")
                    if decision is None:
                        continue
                    self.assertEqual(decision["next_action"], USER_CHOICE_NEXT_ACTION)
                    self.assertTrue(decision["choice_required"])
                    self.assertEqual(decision["selected_owner"], "")
                    self.assertEqual(decision["selected_route_family"], "")

    def test_customer_signal_requests_never_reach_a_coding_owner_decision(self) -> None:
        for message in CUSTOMER_SIGNAL_MESSAGES:
            with self.subTest(message=message):
                hint = awareness_route_hint(message)

                self.assertEqual(hint["primary_workflow"], "feedback-triage")
                self.assertIsNone(hint["primary_coding_route_decision"])
                for item in hint["hints"]:
                    self.assertNotIn("coding_route_decision", item)

    def test_coding_status_requests_are_not_coding_delivery_decisions(self) -> None:
        hint = awareness_route_hint("codex 세션 지금 실행 중이야?")

        self.assertEqual(hint["primary_next_action"], "show_coding_handoff_status")
        self.assertIsNone(hint["primary_coding_route_decision"])


class CodingRouteDecisionWrapperTests(unittest.TestCase):
    def test_recorded_setup_preference_is_its_own_wrapper_state(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = resolve_paths(Path(tmp) / ".omh", Path(tmp) / ".hermes")
            write_setup_profile(paths, default_executor="codex")

            payload = build_chat_interaction_payload(
                "implement a focused parser fix in src/omh/parser.py and update tests",
                source="discord",
                mode="delegate",
                paths=paths,
            )

        decision = payload["coding_route_decision"]
        self.assertEqual(decision["next_action"], RECORDED_OWNER_NEXT_ACTION)
        self.assertEqual(decision["source"], "recorded_setup_preference")
        self.assertEqual(decision["selected_owner"], "codex")
        self.assertFalse(decision["choice_required"])
        self.assertEqual(payload["delegation"]["coding_route_decision"], decision)
        # The decision explains ownership; it never upgrades the handoff into dispatch.
        self.assertIn(payload["delegation"]["dispatch_policy"], {"prepare_only", "ask_before_dispatch"})

    def test_wrapper_without_a_recorded_owner_keeps_the_user_choice_state(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = resolve_paths(Path(tmp) / ".omh", Path(tmp) / ".hermes")

            payload = build_chat_interaction_payload(
                "implement a focused parser fix in src/omh/parser.py and update tests",
                source="discord",
                mode="delegate",
                paths=paths,
            )

        decision = payload["coding_route_decision"]
        self.assertEqual(decision["next_action"], USER_CHOICE_NEXT_ACTION)
        self.assertTrue(decision["choice_required"])


if __name__ == "__main__":  # pragma: no cover - unittest entry point
    unittest.main()
