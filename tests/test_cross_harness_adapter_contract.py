from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import unittest

from _cli_harness import run_cli
from src.quality.cross_harness_adapter_evidence import (
    adapter_evidence_payload,
    adapter_request_payload,
    adapter_result_payload,
    artifact_content_digest,
    corpus_fixture_binding_digest,
    parse_adapter_evidence,
    project_adapter_evidence,
)
from src.quality.cross_harness_adapter_model import (
    AdapterContractError,
    canonical_digest,
    parse_adapter_request,
    parse_adapter_result,
)
from src.quality.cross_harness_benchmark import (
    evaluate_submission,
    parse_corpus,
    score_submission,
)
from src.quality.cross_harness_benchmark_values import JsonValue


ROOT = Path(__file__).parents[1]
EXAMPLE = ROOT / "benchmarks" / "cross-harness" / "v1" / "example-passing-submission.json"


class ExistingBenchmarkCharacterizationTests(unittest.TestCase):
    def test_validate_score_and_report_outputs_are_unchanged(self) -> None:
        expected = {
            "validate": "a90a12a955003b74748a25121b40a12fd74e9074732ea424b1c25842daddebd3",
            "score": "5fbcffbe8208b50973670b0fcd563def5ad8ea61ed38c5f4ed49f084d9cb14af",
            "report": "1d2d1c87ab0bcb2ed54df66846149c4df5b56030e1b6ae3bf9cb672bbf01f8cf",
        }
        for command, digest in expected.items():
            with self.subTest(command=command):
                status, stdout, stderr = run_cli(
                    ["benchmark", command, "--input", str(EXAMPLE)]
                )
                self.assertEqual(status, 0, stderr)
                self.assertEqual(hashlib.sha256(stdout.encode()).hexdigest(), digest)

    def test_production_benchmark_modules_remain_subprocess_free(self) -> None:
        modules = tuple((ROOT / "src" / "quality").glob("cross_harness_benchmark*.py"))
        modules += (ROOT / "src" / "commands" / "cross_harness_benchmark.py",)
        forbidden: list[str] = []
        for path in modules:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = (
                        tuple(alias.name for alias in node.names)
                        if isinstance(node, ast.Import)
                        else (node.module or "",)
                    )
                    if any(name.split(".")[0] == "subprocess" for name in names):
                        forbidden.append(path.name)
        self.assertEqual(forbidden, [])


def _request() -> dict[str, JsonValue]:
    return {
        "schema_version": "cross_harness_adapter_request/v1",
        "protocol_version": "cross_harness_adapter_protocol/v1",
        "corpus_digest": "0" * 64,
        "fixture_binding_digest": "0" * 64,
        "fixture_id": "fixture-a",
        "adapter_id": "adapter-a",
        "capability_id": "capability-a",
        "profile": "codex",
        "executable": "codex",
        "executable_version": "1.2.3",
        "model": "gpt-5.6-sol",
        "effort": "high",
        "capabilities": ["tool-events", "child-events"],
        "argv_digest": "1" * 64,
        "repetition": 1,
        "timeout_seconds": 30,
    }


def _result() -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {
        "schema_version": "cross_harness_adapter_result/v1",
        "request_digest": "0" * 64,
        "fixture_id": "fixture-a",
        "adapter_id": "adapter-a",
        "capability_id": "capability-a",
        "evidence_class": "runtime",
        "observation_state": "observed",
        "actual_machine": {"enabled": True},
        "facts": {"count": 1},
        "skill_events": [{"id": "skill-a", "result": "pass"}],
        "tool_events": [{"id": "tool-a", "result": "pass"}],
        "child_results": [{"id": "child-a", "result": "pass"}],
        "artifact_type": "cross_harness_adapter_fixture_result/v1",
        "artifact_hash": "2" * 64,
        "process_status": "exit",
        "exit_code": 0,
        "side_effects": [{"path": "output/result.json", "change": "created"}],
    }
    result["artifact_hash"] = artifact_content_digest(result)
    return result


