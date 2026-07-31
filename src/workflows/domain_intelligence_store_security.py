from __future__ import annotations

import errno
import json
import os
from contextlib import contextmanager
from json import JSONDecodeError
from pathlib import Path
import stat
import time
from typing import Iterator

from ..paths import OmhPaths
from ..system.local_store import FileLockTimeout, ensure_dir

try:
    import fcntl
except ImportError:
    fcntl = None


_NOFOLLOW_FLAG = getattr(os, "O_NOFOLLOW", 0)

# These bounds keep local reviewed metadata cheap to inspect and diagnose.
MAX_DOMAIN_ARTIFACT_BYTES = 256 * 1024
MAX_DOMAIN_CANDIDATE_FILES = 256
MAX_DOMAIN_ARTIFACT_FILES = 1024
MAX_DOMAIN_JSON_DEPTH = 32
MAX_DOMAIN_JSON_NODES = 4096
MAX_DOMAIN_DIAGNOSTICS = 64


def ensure_new_artifact_capacity(
    directory: Path,
    target: Path,
    *,
    limit: int,
    reason: str,
) -> None:
    if not target.exists() and sum(1 for _ in directory.glob("*.json")) >= limit:
        raise ValueError(reason)


def secure_domain_root(paths: OmhPaths, *, create: bool = False) -> Path:
    home = paths.omh_home
    memory = paths.memory_dir
    if memory.is_symlink():
        raise ValueError("domain-intelligence memory storage must not be a symlink")
    resolved_home = home.resolve(strict=False)
    resolved_memory = memory.resolve(strict=False)
    if not resolved_memory.is_relative_to(resolved_home):
        raise ValueError(
            "domain-intelligence memory storage must resolve under OMH home"
        )
    root = memory / "domain-intelligence"
    if root.is_symlink():
        raise ValueError("domain-intelligence storage must not be a symlink")
    resolved_root = root.resolve(strict=False)
    if resolved_root.parent != resolved_memory or not resolved_root.is_relative_to(
        resolved_home
    ):
        raise ValueError("domain-intelligence storage must resolve under OMH home")
    if create:
        ensure_dir(root, private=True)
    return root


def secure_managed_dir(paths: OmhPaths, name: str, *, create: bool = True) -> Path:
    root = secure_domain_root(paths, create=create)
    directory = root / name
    if directory.is_symlink():
        raise ValueError(f"domain-intelligence {name} storage must not be a symlink")
    resolved_root = root.resolve(strict=False)
    resolved_directory = directory.resolve(strict=False)
    if resolved_directory.parent != resolved_root:
        raise ValueError(
            f"domain-intelligence {name} storage must resolve under domain root"
        )
    if create:
        ensure_dir(directory, private=True)
    return directory


def secure_artifact_path(directory: Path, filename: str) -> Path:
    path = directory / filename
    if path.is_symlink():
        raise ValueError("domain-intelligence artifact path must not be a symlink")
    if path.resolve(strict=False).parent != directory.resolve(strict=False):
        raise ValueError(
            "domain-intelligence artifact path must resolve under managed storage"
        )
    if path.exists() and not path.is_file():
        raise ValueError("domain-intelligence artifact path must be a regular file")
    return path


def secure_store_lock_target(paths: OmhPaths) -> Path:
    root = secure_domain_root(paths, create=True)
    target = secure_artifact_path(root, "store")
    lock_path = root / ".store.lock"
    if lock_path.is_symlink():
        raise ValueError("domain-intelligence lock path must not be a symlink")
    if lock_path.resolve(strict=False).parent != root.resolve(strict=False):
        raise ValueError("domain-intelligence lock path must resolve under domain root")
    if lock_path.exists() and not lock_path.is_file():
        raise ValueError("domain-intelligence lock path must be a regular file")
    return target


@contextmanager
def domain_store_lock(
    paths: OmhPaths,
    *,
    timeout_seconds: float = 10.0,
    poll_interval: float = 0.05,
) -> Iterator[dict[str, object]]:
    target = secure_store_lock_target(paths)
    lock_path = target.with_name(f".{target.name}.lock")
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_CLOEXEC", 0)
    if not _NOFOLLOW_FLAG:
        raise ValueError("domain-intelligence safe lock requires O_NOFOLLOW")
    try:
        descriptor = os.open(lock_path, flags | _NOFOLLOW_FLAG, 0o600)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.EMLINK}:
            raise ValueError(
                "domain-intelligence lock path must not be a symlink"
            ) from exc
        raise
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("domain-intelligence lock path must be a regular file")
        os.fchmod(descriptor, 0o600)
        if fcntl is None:
            yield {"locked": False, "reason": "fcntl_unavailable"}
            return
        deadline = time.monotonic() + max(timeout_seconds, 0.0)
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                if time.monotonic() >= deadline:
                    raise FileLockTimeout(
                        f"could not acquire lock on {target} within {timeout_seconds}s"
                    ) from exc
                time.sleep(poll_interval)
        try:
            yield {"locked": True, "reason": ""}
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def read_bounded_json(path: Path) -> dict[str, object] | None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if not _NOFOLLOW_FLAG:
        raise ValueError("domain-intelligence safe reads require O_NOFOLLOW")
    try:
        descriptor = os.open(path, flags | _NOFOLLOW_FLAG)
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.EMLINK}:
            raise ValueError("artifact_symlink") from exc
        raise
    try:
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise ValueError("symlink_or_not_file")
        if file_stat.st_size > MAX_DOMAIN_ARTIFACT_BYTES:
            raise ValueError("artifact_too_large")
        raw = _read_limited(descriptor)
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


def _read_limited(descriptor: int) -> bytes:
    remaining = MAX_DOMAIN_ARTIFACT_BYTES + 1
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
    stack: list[tuple[object, int]] = [(value, 0)]
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
