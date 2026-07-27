"""Undecidable routes hand their shortlist to model selection.

The deterministic router keeps every confident route. These tests pin the other
half: a tie, a near-tie, a low-confidence score, or a script the trigger tables
do not cover must produce candidates for the model to choose from instead of a
picker or a bare fallback.
"""

from __future__ import annotations

import unittest

from omh.routing.candidate_handoff import (
    CANDIDATE_HANDOFF_SCHEMA_VERSION,
    MAX_CANDIDATES,
    REASON_LOW_CONFIDENCE,
    REASON_NARROW_SCORE_GAP,
    REASON_NO_TRIGGER_COVERAGE,
    build_candidate_handoff,
    candidate_handoff_digest,
)
from omh.routing.chat import route_chat_message


class CandidateHandoffTests(unittest.TestCase):
    def test_a_confident_route_carries_no_handoff(self) -> None:
        route = route_chat_message("why is the build failing on main?", source="generic", limit=3)

        self.assertEqual(route["action"], "dispatch")
        self.assertIsNone(route.get("candidate_handoff"))

    def test_a_scoring_tie_hands_the_shortlist_over(self) -> None:
        # Two skills scored 9 apiece here, so the picker was standing in for a
        # decision the scorer could not make.
        route = route_chat_message("PR 리뷰 좀 해줘", source="generic", limit=3)
        handoff = route["candidate_handoff"]

        self.assertEqual(route["action"], "clarify")
        self.assertEqual(handoff["schema_version"], CANDIDATE_HANDOFF_SCHEMA_VERSION)
        self.assertIn(REASON_NARROW_SCORE_GAP, handoff["reasons"])
        self.assertIn("code-review", [candidate["skill"] for candidate in handoff["candidates"]])
        self.assertEqual(handoff["selector"], "hermes")

    def test_a_script_without_trigger_coverage_hands_over(self) -> None:
        route = route_chat_message("ビルドが失敗した理由を教えて", source="generic", limit=3)
        handoff = route["candidate_handoff"]

        self.assertIn(REASON_NO_TRIGGER_COVERAGE, handoff["reasons"])
        self.assertIn(REASON_LOW_CONFIDENCE, handoff["reasons"])

    def test_every_candidate_carries_its_reason_and_evidence_boundary(self) -> None:
        route = route_chat_message("PR 리뷰 좀 해줘", source="generic", limit=3)

        for candidate in route["candidate_handoff"]["candidates"]:
            with self.subTest(skill=candidate["skill"]):
                self.assertTrue(candidate["skill"])
                self.assertTrue(candidate["why_it_matched"])
                self.assertTrue(candidate["next_action"])
                self.assertTrue(candidate["evidence_boundary"])

    def test_the_candidate_set_is_bounded(self) -> None:
        route = route_chat_message("PR 리뷰 좀 해줘", source="generic", limit=8)

        self.assertLessEqual(route["candidate_handoff"]["candidate_count"], MAX_CANDIDATES)

    def test_the_handoff_is_reproducible(self) -> None:
        first = route_chat_message("PR 리뷰 좀 해줘", source="generic", limit=3)["candidate_handoff"]
        second = route_chat_message("PR 리뷰 좀 해줘", source="generic", limit=3)["candidate_handoff"]

        self.assertEqual(first["digest"], second["digest"])

    def test_the_digest_tracks_the_shortlist_not_the_scores(self) -> None:
        reasons = (REASON_NARROW_SCORE_GAP,)
        low = candidate_handoff_digest([{"skill": "code-review", "score": 9}], reasons)
        high = candidate_handoff_digest([{"skill": "code-review", "score": 41}], reasons)
        other = candidate_handoff_digest([{"skill": "verification-gate", "score": 9}], reasons)

        self.assertEqual(low, high)
        self.assertNotEqual(low, other)

    def test_an_empty_shortlist_points_at_the_catalog_index(self) -> None:
        route = {
            "action": "fallback",
            "confidence": "low",
            "recommendations": [],
            "input_language": {"trigger_support": "model_selection_required"},
        }
        handoff = build_candidate_handoff(route)

        self.assertEqual(handoff["candidate_count"], 0)
        self.assertEqual(handoff["catalog_reference"], "references/catalog-index.md")
        self.assertIn("catalog-index", str(handoff["question"]))

    def test_the_handoff_never_claims_a_decision(self) -> None:
        route = route_chat_message("PR 리뷰 좀 해줘", source="generic", limit=3)

        self.assertIn("not a routing decision", route["candidate_handoff"]["claim_boundary"])


if __name__ == "__main__":
    unittest.main()
