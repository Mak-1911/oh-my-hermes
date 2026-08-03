"""Fenced code must survive the trip to a messenger.

Before this contract existed, a fenced block collapsed into a single
`paragraph` with its newlines flattened to spaces, on BOTH render profiles.
Any adapter that consumes `body_blocks` therefore lost column alignment --
which is the whole point of putting a status table in a fence.
"""

from __future__ import annotations

import unittest

from omh.wrapper.contract import messenger_rendering_contract

_ALIGNED = "\n".join(
    (
        "unit              runtime      model          status",
        "research-sweep    claude-code  opus xhigh     running",
        "api-ratelimit     codex        gpt-5.6-sol    running",
    )
)
_BODY = f"Running work\n\n```text\n{_ALIGNED}\n```\n\nBoundary: metadata only"

PROFILES = ("limited_markdown", "rich_markdown")


def _contract(body: str, profile: str) -> dict:
    return messenger_rendering_contract(
        visible_prefix="[omh] board",
        first_line="Running work",
        body=body,
        claim_boundary="metadata only",
        render_profile=profile,
    )


def _blocks_of_type(contract: dict, block_type: str) -> list[dict]:
    return [block for block in contract["body_blocks"] if block["type"] == block_type]


class FencedCodeSurvivesTests(unittest.TestCase):
    def test_a_fence_becomes_one_code_block_on_every_profile(self) -> None:
        for profile in PROFILES:
            with self.subTest(profile=profile):
                code_blocks = _blocks_of_type(_contract(_BODY, profile), "code_block")
                self.assertEqual(len(code_blocks), 1)

    def test_newlines_and_alignment_are_preserved_verbatim(self) -> None:
        for profile in PROFILES:
            with self.subTest(profile=profile):
                block = _blocks_of_type(_contract(_BODY, profile), "code_block")[0]
                self.assertEqual(block["text"], _ALIGNED)
                self.assertIn("\n", block["text"])

    def test_the_fence_language_is_carried(self) -> None:
        for profile in PROFILES:
            with self.subTest(profile=profile):
                block = _blocks_of_type(_contract(_BODY, profile), "code_block")[0]
                self.assertEqual(block["language"], "text")

    def test_a_fence_without_a_language_reports_an_empty_one(self) -> None:
        body = "Heading\n\n```\nalpha  beta\n```"
        for profile in PROFILES:
            with self.subTest(profile=profile):
                block = _blocks_of_type(_contract(body, profile), "code_block")[0]
                self.assertEqual(block["language"], "")
                self.assertEqual(block["text"], "alpha  beta")

    def test_leading_whitespace_inside_a_fence_is_kept(self) -> None:
        body = "Tree\n\n```\nroot\n    child\n        leaf\n```"
        for profile in PROFILES:
            with self.subTest(profile=profile):
                block = _blocks_of_type(_contract(body, profile), "code_block")[0]
                self.assertEqual(block["text"], "root\n    child\n        leaf")

    def test_a_blank_line_inside_a_fence_does_not_split_the_block(self) -> None:
        body = "Log\n\n```\nfirst\n\nsecond\n```"
        for profile in PROFILES:
            with self.subTest(profile=profile):
                blocks = _blocks_of_type(_contract(body, profile), "code_block")
                self.assertEqual(len(blocks), 1)
                self.assertEqual(blocks[0]["text"], "first\n\nsecond")

    def test_an_unterminated_fence_still_keeps_its_shape(self) -> None:
        # Falling back to prose would reflow exactly the content the fence was
        # protecting, which is the failure this whole contract exists to stop.
        body = "Truncated\n\n```\nalpha  beta\ngamma  delta"
        for profile in PROFILES:
            with self.subTest(profile=profile):
                blocks = _blocks_of_type(_contract(body, profile), "code_block")
                self.assertEqual(len(blocks), 1)
                self.assertEqual(blocks[0]["text"], "alpha  beta\ngamma  delta")

    def test_prose_around_a_fence_still_becomes_ordinary_blocks(self) -> None:
        for profile in PROFILES:
            with self.subTest(profile=profile):
                types = [block["type"] for block in _contract(_BODY, profile)["body_blocks"]]
                self.assertEqual(types, ["paragraph", "code_block", "paragraph"])

    def test_bullets_and_numbers_are_unaffected_by_the_fence_handling(self) -> None:
        body = "Intro\n\n- first\n- second\n\n1. one\n2. two"
        for profile in PROFILES:
            with self.subTest(profile=profile):
                contract = _contract(body, profile)
                self.assertEqual(len(_blocks_of_type(contract, "bullet")), 2)
                self.assertEqual(len(_blocks_of_type(contract, "numbered")), 2)
                self.assertEqual(_blocks_of_type(contract, "code_block"), [])

    def test_a_body_with_no_fence_emits_no_code_block(self) -> None:
        for profile in PROFILES:
            with self.subTest(profile=profile):
                self.assertEqual(_blocks_of_type(_contract("Just prose here.", profile), "code_block"), [])

    def test_only_code_blocks_carry_a_language_key(self) -> None:
        for profile in PROFILES:
            with self.subTest(profile=profile):
                for block in _contract(_BODY, profile)["body_blocks"]:
                    if block["type"] != "code_block":
                        self.assertNotIn("language", block)


class CodeBlockIsPreferredEverywhereTests(unittest.TestCase):
    def test_both_profiles_prefer_code_blocks(self) -> None:
        # Discord, Slack, and Telegram all render triple-backtick fences, so the
        # limited profile has no reason to avoid them the way it avoids tables.
        for profile in PROFILES:
            with self.subTest(profile=profile):
                contract = _contract(_BODY, profile)
                self.assertIn("code_block", contract["preferred_blocks"])
                self.assertNotIn("code_block", contract["avoid_blocks"])

    def test_the_limited_profile_still_avoids_tables(self) -> None:
        contract = _contract(_BODY, "limited_markdown")
        self.assertIn("markdown_table", contract["avoid_blocks"])
        self.assertNotIn("markdown_table", contract["preferred_blocks"])

    def test_the_fallback_blocks_keep_the_fence_too(self) -> None:
        # `fallback_body_blocks` is what an adapter uses when it cannot render
        # the primary format; it must not be the one that loses alignment.
        for profile in PROFILES:
            with self.subTest(profile=profile):
                fallback = _contract(_BODY, profile)["fallback_body_blocks"]
                code_blocks = [block for block in fallback if block["type"] == "code_block"]
                self.assertEqual(len(code_blocks), 1)
                self.assertEqual(code_blocks[0]["text"], _ALIGNED)


if __name__ == "__main__":
    unittest.main()
