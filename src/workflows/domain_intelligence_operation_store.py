from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
from pathlib import Path

from ..paths import OmhPaths
from . import domain_intelligence_store as store
from . import domain_intelligence_store_security as security
from .domain_intelligence_contracts import SAFE_REF, ensure_no_forbidden_keys


OperationValidator = Callable[[OmhPaths | None, dict[str, object]], None]


def seal_operation(operation: dict[str, object]) -> dict[str, object]:
    sealed = dict(operation)
    sealed["operation_digest"] = operation_digest(sealed)
    return sealed


def operation_digest(operation: dict[str, object]) -> str:
    payload = {key: value for key, value in operation.items() if key != "operation_digest"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_operation_envelope(operation: dict[str, object], *, operation_id: str) -> None:
    ensure_no_forbidden_keys(operation)
    _validate_bounds(operation)
    if operation.get("operation_id") != operation_id or not SAFE_REF.fullmatch(operation_id):
        raise ValueError("decision_operation_identity_mismatch")
    if operation.get("operation_digest") != operation_digest(operation):
        raise ValueError("decision_operation_digest_mismatch")


def load_operation(
    paths: OmhPaths,
    operation_id: str,
    validate: OperationValidator,
) -> dict[str, object] | None:
    operation = security.read_bounded_json(operation_path(paths, operation_id))
    if operation is not None:
        validate(paths, operation)
    return operation


def operation_exists(paths: OmhPaths, operation_id: str, validate: OperationValidator) -> bool:
    return load_operation(paths, operation_id, validate) is not None


def scan_operations(paths: OmhPaths) -> list[tuple[Path, dict[str, object]]]:
    directory = security.secure_managed_dir(paths, "operations")
    candidates, overflow = security.bounded_json_paths(
        directory, limit=security.MAX_DOMAIN_ARTIFACT_FILES
    )
    if overflow:
        raise ValueError("decision_operation_capacity_exceeded")
    records: list[tuple[Path, dict[str, object]]] = []
    for candidate in candidates:
        path = security.secure_artifact_path(directory, candidate.name)
        operation = security.read_bounded_json(path)
        if operation is None:
            raise ValueError("decision_operation_disappeared")
        records.append((path, operation))
    return records


def write_operation(paths: OmhPaths, operation: dict[str, object], validate: OperationValidator) -> None:
    validate(paths, operation)
    operation_id = str(operation["operation_id"])
    path = operation_path(paths, operation_id)
    existing = security.read_bounded_json(path)
    if existing is not None:
        validate(paths, existing)
        if existing != operation:
            raise ValueError("decision_operation_state_conflict")
        return
    security.ensure_new_artifact_capacity(
        path.parent,
        path,
        limit=security.MAX_DOMAIN_ARTIFACT_FILES,
        reason="decision_operation_capacity_exceeded",
    )
    _write_json(paths, path, operation)


def delete_operation(paths: OmhPaths, operation_id: str, validate: OperationValidator) -> None:
    path = operation_path(paths, operation_id)
    existing = security.read_bounded_json(path)
    if existing is None:
        return
    validate(paths, existing)
    path.unlink()


def require_absent_or_exact(path: Path, target: dict[str, object], *, label: str) -> None:
    existing = security.read_bounded_json(path)
    if existing is not None and existing != target:
        raise ValueError(f"{label}_state_conflict")


def write_absent_or_exact(
    paths: OmhPaths, path: Path, target: dict[str, object], *, label: str
) -> None:
    require_absent_or_exact(path, target, label=label)
    if security.read_bounded_json(path) is None:
        _write_json(paths, path, target)


def require_expected_or_target(
    path: Path,
    expected: dict[str, object] | None,
    target: dict[str, object],
    *,
    label: str,
) -> None:
    current = security.read_bounded_json(path)
    if current not in (expected, target):
        raise ValueError(f"{label}_state_conflict")


def write_expected_or_target(
    paths: OmhPaths,
    path: Path,
    expected: dict[str, object] | None,
    target: dict[str, object],
    *,
    label: str,
) -> None:
    current = security.read_bounded_json(path)
    if current == target:
        return
    if current != expected:
        raise ValueError(f"{label}_state_conflict")
    _write_json(paths, path, target)


def operation_path(paths: OmhPaths, operation_id: str) -> Path:
    if not SAFE_REF.fullmatch(operation_id):
        raise ValueError("unsafe_operation_id")
    directory = security.secure_managed_dir(paths, "operations")
    return security.secure_artifact_path(directory, f"{operation_id}.json")


def _write_json(paths: OmhPaths, path: Path, value: dict[str, object]) -> None:
    store.atomic_write_managed_json(paths, path.parent.name, path.name, value)


def _validate_bounds(value: object) -> None:
    if len(json.dumps(value, sort_keys=True).encode("utf-8")) > security.MAX_DOMAIN_ARTIFACT_BYTES:
        raise ValueError("decision_operation_too_large")
    nodes = 0
    stack = [(value, 0)]
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > security.MAX_DOMAIN_JSON_NODES or depth > security.MAX_DOMAIN_JSON_DEPTH:
            raise ValueError("decision_operation_json_bounds")
        if isinstance(current, dict):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
