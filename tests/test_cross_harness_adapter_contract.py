from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

from src.quality.cross_harness_adapter_evidence import artifact_content_digest
from src.quality.cross_harness_adapter_model import (
    AdapterContractError,
    canonical_digest,
    parse_adapter_request,
    parse_adapter_result,
)
from src.quality.cross_harness_benchmark_values import JsonValue


ROOT = Path(__file__).parents[1]


class ExistingBenchmarkCharacterizationTests(unittest.TestCase):
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


class AdapterBoundaryFailingFirstTests(unittest.TestCase):
    def test_canonical_digest_has_a_stable_golden_vector(self) -> None:
        value: JsonValue = {"b": ["x", True], "a": 1}

        self.assertEqual(
            canonical_digest(value),
            "c2a9eac3043628b0883d74191c1b921ab2aeb873c5e82395033831287bac514b",
        )

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

    def test_deep_machine_data_is_rejected_before_flattening(self) -> None:
        nested: JsonValue = "leaf"
        for _index in range(33):
            nested = {"nested": nested}
        result = _result()
        result["facts"] = {"nested": nested}

        with self.assertRaisesRegex(AdapterContractError, "input_too_complex"):
            parse_adapter_result(result)


if __name__ == "__main__":
    unittest.main()