def _passing_bundle_raw() -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    benchmark = _json_object(_load_json(EXAMPLE))
    corpus_raw = _json_object(benchmark["corpus"])
    corpus = parse_corpus(corpus_raw)
    passing = _json_object(benchmark["submission"])
    cases: list[JsonValue] = []
    for raw_result in _json_array(passing["results"]):
        submission_result = _json_object(raw_result)
        result = _result()
        for field in (
            "fixture_id",
            "adapter_id",
            "capability_id",
            "evidence_class",
            "actual_machine",
            "facts",
            "child_results",
        ):
            result[field] = submission_result[field]
        result["observation_state"] = submission_result["runtime_observation"]
        request = _request()
        request["corpus_digest"] = corpus.digest
        fixture = next(item for item in corpus.fixtures if item.id == result["fixture_id"])
        request["fixture_binding_digest"] = corpus_fixture_binding_digest(fixture)
        request["fixture_id"] = result["fixture_id"]
        request["adapter_id"] = result["adapter_id"]
        request["capability_id"] = result["capability_id"]
        request_digest = canonical_digest(request)
        result["request_digest"] = request_digest
        result["artifact_hash"] = artifact_content_digest(result)
        cases.append(
            {
                "fixture_id": result["fixture_id"],
                "request": request,
                "request_digest": request_digest,
                "result": result,
                "result_digest": canonical_digest(result),
                "source_binding": submission_result["source_binding"],
                "command_evidence": submission_result["command_evidence"],
            }
        )
    bundle: dict[str, JsonValue] = {
        "schema_version": "cross_harness_adapter_evidence/v1",
        "corpus_digest": corpus.digest,
        "harness_id": passing["harness_id"],
        "cases": cases,
    }
    bundle["bundle_digest"] = canonical_digest(bundle)
    return corpus_raw, bundle


