from __future__ import annotations

import errno
import hashlib
import os
from pathlib import Path
import re
import stat

from ..paths import OmhPaths, find_project_root, project_identity
from ..system.local_store import utc_now
from .domain_intelligence_contracts import (
    CLAIM_BOUNDARY,
    DOMAIN_CANDIDATE_SCHEMA_VERSION,
    REDUCTION_POLICY,
    normalize_confidence,
    normalize_identifier,
    normalize_mappings,
    normalize_provenance,
    normalize_scope,
    normalize_workflow_hints,
    stable_profile_id,
)
from .domain_intelligence_store import (
    MAX_DOMAIN_CANDIDATE_FILES,
    bounded_json_paths,
    candidate_path,
    domain_store_lock,
    ensure_candidate_capacity,
    write_candidate,
)
from .domain_intelligence_validation import (
    current_profile_revision,
    validate_candidate_artifact,
)
from .project_terms import (
    MAX_PROJECT_TERMS_SOURCE_BYTES,
    ProjectTermsCaptureInput,
    build_project_terms_capture_inputs,
    parse_project_terms,
)


_CAPTURE_SCHEMA_VERSION = "project_terms_capture/v1"
_SOURCE_NAME = "PROJECT_TERMS.md"
_NOFOLLOW_FLAG = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY_FLAG = getattr(os, "O_DIRECTORY", 0)
_CLOEXEC_FLAG = getattr(os, "O_CLOEXEC", 0)
_PROJECT_TERMS_SOURCE_REF = re.compile(r"^pt_sha256:([0-9a-f]{64})$")


def capture_project_terms_file(
    paths: OmhPaths,
    *,
    from_file: str,
    stage: bool = False,
    invocation_cwd: str | Path | None = None,
) -> dict[str, object]:
    """Preview or atomically stage repository-root project terms."""
    root = _canonical_repository_root(invocation_cwd)
    source = _read_repository_project_terms(root, from_file)
    document = parse_project_terms(source)
    inputs = build_project_terms_capture_inputs(document)
    scope = normalize_scope("project", project_identity(root))
    domains = _preview_domains(paths, scope, inputs)
    available = _candidate_capacity_available(paths)
    required = len(inputs)
    payload: dict[str, object] = {
        "schema_version": _CAPTURE_SCHEMA_VERSION,
        "state": "prepared_not_observed",
        "reason": "preview_ready",
        "source_path": _SOURCE_NAME,
        "source_sha256": document.source_sha256,
        "scope": scope,
        "domains": domains,
        "capacity": {"available": available, "required": required},
        "mutation_set": [],
        "claim_boundary": CLAIM_BOUNDARY,
    }
    if not stage:
        return payload

    candidates = _stage_candidates(paths, scope, inputs)
    candidate_ids = [str(candidate["candidate_id"]) for candidate in candidates]
    payload.update(
        {
            "reason": "pending_review_staged",
            "domains": [
                {
                    **domain,
                    "base_profile_revision": candidate["base_profile_revision"],
                }
                for domain, candidate in zip(domains, candidates, strict=True)
            ],
            "candidate_ids": candidate_ids,
            "mutation_set": candidate_ids,
        }
    )
    return payload


def project_terms_source_freshness(
    artifact: dict[str, object],
    *,
    invocation_cwd: str | Path | None = None,
) -> dict[str, object]:
    """Derive closed, read-only source freshness for one candidate or profile."""
    root = _canonical_repository_root(invocation_cwd)
    provenance = artifact.get("provenance")
    scope = artifact.get("scope")
    source_ref = provenance.get("source_ref") if isinstance(provenance, dict) else None
    source_class = provenance.get("source_class") if isinstance(provenance, dict) else None
    digest_match = (
        _PROJECT_TERMS_SOURCE_REF.fullmatch(source_ref)
        if isinstance(source_ref, str)
        else None
    )
    tracked = (
        source_class == "omh_local"
        and digest_match is not None
        and isinstance(scope, dict)
        and scope.get("kind") == "project"
        and scope.get("ref") == project_identity(root)
    )
    if not tracked:
        return _freshness_payload(
            state="untracked",
            current_sha256=None,
            candidate_sha256=None,
            reason="not_project_terms_source",
        )

    candidate_sha256 = digest_match.group(1)
    try:
        source = _read_repository_project_terms(root, _SOURCE_NAME)
    except ValueError as exc:
        if str(exc) != "project_terms_source_not_found":
            raise
        return _freshness_payload(
            state="missing",
            current_sha256=None,
            candidate_sha256=candidate_sha256,
            reason="source_file_missing",
        )
    current_sha256 = hashlib.sha256(source).hexdigest()
    if current_sha256 == candidate_sha256:
        return _freshness_payload(
            state="unchanged",
            current_sha256=current_sha256,
            candidate_sha256=candidate_sha256,
            reason="source_matches_candidate",
        )
    return _freshness_payload(
        state="changed",
        current_sha256=current_sha256,
        candidate_sha256=candidate_sha256,
        reason="source_digest_changed",
    )


