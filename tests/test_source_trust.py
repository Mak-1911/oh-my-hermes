"""Contracts for `source_trust_claim/v1` and `source_trust_summary/v1`.

The axis exists so knowledge OMH never observed can be carried without being
mistaken for something OMH did observe. These group by the guarantee each test
protects:

- The ceiling: a tier may back only the claim kinds the table gives it, and the
  refusal is a rejection rather than a silent downgrade.
- The floor under every tier: no source, however official, backs a completion
  claim -- that belongs to the observation axis alone.
- Attribution: a tier that names a source must have one, and the tier that means
  "nobody in particular" must not.
- The summary: it cannot be raised by malformed input and cannot report a
  completion.

Each positive case ships with the negative case that proves the guard is doing
the work, per the repo's guard-pattern rule.
"""

from __future__ import annotations

import unittest

from _local_package import load_local_package

load_local_package()
from omh.workflows.source_trust import (
    CLAIM_KIND_NONE,
    CLAIM_KINDS,
    SOURCE_TRUST_CLAIM_BOUNDARY,
    SOURCE_TRUST_CLAIM_SCHEMA_VERSION,
    SOURCE_TRUST_CLAIM_KEYS,
    SOURCE_TRUST_SUMMARY_SCHEMA_VERSION,
    SOURCE_TRUST_TIER_FALLBACK,
    SOURCE_TRUST_TIERS,
    TRUST_CLAIM_CEILING,
    SourceTrustError,
    build_source_trust_claim,
    claim_kinds_for_tier,
    completion_is_never_source_backed,
    normalize_source_trust_tier,
    source_trust_claim_errors,
    summarize_source_trust,
    tier_may_claim,
    validate_source_trust_summary,
)


STAMP = "2026-08-11T00:00:00Z"


def _claim(**overrides: object) -> dict[str, object]:
    record = build_source_trust_claim(
        tier="upstream_official",
        claim_kind="finding",
        claim="The runtime rejects a handoff without an owner.",
        recorded_at=STAMP,
        source_ref="upstream-runtime-spec",
    )
    record.update(overrides)
    return record


class CeilingTests(unittest.TestCase):
    def test_practitioner_heuristic_backs_approach(self) -> None:
        record = build_source_trust_claim(
            tier="practitioner_heuristic",
            claim_kind="approach",
            claim="Warm the cache before the first batch or the first run skews the timing.",
            recorded_at=STAMP,
            source_ref="practitioner-note-cache-warm",
        )
        self.assertEqual(record["tier"], "practitioner_heuristic")
        self.assertEqual(record["claim_kind"], "approach")
        self.assertEqual(source_trust_claim_errors(record), [])

    def test_practitioner_heuristic_is_refused_as_a_finding(self) -> None:
        with self.assertRaises(SourceTrustError) as raised:
            build_source_trust_claim(
                tier="practitioner_heuristic",
                claim_kind="finding",
                claim="Warming the cache halves p99.",
                recorded_at=STAMP,
                source_ref="practitioner-note-cache-warm",
            )
        self.assertIn("may not back a finding claim", str(raised.exception))

    def test_refusal_is_not_a_silent_downgrade(self) -> None:
        """A rejected claim must not come back stored one rung lower."""
        with self.assertRaises(SourceTrustError):
            build_source_trust_claim(
                tier="practitioner_heuristic",
                claim_kind="finding",
                claim="Warming the cache halves p99.",
                recorded_at=STAMP,
                source_ref="practitioner-note-cache-warm",
            )

    def test_unattributed_backs_nothing(self) -> None:
        self.assertEqual(claim_kinds_for_tier("unattributed"), ())
        for kind in CLAIM_KINDS:
            with self.subTest(kind=kind):
                with self.assertRaises(SourceTrustError):
                    build_source_trust_claim(
                        tier="unattributed",
                        claim_kind=kind,
                        claim="Somebody said the scheduler retries twice.",
                        recorded_at=STAMP,
                    )

    def test_every_tier_has_an_explicit_ceiling(self) -> None:
        self.assertEqual(sorted(TRUST_CLAIM_CEILING), sorted(SOURCE_TRUST_TIERS))
        for tier, kinds in TRUST_CLAIM_CEILING.items():
            with self.subTest(tier=tier):
                self.assertTrue(set(kinds) <= set(CLAIM_KINDS), tier)