class AdapterBoundaryFailingFirstTests(unittest.TestCase):
    def test_canonical_digest_has_a_stable_golden_vector(self) -> None:
        value: JsonValue = {"b": ["x", True], "a": 1}

        self.assertEqual(
            canonical_digest(value),
            "c2a9eac3043628b0883d74191c1b921ab2aeb873c5e82395033831287bac514b",
        )

    def test_canonical_payloads_round_trip_without_shape_drift(self) -> None:
        request = parse_adapter_request(_request())
        result = parse_adapter_result(_result())
        self.assertEqual(parse_adapter_request(adapter_request_payload(request)), request)
        self.assertEqual(parse_adapter_result(adapter_result_payload(result)), result)

        _, bundle_raw = _passing_bundle_raw()
        bundle = parse_adapter_evidence(bundle_raw)
        self.assertEqual(parse_adapter_evidence(adapter_evidence_payload(bundle)), bundle)

    def test_exact_request_and_result_shapes_parse_to_frozen_values(self) -> None:
        request = parse_adapter_request(_request())
        result = parse_adapter_result(_result())

        self.assertEqual((request.profile.value, request.repetition), ("codex", 1))
        self.assertEqual((result.fixture_id, result.exit_code), ("fixture-a", 0))
        with self.assertRaises(FrozenInstanceError):
            setattr(request, "profile", "pi")

    def test_stale_request_and_partial_child_fail_closed(self) -> None:
        stale = _request()
        stale["schema_version"] = "cross_harness_adapter_request/v0"
        with self.assertRaisesRegex(AdapterContractError, "stale_adapter_version"):
            parse_adapter_request(stale)

        result = _result()
        result["child_results"] = [
            {"id": "child-a", "result": "pass"},
            {"id": "child-b", "result": "partial"},
        ]
        result["artifact_hash"] = artifact_content_digest(result)
        with self.assertRaisesRegex(AdapterContractError, "partial_child_failure"):
            parse_adapter_result(result)

    def test_all_profile_effort_observation_and_process_variants_are_typed(self) -> None:
        for profile in ("codex", "claude-code", "pi", "hermes", "omx", "omo", "omc"):
            with self.subTest(profile=profile):
                request = _request()
                request["profile"] = profile
                self.assertEqual(parse_adapter_request(request).profile.value, profile)
        for effort in ("none", "low", "medium", "high", "xhigh", "max", "ultra"):
            with self.subTest(effort=effort):
                request = _request()
                request["effort"] = effort
                self.assertEqual(parse_adapter_request(request).effort.value, effort)
        for observation in ("observed", "prepared_not_observed", "not_applicable"):
            with self.subTest(observation=observation):
                result = _result()
                result["observation_state"] = observation
                if observation != "observed":
                    result["process_status"] = "not_started"
                    result["exit_code"] = None
                result["artifact_hash"] = artifact_content_digest(result)
                self.assertEqual(parse_adapter_result(result).observation_state.value, observation)
        for process in ("timeout", "crash", "not_started"):
            with self.subTest(process=process):
                result = _result()
                result["process_status"] = process
                result["exit_code"] = None
                if process == "not_started":
                    result["observation_state"] = "prepared_not_observed"
                result["artifact_hash"] = artifact_content_digest(result)
                self.assertEqual(parse_adapter_result(result).process_status.value, process)

    def test_bundle_projection_requires_digest_bound_exact_fixture_evidence(self) -> None:
        corpus_raw, bundle_raw = _passing_bundle_raw()
        corpus = parse_corpus(corpus_raw)
        passing = _json_object(_json_object(_load_json(EXAMPLE))["submission"])
        projected = project_adapter_evidence(corpus, parse_adapter_evidence(bundle_raw))

        report = evaluate_submission(projected, corpus)
        score = score_submission(projected, corpus)
        self.assertEqual(projected, passing)
        self.assertEqual(sum(outcome.status == "pass" for outcome in report.outcomes), 15)
        self.assertEqual((score.total, score.level), (100, 5))

    def test_unknown_shapes_types_profiles_and_secrets_are_rejected(self) -> None:
        cases = (
            ("missing_fields", lambda raw: raw.pop("model")),
            ("extra_fields", lambda raw: raw.update({"prompt": "body"})),
            ("wrong_type", lambda raw: raw.update({"timeout_seconds": True})),
            ("unknown_enum_value", lambda raw: raw.update({"profile": "unknown"})),
            ("secret_or_raw_data", lambda raw: raw.update({"model": "sk-attacker"})),
        )
        for reason, mutate in cases:
            with self.subTest(reason=reason):
                request = _request()
                mutate(request)
                with self.assertRaisesRegex(AdapterContractError, reason):
                    parse_adapter_request(request)

    def test_recursive_raw_keys_secret_vectors_and_credential_paths_are_rejected(self) -> None:
        secret_values = (
            "ghp_1234567890abcdefghijklmnopqrstuvwxyz",
            "AKIAIOSFODNN7EXAMPLE",
            "sk-attacker",
            "-----BEGIN EC PRIVATE KEY-----",
            "/home/alice/.aws/credentials",
            "C:\\Users\\alice\\.aws\\credentials",
        )
        for value in secret_values:
            with self.subTest(value=value[:4]):
                request = _request()
                request["model"] = value
                with self.assertRaisesRegex(AdapterContractError, "secret_or_raw_data|unsafe_path"):
                    parse_adapter_request(request)
        for key in ("environment", "env", "path", "raw_path", "executable_path", "prompt", "response", "stdout", "stderr", "skill_body", "access_token", "credential_blob"):
            with self.subTest(key=key):
                result = _result()
                result["facts"] = {key: "redacted"}
                result["artifact_hash"] = artifact_content_digest(result)
                with self.assertRaisesRegex(AdapterContractError, "raw_field_forbidden"):
                    parse_adapter_result(result)

    def test_wrong_artifact_paths_duplicates_and_bounds_are_rejected(self) -> None:
        cases = (
            ("wrong_artifact_type", lambda raw: raw.update({"artifact_type": "text/plain"})),
            ("unsafe_path", lambda raw: raw.update({"side_effects": [{"path": "../secret", "change": "created"}]})),
            ("unsafe_path", lambda raw: raw.update({"side_effects": [{"path": "/tmp/secret", "change": "created"}]})),
            ("duplicate_event", lambda raw: raw.update({"tool_events": [{"id": "same", "result": "pass"}, {"id": "same", "result": "pass"}]})),
            ("collection_too_large", lambda raw: raw.update({"tool_events": [{"id": f"t-{index}", "result": "pass"} for index in range(129)]})),
        )
        for reason, mutate in cases:
            with self.subTest(reason=reason):
                result = _result()
                mutate(result)
                result["artifact_hash"] = artifact_content_digest(result)
                with self.assertRaisesRegex(AdapterContractError, reason):
                    parse_adapter_result(result)

    def test_digest_tamper_missing_duplicate_and_attacker_rehash_fail_closed(self) -> None:
        corpus_raw, bundle = _passing_bundle_raw()
        cases = _json_array(bundle["cases"])
        first = _json_object(cases[0])
        first["result_digest"] = "f" * 64
        bundle["bundle_digest"] = canonical_digest({key: value for key, value in bundle.items() if key != "bundle_digest"})
        with self.assertRaisesRegex(AdapterContractError, "result_digest_mismatch"):
            parse_adapter_evidence(bundle)

        corpus = parse_corpus(corpus_raw)
        _, missing = _passing_bundle_raw()
        _json_array(missing["cases"]).pop()
        missing["bundle_digest"] = canonical_digest({key: value for key, value in missing.items() if key != "bundle_digest"})
        with self.assertRaisesRegex(AdapterContractError, "missing_fixture_evidence"):
            project_adapter_evidence(corpus, parse_adapter_evidence(missing))

        _, duplicate = _passing_bundle_raw()
        duplicate_cases = _json_array(duplicate["cases"])
        duplicate_cases.append(dict(_json_object(duplicate_cases[0])))
        duplicate["bundle_digest"] = canonical_digest({key: value for key, value in duplicate.items() if key != "bundle_digest"})
        with self.assertRaisesRegex(AdapterContractError, "duplicate_fixture_evidence"):
            parse_adapter_evidence(duplicate)

        _, attacker = _passing_bundle_raw()
        attacker_case = _json_object(_json_array(attacker["cases"])[0])
        attacker_request = _json_object(attacker_case["request"])
        attacker_request["schema_version"] = "cross_harness_adapter_request/v999"
        attacker_case["request_digest"] = canonical_digest(attacker_request)
        attacker_result = _json_object(attacker_case["result"])
        attacker_result["request_digest"] = attacker_case["request_digest"]
        attacker_result["artifact_hash"] = artifact_content_digest(attacker_result)
        attacker_case["result_digest"] = canonical_digest(attacker_result)
        attacker["bundle_digest"] = canonical_digest({key: value for key, value in attacker.items() if key != "bundle_digest"})
        with self.assertRaisesRegex(AdapterContractError, "stale_adapter_version"):
            parse_adapter_evidence(attacker)

    def test_outer_fixture_identity_and_copied_fixture_content_are_bound(self) -> None:
        _, outer_mismatch = _passing_bundle_raw()
        outer_case = _json_object(_json_array(outer_mismatch["cases"])[0])
        outer_case["fixture_id"] = "different-fixture"
        outer_mismatch["bundle_digest"] = canonical_digest({key: value for key, value in outer_mismatch.items() if key != "bundle_digest"})
        with self.assertRaisesRegex(AdapterContractError, "fixture_binding_mismatch"):
            parse_adapter_evidence(outer_mismatch)

    def test_fully_rehashed_cross_case_retaining_source_and_command_is_rejected(self) -> None:
        corpus_raw, bundle = _passing_bundle_raw()
        corpus = parse_corpus(corpus_raw)
        cases = _json_array(bundle["cases"])
        copied = deepcopy(_json_object(cases[0]))
        target = _json_object(cases[1])
        target_fixture = corpus.fixtures[1]
        request = _json_object(copied["request"])
        result = _json_object(copied["result"])
        copied["fixture_id"] = target["fixture_id"]
        request["fixture_id"] = target_fixture.id
        request["adapter_id"] = target_fixture.adapter_id
        request["capability_id"] = target_fixture.capability_id
        request["fixture_binding_digest"] = corpus_fixture_binding_digest(target_fixture)
        copied["request_digest"] = canonical_digest(request)
        result["request_digest"] = copied["request_digest"]
        result["fixture_id"] = target_fixture.id
        result["adapter_id"] = target_fixture.adapter_id
        result["capability_id"] = target_fixture.capability_id
        result["artifact_hash"] = artifact_content_digest(result)
        copied["result_digest"] = canonical_digest(result)
        cases[1] = copied
        bundle["bundle_digest"] = canonical_digest({key: value for key, value in bundle.items() if key != "bundle_digest"})

        with self.assertRaisesRegex(AdapterContractError, "fixture_binding_mismatch"):
            project_adapter_evidence(corpus, parse_adapter_evidence(bundle))

    def test_source_and_command_bindings_match_the_full_trusted_corpus_values(self) -> None:
        mutations: tuple[tuple[str, str, JsonValue], ...] = (
            ("source_binding", "source_id", "different-source"),
            ("source_binding", "commit", "f" * 40),
            ("source_binding", "license", "different-license"),
            ("source_binding", "path_metadata", "different/metadata"),
            ("source_binding", "source_digest", "f" * 64),
            ("command_evidence", "command_id", "different-command"),
            ("command_evidence", "harness", "different-harness"),
            ("command_evidence", "argv", ["different-command"]),
            ("command_evidence", "cwd_class", "different-cwd"),
            ("command_evidence", "source_id", "different-source"),
            ("command_evidence", "source_commit", "f" * 40),
            ("command_evidence", "expected_exit", 1),
            ("command_evidence", "expected_semantic_result", "different-result"),
            ("command_evidence", "binding_digest", "f" * 64),
        )
        for section, field, value in mutations:
            with self.subTest(section=section, field=field):
                corpus_raw, bundle = _passing_bundle_raw()
                case = _json_object(_json_array(bundle["cases"])[0])
                _json_object(case[section])[field] = value
                bundle["bundle_digest"] = canonical_digest({key: item for key, item in bundle.items() if key != "bundle_digest"})
                with self.assertRaisesRegex(AdapterContractError, "fixture_binding_mismatch"):
                    project_adapter_evidence(parse_corpus(corpus_raw), parse_adapter_evidence(bundle))

    def test_artifact_hash_is_verified_independently_of_envelope_digests(self) -> None:
        corpus_raw, bundle = _passing_bundle_raw()
        case = _json_object(_json_array(bundle["cases"])[0])
        result = _json_object(case["result"])
        result["artifact_hash"] = "f" * 64
        case["result_digest"] = canonical_digest(result)
        bundle["bundle_digest"] = canonical_digest({key: value for key, value in bundle.items() if key != "bundle_digest"})

        with self.assertRaisesRegex(AdapterContractError, "artifact_hash_mismatch"):
            project_adapter_evidence(parse_corpus(corpus_raw), parse_adapter_evidence(bundle))

    def test_deep_machine_data_is_rejected_before_flattening(self) -> None:
        nested: JsonValue = "leaf"
        for _index in range(33):
            nested = {"nested": nested}
        result = _result()
        result["facts"] = {"nested": nested}

        with self.assertRaisesRegex(AdapterContractError, "input_too_complex"):
            parse_adapter_result(result)

    def test_failed_child_survives_projection_and_blocks_certification(self) -> None:
        corpus_raw, bundle = _passing_bundle_raw()
        first_case = _json_object(_json_array(bundle["cases"])[0])
        result = _json_object(first_case["result"])
        result["child_results"] = [{"id": "child-a", "result": "fail"}]
        result["artifact_hash"] = artifact_content_digest(result)
        first_case["result_digest"] = canonical_digest(result)
        bundle["bundle_digest"] = canonical_digest({key: value for key, value in bundle.items() if key != "bundle_digest"})
        corpus = parse_corpus(corpus_raw)
        projected = project_adapter_evidence(corpus, parse_adapter_evidence(bundle))

        outcome = evaluate_submission(projected, corpus).outcomes[0]
        score = score_submission(projected, corpus)
        self.assertEqual((outcome.status, outcome.reason_codes), ("fail", ("child_failed",)))
        self.assertFalse(score.contract_certified)


def _load_json(path: Path) -> JsonValue:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _json_array(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


if __name__ == "__main__":
    unittest.main()