def _freshness_payload(
    *,
    state: str,
    current_sha256: str | None,
    candidate_sha256: str | None,
    reason: str,
) -> dict[str, object]:
    return {
        "state": state,
        "checked_source_path": _SOURCE_NAME,
        "current_source_sha256": current_sha256,
        "candidate_source_sha256": candidate_sha256,
        "reason": reason,
    }


def _canonical_repository_root(invocation_cwd: str | Path | None) -> Path:
    root = find_project_root(invocation_cwd)
    if root is None:
        raise ValueError("project_terms_repository_root_required")
    canonical = root.resolve(strict=True)
    if canonical != root:
        raise ValueError("project_terms_repository_root_not_canonical")
    return canonical


def _read_repository_project_terms(root: Path, from_file: str) -> bytes:
    if from_file != _SOURCE_NAME:
        raise ValueError("project_terms_source_must_be_repository_root_PROJECT_TERMS.md")
    if not _NOFOLLOW_FLAG or not _DIRECTORY_FLAG:
        raise ValueError("project_terms_safe_source_open_unavailable")
    root_fd = os.open(
        root,
        os.O_RDONLY | _DIRECTORY_FLAG | _CLOEXEC_FLAG | _NOFOLLOW_FLAG,
    )
    try:
        try:
            source_fd = os.open(
                _SOURCE_NAME,
                os.O_RDONLY | _CLOEXEC_FLAG | _NOFOLLOW_FLAG,
                dir_fd=root_fd,
            )
        except FileNotFoundError as exc:
            raise ValueError("project_terms_source_not_found") from exc
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.EMLINK}:
                raise ValueError("project_terms_source_must_not_be_symlink") from exc
            raise
        try:
            source_stat = os.fstat(source_fd)
            if not stat.S_ISREG(source_stat.st_mode):
                raise ValueError("project_terms_source_must_be_regular_file")
            if source_stat.st_size > MAX_PROJECT_TERMS_SOURCE_BYTES:
                raise ValueError("project_terms_source_too_large")
            chunks: list[bytes] = []
            remaining = MAX_PROJECT_TERMS_SOURCE_BYTES + 1
            while remaining:
                chunk = os.read(source_fd, min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            source = b"".join(chunks)
            if len(source) > MAX_PROJECT_TERMS_SOURCE_BYTES:
                raise ValueError("project_terms_source_too_large")
            return source
        finally:
            os.close(source_fd)
    finally:
        os.close(root_fd)


def _preview_domains(
    paths: OmhPaths,
    scope: dict[str, object],
    inputs: tuple[ProjectTermsCaptureInput, ...],
) -> list[dict[str, object]]:
    store_root = paths.memory_dir / "domain-intelligence"
    store_is_readable_without_creation = all(
        (store_root / name).is_dir() for name in ("profiles", "reviews", "history")
    )
    domains: list[dict[str, object]] = []
    for capture_input in inputs:
        domain_id = normalize_identifier(capture_input.domain_id, "domain_id")
        profile_id = stable_profile_id(scope, domain_id)
        revision = (
            current_profile_revision(paths, profile_id)
            if store_is_readable_without_creation
            else 0
        )
        domains.append(
            {
                "domain_id": domain_id,
                "profile_id": profile_id,
                "vocabulary_mappings": normalize_mappings(list(capture_input.mappings)),
                "workflow_hints": normalize_workflow_hints(list(capture_input.workflow_hints)),
                "base_profile_revision": revision,
            }
        )
    return domains


def _candidate_capacity_available(paths: OmhPaths) -> int:
    directory = paths.memory_dir / "domain-intelligence" / "candidates"
    if not directory.exists():
        return MAX_DOMAIN_CANDIDATE_FILES
    existing, overflow = bounded_json_paths(
        directory,
        limit=MAX_DOMAIN_CANDIDATE_FILES,
    )
    if overflow:
        return 0
    return max(MAX_DOMAIN_CANDIDATE_FILES - len(existing), 0)


def _stage_candidates(
    paths: OmhPaths,
    scope: dict[str, object],
    inputs: tuple[ProjectTermsCaptureInput, ...],
) -> list[dict[str, object]]:
    # Validate the complete batch before acquiring the mutation lock.
    prepared = [_normalized_capture_input(capture_input) for capture_input in inputs]
    if _candidate_capacity_available(paths) < len(prepared):
        raise ValueError("candidate_capacity_exceeded")

    created_at = utc_now()
    with domain_store_lock(paths):
        ensure_candidate_capacity(paths, required=len(prepared))
        candidates: list[dict[str, object]] = []
        reserved_ids: set[str] = set()
        for capture_input in prepared:
            profile_id = stable_profile_id(scope, capture_input.domain_id)
            candidate_id = _new_candidate_id(paths, reserved_ids)
            reserved_ids.add(candidate_id)
            candidate = {
                "schema_version": DOMAIN_CANDIDATE_SCHEMA_VERSION,
                "candidate_id": candidate_id,
                "status": "pending_review",
                "profile_id": profile_id,
                "scope": scope,
                "domain_id": capture_input.domain_id,
                "vocabulary_mappings": normalize_mappings(list(capture_input.mappings)),
                "workflow_hints": normalize_workflow_hints(list(capture_input.workflow_hints)),
                "confidence": normalize_confidence(0.5, 1),
                "provenance": normalize_provenance(
                    capture_input.source_class,
                    capture_input.source_ref,
                    1,
                ),
                "base_profile_revision": current_profile_revision(paths, profile_id),
                "created_at": created_at,
                "updated_at": created_at,
                "redaction_policy": REDUCTION_POLICY,
                "claim_boundary": CLAIM_BOUNDARY,
            }
            validate_candidate_artifact(candidate)
            candidates.append(candidate)
        _write_candidate_batch(paths, candidates)
        return candidates


def _normalized_capture_input(capture_input: ProjectTermsCaptureInput) -> ProjectTermsCaptureInput:
    mappings = normalize_mappings(list(capture_input.mappings))
    hints = normalize_workflow_hints(list(capture_input.workflow_hints))
    normalize_provenance(capture_input.source_class, capture_input.source_ref, 1)
    return ProjectTermsCaptureInput(
        domain_id=normalize_identifier(capture_input.domain_id, "domain_id"),
        mappings=tuple((str(item["phrase"]), str(item["canonical"])) for item in mappings),
        workflow_hints=tuple(hints),
        source_class="omh_local",
        source_ref=capture_input.source_ref,
    )


def _new_candidate_id(paths: OmhPaths, reserved: set[str]) -> str:
    for _attempt in range(16):
        candidate_id = "dicand_" + os.urandom(8).hex()
        if candidate_id in reserved:
            continue
        if not candidate_path(paths, candidate_id).exists():
            return candidate_id
    raise ValueError("candidate_id_generation_exhausted")


def _write_candidate_batch(paths: OmhPaths, candidates: list[dict[str, object]]) -> None:
    written: list[Path] = []
    try:
        for candidate in candidates:
            candidate_id = str(candidate["candidate_id"])
            write_candidate(paths, candidate_id, candidate)
            written.append(candidate_path(paths, candidate_id))
    except Exception:
        cleanup_failed = False
        for path in reversed(written):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                cleanup_failed = True
        if cleanup_failed:
            raise ValueError("candidate_batch_atomic_rollback_failed")
        raise
