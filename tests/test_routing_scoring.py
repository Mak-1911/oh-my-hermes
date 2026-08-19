"""Scorer-level contracts for trigger matching.

These live apart from `tests/test_routing_precision.py` because the corpus there
also asserts that the raw message never appears in the machine payload, which a
one-word message always violates. The bare-word cases below are exactly the ones
that exposed the defect, so they need a home where a single common word is a
legal input.
"""

from __future__ import annotations

import unittest

from omh.routing.recommend import _phrase_match, _trigger_phrase_match, recommend_skills


class TriggerPhraseDirectionTests(unittest.TestCase):
    def test_trigger_fires_only_when_the_message_contains_the_phrase(self) -> None:
        self.assertTrue(_trigger_phrase_match("please run npm test now", "npm test"))
        self.assertTrue(_trigger_phrase_match("test", "test"))
        # The reverse arm is what inflated ambiguous single words.
        self.assertFalse(_trigger_phrase_match("test", "npm test"))
        self.assertFalse(_trigger_phrase_match("design", "design system contract"))

    def test_general_phrase_match_keeps_both_directions(self) -> None:
        # `_phrase_match` still backs description and use_when scoring, where a
        # short query legitimately appears inside a long prose field. Narrowing
        # it globally would delete that signal for every skill.
        self.assertTrue(_phrase_match("test", "npm test"))
        self.assertTrue(_phrase_match("please run npm test now", "npm test"))

    def test_one_ambiguous_word_does_not_inherit_multi_word_trigger_scores(self) -> None:
        # Before the fix: command-operator at 73, high confidence, from
        # trigger:`npm test`, `cargo test`, `pytest`, `python -m unittest`.
        top = recommend_skills("test", limit=1)[0]
        self.assertNotEqual(top["skill"], "command-operator")
        self.assertLess(top["score"], 30)

        for word, stolen_by in (("design", "design-quality-gate"), ("review", "security-safety-review")):
            with self.subTest(word=word):
                first = recommend_skills(word, limit=1)[0]
                self.assertNotEqual(first["skill"], stolen_by)
                self.assertLess(first["score"], 30)

    def test_a_message_that_contains_the_command_phrase_still_reaches_it(self) -> None:
        top = recommend_skills("npm test", limit=1)[0]
        self.assertEqual(top["skill"], "command-operator")
        self.assertIn("trigger:npm test", top["matched"])


class GreenfieldBuildGuardTests(unittest.TestCase):
    GREENFIELD = (
        "build a todo list",
        "build a react app",
        "build a dashboard",
        "build a chrome extension",
        "let's build a react todo list",
        "웹사이트 하나 만들어줘",
    )

    def test_greenfield_requests_reach_the_interview_lane_whatever_the_noun(self) -> None:
        for message in self.GREENFIELD:
            with self.subTest(message=message):
                self.assertEqual(recommend_skills(message, limit=1)[0]["skill"], "deep-interview")

    def test_the_guard_is_a_floor_not_an_override(self) -> None:
        # Each of these opens with a creation phrase but was already claimed by
        # a lane that matched real vocabulary; the greenfield guard must lose.
        for message, owner in (
            ("make me a landing page", "frontend"),
            ("build a login component", "ultrawork"),
            ("create a research brief for the auth migration", "research-brief"),
            ("웹 검색 싸게 만들어줘", "websearch-setup"),
        ):
            with self.subTest(message=message):
                self.assertEqual(recommend_skills(message, limit=1)[0]["skill"], owner)

    def test_asking_how_something_is_created_is_not_a_build_request(self) -> None:
        top = recommend_skills("how do I create a virtualenv in Python?", limit=1)[0]
        self.assertNotEqual(top["skill"], "deep-interview")


if __name__ == "__main__":
    unittest.main()
