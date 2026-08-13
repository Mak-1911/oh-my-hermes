from __future__ import annotations

from importlib import resources
import json
import os
from pathlib import Path
import secrets

WIDGET_FILENAME = "omh-status.mjs"
MANIFEST_FILENAME = ".omh-status.manifest.json"
INTERPRETER_MARKER = "__OMH_PYTHON_EXECUTABLE__"


class TuiWidgetInstallError(RuntimeError):
    """The managed Hermes widget destination is unsafe."""


def widget_payload(python_executable: Path) -> bytes:
    template = resources.files("omh.tui_widgets").joinpath(WIDGET_FILENAME).read_text(encoding="utf-8")
    executable = os.path.realpath(python_executable)
    if not Path(executable).is_file():
        raise TuiWidgetInstallError("OMH Python executable is not a regular file")
    return template.replace(INTERPRETER_MARKER, json.dumps(executable)).encode()


def _reject_symlink_path(path: Path) -> None:
    current = path
    while True:
        if current.is_symlink():
            raise TuiWidgetInstallError(f"refusing symlinked widget path: {current}")
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


def install_tui_widget(hermes_home: Path, *, dry_run: bool = False) -> dict[str, str]:
    destination_dir = hermes_home / "tui-widgets"
    destination = destination_dir / WIDGET_FILENAME
    manifest = destination_dir / MANIFEST_FILENAME
    _reject_symlink_path(hermes_home)
    _reject_symlink_path(destination_dir)
    _reject_symlink_path(destination)
    if destination.exists() and not destination.is_file():
        raise TuiWidgetInstallError(f"widget destination is not a regular file: {destination}")
    payload = widget_payload(Path(os.sys.executable))
    if destination.exists() and not _is_managed_widget(destination, manifest):
        raise TuiWidgetInstallError(f"refusing to replace unmanaged widget: {destination}")
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
                    "schema_version": "omh_tui_widget_manifest/v1",
                    "filename": WIDGET_FILENAME,
                    "sha256": _sha256(payload),
                },
                sort_keys=True,
            ).encode(),
        )
    return {
        "status": status,
        "path": str(destination),
        "extension_point": "hermes_tui_widgets",
    }


def _sha256(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()


def _is_managed_widget(destination: Path, manifest: Path) -> bool:
    try:
        if manifest.is_symlink() or not manifest.is_file():
            return False
        record = json.loads(manifest.read_text(encoding="utf-8"))
        return (
            record.get("schema_version") == "omh_tui_widget_manifest/v1"
            and record.get("filename") == WIDGET_FILENAME
            and record.get("sha256") == _sha256(destination.read_bytes())
        )
    except (OSError, json.JSONDecodeError, AttributeError):
        return False


def uninstall_tui_widget(hermes_home: Path, *, dry_run: bool = False) -> dict[str, str]:
    destination_dir = hermes_home / "tui-widgets"
    destination = destination_dir / WIDGET_FILENAME
    manifest = destination_dir / MANIFEST_FILENAME
    _reject_symlink_path(destination_dir)
    _reject_symlink_path(destination)
    _reject_symlink_path(manifest)
    if not destination.exists() and not manifest.exists():
        return {"status": "absent", "path": str(destination)}
    if not _is_managed_widget(destination, manifest):
        return {"status": "kept_unmanaged", "path": str(destination)}
    if not dry_run:
        destination.unlink()
        manifest.unlink()
    return {"status": "would_remove" if dry_run else "removed", "path": str(destination)}
