from __future__ import annotations

from collections import Counter
from pathlib import Path

from ..paths import OmhPaths
from ..system.local_store import atomic_write_json
from .domain_intelligence_contracts import (
    DOMAIN_REVIEW_RECORD_SCHEMA_VERSION,
    SAFE_REF,
    SHA256,
    ensure_no_forbidden_keys,
)
from .domain_intelligence_store_security import (
    MAX_DOMAIN_ARTIFACT_BYTES,
    MAX_DOMAIN_ARTIFACT_FILES,
    MAX_DOMAIN_DIAGNOSTICS,
    MAX_DOMAIN_JSON_DEPTH,
    MAX_DOMAIN_JSON_NODES,
    domain_store_lock,
    read_bounded_json,
    secure_artifact_path,
    secure_domain_root,
    secure_managed_dir,
    secure_store_lock_target,
)

__all__ = (
    "MAX_DOMAIN_ARTIFACT_BYTES",
    "MAX_DOMAIN_ARTIFACT_FILES",
    "MAX_DOMAIN_JSON_DEPTH",
    "MAX_DOMAIN_JSON_NODES",
    "domain_store_lock",
    "read_history_profiles",
)


def read_candidate_or_raise(paths: OmhPaths, candidate_id: str) -> dict[str, object]:
    if not SAFE_REF.match(candidate_id):
        raise ValueError("unsafe_candidate_id")
    candidate = read_bounded_json(candidate_path(paths, candidate_id))
    if not candidate:
        raise FileNotFoundError(candidate_id)
    if candidate.get("candidate_id") != candidate_id:
        raise ValueError("candidate_identity_mismatch")
    return candidate


def read_profile(paths: OmhPaths, profile_id: str) -> dict[str, object] | None:
    if not SAFE_REF.match(profile_id):
        raise ValueError("unsafe_profile_id")
    profile = read_bounded_json(profile_path(paths, profile_id))
    if profile and profile.get("profile_id") != profile_id:
        raise ValueError("profile_identity_mismatch")
    return profile


def read_review(paths: OmhPaths, review_id: str) -> tuple[dict[str, object] | None, str | None]:
    try:
        review = read_bounded_json(review_path(paths, review_id))
        if review and review.get("review_id") != review_id:
            raise ValueError("review_identity_mismatch")
        return review, None
    except (OSError, ValueError) as exc:
        return None, str(exc)


def archive_profile(paths: OmhPaths, profile: dict[str, object]) -> None:
    profile_id = str(profile.get("profile_id", ""))
    revision = int(profile.get("revision", 0))
    if not SAFE_REF.match(profile_id) or revision < 1:
        raise ValueError("invalid_profile_history_identity")
    atomic_write_json(history_path(paths, profile_id, revision), profile, private=True)


def write_candidate(paths: OmhPaths, candidate_id: str, candidate: dict[str, object]) -> None:
    atomic_write_json(candidate_path(paths, candidate_id), candidate, private=True)


def write_profile(paths: OmhPaths, profile_id: str, profile: dict[str, object]) -> None:
    atomic_write_json(profile_path(paths, profile_id), profile, private=True)


def write_review(paths: OmhPaths, review_id: str, review: dict[str, object]) -> None:
    atomic_write_json(review_path(paths, review_id), review, private=True)


def read_candidates(paths: OmhPaths, diagnostics: list[dict[str, str]]) -> list[tuple[dict[str, object], Path]]:
    return _read_artifacts(candidates_dir(paths), diagnostics, "candidate_id")


def read_profiles(paths: OmhPaths, diagnostics: list[dict[str, str]]) -> list[tuple[dict[str, object], Path]]:
    return _read_artifacts(profiles_dir(paths), diagnostics, "profile_id")


def read_reviews(paths: OmhPaths, diagnostics: list[dict[str, str]]) -> list[tuple[dict[str, object], Path]]:
    return _read_artifacts(reviews_dir(paths), diagnostics, "review_id")


def read_history_profiles(
    paths: OmhPaths,
    diagnostics: list[dict[str, str]],
) -> list[tuple[dict[str, object], Path]]:
    directory = history_dir(paths)
    paths_on_disk = sorted(directory.glob("*.json"))
    if len(paths_on_disk) > MAX_DOMAIN_ARTIFACT_FILES:
        _append_diagnostic(diagnostics, directory, "artifact_file_count_exceeded")
        return []
    parsed: list[tuple[dict[str, object], Path, tuple[str, int]]] = []
    for path in paths_on_disk:
        try:
            secure_artifact_path(directory, path.name)
            data = read_bounded_json(path)
        except (OSError, ValueError) as exc:
            _append_diagnostic(diagnostics, path, str(exc))
            continue
        if data is None:
            _append_diagnostic(diagnostics, path, "malformed_json")
            continue
        try:
            ensure_no_forbidden_keys(data)
        except ValueError as exc:
            _append_diagnostic(diagnostics, path, str(exc))
            continue
        profile_id = data.get("profile_id")
        revision = data.get("revision")
        valid_revision = isinstance(revision, int) and not isinstance(revision, bool) and revision > 0
        if not isinstance(profile_id, str) or not SAFE_REF.match(profile_id) or not valid_revision:
            _append_diagnostic(diagnostics, path, "artifact_identity_mismatch")
            continue
        parsed.append((data, path, (profile_id, revision)))
    duplicate_ids = {value for value, count in Counter(item[2] for item in parsed).items() if count > 1}
    records: list[tuple[dict[str, object], Path]] = []
    for data, path, identity in parsed:
        if identity in duplicate_ids:
            _append_diagnostic(diagnostics, path, "duplicate_embedded_id")
            continue
        profile_id, revision = identity
        if path.stem != f"{profile_id}_r{revision}":
            _append_diagnostic(diagnostics, path, "artifact_identity_mismatch")
            continue
        records.append((data, path))
    return records


