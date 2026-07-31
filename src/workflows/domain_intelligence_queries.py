from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
import errno
import json
from json import JSONDecodeError
import os
from pathlib import Path
import stat

from ..paths import OmhPaths
from .domain_intelligence_artifacts import candidate_card, profile_projection
from .domain_intelligence_contracts import (
    CLAIM_BOUNDARY,
    DOMAIN_LIST_SCHEMA_VERSION,
    DOMAIN_REVIEW_QUEUE_SCHEMA_VERSION,
    DOMAIN_STATUS_SCHEMA_VERSION,
    SAFE_CANDIDATE_ID,
    SAFE_PROFILE_ID,
    ensure_no_forbidden_keys,
    normalize_identifier,
    normalize_scope,
)
from .domain_intelligence_store import (
    diagnostic,
    domain_root,
    read_candidates,
    read_history_profiles,
    read_profiles,
    read_reviews,
    store_lock_target,
)
from .domain_intelligence_review_validation import validate_review_artifact_for_status
from .domain_intelligence_lineage import ProfileValidationContext
from .domain_intelligence_review_validation import (
    canonical_reason_code,
    canonical_reviewer_claim,
)
from .domain_intelligence_schema import (
    REJECTED_REVIEW_KEYS,
    validate_review_contract,
)
from .domain_intelligence_store_security import (
    MAX_DOMAIN_ARTIFACT_BYTES,
    MAX_DOMAIN_ARTIFACT_FILES,
    MAX_DOMAIN_JSON_DEPTH,
    MAX_DOMAIN_JSON_NODES,
)
from .domain_intelligence_validation import (
    build_profile_validation_context,
    validate_candidate_artifact,
    validate_profile_artifact,
    validate_profile_artifact_for_resolution,
)


_HEALTH_DIRECTORIES = ("profiles", "reviews", "history")
_NOFOLLOW_FLAG = getattr(os, "O_NOFOLLOW", 0)
_CLOEXEC_FLAG = getattr(os, "O_CLOEXEC", 0)


@dataclass(frozen=True)
class _DirectorySnapshot:
    identity: tuple[int, int, int, int, int]
    manifest: tuple[tuple[str, int, int, int, int, int, int], ...]


def read_validated_domain_profiles_at(binding: object) -> tuple[dict[str, object], ...]:
    """Read one complete, stable, descriptor-bound profile health universe."""
    from .domain_project_context import HostProjectBinding

    if not isinstance(binding, HostProjectBinding):
        raise ValueError("host_project_binding_required")
    with binding.shared_store_lock(), ExitStack() as stack:
        directories = {
            name: stack.enter_context(binding.open_directory(name))
            for name in _HEALTH_DIRECTORIES
        }
        before = {
            name: _snapshot_directory(descriptor)
            for name, descriptor in directories.items()
        }
        for name, descriptor in directories.items():
            _require_bound_directory(binding.domain_store_fd, name, descriptor)
        records = {
            name: tuple(
                (filename, _read_stable_json_at(directories[name], filename))
                for filename, *_rest in before[name].manifest
            )
            for name in _HEALTH_DIRECTORIES
        }
        profiles = _validate_resolution_records(binding, records)
        after = {
            name: _snapshot_directory(descriptor)
            for name, descriptor in directories.items()
        }
        for name, descriptor in directories.items():
            _require_bound_directory(binding.domain_store_fd, name, descriptor)
        if before != after:
            raise ValueError("domain_profile_snapshot_changed")
        return profiles


def _snapshot_directory(directory_fd: int) -> _DirectorySnapshot:
    directory_stat = os.fstat(directory_fd)
    if not stat.S_ISDIR(directory_stat.st_mode):
        raise ValueError("domain_health_directory_invalid")
    names = sorted(name for name in os.listdir(directory_fd) if name.endswith(".json"))
    if len(names) > MAX_DOMAIN_ARTIFACT_FILES:
        raise ValueError("artifact_file_count_exceeded")
    manifest: list[tuple[str, int, int, int, int, int, int]] = []
    for name in names:
        if Path(name).name != name:
            raise ValueError("artifact_path_escape")
        item = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(item.st_mode):
            raise ValueError("symlink_or_not_file")
        manifest.append((name, *_file_identity(item)))
    return _DirectorySnapshot(
        identity=_directory_identity(directory_stat),
        manifest=tuple(manifest),
    )


