"""P2 exact channel-envelope fixture contracts."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from _local_package import load_local_package

load_local_package()

from _platform_golden import (
    FIXED_ACTIONS, FIXED_ATTACHMENTS, FIXED_BODY, FIXTURE_CLAIM_BOUNDARY,
    FIXTURE_SCHEMA_VERSION, GOLDEN_PLATFORMS, build_platform_fixture,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "examples" / "wrapper-golden" / "platform-envelopes"


class PlatformEnvelopeGoldenTests(unittest.TestCase):
    def _load(self, platform_id: str) -> dict:
        return json.loads((FIXTURE_DIR / f"{platform_id}.json").read_text(encoding="utf-8"))

    def test_exactly_seven_fixtures_exist_and_match_generation(self) -> None:
        paths = sorted(FIXTURE_DIR.glob("*.json"))
        self.assertEqual([path.stem for path in paths], sorted(GOLDEN_PLATFORMS))
        for platform_id in GOLDEN_PLATFORMS:
            with self.subTest(platform_id=platform_id):
                self.assertEqual(self._load(platform_id), build_platform_fixture(platform_id))

    def test_schema_fixed_inputs_default_limits_and_no_delivery(self) -> None:
        for platform_id in GOLDEN_PLATFORMS:
            fixture = self._load(platform_id)
            envelope = fixture["platform_envelope"]
            rendering = fixture["messenger_rendering"]
            with self.subTest(platform_id=platform_id):
                self.assertEqual(fixture["schema_version"], FIXTURE_SCHEMA_VERSION)
                self.assertEqual(fixture["source"], "generic")
                self.assertEqual(fixture["body"], FIXED_BODY)
                self.assertEqual(fixture["actions"], FIXED_ACTIONS)
                self.assertEqual(fixture["attachments"], FIXED_ATTACHMENTS)
                self.assertEqual(envelope["limits"], {"max_recommended_chars": 1600, "hard_limit_chars": 1800})
                self.assertEqual(envelope["limit_provenance"], "conservative_default")
                self.assertEqual(rendering["adapter_payload"]["delivery"]["state"], "prepared_not_delivered")
                self.assertFalse(rendering["adapter_payload"]["delivery"]["observed"])
                self.assertEqual(fixture["claim_boundary"], FIXTURE_CLAIM_BOUNDARY)

    def test_declared_capabilities_keep_adapter_provenance_and_gate(self) -> None:
        for platform_id in GOLDEN_PLATFORMS:
            fixture = self._load(platform_id)
            declared = fixture["platform_context"]["capabilities"]
            envelope = fixture["platform_envelope"]
            rendering = fixture["messenger_rendering"]
            with self.subTest(platform_id=platform_id):
                for group, capabilities in declared.items():
                    for name, value in capabilities.items():
                        self.assertEqual(envelope["capabilities"][group][name], value)
                        self.assertEqual(envelope["capability_provenance"][group][name], "adapter_declared")
                self.assertEqual(rendering["omh_message_gate"]["schema_version"], "omh_message_gate/v1")
                self.assertEqual(rendering["adapter_payload"]["platform_id"], platform_id)
                self.assertEqual(rendering["adapter_payload"]["claim_boundary"], "Rendering and capabilities are not execution or delivery evidence.")

    def test_refs_are_safe_opaque_and_fixtures_make_no_network_claim(self) -> None:
        phone = re.compile(r"(?:\+?\d[\d ().-]{7,}\d)")
        for platform_id in GOLDEN_PLATFORMS:
            fixture = self._load(platform_id)
            serialized = json.dumps(fixture, sort_keys=True)
            context = fixture["platform_context"]
            with self.subTest(platform_id=platform_id):
                self.assertTrue(context["conversation_ref"].startswith(f"conv:{platform_id}:"))
                self.assertTrue(context["thread_ref"].startswith(f"thread:{platform_id}:"))
                self.assertNotIn("@", serialized)
                self.assertIsNone(phone.search(serialized))
                self.assertNotIn("http://", serialized)
                self.assertNotIn("https://", serialized)
                self.assertIn("not network, posting, delivery", fixture["claim_boundary"])


if __name__ == "__main__":
    unittest.main()
