"""Pure, independent cross-harness benchmark contract and scorer."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import hashlib, json, re
from typing import Final, Never, TypeAlias


JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
SCHEMA: Final = "cross_harness_benchmark/v1"; SUBMISSION_SCHEMA: Final = "cross_harness_benchmark_submission/v1"
EVIDENCE_RANK: Final = {"prepared": 0, "static": 1, "test": 2, "runtime": 3}
_HEX_40: Final = re.compile(r"[0-9a-f]{40}\Z")
_HEX_64: Final = re.compile(r"[0-9a-f]{64}\Z")
_UNSAFE: Final = re.compile(r"(^/|/Users/|/home/|[A-Za-z]:\\|sk-[A-Za-z0-9]|api[_-]?key|BEGIN PRIVATE KEY|ignore previous|<script)", re.IGNORECASE)


class BenchmarkValidationError(ValueError):
    __slots__: tuple[str, ...] = ("reason_codes",)
    reason_codes: tuple[str, ...]

    def __init__(self, reason_codes: tuple[str, ...]) -> None:
        self.reason_codes = reason_codes
        super().__init__(*reason_codes)

    def __str__(self) -> str:
        return ",".join(self.reason_codes)


@dataclass(frozen=True, slots=True)
class Dimension: id: str; weight: int; minimum: int


@dataclass(frozen=True, slots=True)
class Source: source_id: str; commit: str; license: str; path_metadata: str


@dataclass(frozen=True, slots=True)
class CommandBinding: command_id: str; harness: str; argv: tuple[str, ...]; cwd_class: str; source_id: str; source_commit: str; expected_exit: int; expected_semantic_result: str


@dataclass(frozen=True, slots=True)
class Predicate: scope: str; key: str; value: JsonScalar


@dataclass(frozen=True, slots=True)
class Fixture: id: str; dimension: str; priority: str; dynamic: bool; predicates: tuple[Predicate, ...]; required_evidence_class: str; adapter_id: str; capability_id: str; source_id: str; command_binding_id: str


@dataclass(frozen=True, slots=True)
class Corpus: corpus_id: str; digest: str; dimensions: tuple[Dimension, ...]; sources: tuple[Source, ...]; commands: tuple[CommandBinding, ...]; fixtures: tuple[Fixture, ...]


@dataclass(frozen=True, slots=True)
class FixtureOutcome: fixture_id: str; dimension: str; priority: str; status: str; reason_codes: tuple[str, ...]; runtime_observed: bool


@dataclass(frozen=True, slots=True)
class EvaluationReport: schema_version: str; corpus_digest: str; harness_id: str; outcomes: tuple[FixtureOutcome, ...]


@dataclass(frozen=True, slots=True)
class DimensionScore: dimension: str; earned: int; available: int; supported: int; fixtures: int


@dataclass(frozen=True, slots=True)
class ScoreReport:
    total: int; level: int; certified: bool
    coverage_supported: int; coverage_total: int
    dimensions: tuple[DimensionScore, ...]; reason_codes: tuple[str, ...]


def corpus_digest(value: JsonValue | Mapping[str, JsonValue]) -> str:
    """Return the canonical SHA-256 digest for JSON-compatible metadata."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def parse_corpus(raw: Mapping[str, JsonValue]) -> Corpus:
    """Parse the exact frozen corpus shape and reject semantic drift."""
    _shape(raw, {"schema_version", "corpus_id", "corpus_digest", "claim_boundary", "dimensions", "sources", "command_bindings", "fixtures"})
    _safe(raw)
    _ = _text(raw["claim_boundary"])
    if _text(raw["schema_version"]) != SCHEMA:
        _raise("unknown_schema")
    declared = _digest(raw["corpus_digest"], "invalid_corpus_digest")
    payload = {key: value for key, value in raw.items() if key != "corpus_digest"}
    if corpus_digest(payload) != declared:
        _raise("corpus_digest_mismatch")
    dimensions = tuple(_parse_dimension(item) for item in _items(raw["dimensions"]))
    sources = tuple(_parse_source(item) for item in _items(raw["sources"]))
    commands = tuple(_parse_command(item) for item in _items(raw["command_bindings"]))
    fixtures = tuple(_parse_fixture(item) for item in _items(raw["fixtures"]))
    _unique((item.id for item in dimensions), "duplicate_dimension")
    _unique((item.source_id for item in sources), "duplicate_source")
    _unique((item.command_id for item in commands), "duplicate_command")
    _unique((item.id for item in fixtures), "duplicate_fixture")
    if len(dimensions) != 10 or sum(item.weight for item in dimensions) != 100:
        _raise("invalid_dimension_weights")
    dimension_ids = {item.id for item in dimensions}
    source_ids = {item.source_id for item in sources}
    command_ids = {item.command_id for item in commands}
    if len(fixtures) != 15 or any(item.dimension not in dimension_ids for item in fixtures):
        _raise("invalid_fixture_corpus")
    if any(item.source_id not in source_ids or item.command_binding_id not in command_ids for item in fixtures):
        _raise("unknown_fixture_binding")
    if any(command.source_id not in source_ids or next(source for source in sources if source.source_id == command.source_id).commit != command.source_commit for command in commands): _raise("invalid_command_source_binding")
    return Corpus(_text(raw["corpus_id"]), declared, dimensions, sources, commands, fixtures)


