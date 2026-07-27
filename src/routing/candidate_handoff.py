"""Hand an undecidable route to model selection instead of degrading it.

The deterministic router resolves confident requests well, and it should keep
doing that. What it does badly is the undecided case. Measured on a 24-message
natural-language sample, 8 turns ended in a picker and 2 in a bare fallback,
and 6 produced a score tie the scorer could not break. A user who wrote "PR
리뷰 좀 해줘" got a picker because two skills scored 9 apiece; a user who wrote
"ビルドが失敗した理由を教えて" got nothing because the trigger tables carry no
Kana. In both cases the router had the information needed to shortlist, and
threw it away to ask the user to do the routing instead.

This module turns that dead end into a handoff. When the route is undecidable,
OMH emits the candidates it did find -- each with the reason it matched, its
next action, and its evidence boundary -- and asks the model to choose. Hermes
already understands every language OMH targets and can read a shortlist of four
descriptions; that is the part it is good at.

OMH makes no LLM call here. It assembles candidates and a question; the
selection happens in Hermes. `docs/DIRECTION.md`'s "not an LLM router" boundary
holds, and the payload stays reproducible: the same message yields the same
candidate set and the same digest, so a routing decision remains auditable.
"""

from __future__ import annotations

import hashlib
import json

from .input_language import SUPPORT_MODEL_SELECTION_REQUIRED


CANDIDATE_HANDOFF_SCHEMA_VERSION = "model_selection_candidates/v1"

# Below this score gap the scorer is not discriminating between the top two
# candidates, it is picking one arbitrarily. Measured ties (gap 0) and near-ties
# (gap 1) both produced wrong winners on the sample corpus.
DECIDING_SCORE_GAP = 5

MAX_CANDIDATES = 4

REASON_LOW_CONFIDENCE = "low_confidence"
REASON_NARROW_SCORE_GAP = "narrow_score_gap"
REASON_NO_TRIGGER_COVERAGE = "no_trigger_coverage"

CLAIM_BOUNDARY = (
    "A candidate set is routing input for model selection, not a routing decision. "
    "It is not execution, review, CI, merge, or evidence that any candidate ran."
)

_UNDECIDED_ACTIONS = ("clarify", "fallback")


def _score_gap(recommendations: list[dict[str, object]]) -> int | None:
    if len(recommendations) < 2:
        return None
    return int(recommendations[0].get("score", 0) or 0) - int(recommendations[1].get("score", 0) or 0)


def candidate_handoff_reasons(route: dict[str, object]) -> tuple[str, ...]:
    """Why this route cannot be decided deterministically, in stable order."""
    if str(route.get("action", "")) not in _UNDECIDED_ACTIONS:
        return ()

    reasons: list[str] = []
    input_language = route.get("input_language")
    if isinstance(input_language, dict):
        if input_language.get("trigger_support") == SUPPORT_MODEL_SELECTION_REQUIRED:
            reasons.append(REASON_NO_TRIGGER_COVERAGE)

    recommendations = [item for item in route.get("recommendations", []) if isinstance(item, dict)]
    gap = _score_gap(recommendations)
    if gap is not None and gap < DECIDING_SCORE_GAP:
        reasons.append(REASON_NARROW_SCORE_GAP)
    if str(route.get("confidence", "")) == "low":
        reasons.append(REASON_LOW_CONFIDENCE)
    return tuple(reasons)


def _candidate(recommendation: dict[str, object]) -> dict[str, object]:
    return {
        "skill": recommendation.get("skill"),
        "description": recommendation.get("description"),
        "why_it_matched": recommendation.get("why"),
        "matched": list(recommendation.get("matched", []) or []),
        "score": recommendation.get("score"),
        "confidence": recommendation.get("confidence"),
        "next_action": recommendation.get("next_action"),
        "evidence_boundary": recommendation.get("evidence_boundary"),
    }


def candidate_handoff_digest(candidates: list[dict[str, object]], reasons: tuple[str, ...]) -> str:
    """Reproducible identity for this candidate set.

    Keyed on the candidate skills and the reasons, not on scores, so the digest
    survives score tuning while still changing when the shortlist changes.
    """
    identity = {
        "schema_version": CANDIDATE_HANDOFF_SCHEMA_VERSION,
        "reasons": list(reasons),
        "skills": [candidate.get("skill") for candidate in candidates],
    }
    encoded = json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_candidate_handoff(route: dict[str, object]) -> dict[str, object] | None:
    """Build the model-selection handoff, or None when the route is decidable."""
    reasons = candidate_handoff_reasons(route)
    if not reasons:
        return None

    recommendations = [item for item in route.get("recommendations", []) if isinstance(item, dict)]
    candidates = [_candidate(recommendation) for recommendation in recommendations[:MAX_CANDIDATES]]

    payload: dict[str, object] = {
        "schema_version": CANDIDATE_HANDOFF_SCHEMA_VERSION,
        "reasons": list(reasons),
        "candidates": candidates,
        "candidate_count": len(candidates),
        "selector": "hermes",
        "digest": candidate_handoff_digest(candidates, reasons),
        "claim_boundary": CLAIM_BOUNDARY,
    }

    if candidates:
        payload["question"] = (
            "Which of these workflows fits the request? Choose one, say why in one line, "
            "and carry its evidence boundary forward. If none fit, ask one clarifying question."
        )
    else:
        # Scoring found nothing at all, which is the normal outcome for a script
        # the trigger tables do not cover. Point at the installed shortlist rather
        # than inventing candidates; `references/catalog-index.md` carries one line
        # per skill and is exactly what meta-router already tells the model to read.
        payload["question"] = (
            "No deterministic candidate matched this request. Shortlist from the installed "
            "`references/catalog-index.md`, confirm with a bounded `omh recommend` query, and "
            "name the chosen workflow with its evidence boundary."
        )
        payload["catalog_reference"] = "references/catalog-index.md"

    return payload