def _require_bound_directory(root_fd: int, name: str, directory_fd: int) -> None:
    bound = os.fstat(directory_fd)
    current = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
    if _directory_identity(bound) != _directory_identity(current):
        raise ValueError("domain_health_directory_changed")


def _read_stable_json_at(directory_fd: int, filename: str) -> dict[str, object]:
    if not _NOFOLLOW_FLAG:
        raise ValueError("domain-intelligence safe reads require O_NOFOLLOW")
    flags = os.O_RDONLY | _CLOEXEC_FLAG | _NOFOLLOW_FLAG
    try:
        descriptor = os.open(filename, flags, dir_fd=directory_fd)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.EMLINK}:
            raise ValueError("artifact_symlink") from exc
        raise
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("symlink_or_not_file")
        if before.st_size > MAX_DOMAIN_ARTIFACT_BYTES:
            raise ValueError("artifact_too_large")
        raw = _read_limited(descriptor, MAX_DOMAIN_ARTIFACT_BYTES)
        after = os.fstat(descriptor)
        if _file_identity(before) != _file_identity(after):
            raise ValueError("artifact_changed_during_read")
    finally:
        os.close(descriptor)
    if len(raw) > MAX_DOMAIN_ARTIFACT_BYTES:
        raise ValueError("artifact_too_large")
    try:
        value = json.loads(raw.decode("utf-8"))
    except RecursionError as exc:
        raise ValueError("artifact_json_depth_exceeded") from exc
    except (UnicodeDecodeError, JSONDecodeError) as exc:
        raise ValueError("malformed_json") from exc
    if not isinstance(value, dict):
        raise ValueError("malformed_json")
    _validate_json_bounds(value)
    return value


def _read_limited(descriptor: int, maximum: int) -> bytes:
    remaining = maximum + 1
    chunks: list[bytes] = []
    while remaining:
        chunk = os.read(descriptor, remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _validate_json_bounds(value: object) -> None:
    nodes = 0
    stack = [(value, 0)]
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_DOMAIN_JSON_NODES:
            raise ValueError("artifact_json_nodes_exceeded")
        if depth > MAX_DOMAIN_JSON_DEPTH:
            raise ValueError("artifact_json_depth_exceeded")
        if isinstance(current, dict):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)


def _validate_resolution_records(
    binding: object,
    records: dict[str, tuple[tuple[str, dict[str, object]], ...]],
) -> tuple[dict[str, object], ...]:
    profiles = _identity_records(records["profiles"], "profile_id")
    reviews = _identity_records(records["reviews"], "review_id")
    history = _history_records(records["history"])
    all_profiles = (*profiles, *history)
    profile_index = _unique_profile_index(all_profiles)
    review_index = {str(review["review_id"]): review for review in reviews}
    context = ProfileValidationContext(
        history={
            (str(profile["profile_id"]), int(profile["revision"])): profile
            for profile in history
        },
        candidates={},
        reviews=review_index,
    )
    paths = binding.project_paths
    for profile in all_profiles:
        validate_profile_artifact_for_resolution(paths, profile, context=context)
    for review in reviews:
        if review.get("decision") == "rejected":
            _validate_rejected_review_without_candidate(review)
        else:
            validate_review_artifact_for_status(
                review,
                candidates={},
                profiles=profile_index,
            )
    return tuple(profile for profile in profiles if profile.get("status") == "active")


