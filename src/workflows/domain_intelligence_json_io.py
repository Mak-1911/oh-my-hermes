from __future__ import annotations

import errno
import json
from json import JSONDecodeError
import os
import stat

from .domain_intelligence_store_security import (
    MAX_DOMAIN_ARTIFACT_BYTES,
    MAX_DOMAIN_JSON_DEPTH,
    MAX_DOMAIN_JSON_NODES,
)


_NOFOLLOW_FLAG = getattr(os, "O_NOFOLLOW", 0)
_CLOEXEC_FLAG = getattr(os, "O_CLOEXEC", 0)


def read_stable_json_at(directory_fd: int, filename: str) -> dict[str, object]:
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
        if stable_file_identity(before) != stable_file_identity(after):
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


def stable_file_identity(
    value: os.stat_result,
) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )
