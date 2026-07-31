from __future__ import annotations

import hashlib
import json

from ..paths import OmhPaths
from ..system.local_store import atomic_write_json
from . import domain_intelligence_store as store
from . import domain_intelligence_store_security as store_security
from .domain_intelligence_artifacts import profile_from_candidate, review_record_for_profile
from .domain_intelligence_contracts import (
    CLAIM_BOUNDARY,
    DEFAULT_REVIEW_REASON_CODE,
    DOMAIN_PROFILE_SCHEMA_VERSION,
    DOMAIN_REVIEW_RECORD_SCHEMA_VERSION,
    SAFE_CANDIDATE_ID,
    canonical_profile_digest,
    ensure_no_forbidden_keys,
)
from .domain_intelligence_schema import PROFILE_REVIEW_KEYS, validate_profile_contract, validate_review_contract
from .domain_intelligence_validation import validate_candidate_artifact, validate_profile_artifact


APPROVAL_OPERATION_SCHEMA_VERSION = "domain_intelligence_approval_operation/v1"
_OPERATION_KEYS = frozenset(
    "schema_version operation_id candidate_id profile_id base_profile_revision target_revision "
    "pending_candidate prior_profile target_review target_profile target_candidate claim_boundary operation_digest".split()
)
_TARGET_PROFILE_KEYS = frozenset(
    "schema_version profile_id revision status scope domain_id vocabulary_mappings workflow_hints confidence provenance "
    "base_profile_revision candidate_id approved_by approved_at created_at updated_at redaction_policy claim_boundary payload_digest".split()
)
_TARGET_REVIEW_KEYS = frozenset(
    "schema_version review_id candidate_id profile_id revision decision reviewer_claim payload_digest reviewed_at reason_code claim_boundary".split()
)
_APPROVAL_SHARED_FIELDS = tuple(
    "profile_id scope domain_id vocabulary_mappings workflow_hints confidence provenance "
    "base_profile_revision redaction_policy claim_boundary".split()
)