def _identity_records(
    records: tuple[tuple[str, dict[str, object]], ...], identity_field: str
) -> tuple[dict[str, object], ...]:
    values: list[dict[str, object]] = []
    identities: set[str] = set()
    for filename, value in records:
        ensure_no_forbidden_keys(value)
        identity = value.get(identity_field)
        if (
            not isinstance(identity, str)
            or not identity
            or filename != f"{identity}.json"
        ):
            raise ValueError("artifact_identity_mismatch")
        if identity in identities:
            raise ValueError("duplicate_embedded_id")
        identities.add(identity)
        values.append(value)
    return tuple(values)


def _history_records(
    records: tuple[tuple[str, dict[str, object]], ...],
) -> tuple[dict[str, object], ...]:
    values: list[dict[str, object]] = []
    identities: set[tuple[str, int]] = set()
    for filename, value in records:
        ensure_no_forbidden_keys(value)
        profile_id = value.get("profile_id")
        revision = value.get("revision")
        if (
            not isinstance(profile_id, str)
            or not SAFE_PROFILE_ID.fullmatch(profile_id)
            or isinstance(revision, bool)
            or not isinstance(revision, int)
            or revision < 1
            or filename != f"{profile_id}_r{revision}.json"
        ):
            raise ValueError("artifact_identity_mismatch")
        identity = (profile_id, revision)
        if identity in identities:
            raise ValueError("duplicate_embedded_id")
        identities.add(identity)
        values.append(value)
    return tuple(values)


def _unique_profile_index(
    profiles: tuple[dict[str, object], ...],
) -> dict[tuple[str, int], dict[str, object]]:
    index: dict[tuple[str, int], dict[str, object]] = {}
    for profile in profiles:
        key = (str(profile.get("profile_id")), int(profile.get("revision", 0)))
        if key in index:
            raise ValueError("duplicate_embedded_id")
        index[key] = profile
    return index


def _validate_rejected_review_without_candidate(review: dict[str, object]) -> None:
    ensure_no_forbidden_keys(review)
    validate_review_contract(review, REJECTED_REVIEW_KEYS)
    candidate_id = review.get("candidate_id")
    profile_id = review.get("profile_id")
    if (
        not isinstance(candidate_id, str)
        or not SAFE_CANDIDATE_ID.fullmatch(candidate_id)
        or review.get("review_id") != f"direview_{candidate_id}"
        or not isinstance(profile_id, str)
        or not SAFE_PROFILE_ID.fullmatch(profile_id)
        or review.get("revision") is not None
    ):
        raise ValueError("review_identity_mismatch")
    canonical_reviewer_claim(review.get("reviewer_claim"))
    canonical_reason_code(review.get("reason_code"))


def _directory_identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _file_identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def build_domain_review(paths: OmhPaths, *, candidate_id: str | None = None, limit: int = 20) -> dict[str, object]:
    diagnostics: list[dict[str, str]] = []
    cards: list[dict[str, object]] = []
    for candidate, path in read_candidates(paths, diagnostics):
        try:
            validate_candidate_artifact(candidate)
        except ValueError as exc:
            diagnostics.append(diagnostic(path, str(exc)))
            continue
        if candidate_id and candidate.get("candidate_id") != candidate_id:
            continue
        if candidate.get("status") != "pending_review":
            continue
        cards.append(candidate_card(candidate))
        if len(cards) >= max(1, limit):
            break
    return {
        "schema_version": DOMAIN_REVIEW_QUEUE_SCHEMA_VERSION,
        "cards": cards,
        "counts": {"pending_review": len(cards), "malformed_artifacts": len(diagnostics)},
        "diagnostics": diagnostics[:20],
        "claim_boundary": CLAIM_BOUNDARY,
    }