def evaluate_submission(raw: Mapping[str, JsonValue], corpus: Corpus) -> EvaluationReport:
    """Derive fixture status solely from supplied machine facts and bindings."""
    _shape(raw, {"schema_version", "corpus_digest", "harness_id", "results"})
    _safe(raw)
    if _text(raw["schema_version"]) != SUBMISSION_SCHEMA:
        _raise("unknown_submission_schema")
    if _digest(raw["corpus_digest"], "invalid_corpus_digest") != corpus.digest:
        _raise("stale_corpus_digest")
    harness = _text(raw["harness_id"])
    result_items = _items(raw["results"])
    indexed: dict[str, Mapping[str, JsonValue]] = {}
    for item in result_items:
        result = _map(item)
        fixture_id = _text(result.get("fixture_id"))
        if fixture_id in indexed:
            _raise("duplicate_result")
        indexed[fixture_id] = result
    known = {item.id for item in corpus.fixtures}
    if any(result_id not in known for result_id in indexed):
        _raise("unknown_fixture")
    outcomes = tuple(_evaluate_fixture(fixture, indexed.get(fixture.id), corpus, harness) for fixture in corpus.fixtures)
    return EvaluationReport("cross_harness_benchmark_evaluation/v1", corpus.digest, harness, outcomes)


def score_evaluation(report: EvaluationReport, corpus: Corpus) -> ScoreReport:
    """Score ten fixed dimensions while keeping support separate from quality."""
    scores: list[DimensionScore] = []
    for dimension in corpus.dimensions:
        outcomes = tuple(item for item in report.outcomes if item.dimension == dimension.id)
        supported = sum(item.status != "unsupported" for item in outcomes)
        all_pass = bool(outcomes) and all(item.status == "pass" for item in outcomes)
        partial = bool(outcomes) and all(item.status in {"pass", "partial"} for item in outcomes)
        earned = dimension.weight if all_pass else dimension.weight // 2 if partial else 0
        scores.append(DimensionScore(dimension.id, earned, dimension.weight, supported, len(outcomes)))
    total = sum(item.earned for item in scores)
    all_pass = all(item.status == "pass" for item in report.outcomes)
    dynamic_observed = all(not fixture.dynamic or next(item for item in report.outcomes if item.fixture_id == fixture.id).runtime_observed for fixture in corpus.fixtures)
    level = 5 if all_pass and dynamic_observed else 4 if all_pass else 3 if total >= 70 else 2 if total >= 50 else 1 if total else 0
    reasons: list[str] = []
    if any(item.priority == "P0" and item.status == "fail" for item in report.outcomes):
        reasons.append("p0_failure")
    if not all_pass:
        reasons.append("fixture_not_passed")
    if any(score.earned < dimension.minimum for score, dimension in zip(scores, corpus.dimensions, strict=True)):
        reasons.append("below_dimension_minimum")
    certified = not reasons and level >= 4
    return ScoreReport(total, level, certified, sum(item.supported for item in scores), len(report.outcomes), tuple(scores), tuple(reasons))


