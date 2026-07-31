from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import unicodedata


MAX_DOMAIN_CONTEXT_MATCHES = 64


@dataclass(frozen=True)
class DomainClarificationTarget:
    workflow_hint: str
    required_input: str
    question_locale: str
    question_text: str


def resolve_domain_clarification_target(
    profiles: tuple[dict[str, object], ...],
    message: str,
    *,
    project_root: Path,
    locale: str,
) -> DomainClarificationTarget | None:
    from ..paths import project_identity
    from ..skills import catalog

    expected_scope = {
        "kind": "project",
        "ref": project_identity(project_root),
        "ref_authority": "operator_or_wrapper_supplied",
        "identity_claim": "not_authenticated_identity_evidence",
    }
    matches: list[tuple[dict[str, object], dict[str, object]]] = []
    for profile in profiles:
        if profile.get("scope") != expected_scope:
            continue
        mappings = profile.get("vocabulary_mappings")
        if not isinstance(mappings, list):
            return None
        for mapping in mappings:
            if not isinstance(mapping, dict):
                return None
            if matches_reviewed_phrase(message, mapping.get("phrase")):
                matches.append((profile, mapping))
                if len(matches) > MAX_DOMAIN_CONTEXT_MATCHES:
                    return None
    if not matches:
        return None

    canonicals = {str(mapping.get("canonical")) for _profile, mapping in matches}
    if len(canonicals) != 1:
        return None

    routable = {
        definition.name: definition for definition in catalog.routable_definitions()
    }
    selected_hints: set[str] = set()
    for profile, _mapping in matches:
        hints = profile.get("workflow_hints")
        if not isinstance(hints, list) or not hints:
            return None
        for hint in hints:
            if not isinstance(hint, str) or hint not in routable:
                return None
            selected_hints.add(hint)
    if len(selected_hints) != 1:
        return None

    workflow_hint = next(iter(selected_hints))
    definition = routable[workflow_hint]
    questions = definition.expert_questions
    if not questions:
        return None
    question = questions[0]
    if question.required_input not in definition.required_inputs:
        return None
    selected_locale = (
        "ko" if isinstance(locale, str) and locale.casefold() == "ko" else "en"
    )
    return DomainClarificationTarget(
        workflow_hint=workflow_hint,
        required_input=question.required_input,
        question_locale=selected_locale,
        question_text=question.question_for_locale(selected_locale),
    )


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


def _normalize_match_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    normalized = unicodedata.normalize("NFKC", value).strip()
    return " ".join(normalized.split()).casefold()


def _is_word_like(value: str) -> bool:
    return value == "_" or unicodedata.category(value)[0] in {"L", "N", "M"}
