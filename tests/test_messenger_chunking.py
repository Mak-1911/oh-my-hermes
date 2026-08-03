"""Messenger rendering needs REAL per-platform character ceilings.

Before this contract, `_messenger_chunking_hint()` took no arguments and
returned one global advisory number (`max_recommended_chars: 1800`) for
every platform. Discord, Slack, and Telegram each enforce a different hard
per-message character cap, so a single global number either under-warns on
generous platforms or over-warns on tight ones, and an adapter never had an
enforceable stop -- only advice.

This also covers `density_policy`, a *declared* (not enforced) markdown
saturation policy added alongside the existing `prefix_policy`/`table_policy`
advisories. There was previously no markdown-density or saturation control
on the chat rendering path at all: `context_budget` protects the supervising
agent's context window, not a human reader's chat bubble.
"""

from __future__ import annotations

import unittest

from omh.wrapper.contract import messenger_rendering_contract
from omh.wrapper.route_hints import build_chat_route_hint_payload

# Mirrors the ceilings declared in `omh.wrapper.contract`. Kept here as
# expected values, not re-derived, so the test actually pins the numbers
# rather than re-implementing the lookup.
_CEILINGS = {
    "discord": {"max_recommended_chars": 1700, "hard_limit_chars": 1900},
    "slack": {"max_recommended_chars": 2700, "hard_limit_chars": 2900},
    "telegram": {"max_recommended_chars": 3700, "hard_limit_chars": 3900},
}
_GENERIC_CEILING = {"max_recommended_chars": 1600, "hard_limit_chars": 1800}


def _contract(**overrides: object) -> dict:
    kwargs: dict[str, object] = dict(
        visible_prefix="[omh] board",
        first_line="Status update",
        body="body text",
        claim_boundary="metadata only",
    )
    kwargs.update(overrides)
    return messenger_rendering_contract(**kwargs)


class PerPlatformChunkingCeilingTests(unittest.TestCase):
    def test_each_known_platform_gets_its_own_ceiling(self) -> None:
        for source, expected in _CEILINGS.items():
            with self.subTest(source=source):
                chunking = _contract(source=source)["chunking"]
                self.assertEqual(chunking["max_recommended_chars"], expected["max_recommended_chars"])
                self.assertEqual(chunking["hard_limit_chars"], expected["hard_limit_chars"])

    def test_hermes_and_generic_share_the_generic_ceiling(self) -> None:
        for source in ("hermes", "generic"):
            with self.subTest(source=source):
                chunking = _contract(source=source)["chunking"]
                self.assertEqual(chunking["max_recommended_chars"], _GENERIC_CEILING["max_recommended_chars"])
                self.assertEqual(chunking["hard_limit_chars"], _GENERIC_CEILING["hard_limit_chars"])

    def test_absent_source_falls_back_to_the_generic_ceiling(self) -> None:
        # `source` is optional so no existing caller breaks; the default must
        # resolve to the same generic ceiling as an explicitly unknown one.
        chunking = _contract()["chunking"]
        self.assertEqual(chunking["max_recommended_chars"], _GENERIC_CEILING["max_recommended_chars"])
        self.assertEqual(chunking["hard_limit_chars"], _GENERIC_CEILING["hard_limit_chars"])

    def test_unknown_source_falls_back_to_the_generic_ceiling(self) -> None:
        for source in ("whatsapp", "signal", ""):
            with self.subTest(source=source):
                chunking = _contract(source=source)["chunking"]
                self.assertEqual(chunking["max_recommended_chars"], _GENERIC_CEILING["max_recommended_chars"])
                self.assertEqual(chunking["hard_limit_chars"], _GENERIC_CEILING["hard_limit_chars"])

    def test_recommended_is_always_strictly_below_the_hard_limit(self) -> None:
        for source in ("discord", "slack", "telegram", "hermes", "generic", "unknown", ""):
            with self.subTest(source=source):
                chunking = _contract(source=source)["chunking"]
                self.assertLess(chunking["max_recommended_chars"], chunking["hard_limit_chars"])

    def test_fresh_dict_per_call_is_preserved(self) -> None:
        # A caller embedding the chunking hint in a payload must not be able
        # to mutate it for every other caller.
        first = _contract(source="discord")["chunking"]
        first["hard_limit_chars"] = -1
        second = _contract(source="discord")["chunking"]
        self.assertEqual(second["hard_limit_chars"], 1900)


class DensityPolicyTests(unittest.TestCase):
    def test_density_policy_is_present_on_both_render_profiles(self) -> None:
        for profile in ("limited_markdown", "rich_markdown"):
            with self.subTest(profile=profile):
                density_policy = _contract(render_profile=profile)["density_policy"]
                self.assertEqual(density_policy["max_heading_levels"], 2)
                self.assertEqual(density_policy["max_bullets"], 12)
                self.assertIn("nested_bullets", density_policy["avoid"])
                self.assertIn("bold_inside_bullets", density_policy["avoid"])
                self.assertIn("tables_on_limited_profiles", density_policy["avoid"])


class RouteHintChunkingSurvivesTheKeyWhitelistTests(unittest.TestCase):
    """`build_chat_route_hint_payload` builds its `messenger_rendering` block
    as a hand-rolled literal, not via `messenger_rendering_contract`. A key
    added upstream to `_messenger_chunking_hint` is only visible in the
    emitted hint if the literal actually forwards `source` into that call --
    checking the source text is not enough, only the emitted payload proves
    the key survives.
    """

    def test_hard_limit_chars_reaches_the_emitted_route_hint_for_every_source(self) -> None:
        for source, expected in _CEILINGS.items():
            with self.subTest(source=source):
                payload = build_chat_route_hint_payload("please review my pull request diff", source=source)
                chunking = payload["chat_response"]["messenger_rendering"]["chunking"]
                self.assertIn("hard_limit_chars", chunking)
                self.assertEqual(chunking["max_recommended_chars"], expected["max_recommended_chars"])
                self.assertEqual(chunking["hard_limit_chars"], expected["hard_limit_chars"])

    def test_generic_source_falls_back_in_the_route_hint_too(self) -> None:
        payload = build_chat_route_hint_payload("please review my pull request diff", source="generic")
        chunking = payload["chat_response"]["messenger_rendering"]["chunking"]
        self.assertEqual(chunking["max_recommended_chars"], _GENERIC_CEILING["max_recommended_chars"])
        self.assertEqual(chunking["hard_limit_chars"], _GENERIC_CEILING["hard_limit_chars"])


if __name__ == "__main__":
    unittest.main()