def _evaluate_fixture(fixture: Fixture, raw: Mapping[str, JsonValue] | None, corpus: Corpus, harness: str) -> FixtureOutcome:
    if raw is None:
        return _outcome(fixture, "unsupported", "missing_result", False)
    _shape(raw, {"fixture_id", "adapter_id", "capability_id", "evidence_class", "runtime_observation", "actual_machine", "facts", "source_binding", "command_evidence", "child_results"})
    adapter = _text(raw["adapter_id"])
    capability = _text(raw["capability_id"])
    runtime = _text(raw["runtime_observation"])
    source = next(item for item in corpus.sources if item.source_id == fixture.source_id)
    command = next(item for item in corpus.commands if item.command_id == fixture.command_binding_id)
    _verify_source(_map(raw["source_binding"]), source)
    command_ok = _verify_command(_map(raw["command_evidence"]), command, harness)
    children = tuple(_map(item) for item in _items(raw["child_results"])); _unique((_text(item.get("id")) for item in children), "duplicate_child")
    child_failed = any(_child_failed(item) for item in children)
    actual = _flat(raw["actual_machine"])
    facts = _flat(raw["facts"])
    predicates_ok = all(item.key in values and type(values[item.key]) is type(item.value) and values[item.key] == item.value for item in fixture.predicates for values in (actual if item.scope == "actual_machine" else facts,))
    observed = runtime == "observed"
    evidence = _text(raw["evidence_class"])
    if evidence not in EVIDENCE_RANK or runtime not in {"observed", "prepared_not_observed", "not_applicable"}:
        _raise("invalid_evidence_state")
    if adapter != fixture.adapter_id: return _outcome(fixture, "unsupported", "adapter_unavailable", observed)
    if capability != fixture.capability_id: return _outcome(fixture, "unsupported", "capability_unavailable", observed)
    if child_failed:
        return _outcome(fixture, "fail", "child_failed", observed)
    if not command_ok:
        return _outcome(fixture, "fail", "command_result_mismatch", observed)
    if not predicates_ok:
        return _outcome(fixture, "fail", "predicate_mismatch", observed)
    if EVIDENCE_RANK[evidence] < EVIDENCE_RANK[fixture.required_evidence_class]:
        return _outcome(fixture, "partial", "insufficient_evidence_class", observed)
    if fixture.dynamic and evidence == "runtime" and not observed:
        return _outcome(fixture, "partial", "runtime_not_observed", observed)
    return _outcome(fixture, "pass", "predicate_satisfied", observed, no_reason=True)


def _parse_dimension(value: JsonValue) -> Dimension:
    raw = _map(value); _shape(raw, {"id", "weight", "minimum"})
    weight = _integer(raw["weight"]); minimum = _integer(raw["minimum"])
    if weight <= 0 or minimum < 0 or minimum > weight: _raise("invalid_dimension")
    return Dimension(_text(raw["id"]), weight, minimum)


def _parse_source(value: JsonValue) -> Source:
    raw = _map(value); _shape(raw, {"source_id", "commit", "license", "path_metadata"})
    return Source(_text(raw["source_id"]), _commit(raw["commit"]), _text(raw["license"]), _relative(raw["path_metadata"]))


def _parse_command(value: JsonValue) -> CommandBinding:
    raw = _map(value); _shape(raw, {"command_id", "harness", "argv", "cwd_class", "source_id", "source_commit", "expected_exit", "expected_semantic_result"})
    argv = tuple(_text(item) for item in _items(raw["argv"]))
    if not argv: _raise("invalid_argv")
    return CommandBinding(_text(raw["command_id"]), _text(raw["harness"]), argv, _text(raw["cwd_class"]), _text(raw["source_id"]), _commit(raw["source_commit"]), _integer(raw["expected_exit"]), _text(raw["expected_semantic_result"]))


def _parse_fixture(value: JsonValue) -> Fixture:
    raw = _map(value); _shape(raw, {"id", "dimension", "priority", "dynamic", "prompt", "setup", "expected_machine", "required_evidence_class", "evaluator", "adapter_id", "capability_id", "source_id", "command_binding_id"})
    prompt = _map(raw["prompt"]); setup = _map(raw["setup"]); _shape(prompt, {"intent", "constraint"}); _shape(setup, {"profile", "mode"})
    _ = tuple(_text(item) for item in (*prompt.values(), *setup.values()))
    if _text(raw["evaluator"]) != "predicate_subset/v1": _raise("unknown_evaluator")
    priority = _text(raw["priority"]); dynamic = raw["dynamic"]
    if priority not in {"P0", "P1"} or not isinstance(dynamic, bool): _raise("wrong_type")
    predicates = tuple(_parse_predicate(item) for item in _items(raw["expected_machine"]))
    if not predicates: _raise("missing_predicate")
    evidence = _text(raw["required_evidence_class"])
    if evidence not in EVIDENCE_RANK: _raise("invalid_evidence_class")
    return Fixture(_text(raw["id"]), _text(raw["dimension"]), priority, dynamic, predicates, evidence, _text(raw["adapter_id"]), _text(raw["capability_id"]), _text(raw["source_id"]), _text(raw["command_binding_id"]))


def _parse_predicate(value: JsonValue) -> Predicate:
    raw = _map(value); _shape(raw, {"scope", "key", "operator", "value"})
    scope = _text(raw["scope"])
    if scope not in {"actual_machine", "facts"} or _text(raw["operator"]) != "eq": _raise("invalid_predicate")
    return Predicate(scope, _text(raw["key"]), _scalar(raw["value"]))


