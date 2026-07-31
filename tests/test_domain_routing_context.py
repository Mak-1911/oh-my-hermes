from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


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
        public_preimage = {
            key: value for key, value in context.items() if key != "digest"
        }
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
        public_preimage = {
            key: value for key, value in context.items() if key != "digest"
        }
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

    def test_string_caps_accept_limits_and_reject_overflow_without_truncation(
        self,
    ) -> None:
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
        self.assertTrue(
            matches("pipeline reviewer; pipeline review.", "pipeline review")
        )
        self.assertFalse(matches("pipeline review", ""))
        self.assertFalse(matches("", "pipeline review"))
        self.assertFalse(matches(None, "pipeline review"))


def _resolver():
    return _contract_module().resolve_domain_routing_context


def _repository(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / ".git").mkdir()
    return root


def _approve_profile(
    root: Path,
    *,
    domain_id: str,
    phrase: str = "pipeline review",
    canonical: str = "pipeline_review",
    workflow_hints: list[str] | None = None,
    scope_kind: str = "project",
    scope_ref: str | None = None,
) -> dict[str, object]:
    from omh.paths import project_identity, resolve_paths
    from omh.workflows.domain_intelligence import (
        approve_domain_candidate,
        capture_domain_candidate,
    )

    paths = resolve_paths(root / ".omh", root / ".hermes")
    candidate = capture_domain_candidate(
        paths,
        scope_kind=scope_kind,
        scope_ref=scope_ref or project_identity(root),
        domain_id=domain_id,
        mappings=[(phrase, canonical)],
        workflow_hints=(
            ["sales-development"] if workflow_hints is None else workflow_hints
        ),
    )["candidate"]
    profile = approve_domain_candidate(paths, str(candidate["candidate_id"]))["profile"]
    for dirname in ("profiles", "reviews", "history"):
        (_store(root) / dirname).mkdir(parents=True, exist_ok=True)
    return profile


def _binding(root: Path):
    module = importlib.import_module("omh.workflows.domain_project_context")
    binding = module.bind_cli_project(root)
    if binding is None:
        raise AssertionError("fixture failed to mint a project binding")
    return binding


def _store(root: Path) -> Path:
    return root / ".omh" / "memory" / "domain-intelligence"


