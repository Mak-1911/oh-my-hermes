from __future__ import annotations

import re
import unittest
from pathlib import Path

from omh.skills.render import workflow_reference_markdown, workflow_reference_payload


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_WORKFLOW_INPUTS = {
    "curriculum-design": "learners",
    "finance-analysis": "period",
    "legal-compliance-review": "jurisdiction",
    "localization-review": "locale",
    "people-ops": "role or people-process outcome",
    "product-brief": "product evidence",
    "sales-development": "account or segment",
    "support-operations": "support case",
}


def _markdown_section(document: str, heading: str) -> str:
    lines = document.splitlines()
    start = lines.index(heading) + 1
    level = len(heading) - len(heading.lstrip("#"))
    end = len(lines)
    in_fence = False
    for index in range(start, len(lines)):
        candidate = lines[index]
        if candidate.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not re.fullmatch(r"#{1,6} .+", candidate):
            continue
        candidate_level = len(candidate) - len(candidate.lstrip("#"))
        if candidate_level <= level:
            end = index
            break
    return "\n".join(lines[start:end])


class DomainContextDocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        cls.memory = (ROOT / "docs" / "MEMORY.md").read_text(encoding="utf-8")
        cls.workflows = (ROOT / "docs" / "WORKFLOWS.md").read_text(encoding="utf-8")
        cls.readme_features = _markdown_section(cls.readme, "## Built For Real Work")
        cls.readme_documentation = _markdown_section(cls.readme, "## Documentation")
        cls.memory_domain_intelligence = _markdown_section(
            cls.memory,
            "## Reviewed Domain Intelligence",
        )

    def test_readme_keeps_chat_feature_and_documentation_anchors(self) -> None:
        chat_features = re.findall(r"(?m)^\*\*💬 .+?\*\*", self.readme_features)
        documentation_targets = set(
            re.findall(r"\[[^]]+\]\((docs/[^)]+)\)", self.readme_documentation)
        )

        self.assertEqual(len(chat_features), 1)
        self.assertIn("## Evidence Before Claims", self.readme)
        self.assertGreaterEqual(
            documentation_targets,
            {"docs/DIRECTION.md", "docs/WORKFLOWS.md"},
        )

    def test_memory_keeps_domain_lifecycle_and_authority_contracts(self) -> None:
        for contract_anchor in (
            "domain_intelligence_candidate/v1",
            "domain_intelligence_profile/v1",
            "domain_intelligence_review_record/v1",
            "domain_routing_context/v1",
            "deep_interview_contract/v1",
            "routing_prior_not_override",
        ):
            with self.subTest(contract_anchor=contract_anchor):
                self.assertIn(contract_anchor, self.memory_domain_intelligence)

        for command in (
            "omh memory domain-capture",
            "omh memory domain-review",
            "omh memory domain-approve",
            "omh memory domain-retire",
        ):
            with self.subTest(command=command):
                self.assertIn(command, self.memory_domain_intelligence)

    def test_workflow_reference_is_generated_from_catalog_contracts(self) -> None:
        self.assertEqual(self.workflows, workflow_reference_markdown())

        payload = workflow_reference_payload()
        self.assertEqual(payload["schema_version"], "workflow_catalog/v1")
        skills = {skill["name"]: skill for skill in payload["skills"]}
        for name, required_input in DOMAIN_WORKFLOW_INPUTS.items():
            with self.subTest(workflow=name):
                skill = skills[name]
                self.assertIn(required_input, skill["required_inputs"])
                self.assertEqual(len(skill["expert_questions"]), 1)
                question = skill["expert_questions"][0]
                self.assertEqual(question["required_input"], required_input)
                self.assertEqual(set(question["questions"]), {"en", "ko"})
                self.assertTrue(all(question["questions"].values()))


if __name__ == "__main__":
    unittest.main()
