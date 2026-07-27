"""Global language policy for routing.

OMH targets a global audience with English as the primary language, but its
deterministic trigger tables only ever grew in Latin and Hangul. These tests
make that state explicit and hold it still: they re-derive the distribution
from the catalog so it cannot drift silently, and they freeze the Hangul table
so adding another per-language table becomes a deliberate act with a visible
number to change rather than an incremental habit.

The policy being enforced: per-language trigger tables do not scale to a global
product, so non-English intent resolution belongs to model selection over
supplied candidates, not to more tokens. See `src/routing/input_language.py`.
"""

from __future__ import annotations

import collections
import unittest

from omh.routing.input_language import (
    SCRIPT_HAN,
    SCRIPT_HANGUL,
    SCRIPT_KANA,
    SCRIPT_LATIN,
    SUPPORT_MODEL_SELECTION_REQUIRED,
    SUPPORT_TRIGGER_BACKED,
    TRIGGER_BACKED_SCRIPTS,
    detect_input_script,
    routing_input_language,
    routing_language_support,
)
from omh.skills.catalog import routable_definitions


# Frozen on 2026-07-27. Raising the Hangul figure means another language-specific
# trigger table grew; that is the habit this gate exists to stop. Change the
# number only with a stated reason, and never as a way to make a routing bug go
# away -- the fix for a non-English miss is model selection, not more tokens.
FROZEN_HANGUL_TRIGGER_COUNT = 766


def _trigger_script_counts() -> collections.Counter[str]:
    counts: collections.Counter[str] = collections.Counter()
    for definition in routable_definitions():
        for trigger in definition.triggers:
            counts[detect_input_script(trigger)] += 1
    return counts


class RoutingLanguagePolicyTests(unittest.TestCase):
    def test_the_hangul_trigger_table_stays_frozen(self) -> None:
        counts = _trigger_script_counts()

        self.assertEqual(counts[SCRIPT_HANGUL], FROZEN_HANGUL_TRIGGER_COUNT)

    def test_only_latin_and_hangul_carry_a_real_trigger_table(self) -> None:
        counts = _trigger_script_counts()

        # Han and Kana entries exist but are incidental (single-digit), which is
        # exactly why they are not claimed as trigger-backed: a handful of tokens
        # cannot resolve ordinary Japanese or Chinese requests.
        self.assertGreater(counts[SCRIPT_LATIN], 1000)
        self.assertGreater(counts[SCRIPT_HANGUL], 100)
        self.assertLess(counts[SCRIPT_HAN], 20)
        self.assertLess(counts[SCRIPT_KANA], 20)
        self.assertEqual(set(TRIGGER_BACKED_SCRIPTS), {SCRIPT_LATIN, SCRIPT_HANGUL})

    def test_every_routable_skill_is_reachable_in_english(self) -> None:
        missing = [
            definition.name
            for definition in routable_definitions()
            if not any(detect_input_script(trigger) == SCRIPT_LATIN for trigger in definition.triggers)
        ]

        self.assertEqual(missing, [])

    def test_a_latin_sentence_is_latin(self) -> None:
        self.assertEqual(detect_input_script("why is the build failing on main?"), SCRIPT_LATIN)

    def test_a_product_name_does_not_make_a_korean_request_latin(self) -> None:
        # Product names, commands, and identifiers stay Latin inside otherwise
        # non-Latin sentences, so a Latin majority must not win the vote.
        self.assertEqual(detect_input_script("Claude Code로 바로 열어줘"), SCRIPT_HANGUL)

    def test_scripts_without_a_trigger_table_are_marked_model_selection(self) -> None:
        for message, expected_script in (
            ("ビルドが失敗した理由を教えて", SCRIPT_KANA),
            ("为什么构建失败了", SCRIPT_HAN),
        ):
            with self.subTest(message=message):
                script = detect_input_script(message)
                self.assertEqual(script, expected_script)
                self.assertEqual(routing_language_support(script), SUPPORT_MODEL_SELECTION_REQUIRED)

    def test_trigger_backed_scripts_report_trigger_support(self) -> None:
        for message in ("refactor this module", "빌드 실패 원인 봐줘"):
            with self.subTest(message=message):
                self.assertEqual(routing_language_support(detect_input_script(message)), SUPPORT_TRIGGER_BACKED)

    def test_routing_input_language_states_the_boundary(self) -> None:
        payload = routing_input_language("ビルドが失敗した理由を教えて")

        self.assertEqual(payload["schema_version"], "routing_input_language/v1")
        self.assertEqual(payload["script"], SCRIPT_KANA)
        self.assertEqual(payload["trigger_support"], SUPPORT_MODEL_SELECTION_REQUIRED)
        self.assertIn("not evidence of intent", str(payload["boundary"]))


if __name__ == "__main__":
    unittest.main()
