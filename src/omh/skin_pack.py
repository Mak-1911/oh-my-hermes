"""Managed OMH identity skin for Hermes.

Mirrors ``tui_widget_pack``: the skin is a managed artifact OMH installs into
``$HERMES_HOME/skins/`` and may safely refresh because a manifest proves OMH
wrote it. Hermes' own skin engine is the only consumer — a YAML dropped in
that directory themes the classic CLI, the Ink TUI, and the desktop GUI at
once, with no Hermes patching involved. A file at the destination without a
matching manifest is user-owned and never touched.
"""

from __future__ import annotations

import hashlib
from importlib import resources
import json
import os
from pathlib import Path
import secrets

SKIN_NAME = "omh"
SKIN_FILENAME = "omh.yaml"
MANIFEST_FILENAME = ".omh-skin.manifest.json"
_MANIFEST_SCHEMA = "omh_skin_manifest/v1"


class SkinInstallError(RuntimeError):
    """The managed Hermes skin destination is unsafe."""


def skin_payload() -> bytes:
    return resources.files("omh.skins").joinpath(SKIN_FILENAME).read_text(encoding="utf-8").encode()


def _reject_symlink_path(path: Path) -> None:
    current = path
    while True:
        if current.is_symlink():
            raise SkinInstallError(f"refusing symlinked skin path: {current}")
        if current == current.parent:
            return
        current = current.parent


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}-{secrets.token_hex(8)}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
        os.replace(temporary, path)
    finally:
        if temporary.exists() and not temporary.is_symlink():
            temporary.unlink()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_managed_skin(destination: Path, manifest: Path) -> bool:
    try:
        if manifest.is_symlink() or not manifest.is_file():
            return False
        record = json.loads(manifest.read_text(encoding="utf-8"))
        return (
            record.get("schema_version") == _MANIFEST_SCHEMA
            and record.get("filename") == SKIN_FILENAME
            and record.get("sha256") == _sha256(destination.read_bytes())
        )
    except (OSError, json.JSONDecodeError, AttributeError):
        return False


def install_skin(hermes_home: Path, *, dry_run: bool = False) -> dict[str, str]:
    destination_dir = hermes_home / "skins"
    destination = destination_dir / SKIN_FILENAME
    manifest = destination_dir / MANIFEST_FILENAME
    _reject_symlink_path(hermes_home)
    _reject_symlink_path(destination_dir)
    _reject_symlink_path(destination)
    if destination.exists() and not destination.is_file():
        raise SkinInstallError(f"skin destination is not a regular file: {destination}")
    payload = skin_payload()
    if destination.exists() and not _is_managed_skin(destination, manifest):
        # A user-authored omh.yaml wins over ours forever; identity is theirs
        # to override and update must not undo that.
        return {"status": "kept_unmanaged", "path": str(destination)}
    status = "unchanged" if destination.exists() and destination.read_bytes() == payload else "installed"
    if dry_run and status == "installed":
        status = "would_install"
    elif status == "installed":
        destination_dir.mkdir(parents=True, exist_ok=True)
        _reject_symlink_path(destination_dir)
        _atomic_write_bytes(destination, payload)
        _atomic_write_bytes(
            manifest,
            json.dumps(
                {
                    "schema_version": _MANIFEST_SCHEMA,
                    "filename": SKIN_FILENAME,
                    "sha256": _sha256(payload),
                },
                sort_keys=True,
            ).encode(),
        )
    return {"status": status, "path": str(destination), "skin": SKIN_NAME}


def uninstall_skin(hermes_home: Path, *, dry_run: bool = False) -> dict[str, str]:
    destination_dir = hermes_home / "skins"
    destination = destination_dir / SKIN_FILENAME
    manifest = destination_dir / MANIFEST_FILENAME
    _reject_symlink_path(destination_dir)
    _reject_symlink_path(destination)
    _reject_symlink_path(manifest)
    if not destination.exists() and not manifest.exists():
        return {"status": "absent", "path": str(destination)}
    if not _is_managed_skin(destination, manifest):
        return {"status": "kept_unmanaged", "path": str(destination)}
    if not dry_run:
        destination.unlink()
        manifest.unlink()
    return {"status": "would_remove" if dry_run else "removed", "path": str(destination)}
