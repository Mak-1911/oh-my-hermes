from __future__ import annotations

import unittest

from _local_package import load_local_package

load_local_package()
from omh.quality.native_skill_competition import (
    NATIVE_COMPETITION_CASES,
    build_native_skill_competition_report,
)


class NativeSkillCompetitionTests(unittest.TestCase):
    def test_cases_cover_native_defaults_and_policy_overlay_exceptions(self) -> None:
        expected = {
            ("browser-operator", "native"),
            ("browser-operator", "omh"),
            ("workspace-file-operator", "native"),
            ("workspace-file-operator", "omh"),
            ("command-operator", "native"),
            ("command-operator", "omh"),
            ("live-info-operator", "native"),
            ("live-info-operator", "omh"),
        }
        self.assertEqual(
            {(case.omh_skill, case.expected_winner) for case in NATIVE_COMPETITION_CASES},
            expected,
        )

    def test_frontmatter_lexical_gate_passes_every_case(self) -> None:
        report = build_native_skill_competition_report()

        self.assertEqual(report["schema_version"], "omh_native_skill_competition/v1")
        self.assertEqual(report["case_count"], 8)
        self.assertEqual(report["passed_count"], 8)
        self.assertEqual(report["failed_count"], 0)
        self.assertEqual(report["failures"], [])
        for result in report["results"]:
            with self.subTest(case=result["case_id"]):
                self.assertEqual(result["actual_winner"], result["expected_winner"])
                self.assertGreater(result["winner_score"], result["loser_score"])
                self.assertEqual(result["picker_surface"], "generated_frontmatter_name_description")


if __name__ == "__main__":
    unittest.main()