class CompletionFloorTests(unittest.TestCase):
    def test_no_tier_backs_a_completion_claim(self) -> None:
        self.assertTrue(completion_is_never_source_backed())
        for tier in SOURCE_TRUST_TIERS:
            with self.subTest(tier=tier):
                self.assertFalse(tier_may_claim(tier, "completion"))

    def test_upstream_official_is_also_refused_a_completion(self) -> None:
        with self.assertRaises(SourceTrustError) as raised:
            build_source_trust_claim(
                tier="upstream_official",
                claim_kind="completion",
                claim="The migration shipped and the suite is green.",
                recorded_at=STAMP,
                source_ref="upstream-release-notes",
            )
        self.assertIn("may not back a completion claim", str(raised.exception))


class AttributionTests(unittest.TestCase):
    def test_named_tier_requires_a_source(self) -> None:
        with self.assertRaises(SourceTrustError) as raised:
            build_source_trust_claim(
                tier="upstream_official",
                claim_kind="finding",
                claim="The runtime rejects a handoff without an owner.",
                recorded_at=STAMP,
            )
        self.assertIn("must name the source", str(raised.exception))

    def test_unattributed_must_not_name_a_source(self) -> None:
        """Only reachable on read: `build` refuses `unattributed` at the ceiling first.

        The ordering is deliberate -- a tier that backs nothing is refused for
        that reason before anything about its attribution is considered -- so the
        attribution rule is exercised against a hand-forged record.
        """
        errors = source_trust_claim_errors(_claim(tier="unattributed", source_ref="somewhere"))
        self.assertTrue(any("must not name a source" in error for error in errors), errors)

    def test_source_ref_must_not_be_navigable(self) -> None:
        with self.assertRaises(SourceTrustError):
            build_source_trust_claim(
                tier="upstream_official",
                claim_kind="finding",
                claim="The runtime rejects a handoff without an owner.",
                recorded_at=STAMP,
                source_ref="https://example.invalid/spec",
            )


class NormalizeTests(unittest.TestCase):
    def test_known_tiers_survive_normalization(self) -> None:
        for tier in SOURCE_TRUST_TIERS:
            with self.subTest(tier=tier):
                self.assertEqual(normalize_source_trust_tier(tier), tier)

    def test_unknown_tier_falls_closed(self) -> None:
        for value in ("", None, "trusted", "official-ish", "PRACTITIONER HEURISTICS"):
            with self.subTest(value=value):
                self.assertEqual(normalize_source_trust_tier(value), SOURCE_TRUST_TIER_FALLBACK)

    def test_fallback_tier_backs_nothing(self) -> None:
        """Falling closed is only safe because the fallback has no authority."""
        self.assertEqual(claim_kinds_for_tier(SOURCE_TRUST_TIER_FALLBACK), ())


