"""Gate for the `executor_capability/v1` dispatch-profile metadata table.

The table is DESCRIPTIVE. It records what is known — and, far more often,
what is NOT known — about a spawnable dispatch profile's edit formats,
persistent eval, tool re-entry, and code-mode batching. Three rules carry the
design and are enforced here:

* Every cell is a tri-state string. A boolean would collapse "we looked and it
  is absent" into "we never looked", which is the one distinction the table
  exists to keep.
* Every unresearched cell is `unknown`. A guess dressed as data would be read
  downstream as an observation.
* Nothing ranks. The briefing renders the block verbatim, and no routing,
  scoring, or preference code may read these fields.
"""

from __future__ import annotations

import datetime
import subprocess
import unittest
from pathlib import Path

from _local_package import load_local_package

load_local_package()

from omh.coding.executor_capabilities import (  # noqa: E402
    CAPABILITY_STATES,
    EDIT_FORMAT_KEYS,
    EXECUTOR_CAPABILITY_SCHEMA_VERSION,
    KNOWN_CAPABILITY_PROFILES,
    capability_for_profile,
)
from omh.coding.fanout_dispatch import DISPATCH_COMMAND_TEMPLATES  # noqa: E402
from omh.wrapper.briefing import build_coding_briefing  # noqa: E402


_TRI_STATE_FIELDS = ("persistent_eval", "tool_reentry", "code_mode_batching")


class ExecutorCapabilityTableTests(unittest.TestCase):
    def test_profile_keys_are_exactly_the_spawnable_dispatch_templates(self) -> None:
        self.assertEqual(set(KNOWN_CAPABILITY_PROFILES), set(DISPATCH_COMMAND_TEMPLATES))
        # pi/senpi/opencode are runtime-detected hosts of `omo-runtime`, never
        # separate dispatch profiles.
        for host in ("pi", "senpi", "opencode"):
            self.assertNotIn(host, KNOWN_CAPABILITY_PROFILES)

    def test_capability_shape_is_complete_for_every_profile(self) -> None:
        for profile in KNOWN_CAPABILITY_PROFILES:
            with self.subTest(profile=profile):
                capability = capability_for_profile(profile)

                self.assertEqual(capability["schema_version"], EXECUTOR_CAPABILITY_SCHEMA_VERSION)
                self.assertEqual(capability["profile"], profile)
                self.assertEqual(set(capability["edit_format_support"]), set(EDIT_FORMAT_KEYS))
                for field in _TRI_STATE_FIELDS:
                    self.assertIn(field, capability)
                provenance = capability["provenance"]
                self.assertEqual(set(provenance), {"source", "observed_at", "executor_version"})
                self.assertIsInstance(provenance["source"], str)

    def test_every_cell_is_a_tri_state_string_and_never_a_boolean(self) -> None:
        for profile in KNOWN_CAPABILITY_PROFILES:
            capability = capability_for_profile(profile)
            cells = {
                f"edit_format_support.{name}": value
                for name, value in capability["edit_format_support"].items()
            }
            cells.update({field: capability[field] for field in _TRI_STATE_FIELDS})
            for name, value in cells.items():
                with self.subTest(profile=profile, cell=name):
                    self.assertNotIsInstance(value, bool)
                    self.assertIsInstance(value, str)
                    self.assertIn(value, CAPABILITY_STATES)

    def test_unresearched_cells_default_to_unknown_with_null_provenance(self) -> None:
        for profile in KNOWN_CAPABILITY_PROFILES:
            with self.subTest(profile=profile):
                capability = capability_for_profile(profile)
                provenance = capability["provenance"]

                if not provenance["source"]:
                    self.assertEqual(
                        set(capability["edit_format_support"].values()) | {capability[field] for field in _TRI_STATE_FIELDS},
                        {"unknown"},
                    )
                    self.assertIsNone(provenance["observed_at"])
                    self.assertIsNone(provenance["executor_version"])

    def test_keys_are_executor_neutral(self) -> None:
        vendor_terms = ("codex", "claude", "openai", "anthropic", "senpi", "opencode", "gpt", "sonnet")
        for profile in KNOWN_CAPABILITY_PROFILES:
            capability = capability_for_profile(profile)
            for key in _capability_keys(capability):
                with self.subTest(profile=profile, key=key):
                    self.assertFalse(
                        any(term in key.casefold() for term in vendor_terms),
                        f"capability key {key!r} names a vendor",
                    )

    def test_host_variants_only_exist_under_omo_runtime_and_reuse_the_cell_vocabulary(self) -> None:
        for profile in KNOWN_CAPABILITY_PROFILES:
            variants = capability_for_profile(profile).get("host_variants", {})
            if profile != "omo-runtime":
                self.assertEqual(variants, {}, f"{profile} must not declare host variants")
                continue
            for host, overrides in variants.items():
                with self.subTest(host=host):
                    self.assertIn(host, ("pi", "senpi", "opencode"))
                    for value in _capability_values(overrides):
                        self.assertNotIsInstance(value, bool)
                        self.assertIn(value, CAPABILITY_STATES)

    def test_unknown_profile_raises_value_error_naming_the_profile(self) -> None:
        with self.assertRaises(ValueError) as caught:
            capability_for_profile("nonexistent")

        self.assertIn("nonexistent", str(caught.exception))

    def test_returned_capability_is_a_copy_callers_cannot_mutate(self) -> None:
        first = capability_for_profile("codex")
        first["edit_format_support"]["patch"] = "supported"
        first["persistent_eval"] = "supported"

        second = capability_for_profile("codex")

        self.assertEqual(second["edit_format_support"]["patch"], "unknown")
        self.assertEqual(second["persistent_eval"], "unknown")

    def test_provenance_observed_at_is_none_or_valid_iso_date(self) -> None:
        for profile in KNOWN_CAPABILITY_PROFILES:
            with self.subTest(profile=profile):
                capability = capability_for_profile(profile)
                provenance = capability["provenance"]
                observed_at = provenance["observed_at"]

                # observed_at must be None or a valid ISO date/datetime string
                if observed_at is not None:
                    self._assert_valid_iso_date_or_datetime(observed_at)

                # Check host_variants if they exist
                host_variants = capability.get("host_variants", {})
                for host, overrides in host_variants.items():
                    with self.subTest(profile=profile, host=host):
                        if "provenance" in overrides:
                            host_observed_at = overrides["provenance"].get("observed_at")
                            if host_observed_at is not None:
                                self._assert_valid_iso_date_or_datetime(host_observed_at)

    def _assert_valid_iso_date_or_datetime(self, value: str) -> None:
        """Assert that value is a valid ISO date or datetime string."""
        self.assertIsInstance(value, str, f"observed_at must be a string, got {type(value)}")
        try:
            # Try parsing as date first (YYYY-MM-DD)
            datetime.date.fromisoformat(value)
            return
        except (ValueError, TypeError):
            pass
        try:
            # Try parsing as full datetime (ISO 8601 format)
            datetime.datetime.fromisoformat(value)
            return
        except (ValueError, TypeError):
            self.fail(f"observed_at {value!r} is not a valid ISO date or datetime")


