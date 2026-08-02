from __future__ import annotations

from contextlib import chdir
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from _cli_harness import run_cli
from omh.commands.cross_harness_benchmark import cmd_benchmark_validate
from omh.commands.main import build_parser, main
from omh.quality.cross_harness_benchmark import JsonValue


ROOT = Path(__file__).parents[1]
PASSING_INPUT_PATH = (
    ROOT / "benchmarks" / "cross-harness" / "v1" / "example-passing-submission.json"
)


def _passing_input() -> dict[str, JsonValue]:
    value = json.loads(PASSING_INPUT_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


class CrossHarnessBenchmarkCliTests(unittest.TestCase):
    def test_validate_reads_one_explicit_file_without_creating_runtime_state(
        self,
    ) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "input.json"
            input_path.write_text(json.dumps(_passing_input()), encoding="utf-8")
            with chdir(root):
                status, stdout, stderr = run_cli(
                    ["benchmark", "validate", "--input", str(input_path)]
                )
            self.assertEqual(status, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["valid"])
            self.assertFalse((root / ".omh").exists())

    def test_score_reads_stdin_and_returns_certification_result(self) -> None:
        status, stdout, stderr = run_cli(
            ["benchmark", "score", "--stdin"], stdin_text=json.dumps(_passing_input())
        )
        self.assertEqual(status, 0, stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["certified"])
        self.assertEqual(payload["total"], 100)

    def test_validate_accepts_semantic_failure_but_score_and_report_fail_certification(
        self,
    ) -> None:
        benchmark_input = _passing_input()
        submission = benchmark_input["submission"]
        assert isinstance(submission, dict)
        results = submission["results"]
        assert isinstance(results, list)
        result = next(
            result
            for result in results
            if isinstance(result, dict)
            and result.get("fixture_id") == "ultrawork-child-propagation"
        )
        result["child_results"] = [{"id": "primary", "result": "fail"}]
        encoded = json.dumps(benchmark_input)
        validate_status, validate_stdout, validate_stderr = run_cli(
            ["benchmark", "validate", "--stdin"], stdin_text=encoded
        )
        self.assertEqual(validate_status, 0, validate_stderr)
        failed_outcome = next(
            outcome
            for outcome in json.loads(validate_stdout)["outcomes"]
            if outcome["fixture_id"] == "ultrawork-child-propagation"
        )
        self.assertEqual(failed_outcome["status"], "fail")
        for command in ("score", "report"):
            with self.subTest(command=command):
                status, stdout, stderr = run_cli(
                    ["benchmark", command, "--stdin"], stdin_text=encoded
                )
                self.assertEqual(status, 1, stderr)
                payload = json.loads(stdout)
                self.assertFalse(
                    payload["certified"]
                    if command == "score"
                    else payload["score"]["certified"]
                )
                self.assertIn(
                    "p0_failure",
                    payload["reason_codes"]
                    if command == "score"
                    else payload["score"]["reason_codes"],
                )

    def test_invalid_input_variants_return_deterministic_structured_errors(
        self,
    ) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing_path = root / "missing.json"
            malformed_path = root / "malformed.json"
            malformed_path.write_text("{", encoding="utf-8")
            cases = (
                (["benchmark", "validate"], "missing_input"),
                (
                    ["benchmark", "validate", "--input", str(missing_path)],
                    "input_file_unavailable",
                ),
                (
                    ["benchmark", "validate", "--input", str(malformed_path)],
                    "invalid_json",
                ),
                (["benchmark", "validate", "--stdin"], "input_must_be_object"),
                (
                    [
                        "benchmark",
                        "validate",
                        "--input",
                        str(malformed_path),
                        "--stdin",
                    ],
                    "conflicting_input",
                ),
            )
            for args, reason in cases:
                with self.subTest(reason=reason):
                    stdin = "[]" if reason == "input_must_be_object" else ""
                    status, stdout, _ = run_cli(args, stdin_text=stdin)
                    self.assertEqual(status, 2)
                    self.assertEqual(json.loads(stdout)["reason_codes"], [reason])

    def test_report_exposes_coverage_unknowns_claim_boundary_and_repeated_calls_leave_no_state(
        self,
    ) -> None:
        benchmark_input = _passing_input()
        submission = benchmark_input["submission"]
        assert isinstance(submission, dict)
        results = submission["results"]
        assert isinstance(results, list)
        first = results[0]
        assert isinstance(first, dict)
        first["capability_id"] = "unavailable"
        encoded = json.dumps(benchmark_input)
        first_status, first_stdout, first_stderr = run_cli(
            ["benchmark", "report", "--stdin"], stdin_text=encoded
        )
        second_status, second_stdout, second_stderr = run_cli(
            ["benchmark", "report", "--stdin"], stdin_text=encoded
        )
        self.assertEqual(first_status, 1, first_stderr)
        self.assertEqual(second_status, 1, second_stderr)
        self.assertEqual(first_stdout, second_stdout)
        payload = json.loads(first_stdout)
        self.assertEqual(payload["schema_version"], "cross_harness_benchmark_report/v1")
        self.assertEqual(payload["coverage"]["unsupported"], 1)
        self.assertEqual(payload["unsupported"], ["model-explicit-selection"])
        self.assertEqual(payload["unknowns"], ["model-explicit-selection"])

    def test_parser_registers_validate_callback_and_explicit_input_options(
        self,
    ) -> None:
        parser = build_parser()
        stdin_args = parser.parse_args(["benchmark", "validate", "--stdin"])
        file_args = parser.parse_args(
            ["benchmark", "validate", "--input", "input.json"]
        )
        self.assertEqual(
            (stdin_args.command, stdin_args.benchmark_command),
            ("benchmark", "validate"),
        )
        self.assertIs(stdin_args.func, cmd_benchmark_validate)
        self.assertIsNone(stdin_args.input_file)
        self.assertTrue(stdin_args.stdin)
        self.assertEqual(file_args.input_file, "input.json")
        self.assertFalse(file_args.stdin)

    def test_interrupted_stdin_leaves_no_state_and_next_file_invocation_succeeds(
        self,
    ) -> None:
        class InterruptingStdin:
            def read(self) -> str:
                raise KeyboardInterrupt

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "input.json"
            input_path.write_text(json.dumps(_passing_input()), encoding="utf-8")
            with (
                chdir(root),
                patch(
                    "omh.commands.cross_harness_benchmark.sys.stdin",
                    InterruptingStdin(),
                ),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    main(["benchmark", "validate", "--stdin"])
            self.assertFalse((root / ".omh").exists())
            status, stdout, stderr = run_cli(
                ["benchmark", "validate", "--input", str(input_path)]
            )
            self.assertEqual(status, 0, stderr)
            self.assertTrue(json.loads(stdout)["valid"])
