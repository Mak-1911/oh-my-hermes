from __future__ import annotations

import hashlib
import importlib
import json
import unittest


CLAIM_BOUNDARY = (
    "Reviewed domain context only selects one wrapper clarification question; it is not "
    "routing, plan approval, execution, review, CI, merge, authentication, or Hermes "
    "internal-memory evidence."
)


def _contract_module():
    return importlib.import_module("omh.workflows.domain_routing_context")


def _sales_target(*, locale: str = "ko", question: str | None = None):
    contract = _contract_module()
    return contract.DomainClarificationTarget(
        workflow_hint="sales-development",
        required_input="account or segment",
        question_locale=locale,
        question_text=(
            question
            if question is not None
            else "이 영업 작업은 어떤 계정 또는 고객 세그먼트에 집중해야 하나요?"
        ),
    )


class DomainRoutingContextContractTests(unittest.TestCase):
    def test_exact_public_schema(self) -> None:
        contract = _contract_module()
        fragment = contract.build_domain_routing_context((_sales_target(),))

        self.assertEqual(set(fragment), {"domain_routing_context"})
        context = fragment["domain_routing_context"]
        self.assertEqual(
            set(context),
            {
                "schema_version",
                "workflow_hint",
                "required_input",
                "question",
                "digest",
                "claim_boundary",
            },
        )
        self.assertEqual(context["schema_version"], "domain_routing_context/v1")
        self.assertEqual(context["workflow_hint"], "sales-development")
        self.assertEqual(context["required_input"], "account or segment")
        self.assertEqual(
            context["question"],
            {
                "locale": "ko",
                "text": "이 영업 작업은 어떤 계정 또는 고객 세그먼트에 집중해야 하나요?",
            },
        )
        self.assertEqual(context["claim_boundary"], CLAIM_BOUNDARY)
        self.assertRegex(context["digest"], r"^[a-f0-9]{64}$")

    def test_korean_digest_golden_vector_uses_canonical_utf8(self) -> None:
        contract = _contract_module()
        context = contract.build_domain_routing_context((_sales_target(),))[
            "domain_routing_context"
        ]
        public_preimage = {key: value for key, value in context.items() if key != "digest"}
        serialized = json.dumps(
            public_preimage,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

        self.assertEqual(
            serialized,
            '{"claim_boundary":"Reviewed domain context only selects one wrapper clarification question; it is not routing, plan approval, execution, review, CI, merge, authentication, or Hermes internal-memory evidence.","question":{"locale":"ko","text":"이 영업 작업은 어떤 계정 또는 고객 세그먼트에 집중해야 하나요?"},"required_input":"account or segment","schema_version":"domain_routing_context/v1","workflow_hint":"sales-development"}',
        )
        self.assertIn("이 영업 작업", serialized)
        expected_digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        self.assertEqual(
            expected_digest,
            "fb0ee06c3b440d0f3f9242b96f96494833f1da3332d3fffe299a58138f986b43",
        )
        self.assertEqual(context["digest"], expected_digest)

    def test_digest_excludes_profile_material(self) -> None:
        contract = _contract_module()
        context = contract.build_domain_routing_context((_sales_target(),))[
            "domain_routing_context"
        ]
        public_preimage = {key: value for key, value in context.items() if key != "digest"}
        serialized = json.dumps(
            public_preimage,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        forbidden_keys = (
            "profile_id",
            "revision",
            "payload_digest",
            "mapping_digest",
            "mapping_ref",
            "mapping_index",
            "phrase",
            "canonical",
            "scope_ref",
            "scope_hash",
            "store",
            "root",
            "lineage",
        )
        forbidden_values = (
            "dprof_deadbeefdeadbeefdeadbeef",
            "private-project-ref",
            "sensitive reviewed phrase",
            "/private/repository/.omh",
        )

        for sentinel in (*forbidden_keys, *forbidden_values):
            with self.subTest(sentinel=sentinel):
                self.assertNotIn(sentinel, serialized)
                self.assertNotIn(sentinel, json.dumps(context, ensure_ascii=False))
        self.assertIn('"digest"', json.dumps(context))
        self.assertIn("evidence", context["claim_boundary"])

    def test_complete_absence_for_zero_multiple_or_invalid_targets(self) -> None:
        contract = _contract_module()
        valid = _sales_target()
        invalid_targets = (
            (),
            (valid, valid),
            (
                contract.DomainClarificationTarget(
                    workflow_hint="",
                    required_input="account or segment",
                    question_locale="ko",
                    question_text="질문?",
                ),
            ),
            (
                contract.DomainClarificationTarget(
                    workflow_hint="sales-development",
                    required_input="account or segment",
                    question_locale="ja",
                    question_text="質問?",
                ),
            ),
        )

        for targets in invalid_targets:
            with self.subTest(targets=targets):
                self.assertIsNone(contract.build_domain_routing_context(targets))

    def test_string_caps_accept_limits_and_reject_overflow_without_truncation(self) -> None:
        contract = _contract_module()
        at_limit = contract.DomainClarificationTarget(
            workflow_hint="w" * 120,
            required_input="r" * 120,
            question_locale="en",
            question_text="q" * 240,
        )
        self.assertIsNotNone(contract.build_domain_routing_context((at_limit,)))

        fields_and_values = (
            ("workflow_hint", "w" * 121),
            ("required_input", "r" * 121),
            ("question_text", "q" * 241),
        )
        for field, value in fields_and_values:
            kwargs = {
                "workflow_hint": "sales-development",
                "required_input": "account or segment",
                "question_locale": "en",
                "question_text": "Which account?",
            }
            kwargs[field] = value
            with self.subTest(field=field):
                target = contract.DomainClarificationTarget(**kwargs)
                self.assertIsNone(contract.build_domain_routing_context((target,)))


class DomainPhraseMatcherTests(unittest.TestCase):
    def test_required_unicode_boundary_vectors(self) -> None:
        matches = _contract_module().matches_reviewed_phrase
        vectors = (
            ("ＰＩＰＥＬＩＮＥ REVIEW", "pipeline review", True),
            ("(고객 세그먼트) 검토", "고객 세그먼트", True),
            ("pipeline reviewer", "pipeline review", False),
            ("고객 세그먼트화", "고객 세그먼트", False),
            ("pipeline-review", "pipeline review", False),
            ("sales-development", "pipeline review", False),
        )
        for message, phrase, expected in vectors:
            with self.subTest(message=message, phrase=phrase):
                self.assertEqual(matches(message, phrase), expected)

    def test_normalization_collapses_unicode_whitespace_and_casefolds(self) -> None:
        matches = _contract_module().matches_reviewed_phrase
        self.assertTrue(matches("  STRASSE\n\t review  ", "Straße review"))
        self.assertTrue(matches("pipeline\u3000review", "pipeline review"))

    def test_word_like_categories_and_underscore_enforce_boundaries(self) -> None:
        matches = _contract_module().matches_reviewed_phrase
        for message in ("xpipeline", "1pipeline", "_pipeline", "\u0301pipeline"):
            with self.subTest(message=message):
                self.assertFalse(matches(message, "pipeline"))
        for message in ("pipelinex", "pipeline1", "pipeline_", "pipeline\u0301"):
            with self.subTest(message=message):
                self.assertFalse(matches(message, "pipeline"))
        self.assertTrue(matches("(pipeline).", "pipeline"))

    def test_punctuation_edge_phrase_needs_only_literal_equality(self) -> None:
        matches = _contract_module().matches_reviewed_phrase
        self.assertTrue(matches("x(renewal)!", "(renewal)"))
        self.assertFalse(matches("x renewal !", "renewal!"))

    def test_all_occurrences_are_searched_and_empty_inputs_do_not_match(self) -> None:
        matches = _contract_module().matches_reviewed_phrase
        self.assertTrue(matches("pipeline reviewer; pipeline review.", "pipeline review"))
        self.assertFalse(matches("pipeline review", ""))
        self.assertFalse(matches("", "pipeline review"))
        self.assertFalse(matches(None, "pipeline review"))


if __name__ == "__main__":
    unittest.main()
