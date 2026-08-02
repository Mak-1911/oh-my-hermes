from __future__ import annotations

from typing import Final

from .cross_harness_benchmark_model import Corpus
from .cross_harness_benchmark_values import (
    JsonValue,
    corpus_digest,
    raise_validation,
)


CANONICAL_CORPUS_DIGEST: Final = (
    "8dcea64c0446e7d23fe57b6bf691ac4d8c67d0127cf92bacb392cecad7912380"
)
CANONICAL_TYPED_CORPUS_DIGEST: Final = (
    "f0f9f628b4820720172990896a7d840a700aa1151ccc0ab57d1194458872a703"
)


def typed_corpus_digest(corpus: Corpus) -> str:
    dimensions: list[JsonValue] = [
        {"id": item.id, "weight": item.weight, "minimum": item.minimum}
        for item in corpus.dimensions
    ]
    sources: list[JsonValue] = [
        {
            "source_id": item.source_id,
            "commit": item.commit,
            "license": item.license,
            "path_metadata": item.path_metadata,
        }
        for item in corpus.sources
    ]
    commands: list[JsonValue] = [
        {
            "command_id": item.command_id,
            "harness": item.harness,
            "argv": list(item.argv),
            "cwd_class": item.cwd_class,
            "source_id": item.source_id,
            "source_commit": item.source_commit,
            "expected_exit": item.expected_exit,
            "expected_semantic_result": item.expected_semantic_result,
        }
        for item in corpus.commands
    ]
    fixtures: list[JsonValue] = [
        {
            "id": item.id,
            "dimension": item.dimension,
            "priority": item.priority,
            "dynamic": item.dynamic,
            "predicates": [
                {"scope": predicate.scope, "key": predicate.key, "value": predicate.value}
                for predicate in item.predicates
            ],
            "required_evidence_class": item.required_evidence_class,
            "adapter_id": item.adapter_id,
            "capability_id": item.capability_id,
            "source_id": item.source_id,
            "command_binding_id": item.command_binding_id,
        }
        for item in corpus.fixtures
    ]
    identity: JsonValue = {
        "corpus_id": corpus.corpus_id,
        "digest": corpus.digest,
        "dimensions": dimensions,
        "sources": sources,
        "commands": commands,
        "fixtures": fixtures,
    }
    return corpus_digest(identity)


def require_trusted_corpus(corpus: Corpus) -> None:
    if corpus.digest != CANONICAL_CORPUS_DIGEST:
        raise_validation("untrusted_corpus_digest")
    if typed_corpus_digest(corpus) != CANONICAL_TYPED_CORPUS_DIGEST:
        raise_validation("corpus_digest_mismatch")