def _verify_source(raw: Mapping[str, JsonValue], source: Source) -> None:
    _shape(raw, {"source_id", "commit", "license", "path_metadata", "source_digest"})
    base: dict[str, JsonValue] = {"source_id": source.source_id, "commit": source.commit, "license": source.license, "path_metadata": source.path_metadata}
    supplied = {key: raw[key] for key in base}
    if supplied != base: _raise("source_binding_mismatch")
    if _digest(raw["source_digest"], "invalid_source_digest") != corpus_digest(base): _raise("stale_source_digest")


def _verify_command(raw: Mapping[str, JsonValue], command: CommandBinding, harness: str) -> bool:
    fields = {"command_id", "harness", "argv", "cwd_class", "source_id", "source_commit", "expected_exit", "expected_semantic_result", "binding_digest", "observed_exit", "observed_semantic_result"}; _shape(raw, fields)
    base: dict[str, JsonValue] = {"command_id": command.command_id, "harness": command.harness, "argv": list(command.argv), "cwd_class": command.cwd_class, "source_id": command.source_id, "source_commit": command.source_commit, "expected_exit": command.expected_exit, "expected_semantic_result": command.expected_semantic_result}
    supplied: dict[str, JsonValue] = {"command_id": _text(raw["command_id"]), "harness": _text(raw["harness"]), "argv": [_text(item) for item in _items(raw["argv"])], "cwd_class": _text(raw["cwd_class"]), "source_id": _text(raw["source_id"]), "source_commit": _commit(raw["source_commit"]), "expected_exit": _integer(raw["expected_exit"]), "expected_semantic_result": _text(raw["expected_semantic_result"])}
    if harness != command.harness or supplied != base: _raise("command_binding_mismatch")
    if _digest(raw["binding_digest"], "invalid_binding_digest") != corpus_digest(base): _raise("stale_binding_digest")
    return _integer(raw["observed_exit"]) == command.expected_exit and _text(raw["observed_semantic_result"]) == command.expected_semantic_result


def _child_failed(raw: Mapping[str, JsonValue]) -> bool:
    _shape(raw, {"id", "result"}); _ = _text(raw["id"]); result = _text(raw["result"])
    if result not in {"pass", "fail"}: _raise("invalid_child_result")
    return result == "fail"


def _outcome(fixture: Fixture, status: str, reason: str, observed: bool, *, no_reason: bool = False) -> FixtureOutcome:
    return FixtureOutcome(fixture.id, fixture.dimension, fixture.priority, status, () if no_reason else (reason,), observed)


def _shape(raw: Mapping[str, JsonValue], fields: set[str]) -> None:
    missing = fields - set(raw); extra = set(raw) - fields
    if missing: _raise("missing_fields")
    if extra: _raise("extra_fields")


def _map(value: JsonValue | None) -> Mapping[str, JsonValue]:
    if not isinstance(value, dict): _raise("wrong_type")
    return value


def _items(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list): _raise("wrong_type")
    return value


def _flat(value: JsonValue) -> Mapping[str, JsonScalar]:
    return {key: _scalar(item) for key, item in _map(value).items()}


def _scalar(value: JsonValue) -> JsonScalar:
    if isinstance(value, (dict, list)): _raise("wrong_type")
    return value


def _text(value: JsonValue | None) -> str:
    if not isinstance(value, str) or not value: _raise("wrong_type")
    return value


def _integer(value: JsonValue) -> int:
    if type(value) is not int: _raise("wrong_type")
    return value


def _commit(value: JsonValue) -> str:
    text = _text(value)
    if not _HEX_40.fullmatch(text): _raise("invalid_commit")
    return text


def _digest(value: JsonValue, reason: str) -> str:
    text = _text(value)
    if not _HEX_64.fullmatch(text): _raise(reason)
    return text


def _relative(value: JsonValue) -> str:
    text = _text(value)
    if text.startswith("/") or ".." in text.split("/"): _raise("unsafe_metadata")
    return text


def _safe(value: JsonValue | Mapping[str, JsonValue]) -> None:
    if isinstance(value, str) and _UNSAFE.search(value): _raise("unsafe_metadata")
    if isinstance(value, Mapping):
        for item in value.values(): _safe(item)
    if isinstance(value, list):
        for item in value: _safe(item)


def _unique(values: Iterable[str], reason: str) -> None:
    items = tuple(values)
    if len(items) != len(set(items)): _raise(reason)


def _raise(reason: str) -> Never:
    raise BenchmarkValidationError((reason,))
