from __future__ import annotations

import hashlib
import json
from typing import Sequence
import unicodedata

from .domain_intelligence_profile_resolution import (
    MAX_DOMAIN_CONTEXT_MATCHES,
    DomainClarificationTarget,
    matches_reviewed_phrase,
    resolve_domain_clarification_target,
)


__all__ = (
    "MAX_DOMAIN_CONTEXT_MATCHES",
    "DomainClarificationTarget",
    "build_domain_routing_context",
    "matches_reviewed_phrase",
    "resolve_domain_routing_context",
)


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


def resolve_domain_routing_context(
    binding: object,
    message: object,
    *,
    locale: str,
) -> dict[str, object] | None:
    """Resolve one catalog-owned question from a complete reviewed store snapshot."""
    from .domain_intelligence_queries import read_validated_domain_profiles_at
    from .domain_project_context import HostProjectBinding

    if not isinstance(binding, HostProjectBinding) or not isinstance(message, str):
        return None
    try:
        profiles = read_validated_domain_profiles_at(binding)
        target = resolve_domain_clarification_target(
            profiles,
            message,
            project_root=binding.project_root,
            locale=locale,
        )
        if target is None:
            return None
        return build_domain_routing_context((target,))
    except (OSError, TypeError, ValueError):
        return None


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