def build_approval_operation(candidate: dict[str, object], current: dict[str, object] | None, *, reviewer_claim: str) -> dict[str, object]:
    profile = profile_from_candidate(candidate, current=current, reviewer_claim=reviewer_claim)
    review = review_record_for_profile(candidate, profile, reviewer_claim=reviewer_claim, decision="approved")
    target_candidate = {
        **candidate,
        "status": "approved",
        "reviewed_at": str(review["reviewed_at"]),
        "reviewed_by": reviewer_claim,
        "review_id": str(review["review_id"]),
        "revision": profile["revision"],
        "updated_at": str(review["reviewed_at"]),
    }
    operation = {
        "schema_version": APPROVAL_OPERATION_SCHEMA_VERSION,
        "operation_id": f"approve_{candidate['candidate_id']}",
        "candidate_id": candidate["candidate_id"],
        "profile_id": candidate["profile_id"],
        "base_profile_revision": candidate["base_profile_revision"],
        "target_revision": profile["revision"],
        "pending_candidate": candidate,
        "prior_profile": current,
        "target_review": review,
        "target_profile": profile,
        "target_candidate": target_candidate,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    operation["operation_digest"] = _operation_digest(operation)
    validate_approval_operation(None, operation)
    return operation


def load_approval_operation(paths: OmhPaths, candidate_id: str) -> dict[str, object] | None:
    operation = store_security.read_bounded_json(_operation_path(paths, candidate_id))
    if operation is not None:
        validate_approval_operation(paths, operation)
    return operation


def approval_operation_exists(paths: OmhPaths, candidate_id: str) -> bool:
    return load_approval_operation(paths, candidate_id) is not None


def finalize_legacy_approval(
    paths: OmhPaths, candidate: dict[str, object], current: dict[str, object] | None, *, reviewer_claim: str
) -> dict[str, object] | None:
    if current is None or current.get("candidate_id") != candidate.get("candidate_id"):
        return None
    validate_profile_contract(current)
    review_id = f"direview_{current['profile_id']}_r{current['revision']}"
    review, error = store.read_review(paths, review_id)
    if error or review is None:
        raise ValueError("matching_review_required")
    validate_review_contract(review, PROFILE_REVIEW_KEYS)
    revision = current.get("revision")
    digest = canonical_profile_digest(current)
    exact_profile = all(current.get(field) == candidate.get(field) for field in _APPROVAL_SHARED_FIELDS)
    review_fields = (
        "review_id", "candidate_id", "profile_id", "revision", "decision", "reviewer_claim", "payload_digest", "reason_code", "reviewed_at"
    )
    expected_review = (review_id, candidate.get("candidate_id"), candidate.get("profile_id"), revision, "approved", reviewer_claim, digest, DEFAULT_REVIEW_REASON_CODE, current.get("approved_at"))
    actual_review = tuple(review.get(key) for key in review_fields)
    if not exact_profile or current.get("status") != "active" or current.get("payload_digest") != digest:
        raise ValueError("candidate_already_approved_conflict")
    if revision != candidate.get("base_profile_revision", -1) + 1 or current.get("approved_by") != reviewer_claim:
        raise ValueError("candidate_already_approved_conflict")
    if actual_review != expected_review:
        raise ValueError("candidate_already_approved_conflict")
    decided = {
        **candidate,
        "status": "approved",
        "reviewed_at": str(review["reviewed_at"]),
        "reviewed_by": str(review["reviewer_claim"]),
        "review_id": review_id,
        "revision": current["revision"],
        "updated_at": str(review["reviewed_at"]),
    }
    store.write_candidate(paths, str(candidate["candidate_id"]), decided)
    return {"candidate": decided, "profile": current, "review": review}


def write_approval_operation(paths: OmhPaths, operation: dict[str, object]) -> None:
    validate_approval_operation(paths, operation)
    path = _operation_path(paths, str(operation["candidate_id"]))
    existing = store_security.read_bounded_json(path)
    if existing is not None:
        validate_approval_operation(paths, existing)
        if existing != operation:
            raise ValueError("approval_operation_conflict")
        return
    atomic_write_json(path, operation, private=True)


def validate_approval_resume_state(paths: OmhPaths, operation: dict[str, object]) -> None:
    validate_approval_operation(paths, operation)
    prior = operation["prior_profile"]
    target_profile = operation["target_profile"]
    current = store.read_profile(paths, str(operation["profile_id"]))
    if current not in (prior, target_profile):
        raise ValueError("approval_profile_state_conflict")
    candidate = store.read_candidate_or_raise(paths, str(operation["candidate_id"]))
    if candidate not in (operation["pending_candidate"], operation["target_candidate"]):
        raise ValueError("approval_candidate_state_conflict")
    if prior is not None:
        _require_absent_or_exact(
            store.history_path(paths, str(operation["profile_id"]), int(operation["base_profile_revision"])), prior, "history"
        )
    _require_absent_or_exact(store.review_path(paths, str(operation["target_review"]["review_id"])), operation["target_review"], "review")


def write_archive_idempotent(paths: OmhPaths, operation: dict[str, object]) -> None:
    prior = operation["prior_profile"]
    if prior is None:
        return
    path = store.history_path(paths, str(operation["profile_id"]), int(operation["base_profile_revision"]))
    _write_absent_or_exact(path, prior, "history")


def write_review_idempotent(paths: OmhPaths, operation: dict[str, object]) -> None:
    review = operation["target_review"]
    _write_absent_or_exact(store.review_path(paths, str(review["review_id"])), review, "review")


def write_profile_resumable(paths: OmhPaths, operation: dict[str, object]) -> None:
    path = store.profile_path(paths, str(operation["profile_id"]))
    current = store_security.read_bounded_json(path)
    if current == operation["target_profile"]:
        return
    if current != operation["prior_profile"]:
        raise ValueError("approval_profile_state_conflict")
    atomic_write_json(path, operation["target_profile"], private=True)


def write_candidate_resumable(paths: OmhPaths, operation: dict[str, object]) -> None:
    path = store.candidate_path(paths, str(operation["candidate_id"]))
    current = store_security.read_bounded_json(path)
    if current == operation["target_candidate"]:
        return
    if current != operation["pending_candidate"]:
        raise ValueError("approval_candidate_state_conflict")
    atomic_write_json(path, operation["target_candidate"], private=True)


def delete_approval_operation(paths: OmhPaths, candidate_id: str) -> None:
    path = _operation_path(paths, candidate_id)
    existing = store_security.read_bounded_json(path)
    if existing is None:
        return
    validate_approval_operation(paths, existing)
    path.unlink()


def validate_approval_operation(paths: OmhPaths | None, operation: dict[str, object]) -> None:
    ensure_no_forbidden_keys(operation)
    _validate_bounds(operation)
    if set(operation) != _OPERATION_KEYS or operation.get("schema_version") != APPROVAL_OPERATION_SCHEMA_VERSION:
        raise ValueError("approval_operation_schema_mismatch")
    candidate_id = operation.get("candidate_id")
    if not isinstance(candidate_id, str) or not SAFE_CANDIDATE_ID.fullmatch(candidate_id):
        raise ValueError("unsafe_candidate_id")
    if operation.get("operation_id") != f"approve_{candidate_id}":
        raise ValueError("approval_operation_identity_mismatch")
    if operation.get("operation_digest") != _operation_digest(operation):
        raise ValueError("approval_operation_digest_mismatch")
    pending = operation.get("pending_candidate")
    target_candidate = operation.get("target_candidate")
    profile = operation.get("target_profile")
    review = operation.get("target_review")
    if not all(isinstance(item, dict) for item in (pending, target_candidate, profile, review)):
        raise ValueError("approval_operation_artifact_type")
    validate_candidate_artifact(pending)
    validate_candidate_artifact(target_candidate)
    if pending.get("status") != "pending_review" or target_candidate.get("status") != "approved":
        raise ValueError("approval_operation_candidate_state")
    profile_id = pending.get("profile_id")
    revision = profile.get("revision")
    if operation.get("profile_id") != profile_id or profile.get("profile_id") != profile_id:
        raise ValueError("approval_operation_profile_identity")
    if operation.get("base_profile_revision") != pending.get("base_profile_revision"):
        raise ValueError("approval_operation_base_revision")
    if operation.get("target_revision") != revision or target_candidate.get("revision") != revision:
        raise ValueError("approval_operation_target_revision")
    if set(profile) != _TARGET_PROFILE_KEYS or profile.get("schema_version") != DOMAIN_PROFILE_SCHEMA_VERSION:
        raise ValueError("approval_operation_profile_schema")
    if profile.get("status") != "active" or profile.get("candidate_id") != candidate_id:
        raise ValueError("approval_operation_profile_target")
    digest = canonical_profile_digest(profile)
    if profile.get("payload_digest") != digest:
        raise ValueError("approval_operation_profile_digest")
    if set(review) != _TARGET_REVIEW_KEYS or review.get("schema_version") != DOMAIN_REVIEW_RECORD_SCHEMA_VERSION:
        raise ValueError("approval_operation_review_schema")
    if review.get("decision") != "approved" or review.get("payload_digest") != digest:
        raise ValueError("approval_operation_review_digest")
    if review.get("review_id") != target_candidate.get("review_id") or review.get("candidate_id") != candidate_id:
        raise ValueError("approval_operation_review_identity")
    if review.get("profile_id") != profile_id or review.get("revision") != revision:
        raise ValueError("approval_operation_review_target")
    if review.get("reviewer_claim") != profile.get("approved_by") or review.get("reason_code") != DEFAULT_REVIEW_REASON_CODE:
        raise ValueError("approval_operation_review_authority")
    prior = operation.get("prior_profile")
    if prior is not None:
        if not isinstance(prior, dict) or prior.get("profile_id") != profile_id:
            raise ValueError("approval_operation_prior_profile")
        if prior.get("revision") != operation.get("base_profile_revision"):
            raise ValueError("approval_operation_prior_revision")
        if paths is not None:
            validate_profile_artifact(paths, prior)


def _operation_path(paths: OmhPaths, candidate_id: str):
    if not SAFE_CANDIDATE_ID.fullmatch(candidate_id):
        raise ValueError("unsafe_candidate_id")
    return store_security.secure_artifact_path(store_security.secure_managed_dir(paths, "operations"), f"approve_{candidate_id}.json")


def _operation_digest(operation: dict[str, object]) -> str:
    payload = {key: value for key, value in operation.items() if key != "operation_digest"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_absent_or_exact(path, target: dict[str, object], kind: str) -> None:
    existing = store_security.read_bounded_json(path)
    if existing is not None and existing != target:
        raise ValueError(f"approval_{kind}_state_conflict")


def _write_absent_or_exact(path, target: dict[str, object], kind: str) -> None:
    _require_absent_or_exact(path, target, kind)
    if store_security.read_bounded_json(path) is None:
        atomic_write_json(path, target, private=True)


def _validate_bounds(value: object) -> None:
    if len(json.dumps(value, sort_keys=True).encode("utf-8")) > store_security.MAX_DOMAIN_ARTIFACT_BYTES:
        raise ValueError("approval_operation_too_large")
    nodes = 0
    stack = [(value, 0)]
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > store_security.MAX_DOMAIN_JSON_NODES or depth > store_security.MAX_DOMAIN_JSON_DEPTH:
            raise ValueError("approval_operation_json_bounds")
        if isinstance(current, dict):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
