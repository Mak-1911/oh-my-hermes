from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DomainContextDocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        cls.memory = (ROOT / "docs" / "MEMORY.md").read_text(encoding="utf-8")
        cls.workflows = (ROOT / "docs" / "WORKFLOWS.md").read_text(encoding="utf-8")
        cls.readme_prose = " ".join(cls.readme.split())
        cls.memory_prose = " ".join(cls.memory.split())

    def test_memory_replaces_stale_no_consumer_claim_with_exact_boundary(self) -> None:
        self.assertNotIn("No routing consumer exists for these profiles.", self.memory_prose)
        self.assertIn(
            "Only an eligible, genuinely unresolved wrapper interaction may consume an "
            "active reviewed profile from the current repository's own project-local store, "
            "and only to select one catalog-owned clarification question.",
            self.memory_prose,
        )
        self.assertIn(
            "The route, candidate handoff, and plan artifact's "
            "`deep_interview_contract/v1` remain unchanged.",
            self.memory_prose,
        )
        self.assertIn(
            "This is clarification context, not routing authority, plan approval, execution, "
            "review, CI, merge, authentication, or Hermes internal-memory evidence.",
            self.memory_prose,
        )

    def test_public_docs_explain_natural_chat_and_current_project_binding(self) -> None:
        self.assertIn(
            "In natural-language Hermes chat, reviewed terminology from the current repository "
            "can improve one ambiguous wrapper question.",
            self.readme_prose,
        )
        self.assertIn(
            "OMH derives the current project internally; users do not provide a domain scope, "
            "and the context is not persisted.",
            self.readme_prose,
        )
        self.assertIn(
            "The memory commands below are an agent, wrapper, and operator control-plane "
            "reference, not steps for normal chat users.",
            self.memory_prose,
        )

    def test_memory_documents_freshness_fail_closed_and_scope_limits(self) -> None:
        required = (
            "User and organization profiles are not consumed until an authenticated principal binding exists.",
            "Replacement or retirement takes effect on the next eligible interaction.",
            "Any unhealthy, incomplete, malformed, or conflicting profile store fails closed to the existing generic question.",
            "Direct answers, file lookup, help, maintenance, task cards, explicit workflows, static specialist routes, operator actions, workflow learning, status, and every dispatch remain protected.",
            "Profiles do not automatically learn from chat, select a route, rerank candidates, or trigger dispatch.",
        )
        for statement in required:
            with self.subTest(statement=statement):
                self.assertIn(statement, self.memory_prose)

    def test_docs_name_remaining_goal_without_overclaiming_generated_content(self) -> None:
        for milestone in (
            "reviewed activation before any routing influence",
            "multi-round research and planning cognition",
            "passive missed-route review",
            "domain-pack expansion",
            "optional offline evaluation",
        ):
            with self.subTest(milestone=milestone):
                self.assertIn(milestone, self.memory_prose)

        self.assertIn("- Expert clarification questions:", self.workflows)
        self.assertIn(
            "- `account or segment`\n"
            "    - English: Which account or customer segment should this sales work focus on?\n"
            "    - Korean: 이 영업 작업은 어떤 계정 또는 고객 세그먼트에 집중해야 하나요?",
            self.workflows,
        )


if __name__ == "__main__":
    unittest.main()
