from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Sequence
import unicodedata


DOMAIN_ROUTING_CONTEXT_KEY = "domain_routing_context"
DOMAIN_ROUTING_CONTEXT_SCHEMA_VERSION = "domain_routing_context/v1"
DOMAIN_ROUTING_CONTEXT_CLAIM_BOUNDARY = (
    "Reviewed domain context only selects one wrapper clarification question; it is not "
    "routing, plan approval, execution, review, CI, merge, authentication, or Hermes "
    "internal-memory evidence."
)

MAX_WORKFLOW_HINT_CODE_POINTS = 120
MAX_REQUIRED_INPUT_CODE_POINTS = 120
MAX_QUESTION_CODE_POINTS = 240
MAX_CLAIM_BOUNDARY_CODE_POINTS = 320
_SUPPORTED_QUESTION_LOCALES = frozenset({"en", "ko"})


@dataclass(frozen=True)
class DomainClarificationTarget:
    workflow_hint: str
    required_input: str
    question_locale: str
    question_text: str


def build_domain_routing_context(
    targets: Sequence[DomainClarificationTarget],
) -> dict[str, object] | None:
    """Build the applied-only public fragment for exactly one valid catalog target."""
    if not isinstance(targets, (list, tuple)) or len(targets) != 1:
        return None
    target = targets[0]
    if not isinstance(target, DomainClarificationTarget) or not _valid_target(target):
        return None

    context: dict[str, object] = {
        "schema_version": DOMAIN_ROUTING_CONTEXT_SCHEMA_VERSION,
        "workflow_hint": target.workflow_hint,
        "required_input": target.required_input,
        "question": {
            "locale": target.question_locale,
            "text": target.question_text,
        },
        "claim_boundary": DOMAIN_ROUTING_CONTEXT_CLAIM_BOUNDARY,
    }
    context["digest"] = _canonical_public_digest(context)
    return {DOMAIN_ROUTING_CONTEXT_KEY: context}


def matches_reviewed_phrase(message: object, phrase: object) -> bool:
    """Return whether a normalized literal phrase has a valid Unicode boundary match."""
    normalized_message = _normalize_match_text(message)
    normalized_phrase = _normalize_match_text(phrase)
    if not normalized_message or not normalized_phrase:
        return False

    offset = normalized_message.find(normalized_phrase)
    while offset >= 0:
        end = offset + len(normalized_phrase)
        left_valid = (
            not _is_word_like(normalized_phrase[0])
            or offset == 0
            or not _is_word_like(normalized_message[offset - 1])
        )
        right_valid = (
            not _is_word_like(normalized_phrase[-1])
            or end == len(normalized_message)
            or not _is_word_like(normalized_message[end])
        )
        if left_valid and right_valid:
            return True
        offset = normalized_message.find(normalized_phrase, offset + 1)
    return False


def _valid_target(target: DomainClarificationTarget) -> bool:
    return (
        _valid_public_string(target.workflow_hint, MAX_WORKFLOW_HINT_CODE_POINTS)
        and _valid_public_string(target.required_input, MAX_REQUIRED_INPUT_CODE_POINTS)
        and target.question_locale in _SUPPORTED_QUESTION_LOCALES
        and _valid_public_string(target.question_text, MAX_QUESTION_CODE_POINTS)
        and len(DOMAIN_ROUTING_CONTEXT_CLAIM_BOUNDARY) <= MAX_CLAIM_BOUNDARY_CODE_POINTS
    )


def _valid_public_string(value: object, maximum: int) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and value == value.strip()
        and value == unicodedata.normalize("NFKC", value)
        and len(value) <= maximum
    )


def _canonical_public_digest(context: dict[str, object]) -> str:
    preimage = json.dumps(
        context,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def _normalize_match_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    normalized = unicodedata.normalize("NFKC", value).strip()
    return " ".join(normalized.split()).casefold()


def _is_word_like(value: str) -> bool:
    return value == "_" or unicodedata.category(value)[0] in {"L", "N", "M"}
