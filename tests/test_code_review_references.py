"""The code-review reference files carry clauses that prevent a wrong answer.

These are not style assertions. Each locked string below is the one sentence in
its section that stops a specific failure: a review that covered a fraction of
the change, a fix that was attempted rather than made, or a partial
implementation of a finding set that was not understood. A rewrite that drops
one of them should fail here rather than ship quietly.
"""

from __future__ import annotations

import unittest

from omh.skills.packaging import builtin_skill_reference_templates
from omh.skills.render import code_review_reference_templates


class CodeReviewReferenceTests(unittest.TestCase):
    def _content(self, relative_path: str) -> str:
        for template in code_review_reference_templates():
            if template.relative_path == relative_path:
                return template.content
        self.fail(f"no code-review reference at {relative_path}")

    def test_both_references_ship_under_the_code_review_skill(self) -> None:
        paths = {template.relative_path for template in code_review_reference_templates()}
        self.assertEqual(paths, {"references/review-dispatch.md", "references/review-response.md"})
        for template in code_review_reference_templates():
            self.assertEqual(template.skill_name, "code-review")

    def test_the_packaged_set_includes_them(self) -> None:
        # packaging.py splices six producers by hand; a seventh is a one-line
        # edit and an omitted one is silent until the byte gate runs.
        packaged = {(t.skill_name, t.relative_path) for t in builtin_skill_reference_templates()}
        self.assertIn(("code-review", "references/review-dispatch.md"), packaged)
        self.assertIn(("code-review", "references/review-response.md"), packaged)

    def test_the_base_sha_rule_states_the_defect_not_just_the_preference(self) -> None:
        content = self._content("references/review-dispatch.md")
        # Handing a reviewer HEAD~1 on a multi-commit task yields a clean
        # verdict on code nobody read - a manufactured pass.
        self.assertIn("Never `HEAD~1`", content)
        self.assertIn("BASE_SHA", content)
        self.assertIn("HEAD_SHA", content)

    def test_the_four_implementer_statuses_are_all_present(self) -> None:
        content = self._content("references/review-dispatch.md")
        for status in ("DONE", "DONE_WITH_CONCERNS", "NEEDS_CONTEXT", "BLOCKED"):
            with self.subTest(status=status):
                self.assertIn(status, content)

    def test_attempted_is_not_addressed_survives(self) -> None:
        self.assertIn('"Attempted" is not "addressed."', self._content("references/review-dispatch.md"))

    def test_the_clarification_gate_is_all_or_nothing(self) -> None:
        content = self._content("references/review-response.md")
        self.assertIn("before implementing any of them", content)

    def test_both_references_end_at_a_boundary(self) -> None:
        for relative_path in ("references/review-dispatch.md", "references/review-response.md"):
            with self.subTest(relative_path=relative_path):
                self.assertIn("## Boundary", self._content(relative_path))


if __name__ == "__main__":
    unittest.main()