def list_domain_profiles(
    paths: OmhPaths,
    *,
    scope_kind: str | None = None,
    scope_ref: str | None = None,
    domain_id: str | None = None,
    include_retired: bool = False,
) -> dict[str, object]:
    scope_filter = normalize_scope(scope_kind, scope_ref) if scope_kind or scope_ref else None
    domain_filter = normalize_identifier(domain_id, "domain_id") if domain_id else None
    diagnostics: list[dict[str, str]] = []
    profiles: list[dict[str, object]] = []
    context = build_profile_validation_context(paths)
    for profile, path in read_profiles(paths, diagnostics):
        try:
            validate_profile_artifact(paths, profile, context=context)
        except ValueError as exc:
            diagnostics.append(diagnostic(path, str(exc)))
            continue
        if profile.get("status") != "active" and not include_retired:
            continue
        if scope_filter and profile.get("scope") != scope_filter:
            continue
        if domain_filter and profile.get("domain_id") != domain_filter:
            continue
        profiles.append(profile_projection(profile))
    profiles.sort(key=lambda item: (str(item["scope"]["kind"]), str(item["scope"]["ref"]), str(item["domain_id"])))
    return {
        "schema_version": DOMAIN_LIST_SCHEMA_VERSION,
        "profiles": profiles,
        "counts": {"profiles": len(profiles), "malformed_artifacts": len(diagnostics)},
        "diagnostics": diagnostics[:20],
        "claim_boundary": CLAIM_BOUNDARY,
    }


def build_domain_status(paths: OmhPaths) -> dict[str, object]:
    diagnostics: list[dict[str, str]] = []
    candidates = read_candidates(paths, diagnostics)
    profiles = read_profiles(paths, diagnostics)
    reviews = read_reviews(paths, diagnostics)
    history = read_history_profiles(paths, diagnostics)
    context = build_profile_validation_context(
        paths,
        history=history,
        candidates=candidates,
        reviews=reviews,
    )
    active = 0
    retired = 0
    valid_profiles: list[dict[str, object]] = []
    for profile, path in profiles:
        try:
            validate_profile_artifact(paths, profile, context=context)
        except ValueError as exc:
            diagnostics.append(diagnostic(path, str(exc)))
            continue
        valid_profiles.append(profile)
        if profile.get("status") == "active":
            active += 1
        elif profile.get("status") == "retired":
            retired += 1
    for profile, path in history:
        try:
            validate_profile_artifact(paths, profile, context=context)
        except ValueError as exc:
            diagnostics.append(diagnostic(path, str(exc)))
            continue
        valid_profiles.append(profile)
    valid_candidates: list[dict[str, object]] = []
    for candidate, path in candidates:
        try:
            validate_candidate_artifact(candidate)
        except ValueError as exc:
            diagnostics.append(diagnostic(path, str(exc)))
            continue
        valid_candidates.append(candidate)
    pending = sum(1 for candidate in valid_candidates if candidate.get("status") == "pending_review")
    rejected = sum(1 for candidate in valid_candidates if candidate.get("status") == "rejected")
    approved = sum(1 for candidate in valid_candidates if candidate.get("status") == "approved")
    candidate_index = {
        str(candidate["candidate_id"]): candidate for candidate in valid_candidates
    }
    profile_index = {
        (str(profile["profile_id"]), int(profile["revision"])): profile
        for profile in valid_profiles
    }
    valid_reviews = 0
    for review, path in reviews:
        try:
            validate_review_artifact_for_status(
                review,
                candidates=candidate_index,
                profiles=profile_index,
            )
        except ValueError as exc:
            diagnostics.append(diagnostic(path, str(exc)))
            continue
        valid_reviews += 1
    lock_target = store_lock_target(paths)
    return {
        "schema_version": DOMAIN_STATUS_SCHEMA_VERSION,
        "store_root": str(domain_root(paths)),
        "lock_target": str(lock_target),
        "lock_file": str(lock_target.with_name(".store.lock")),
        "counts": {
            "candidates": len(valid_candidates),
            "pending_review": pending,
            "approved_candidates": approved,
            "rejected_candidates": rejected,
            "active_profiles": active,
            "retired_profiles": retired,
            "reviews": valid_reviews,
            "malformed_artifacts": len(diagnostics),
        },
        "diagnostics": diagnostics[:20],
        "claim_boundary": CLAIM_BOUNDARY,
    }