class DomainContextResolverTests(unittest.TestCase):
    def test_healthy_approved_exact_project_profile_resolves_once(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _repository(Path(tmp) / "healthy-project")
            _approve_profile(root, domain_id="sales")
            with _binding(root) as binding:
                fragment = _resolver()(
                    binding, "Please do a pipeline review", locale="en"
                )

        self.assertEqual(
            fragment["domain_routing_context"]["question"],
            {
                "locale": "en",
                "text": "Which account or customer segment should this sales work focus on?",
            },
        )
        self.assertEqual(
            fragment["domain_routing_context"]["required_input"],
            "account or segment",
        )

    def test_unrelated_scope_and_no_exact_phrase_do_not_resolve(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _repository(Path(tmp) / "scope-project")
            _approve_profile(
                root,
                domain_id="foreign",
                scope_kind="organization",
                scope_ref="org-acme",
            )
            with _binding(root) as binding:
                self.assertIsNone(_resolver()(binding, "pipeline review", locale="en"))

            _approve_profile(root, domain_id="local", phrase="renewal review")
            with _binding(root) as binding:
                self.assertIsNone(_resolver()(binding, "pipeline review", locale="en"))

    def test_valid_plus_empty_hint_fails_closed(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _repository(Path(tmp) / "empty-coexistence")
            _approve_profile(root, domain_id="valid")
            _approve_profile(root, domain_id="empty", workflow_hints=[])
            with _binding(root) as binding:
                self.assertIsNone(_resolver()(binding, "pipeline review", locale="en"))

    def test_valid_plus_invalid_or_conflicting_hint_fails_closed(self) -> None:
        cases = (
            ("unknown-workflow", "pipeline_review"),
            ("finance-analysis", "pipeline_review"),
            ("sales-development", "different_canonical"),
        )
        for workflow_hint, canonical in cases:
            with (
                self.subTest(workflow_hint=workflow_hint, canonical=canonical),
                TemporaryDirectory() as tmp,
            ):
                root = _repository(Path(tmp) / "conflicting-coexistence")
                _approve_profile(root, domain_id="valid")
                _approve_profile(
                    root,
                    domain_id="other",
                    canonical=canonical,
                    workflow_hints=[workflow_hint],
                )
                with _binding(root) as binding:
                    self.assertIsNone(
                        _resolver()(binding, "pipeline review", locale="en")
                    )

    def test_missing_question_spec_fails_closed(self) -> None:
        from dataclasses import replace
        from omh.skills import catalog

        with TemporaryDirectory() as tmp:
            root = _repository(Path(tmp) / "missing-spec")
            _approve_profile(root, domain_id="sales")
            definitions = [
                replace(item, expert_questions=())
                if item.name == "sales-development"
                else item
                for item in catalog.routable_definitions()
            ]
            with patch.object(
                catalog, "routable_definitions", return_value=definitions
            ):
                with _binding(root) as binding:
                    self.assertIsNone(
                        _resolver()(binding, "pipeline review", locale="en")
                    )

    def test_exactly_64_matches_resolve_and_65_fail_closed(self) -> None:
        for count, expected in ((64, True), (65, False)):
            with self.subTest(count=count), TemporaryDirectory() as tmp:
                root = _repository(Path(tmp) / f"matches-{count}")
                for index in range(count):
                    _approve_profile(root, domain_id=f"sales-{index:02d}")
                with _binding(root) as binding:
                    result = _resolver()(binding, "pipeline review", locale="en")
                self.assertEqual(result is not None, expected)

    def test_each_health_directory_overflow_fails_closed_independently(self) -> None:
        for dirname in ("profiles", "reviews", "history"):
            with self.subTest(dirname=dirname), TemporaryDirectory() as tmp:
                root = _repository(Path(tmp) / f"overflow-{dirname}")
                _approve_profile(root, domain_id="sales")
                directory = _store(root) / dirname
                for index in range(1025 - len(list(directory.glob("*.json")))):
                    (directory / f"overflow-{index:04d}.json").write_text(
                        "{}", encoding="utf-8"
                    )
                with _binding(root) as binding:
                    self.assertIsNone(
                        _resolver()(binding, "pipeline review", locale="en")
                    )

    def test_unrelated_malformed_artifact_early_or_late_fails_closed(self) -> None:
        for dirname in ("profiles", "reviews", "history"):
            for filename in ("000-malformed.json", "zzz-malformed.json"):
                with (
                    self.subTest(dirname=dirname, filename=filename),
                    TemporaryDirectory() as tmp,
                ):
                    root = _repository(Path(tmp) / f"malformed-{dirname}")
                    _approve_profile(root, domain_id="sales")
                    (_store(root) / dirname / filename).write_bytes(b"\xff")
                    with _binding(root) as binding:
                        self.assertIsNone(
                            _resolver()(binding, "pipeline review", locale="en")
                        )

    def test_bad_digest_and_invalid_lineage_fail_closed(self) -> None:
        for mutation in ("digest", "lineage"):
            with self.subTest(mutation=mutation), TemporaryDirectory() as tmp:
                root = _repository(Path(tmp) / f"invalid-{mutation}")
                _approve_profile(root, domain_id="sales")
                profile_path = next((_store(root) / "profiles").glob("*.json"))
                profile = json.loads(profile_path.read_text(encoding="utf-8"))
                if mutation == "digest":
                    profile["payload_digest"] = "0" * 64
                else:
                    profile["base_profile_revision"] = 7
                profile_path.write_text(json.dumps(profile), encoding="utf-8")
                with _binding(root) as binding:
                    self.assertIsNone(
                        _resolver()(binding, "pipeline review", locale="en")
                    )

    def test_malformed_candidates_and_operations_are_irrelevant(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _repository(Path(tmp) / "irrelevant-artifacts")
            _approve_profile(root, domain_id="sales")
            for dirname in ("candidates", "operations"):
                directory = _store(root) / dirname
                directory.mkdir(exist_ok=True)
                (directory / "malformed.json").write_bytes(b"\xff")
            with _binding(root) as binding:
                self.assertIsNotNone(
                    _resolver()(binding, "pipeline review", locale="en")
                )

    def test_bound_descriptor_survives_store_path_swap(self) -> None:
        with TemporaryDirectory() as tmp:
            root = _repository(Path(tmp) / "descriptor-bound")
            _approve_profile(root, domain_id="sales")
            binding = _binding(root)
            self.addCleanup(binding.close)
            (root / ".omh").rename(root / ".omh-opened")
            replacement = _store(root)
            for dirname in ("profiles", "reviews", "history"):
                (replacement / dirname).mkdir(parents=True, exist_ok=True)
            (replacement / ".store.lock").write_text("", encoding="utf-8")

            self.assertIsNotNone(_resolver()(binding, "pipeline review", locale="en"))

    def test_noncooperating_snapshot_mutations_fail_closed_without_retry(self) -> None:
        query = importlib.import_module("omh.workflows.domain_intelligence_queries")
        for dirname in ("profiles", "reviews", "history"):
            for operation in ("create", "replace", "delete", "content"):
                with (
                    self.subTest(dirname=dirname, operation=operation),
                    TemporaryDirectory() as tmp,
                ):
                    root = _repository(Path(tmp) / f"mutation-{dirname}-{operation}")
                    _approve_profile(root, domain_id="sales")
                    directory = _store(root) / dirname
                    original = next(directory.glob("*.json"), None)
                    real_read = query._read_stable_json_at
                    mutated = False

                    def mutate_after_first_read(*args, **kwargs):
                        nonlocal mutated
                        value = real_read(*args, **kwargs)
                        if not mutated:
                            mutated = True
                            if operation == "create":
                                (directory / "zzz-created.json").write_text(
                                    "{}", encoding="utf-8"
                                )
                            elif operation == "replace" and original is not None:
                                replacement = directory / "replacement.tmp"
                                replacement.write_bytes(original.read_bytes())
                                os.replace(replacement, original)
                            elif operation == "delete" and original is not None:
                                original.unlink()
                            elif operation == "content" and original is not None:
                                original.write_bytes(original.read_bytes() + b" ")
                        return value

                    with patch.object(
                        query,
                        "_read_stable_json_at",
                        side_effect=mutate_after_first_read,
                    ) as reader:
                        with _binding(root) as binding:
                            self.assertIsNone(
                                _resolver()(binding, "pipeline review", locale="en")
                            )
                    self.assertTrue(mutated)
                    self.assertEqual(reader.call_count, 1)


if __name__ == "__main__":
    unittest.main()
