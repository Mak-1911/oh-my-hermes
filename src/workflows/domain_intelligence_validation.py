from __future__ import annotations

from ..paths import OmhPaths
from .domain_intelligence_contracts import (
    DEFAULT_REVIEW_REASON_CODE,
    SAFE_CANDIDATE_ID,
    SAFE_PROFILE_ID,
    SHA256,
    canonical_profile_digest,
    ensure_no_forbidden_keys,
    normalize_base_profile_revision,
    normalize_confidence_from_value,
    normalize_identifier,
    normalize_mappings_from_value,
    normalize_provenance_from_value,
    normalize_reason_code,
    normalize_safe_ref,
    normalize_scope_from_value,
    normalize_workflow_hints,
    stable_profile_id,
)
from .domain_intelligence_lineage import validate_profile_candidate_lineage
from .domain_intelligence_schema import (
    PROFILE_REVIEW_KEYS,
    REJECTED_REVIEW_KEYS,
    validate_candidate_contract,
    validate_profile_contract,
    validate_review_contract,
)
from .domain_intelligence_store import read_profile, read_review


def ensure_candidate_pending(candidate: dict[str, object]) -> None:
    validate_candidate_artifact(candidate)
    if candidate.get("status") != "pending_review":
        raise ValueError("candidate_not_pending_review")


def validate_candidate_artifact(candidate: dict[str, object]) -> None:
    ensure_no_forbidden_keys(candidate)
    status = validate_candidate_contract(candidate)
    candidate_id = candidate.get("candidate_id")
    if not isinstance(candidate_id, str) or not SAFE_CANDIDATE_ID.fullmatch(candidate_id):
        raise ValueError("unsafe_candidate_id")
    scope = normalize_scope_from_value(candidate.get("scope"))
    domain_id = normalize_identifier(candidate.get("domain_id"), "domain_id")
    if candidate.get("domain_id") != domain_id:
        raise ValueError("candidate_domain_id_not_canonical")
    if candidate.get("scope") != scope:
        raise ValueError("candidate_scope_not_normalized")
    if candidate.get("profile_id") != stable_profile_id(scope, domain_id):
        raise ValueError("candidate_profile_identity_mismatch")
    if candidate.get("vocabulary_mappings") != normalize_mappings_from_value(candidate.get("vocabulary_mappings")):
        raise ValueError("candidate_mappings_not_canonical")
    if candidate.get("workflow_hints") != normalize_workflow_hints(candidate.get("workflow_hints")):
        raise ValueError("candidate_workflow_hints_not_canonical")
    confidence = _canonical_confidence(candidate.get("confidence"))
    provenance = _canonical_provenance(candidate.get("provenance"))
    if confidence["observation_count"] != provenance["observation_count"]:
        raise ValueError("observation_count_mismatch")
    normalize_base_profile_revision(candidate.get("base_profile_revision"))
    if status == "approved":
        revision = candidate.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ValueError("invalid_revision")
        if candidate.get("review_id") != f"direview_{candidate['profile_id']}_r{revision}":
            raise ValueError("candidate_review_identity_mismatch")
        _canonical_reviewer_claim(candidate.get("reviewed_by"))
    elif status == "rejected":
        if candidate.get("review_id") != f"direview_{candidate_id}":
            raise ValueError("candidate_review_identity_mismatch")
        _canonical_reviewer_claim(candidate.get("reviewed_by"))
        _canonical_reason_code(candidate.get("rejection_reason_code"))


def validate_profile_artifact(paths: OmhPaths, profile: dict[str, object]) -> None:
    ensure_no_forbidden_keys(profile)
    status = validate_profile_contract(profile)
    revision = profile.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ValueError("invalid_revision")
    scope = normalize_scope_from_value(profile.get("scope"))
    domain_id = normalize_identifier(profile.get("domain_id"), "domain_id")
    if profile.get("domain_id") != domain_id:
        raise ValueError("profile_domain_id_not_canonical")
    profile_id = profile.get("profile_id")
    if not isinstance(profile_id, str) or not SAFE_PROFILE_ID.fullmatch(profile_id):
        raise ValueError("unsafe_profile_id")
    if profile_id != stable_profile_id(scope, domain_id):
        raise ValueError("profile_identity_mismatch")
    if profile.get("scope") != scope:
        raise ValueError("scope_not_normalized")
    if profile.get("vocabulary_mappings") != normalize_mappings_from_value(profile.get("vocabulary_mappings")):
        raise ValueError("profile_mappings_not_canonical")
    if profile.get("workflow_hints") != normalize_workflow_hints(profile.get("workflow_hints")):
        raise ValueError("profile_workflow_hints_not_canonical")
    confidence = _canonical_confidence(profile.get("confidence"))
    provenance = _canonical_provenance(profile.get("provenance"))
    if confidence["observation_count"] != provenance["observation_count"]:
        raise ValueError("observation_count_mismatch")
    normalize_base_profile_revision(profile.get("base_profile_revision"))
    candidate_id = profile.get("candidate_id")
    if not isinstance(candidate_id, str) or not SAFE_CANDIDATE_ID.fullmatch(candidate_id):
        raise ValueError("unsafe_candidate_id")
    _canonical_reviewer_claim(profile.get("approved_by"))
    digest = canonical_profile_digest(profile)
    if profile.get("payload_digest") != digest:
        raise ValueError("payload_digest_mismatch")
    reviewer = profile.get("approved_by")
    reason = DEFAULT_REVIEW_REASON_CODE
    review_candidate_id = candidate_id
    decision = "approved"
    if status == "retired":
        reviewer = _canonical_reviewer_claim(profile.get("retired_by"))
        reason = _canonical_reason_code(profile.get("retirement_reason_code"))
        review_candidate_id = ""
        decision = "retired"
    review = _matching_review(paths, profile_id, revision, decision, digest, reviewer, reason, review_candidate_id)
    if not review:
        raise ValueError("matching_review_required")
    validate_profile_candidate_lineage(
        paths,
        profile,
        review,
        validate_candidate=validate_candidate_artifact,
        validate_profile=validate_profile_artifact,
    )