def _read_artifacts(
    directory: Path,
    diagnostics: list[dict[str, str]],
    identity_field: str,
) -> list[tuple[dict[str, object], Path]]:
    if not directory.exists():
        return []
    paths = sorted(directory.glob("*.json"))
    if len(paths) > MAX_DOMAIN_ARTIFACT_FILES:
        _append_diagnostic(diagnostics, directory, "artifact_file_count_exceeded")
        return []
    parsed: list[tuple[dict[str, object], Path, str]] = []
    for path in paths:
        try:
            secure_artifact_path(directory, path.name)
            data = read_bounded_json(path)
        except (OSError, ValueError) as exc:
            _append_diagnostic(diagnostics, path, str(exc))
            continue
        if data is None:
            _append_diagnostic(diagnostics, path, "malformed_json")
            continue
        try:
            ensure_no_forbidden_keys(data)
        except ValueError as exc:
            _append_diagnostic(diagnostics, path, str(exc))
            continue
        embedded_id = data.get(identity_field)
        if not isinstance(embedded_id, str) or not SAFE_REF.match(embedded_id):
            _append_diagnostic(diagnostics, path, "artifact_identity_mismatch")
            continue
        parsed.append((data, path, embedded_id))
    duplicate_ids = {value for value, count in Counter(item[2] for item in parsed).items() if count > 1}
    records: list[tuple[dict[str, object], Path]] = []
    for data, path, embedded_id in parsed:
        conflicting = embedded_id in duplicate_ids
        if conflicting:
            _append_diagnostic(diagnostics, path, "duplicate_embedded_id")
        precedence_reason = _storage_precedence_reason(data, identity_field)
        if precedence_reason:
            _append_diagnostic(diagnostics, path, precedence_reason)
            continue
        if conflicting:
            continue
        if path.stem != embedded_id:
            _append_diagnostic(diagnostics, path, "artifact_identity_mismatch")
        else:
            records.append((data, path))
    return records


def _append_diagnostic(diagnostics: list[dict[str, str]], path: Path, reason: str) -> None:
    if len(diagnostics) < MAX_DOMAIN_DIAGNOSTICS:
        diagnostics.append(diagnostic(path, reason))


def _storage_precedence_reason(data: dict[str, object], identity_field: str) -> str:
    if identity_field != "review_id":
        return ""
    schema = data.get("schema_version")
    if schema is not None and schema != DOMAIN_REVIEW_RECORD_SCHEMA_VERSION:
        return "unsupported_review_schema"
    digest = data.get("payload_digest")
    if digest is not None and (not isinstance(digest, str) or not SHA256.match(digest)):
        return "invalid_review_digest"
    return ""


def diagnostic(path: Path, reason: str) -> dict[str, str]:
    return {"path_name": path.name, "reason": reason}


def domain_root(paths: OmhPaths) -> Path:
    return secure_domain_root(paths)


def store_lock_target(paths: OmhPaths) -> Path:
    return secure_store_lock_target(paths)


def candidates_dir(paths: OmhPaths) -> Path:
    return secure_managed_dir(paths, "candidates")


def profiles_dir(paths: OmhPaths) -> Path:
    return secure_managed_dir(paths, "profiles")


def reviews_dir(paths: OmhPaths) -> Path:
    return secure_managed_dir(paths, "reviews")


def history_dir(paths: OmhPaths) -> Path:
    return secure_managed_dir(paths, "history")


def candidate_path(paths: OmhPaths, candidate_id: str) -> Path:
    if not SAFE_REF.match(candidate_id):
        raise ValueError("unsafe_candidate_id")
    return secure_artifact_path(candidates_dir(paths), f"{candidate_id}.json")


def profile_path(paths: OmhPaths, profile_id: str) -> Path:
    if not SAFE_REF.match(profile_id):
        raise ValueError("unsafe_profile_id")
    return secure_artifact_path(profiles_dir(paths), f"{profile_id}.json")


def review_path(paths: OmhPaths, review_id: str) -> Path:
    if not SAFE_REF.match(review_id):
        raise ValueError("unsafe_review_id")
    return secure_artifact_path(reviews_dir(paths), f"{review_id}.json")


def history_path(paths: OmhPaths, profile_id: str, revision: int) -> Path:
    if not SAFE_REF.match(profile_id) or revision < 1:
        raise ValueError("unsafe_history_id")
    return secure_artifact_path(history_dir(paths), f"{profile_id}_r{revision}.json")