class ClaimValidationTests(unittest.TestCase):
    def test_built_claim_validates(self) -> None:
        self.assertEqual(source_trust_claim_errors(_claim()), [])
        self.assertEqual(sorted(_claim()), sorted(SOURCE_TRUST_CLAIM_KEYS))

    def test_missing_and_unexpected_keys_are_both_reported(self) -> None:
        record = _claim()
        record.pop("recorded_at")
        record["notes"] = "extra"
        errors = source_trust_claim_errors(record)
        self.assertTrue(any("missing keys" in error for error in errors), errors)
        self.assertTrue(any("unsupported keys" in error for error in errors), errors)

    def test_schema_version_is_pinned(self) -> None:
        errors = source_trust_claim_errors(_claim(schema_version="source_trust_claim/v2"))
        self.assertTrue(any(SOURCE_TRUST_CLAIM_SCHEMA_VERSION in error for error in errors), errors)

    def test_hand_forged_ceiling_violation_is_caught_on_read(self) -> None:
        """The guard cannot be bypassed by writing the record by hand."""
        errors = source_trust_claim_errors(
            _claim(tier="practitioner_heuristic", source_ref="practitioner-note")
        )
        self.assertTrue(any("may not back a finding claim" in error for error in errors), errors)

    def test_non_mapping_is_rejected(self) -> None:
        self.assertEqual(source_trust_claim_errors(["not", "a", "record"]), ["source trust claim must be an object"])


class SummaryTests(unittest.TestCase):
    def test_summary_reports_the_strongest_accepted_claim(self) -> None:
        summary = summarize_source_trust(
            topic="handoff owner requirement",
            claims=[
                build_source_trust_claim(
                    tier="practitioner_heuristic",
                    claim_kind="approach",
                    claim="Set the owner before preparing the handoff.",
                    recorded_at=STAMP,
                    source_ref="practitioner-note-owner",
                ),
                _claim(),
            ],
        )
        self.assertEqual(summary["strongest_claim_kind"], "finding")
        self.assertEqual(summary["accepted_count"], 2)
        self.assertEqual(summary["rejected_count"], 0)
        self.assertEqual(summary["tiers_present"], ["upstream_official", "practitioner_heuristic"])
        self.assertEqual(summary["claim_boundary"], SOURCE_TRUST_CLAIM_BOUNDARY)
        self.assertEqual(validate_source_trust_summary(summary), [])

    def test_empty_summary_backs_nothing(self) -> None:
        summary = summarize_source_trust(topic="handoff owner requirement")
        self.assertEqual(summary["strongest_claim_kind"], CLAIM_KIND_NONE)
        self.assertEqual(summary["tiers_present"], [])
        self.assertEqual(validate_source_trust_summary(summary), [])

    def test_malformed_claims_cannot_raise_the_summary(self) -> None:
        summary = summarize_source_trust(
            topic="handoff owner requirement",
            claims=[
                {"tier": "upstream_official", "claim_kind": "finding"},
                _claim(tier="practitioner_heuristic", source_ref="practitioner-note"),
                build_source_trust_claim(
                    tier="practitioner_heuristic",
                    claim_kind="approach",
                    claim="Set the owner before preparing the handoff.",
                    recorded_at=STAMP,
                    source_ref="practitioner-note-owner",
                ),
            ],
        )
        self.assertEqual(summary["accepted_count"], 1)
        self.assertEqual(summary["rejected_count"], 2)
        self.assertEqual(summary["strongest_claim_kind"], "approach")
        self.assertEqual([row["index"] for row in summary["rejected_claims"]], [0, 1])
        self.assertEqual(validate_source_trust_summary(summary), [])

    def test_summary_schema_version_is_pinned(self) -> None:
        summary = summarize_source_trust(topic="handoff owner requirement")
        self.assertEqual(summary["schema_version"], SOURCE_TRUST_SUMMARY_SCHEMA_VERSION)

    def test_a_forged_completion_summary_is_rejected(self) -> None:
        summary = summarize_source_trust(topic="handoff owner requirement")
        summary["strongest_claim_kind"] = "completion"
        errors = validate_source_trust_summary(summary)
        self.assertTrue(any("never be completion" in error for error in errors), errors)

    def test_a_stripped_boundary_is_rejected(self) -> None:
        summary = summarize_source_trust(topic="handoff owner requirement")
        summary["claim_boundary"] = "checked and verified"
        errors = validate_source_trust_summary(summary)
        self.assertTrue(any("frozen boundary sentence" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
