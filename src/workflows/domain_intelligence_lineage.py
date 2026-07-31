from __future__ import annotations

from collections.abc import Callable

from ..paths import OmhPaths
from .domain_intelligence_store import read_candidate_or_raise, read_history_profiles


_CONTENT_FIELDS = (
    "profile_id",
    "scope",
    "domain_id",
    "vocabulary_mappings",
    "workflow_hints",
    "confidence",
    "provenance",
)
_SHARED_APPROVAL_FIELDS = _CONTENT_FIELDS + ("base_profile_revision",)
_RETIRED_INHERITED_FIELDS = _CONTENT_FIELDS + (
    "candidate_id",
    "approved_by",
    "approved_at",
    "created_at",
)
_CHAIN_IDENTITY_FIELDS = ("profile_id", "scope", "domain_id")


def validate_profile_candidate_lineage(
    paths: OmhPaths,
    profile: dict[str, object],
    review: dict[str, object],
    *,
    validate_candidate: Callable[[dict[str, object]], None],
    validate_profile: Callable[[OmhPaths, dict[str, object]], None],
) -> None:
    approved = _validated_active_predecessor(paths, profile, validate_profile)
    if profile.get("status") == "active":
        candidate = _read_approved_candidate(paths, profile, validate_candidate)
        _validate_active_lineage(profile, review, candidate)
        return
    if approved is None:
        raise ValueError("approved_candidate_lineage_required")
    if any(
        profile.get(field) != approved.get(field) for field in _RETIRED_INHERITED_FIELDS
    ):
        raise ValueError("approved_candidate_lineage_required")
    if review.get("candidate_id") != "" or review.get("reviewed_at") != profile.get(
        "retired_at"
    ):
        raise ValueError("approved_candidate_lineage_required")


def _validated_active_predecessor(
    paths: OmhPaths,
    profile: dict[str, object],
    validate_profile: Callable[[OmhPaths, dict[str, object]], None],
) -> dict[str, object] | None:
    revision = profile.get("revision")
    base_revision = profile.get("base_profile_revision")
    if (
        not isinstance(revision, int)
        or isinstance(revision, bool)
        or base_revision != revision - 1
    ):
        raise ValueError("approved_candidate_lineage_required")
    if revision == 1:
        return None
    history = read_history_profiles(paths, [])
    approved = next(
        (
            item
            for item, _path in history
            if item.get("profile_id") == profile.get("profile_id")
            and item.get("revision") == base_revision
            and item.get("status") == "active"
        ),
        None,
    )
    if approved is None or any(
        approved.get(field) != profile.get(field) for field in _CHAIN_IDENTITY_FIELDS
    ):
        raise ValueError("approved_candidate_lineage_required")
    if approved.get("base_profile_revision") != base_revision - 1:
        raise ValueError("approved_candidate_lineage_required")
    try:
        validate_profile(paths, approved)
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError("approved_candidate_lineage_required") from exc
    return approved


def _read_approved_candidate(
    paths: OmhPaths,
    profile: dict[str, object],
    validate_candidate: Callable[[dict[str, object]], None],
) -> dict[str, object]:
    try:
        candidate = read_candidate_or_raise(paths, profile["candidate_id"])
        validate_candidate(candidate)
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError("approved_candidate_lineage_required") from exc
    if candidate.get("status") != "approved":
        raise ValueError("approved_candidate_lineage_required")
    return candidate


def _validate_active_lineage(
    profile: dict[str, object], review: dict[str, object], candidate: dict[str, object]
) -> None:
    if any(
        candidate.get(field) != profile.get(field) for field in _SHARED_APPROVAL_FIELDS
    ):
        raise ValueError("approved_candidate_lineage_required")
    expected = {
        "candidate_id": profile.get("candidate_id"),
        "profile_id": profile.get("profile_id"),
        "revision": profile.get("revision"),
        "review_id": review.get("review_id"),
        "reviewed_by": profile.get("approved_by"),
        "reviewed_at": review.get("reviewed_at"),
    }
    if any(candidate.get(key) != value for key, value in expected.items()):
        raise ValueError("approved_candidate_lineage_required")
    if review.get("decision") != "approved" or review.get(
        "reviewer_claim"
    ) != candidate.get("reviewed_by"):
        raise ValueError("approved_candidate_lineage_required")
    if profile.get("approved_at") != review.get("reviewed_at"):
        raise ValueError("approved_candidate_lineage_required")
