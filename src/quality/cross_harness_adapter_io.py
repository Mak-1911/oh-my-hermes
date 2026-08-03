from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
from tempfile import mkstemp

from .cross_harness_benchmark_values import JsonValue


@dataclass(frozen=True, slots=True)
class InventoryEntry:
    path: str
    sha256: str


class UnsafeRegularFileError(OSError):
    pass


def read_regular_file(path: Path) -> tuple[bytes, os.stat_result]:
    directory_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    directory = os.open("/", directory_flags)
    try:
        for part in path.absolute().parts[1:-1]:
            child = os.open(part, directory_flags, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(
            path.name,
            os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory,
        )
    except OSError as error:
        if error.errno == getattr(os, "ELOOP", 62):
            raise UnsafeRegularFileError from None
        raise
    finally:
        os.close(directory)
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise UnsafeRegularFileError
        return stream.read(), metadata


def inventory(root: Path, excluded: set[str]) -> tuple[InventoryEntry, ...]:
    entries: list[InventoryEntry] = []
    for directory, names, files in os.walk(root, followlinks=False):
        names.sort()
        files.sort()
        base = Path(directory)
        if any((base / name).is_symlink() for name in names):
            raise UnsafeRegularFileError
        for name in files:
            path = base / name
            relative = path.relative_to(root).as_posix()
            if relative in excluded:
                continue
            if path.is_symlink():
                raise UnsafeRegularFileError
            entries.append(InventoryEntry(relative, hashlib.sha256(read_regular_file(path)[0]).hexdigest()))
    return tuple(entries)


def write_json(path: Path, payload: Mapping[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    descriptor, temporary = mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        stream = os.fdopen(descriptor, "wb")
        descriptor = -1
        with stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        Path(temporary).unlink(missing_ok=True)
