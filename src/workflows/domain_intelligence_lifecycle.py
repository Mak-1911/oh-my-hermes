from __future__ import annotations

import os

from ..paths import OmhPaths
from ..system.local_store import utc_now
from .domain_intelligence_artifacts import review_record_for_profile
from .domain_intelligence_contracts import (
    CLAIM_BOUNDARY,
    DOMAIN_CANDIDATE_SCHEMA_VERSION,
    DOMAIN_REVIEW_RECORD_SCHEMA_VERSION,
    REDUCTION_POLICY,
    canonical_profile_digest,
    ensure_no_forbidden_keys,
    normalize_confidence,
    normalize_identifier,
    normalize_mappings,
    normalize_provenance,
    normalize_reason_code,
    normalize_safe_ref,
    normalize_scope,
    normalize_workflow_hints,
    stable_profile_id,
)
from .domain_intelligence_store import (
    archive_profile,
    domain_store_lock,
    read_candidate_or_raise,
    read_profile,
    write_candidate,
    write_profile,
    write_review,
)
from .domain_intelligence_operations import (
    approval_operation_exists,
    build_approval_operation,
    delete_approval_operation,
    finalize_legacy_approval,
    load_approval_operation,
    validate_approval_resume_state,
    write_approval_operation,
    write_archive_idempotent,
    write_candidate_resumable,
    write_profile_resumable,
    write_review_idempotent,
)
from .domain_intelligence_validation import (
    current_profile_for_authority,
    current_profile_revision,
    ensure_candidate_pending,
    validate_profile_artifact,
)


def capture_domain_candidate(
    paths: OmhPaths,
    *,
    scope_kind: str,
    scope_ref: str,
    domain_id: str,
    mappings: list[tuple[str, str]],
    workflow_hints: list[str] | None = None,
    source_class: str = "operator_supplied",
    source_ref: str = "",
    observation_count: int = 1,
    confidence: float = 0.5,
) -> dict[str, object]:
    ensure_no_forbidden_keys(locals())
    scope = normalize_scope(scope_kind, scope_ref)
    normalized_domain = normalize_identifier(domain_id, "domain_id")
    normalized_mappings = normalize_mappings(mappings)
    normalized_hints = normalize_workflow_hints(workflow_hints or [])
    provenance = normalize_provenance(source_class, source_ref, observation_count)
    confidence_metadata = normalize_confidence(confidence, observation_count)
    created_at = utc_now()
    profile_id = stable_profile_id(scope, normalized_domain)
    candidate_id = "dicand_" + os.urandom(8).hex()
    with domain_store_lock(paths):
        candidate = {
            "schema_version": DOMAIN_CANDIDATE_SCHEMA_VERSION,
            "candidate_id": candidate_id,
            "status": "pending_review",
            "profile_id": profile_id,
            "scope": scope,
            "domain_id": normalized_domain,
            "vocabulary_mappings": normalized_mappings,
            "workflow_hints": normalized_hints,
            "confidence": confidence_metadata,
            "provenance": provenance,
            "base_profile_revision": current_profile_revision(paths, profile_id),
            "created_at": created_at,
            "updated_at": created_at,
            "redaction_policy": REDUCTION_POLICY,
            "claim_boundary": CLAIM_BOUNDARY,
        }
        write_candidate(paths, candidate_id, candidate)
    return {"schema_version": "domain_intelligence_capture/v1", "candidate": candidate, "claim_boundary": CLAIM_BOUNDARY}