def current_profile_for_authority(paths: OmhPaths, profile_id: str) -> dict[str, object] | None:
    profile = read_profile(paths, profile_id)
    if profile:
        validate_profile_artifact(paths, profile)
    return profile


def current_profile_revision(paths: OmhPaths, profile_id: str) -> int:
    profile = current_profile_for_authority(paths, profile_id)
    return int(profile["revision"]) if profile else 0


def validate_review_artifact_for_status(
    review: dict[str, object], *, candidates: list[dict[str, object]], profiles: list[dict[str, object]]
) -> None:
    ensure_no_forbidden_keys(review)
    decision = review.get("decision")
    if decision in {"approved", "retired"}:
        validate_review_contract(review, PROFILE_REVIEW_KEYS)
        profile_id = review.get("profile_id")
        revision = review.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ValueError("invalid_review_revision")
        if not isinstance(profile_id, str) or not SAFE_PROFILE_ID.fullmatch(profile_id):
            raise ValueError("unsafe_review_profile_id")
        matched = next((p for p in profiles if p.get("profile_id") == profile_id and p.get("revision") == revision), None)
        if not matched or matched.get("status") != ("active" if decision == "approved" else "retired"):
            raise ValueError("orphan_review")
        expected_candidate = matched.get("candidate_id") if decision == "approved" else ""
        expected_reviewer = matched.get("approved_by") if decision == "approved" else matched.get("retired_by")
        expected_reason = DEFAULT_REVIEW_REASON_CODE if decision == "approved" else matched.get("retirement_reason_code")
        _validate_profile_review(review, profile_id, revision, decision, matched.get("payload_digest"), expected_reviewer, expected_reason, expected_candidate)
        return
    if decision != "rejected":
        raise ValueError("invalid_review_decision")
    validate_review_contract(review, REJECTED_REVIEW_KEYS)
    candidate_id = review.get("candidate_id")
    if not isinstance(candidate_id, str) or not SAFE_CANDIDATE_ID.fullmatch(candidate_id):
        raise ValueError("unsafe_review_candidate_id")
    matched = next((c for c in candidates if c.get("candidate_id") == candidate_id and c.get("status") == "rejected"), None)
    if not matched:
        raise ValueError("orphan_review")
    if review.get("review_id") != matched.get("review_id") or review.get("profile_id") != matched.get("profile_id"):
        raise ValueError("review_identity_mismatch")
    if review.get("revision") is not None:
        raise ValueError("invalid_review_revision")
    if review.get("reviewer_claim") != matched.get("reviewed_by"):
        raise ValueError("review_reviewer_mismatch")
    if review.get("reason_code") != matched.get("rejection_reason_code"):
        raise ValueError("review_reason_mismatch")
    if review.get("reviewed_at") != matched.get("reviewed_at"):
        raise ValueError("review_timestamp_mismatch")
    _canonical_reviewer_claim(review.get("reviewer_claim"))
    _canonical_reason_code(review.get("reason_code"))


def _matching_review(paths: OmhPaths, profile_id: str, revision: int, decision: str, digest: str, reviewer: object, reason: object, candidate_id: object) -> dict[str, object] | None:
    review, error = read_review(paths, f"direview_{profile_id}_r{revision}")
    if error or not review:
        return None
    try:
        _validate_profile_review(review, profile_id, revision, decision, digest, reviewer, reason, candidate_id)
    except ValueError:
        return None
    return review


def _validate_profile_review(review: dict[str, object], profile_id: str, revision: int, decision: str, digest: object, reviewer: object, reason: object, candidate_id: object) -> None:
    ensure_no_forbidden_keys(review)
    validate_review_contract(review, PROFILE_REVIEW_KEYS)
    if review.get("review_id") != f"direview_{profile_id}_r{revision}" or review.get("profile_id") != profile_id:
        raise ValueError("review_identity_mismatch")
    review_revision = review.get("revision")
    if isinstance(review_revision, bool) or review_revision != revision:
        raise ValueError("invalid_review_revision")
    if review.get("decision") != decision or review.get("candidate_id") != candidate_id:
        raise ValueError("review_decision_or_candidate_mismatch")
    review_digest = review.get("payload_digest")
    if not isinstance(review_digest, str) or not SHA256.fullmatch(review_digest):
        raise ValueError("invalid_review_digest")
    if review_digest != digest:
        raise ValueError("review_digest_mismatch")
    if _canonical_reviewer_claim(review.get("reviewer_claim")) != reviewer:
        raise ValueError("review_reviewer_mismatch")
    if _canonical_reason_code(review.get("reason_code")) != reason:
        raise ValueError("review_reason_mismatch")
def _canonical_reviewer_claim(value: object) -> str:
    normalized = normalize_safe_ref(value, "reviewer_claim")
    if value != normalized:
        raise ValueError("reviewer_claim_not_canonical")
    return normalized


def _canonical_reason_code(value: object) -> str:
    normalized = normalize_reason_code(value)
    if value != normalized:
        raise ValueError("review_reason_not_canonical")
    return normalized


def _canonical_confidence(value: object) -> dict[str, object]:
    normalized = normalize_confidence_from_value(value)
    if value != normalized:
        raise ValueError("confidence_not_canonical")
    return normalized


def _canonical_provenance(value: object) -> dict[str, object]:
    normalized = normalize_provenance_from_value(value)
    if value != normalized:
        raise ValueError("provenance_not_canonical")
    return normalized