class ExecutorCapabilityBriefingRenderTests(unittest.TestCase):
    def _briefing(self, profile: str) -> dict:
        session = {
            "session_id": "sess-1",
            "status": "prompt_handoff_prepared",
            "selected_executor_profile": profile,
            "prompt_handoff": {
                "schema_version": "coding_handoff/v1",
                "selected_executor_profile": profile,
            },
        }
        return build_coding_briefing(session)

    def test_briefing_carries_the_capability_block_verbatim(self) -> None:
        briefing = self._briefing("codex")

        block = briefing["work_summary"]["handoff_contract"]["executor_capability"]

        self.assertEqual(block, capability_for_profile("codex"))

    def test_briefing_block_is_absent_for_a_profile_without_a_capability_row(self) -> None:
        briefing = self._briefing("hermes")

        self.assertNotIn("executor_capability", briefing["work_summary"]["handoff_contract"])

    def test_briefing_never_ranks_scores_or_recommends_from_capabilities(self) -> None:
        briefing = self._briefing("omo-runtime")

        block = briefing["work_summary"]["handoff_contract"]["executor_capability"]
        self.assertNotIn("rank", _capability_keys(block))
        self.assertNotIn("score", _capability_keys(block))
        self.assertNotIn("recommended", _capability_keys(block))
        rendered = " ".join(briefing["user_facing_lines"]).casefold()
        for ranking_word in ("better", "best", "faster", "prefer", "recommend", "stronger"):
            self.assertNotIn(ranking_word, rendered)


class ExecutorCapabilityRoutingIsolationTests(unittest.TestCase):
    def test_no_routing_module_reads_capability_fields(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        probe = subprocess.run(
            ["rg", "-n", "edit_format_support|code_mode_batching|capability_for_profile", "src/routing/"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )

        self.assertEqual(probe.stdout, "", "routing must not read descriptive capability metadata")


def _capability_keys(value: object, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        keys: list[str] = []
        for key, item in value.items():
            keys.append(str(key))
            keys.extend(_capability_keys(item, str(key)))
        return keys
    return []


def _capability_values(value: object) -> list[object]:
    if isinstance(value, dict):
        values: list[object] = []
        for item in value.values():
            values.extend(_capability_values(item))
        return values
    return [value]


if __name__ == "__main__":
    unittest.main()