def approve_domain_candidate(paths: OmhPaths, candidate_id: str, *, approved_by: str = "operator") -> dict[str, object]:
    reviewer_claim = normalize_safe_ref(approved_by, "reviewer_claim")
    with domain_store_lock(paths):
        operation = load_approval_operation(paths, candidate_id)
        if operation is None:
            candidate = read_candidate_or_raise(paths, candidate_id)
            ensure_candidate_pending(candidate)
            observed_current = read_profile(paths, str(candidate["profile_id"]))
            legacy = finalize_legacy_approval(
                paths,
                candidate,
                observed_current,
                reviewer_claim=reviewer_claim,
            )
            if legacy is not None:
                return {
                    "schema_version": DOMAIN_REVIEW_RECORD_SCHEMA_VERSION,
                    "decision": "approved",
                    **legacy,
                    "claim_boundary": CLAIM_BOUNDARY,
                }
            current = current_profile_for_authority(paths, str(candidate["profile_id"]))
            current_revision = int(current.get("revision", 0)) if current else 0
            if int(candidate.get("base_profile_revision", -1)) != current_revision:
                raise ValueError("stale_candidate")
            operation = build_approval_operation(candidate, current, reviewer_claim=reviewer_claim)
            write_approval_operation(paths, operation)
        elif operation["target_profile"].get("approved_by") != reviewer_claim:
            raise ValueError("approval_operation_reviewer_mismatch")
        validate_approval_resume_state(paths, operation)
        write_archive_idempotent(paths, operation)
        write_review_idempotent(paths, operation)
        write_profile_resumable(paths, operation)
        write_candidate_resumable(paths, operation)
        profile = operation["target_profile"]
        review = operation["target_review"]
        decided = operation["target_candidate"]
        delete_approval_operation(paths, candidate_id)
    return {
        "schema_version": DOMAIN_REVIEW_RECORD_SCHEMA_VERSION,
        "decision": "approved",
        "candidate": decided,
        "profile": profile,
        "review": review,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def reject_domain_candidate(
    paths: OmhPaths,
    candidate_id: str,
    *,
    rejected_by: str = "operator",
    reason: str = "",
) -> dict[str, object]:
    reviewer_claim = normalize_safe_ref(rejected_by, "reviewer_claim")
    reason_code = normalize_reason_code(reason)
    with domain_store_lock(paths):
        candidate = read_candidate_or_raise(paths, candidate_id)
        ensure_candidate_pending(candidate)
        if approval_operation_exists(paths, candidate_id):
            raise ValueError("approval_in_progress")
        current = current_profile_for_authority(paths, str(candidate["profile_id"]))
        if current is not None and current.get("candidate_id") == candidate_id:
            raise ValueError("candidate_already_approved")
        now = utc_now()
        review_id = f"direview_{candidate_id}"
        review = {
            "schema_version": DOMAIN_REVIEW_RECORD_SCHEMA_VERSION,
            "review_id": review_id,
            "candidate_id": candidate_id,
            "profile_id": str(candidate.get("profile_id", "")),
            "revision": None,
            "decision": "rejected",
            "reviewer_claim": reviewer_claim,
            "reason_code": reason_code,
            "reviewed_at": now,
            "claim_boundary": CLAIM_BOUNDARY,
        }
        decided = {
            **candidate,
            "status": "rejected",
            "reviewed_at": now,
            "reviewed_by": reviewer_claim,
            "review_id": review_id,
            "rejection_reason_code": reason_code,
            "updated_at": now,
        }
        write_review(paths, review_id, review)
        write_candidate(paths, candidate_id, decided)
    return {
        "schema_version": DOMAIN_REVIEW_RECORD_SCHEMA_VERSION,
        "decision": "rejected",
        "candidate": decided,
        "review": review,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def retire_domain_profile(
    paths: OmhPaths,
    *,
    scope_kind: str,
    scope_ref: str,
    domain_id: str,
    retired_by: str = "operator",
    reason: str = "",
) -> dict[str, object]:
    reviewer_claim = normalize_safe_ref(retired_by, "reviewer_claim")
    reason_code = normalize_reason_code(reason)
    scope = normalize_scope(scope_kind, scope_ref)
    normalized_domain = normalize_identifier(domain_id, "domain_id")
    profile_id = stable_profile_id(scope, normalized_domain)
    with domain_store_lock(paths):
        current = read_profile(paths, profile_id)
        if current is None:
            raise FileNotFoundError(profile_id)
        validate_profile_artifact(paths, current)
        if current.get("status") == "retired":
            raise ValueError("already_retired")
        archive_profile(paths, current)
        now = utc_now()
        retired = {
            **current,
            "revision": int(current.get("revision", 0)) + 1,
            "status": "retired",
            "base_profile_revision": int(current.get("revision", 0)),
            "updated_at": now,
            "retired_at": now,
            "retired_by": reviewer_claim,
            "retirement_reason_code": reason_code,
        }
        retired["payload_digest"] = canonical_profile_digest(retired)
        review = review_record_for_profile(
            None,
            retired,
            reviewer_claim=reviewer_claim,
            decision="retired",
            reason=reason_code,
        )
        write_review(paths, str(review["review_id"]), review)
        write_profile(paths, profile_id, retired)
    return {
        "schema_version": DOMAIN_REVIEW_RECORD_SCHEMA_VERSION,
        "decision": "retired",
        "profile": retired,
        "review": review,
        "claim_boundary": CLAIM_BOUNDARY,
    }
