from __future__ import annotations

import json
from pathlib import Path
import unittest

from src.quality.cross_harness_benchmark import (
    JsonValue,
    corpus_digest,
    evaluate_submission,
    parse_corpus,
)


ROOT = Path(__file__).parents[1]
CORPUS_PATH = ROOT / "benchmarks" / "cross-harness" / "v1" / "manifest.json"
PASSING_INPUT_PATH = ROOT / "benchmarks" / "cross-harness" / "v1" / "example-passing-submission.json"


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _json_array(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _load_corpus_data() -> dict[str, JsonValue]:
    with CORPUS_PATH.open(encoding="utf-8") as stream:
        value: JsonValue = json.load(stream)
    return _json_object(value)


def _passing_submission() -> dict[str, JsonValue]:
    with PASSING_INPUT_PATH.open(encoding="utf-8") as stream:
        value: JsonValue = json.load(stream)
    return _json_object(_json_object(value)["submission"])


def _actual_machine(
    submission: dict[str, JsonValue], index: int = 0
) -> dict[str, JsonValue]:
    results = _json_array(submission["results"])
    return _json_object(_json_object(results[index])["actual_machine"])


def _refresh_corpus_digest(raw: dict[str, JsonValue]) -> None:
    payload = {key: value for key, value in raw.items() if key != "corpus_digest"}
    raw["corpus_digest"] = corpus_digest(payload)


def _first_predicate(raw_corpus: dict[str, JsonValue]) -> dict[str, JsonValue]:
    first_fixture = _json_object(_json_array(raw_corpus["fixtures"])[0])
    return _json_object(_json_array(first_fixture["expected_machine"])[0])


class CrossHarnessBenchmarkPredicateTests(unittest.TestCase):
    def test_missing_machine_fact_detects_fixture_drift(self) -> None:
        corpus = parse_corpus(_load_corpus_data())
        submission = _passing_submission()
        _actual_machine(submission).clear()

        outcome = evaluate_submission(submission, corpus).outcomes[0]

        self.assertEqual(
            (outcome.status, outcome.reason_codes),
            ("fail", ("predicate_mismatch",)),
        )

    def test_false_does_not_satisfy_integer_zero_predicate(self) -> None:
        # Given: the P0 fixture expects the JSON integer zero.
        corpus = parse_corpus(_load_corpus_data())
        submission = _passing_submission()
        fixture_index = next(
            index
            for index, fixture in enumerate(corpus.fixtures)
            if fixture.id == "ultrawork-child-propagation"
        )
        _actual_machine(submission, fixture_index)["parent_exit"] = False

        # When: the submission is evaluated with the JSON boolean false.
        outcome = evaluate_submission(submission, corpus).outcomes[fixture_index]

        # Then: exact scalar typing prevents Python's False == 0 equivalence.
        self.assertEqual(
            (outcome.status, outcome.reason_codes),
            ("fail", ("predicate_mismatch",)),
        )

    def test_missing_key_does_not_satisfy_null_predicate(self) -> None:
        # Given: a valid corpus explicitly expects a present JSON null value.
        raw_corpus = _load_corpus_data()
        _first_predicate(raw_corpus)["value"] = None
        _refresh_corpus_digest(raw_corpus)
        corpus = parse_corpus(raw_corpus)
        submission = _passing_submission()
        submission["corpus_digest"] = corpus.digest
        del _actual_machine(submission)["selected_owner"]

        # When: the submission omits the predicate key entirely.
        outcome = evaluate_submission(submission, corpus).outcomes[0]

        # Then: absence remains distinct from a present null value.
        self.assertEqual(
            (outcome.status, outcome.reason_codes),
            ("fail", ("predicate_mismatch",)),
        )

    def test_exact_predicate_equality_preserves_json_scalar_types(self) -> None:
        for scalar in (None, False, 0, 1.5, "codex"):
            with self.subTest(scalar=scalar):
                # Given: the predicate and submitted fact contain the same JSON scalar.
                raw_corpus = _load_corpus_data()
                _first_predicate(raw_corpus)["value"] = scalar
                _refresh_corpus_digest(raw_corpus)
                corpus = parse_corpus(raw_corpus)
                submission = _passing_submission()
                submission["corpus_digest"] = corpus.digest
                _actual_machine(submission)["selected_owner"] = scalar

                # When: exact predicate equality evaluates the matching fact.
                outcome = evaluate_submission(submission, corpus).outcomes[0]

                # Then: every valid JSON scalar remains supported.
                self.assertEqual((outcome.status, outcome.reason_codes), ("pass", ()))


if __name__ == "__main__":
    unittest.main()
