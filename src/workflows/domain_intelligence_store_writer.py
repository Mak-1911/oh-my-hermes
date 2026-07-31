from __future__ import annotations

import errno
import json
import os
from pathlib import Path
import secrets
import stat

from ..paths import OmhPaths


_NOFOLLOW_FLAG = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY_FLAG = getattr(os, "O_DIRECTORY", 0)
_CLOEXEC_FLAG = getattr(os, "O_CLOEXEC", 0)
_MANAGED_DIRECTORIES = frozenset(
    {"candidates", "history", "operations", "profiles", "reviews"}
)


def atomic_write_managed_json(
    paths: OmhPaths,
    managed_name: str,
    filename: str,
    data: dict[str, object],
) -> None:
    """Atomically write private JSON below one dirfd-anchored managed directory."""
    if managed_name not in _MANAGED_DIRECTORIES:
        raise ValueError("unsafe_domain_managed_directory")
    if Path(filename).name != filename or not filename.endswith(".json"):
        raise ValueError("unsafe_domain_artifact_filename")
    directory_fd = _open_managed_directory(paths, managed_name)
    temporary_name = f".{filename}.{os.getpid()}-{secrets.token_hex(8)}.tmp"
    temporary_created = False
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _CLOEXEC_FLAG | _NOFOLLOW_FLAG
        temporary_fd = os.open(temporary_name, flags, 0o600, dir_fd=directory_fd)
        temporary_created = True
        try:
            if not stat.S_ISREG(os.fstat(temporary_fd).st_mode):
                raise ValueError("domain-intelligence temporary path must be regular")
            os.fchmod(temporary_fd, 0o600)
            _write_all(
                temporary_fd,
                (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            )
            os.fsync(temporary_fd)
        finally:
            os.close(temporary_fd)
        os.replace(
            temporary_name,
            filename,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        temporary_created = False
        os.fsync(directory_fd)
    except (TypeError, NotImplementedError) as exc:
        raise ValueError(
            "domain-intelligence safe managed writes are unavailable"
        ) from exc
    finally:
        if temporary_created:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
        os.close(directory_fd)


def _open_managed_directory(paths: OmhPaths, managed_name: str) -> int:
    if not _NOFOLLOW_FLAG or not _DIRECTORY_FLAG:
        raise ValueError("domain-intelligence safe managed writes are unavailable")
    home = Path(os.path.abspath(paths.omh_home))
    parts = (home.name, "memory", "domain-intelligence", managed_name)
    flags = os.O_RDONLY | _DIRECTORY_FLAG | _CLOEXEC_FLAG | _NOFOLLOW_FLAG
    directory_fd = -1
    try:
        directory_fd = os.open(home.parent, flags)
        for index, part in enumerate(parts):
            try:
                next_directory_fd = os.open(part, flags, dir_fd=directory_fd)
            except FileNotFoundError:
                os.mkdir(part, 0o700, dir_fd=directory_fd)
                next_directory_fd = os.open(part, flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_directory_fd
            if index:
                os.fchmod(directory_fd, 0o700)
        return directory_fd
    except OSError as exc:
        if directory_fd >= 0:
            os.close(directory_fd)
        if exc.errno in {errno.ELOOP, errno.EMLINK, errno.ENOTDIR}:
            raise ValueError(
                "domain-intelligence managed storage cannot be safely opened"
            ) from exc
        raise


def _write_all(file_descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(file_descriptor, view)
        if written <= 0:
            raise OSError("domain-intelligence managed write made no progress")
        view = view[written:]
