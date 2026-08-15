"""Hermes-side TUI preflight: can the OMH HUD/todo surface render at all?

OMH's TUI extension only exists inside Hermes' modern Ink TUI: the widget
file under ``$HERMES_HOME/tui-widgets/`` is loaded by that TUI's user-widget
SDK, and only when ``display.interface`` boots it. None of that is visible
from OMH's own install state, so ``omh update`` used to succeed while a user
on an old Hermes kept the classic REPL and read the silence as "OMH is
broken". This module inspects the Hermes side read-only — no subprocess, no
network — and reports what can and cannot render, with the repair action.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..paths import OmhPaths
from ..tui_widget_pack import MANIFEST_FILENAME, WIDGET_FILENAME

HERMES_TUI_PREFLIGHT_SCHEMA_VERSION = "omh_hermes_tui_preflight/v1"

# The exact SDK names the installed widget destructures from ``register(sdk)``.
# If Hermes drops or renames one, its loader skips the widget with only a log
# line — this preflight is what turns that silent skip into a named finding.
REQUIRED_WIDGET_SDK_KEYS = (
    "Box",
    "Text",
    "defineWidgetApp",
    "h",
    "openWidget",
    "updateWidget",
    "useShimmerPhase",
)

# Reading caps: userWidgets.ts is ~8KB and config.yaml tens of KB today.
_MAX_INSPECT_BYTES = 512_000

_HERMES_INSTALL_DIRNAME = "hermes-agent"
_WIDGET_LOADER_RELATIVE = Path("ui-tui") / "src" / "sdk" / "userWidgets.ts"
_PREBUILT_BUNDLE_RELATIVE = Path("hermes_cli") / "tui_dist" / "entry.js"
_VERSION_MODULE_RELATIVE = Path("hermes_cli") / "__init__.py"


def _read_text_bounded(path: Path) -> str | None:
    try:
        if not path.is_file() or path.stat().st_size > _MAX_INSPECT_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _hermes_install_dir(paths: OmhPaths) -> Path:
    return paths.hermes_home / _HERMES_INSTALL_DIRNAME


def _hermes_version(install_dir: Path) -> str:
    text = _read_text_bounded(install_dir / _VERSION_MODULE_RELATIVE)
    if text is None:
        return ""
    match = re.search(r"__version__\s*=\s*[\"']([^\"']+)[\"']", text)
    return match.group(1) if match else ""


def _widget_sdk_block(loader_text: str) -> str | None:
    marker = "export const widgetSdk"
    start = loader_text.find(marker)
    if start < 0:
        return None
    end = loader_text.find("} as const", start)
    return loader_text[start:end] if end > start else loader_text[start:]


def _missing_sdk_keys(loader_text: str) -> list[str]:
    block = _widget_sdk_block(loader_text)
    if block is None:
        return list(REQUIRED_WIDGET_SDK_KEYS)
    return [key for key in REQUIRED_WIDGET_SDK_KEYS if not re.search(rf"\b{key}\b", block)]


def _display_interface(config_text: str) -> tuple[str, bool]:
    """Return (value, explicit) for ``display.interface`` in Hermes config.

    Mirrors the shape ``ensure_tui_interface`` writes: a top-level ``display:``
    block with an indented ``interface:`` line, or a dotted top-level
    ``display.interface:`` key. Anything unreadable reports as unset.
    """
    dotted = re.search(r"^display\.interface\s*:\s*(\S+)", config_text, re.MULTILINE)
    if dotted:
        return dotted.group(1).strip().strip("'\""), True
    in_display = False
    for line in config_text.splitlines():
        if re.match(r"^display\s*:\s*$", line):
            in_display = True
            continue
        if in_display:
            if line.strip() and not line.startswith((" ", "\t")):
                in_display = False
                continue
            match = re.match(r"^\s+interface\s*:\s*(\S+)", line)
            if match:
                return match.group(1).strip().strip("'\""), True
    return "", False


def _widget_interpreter(widget_text: str) -> str:
    match = re.search(r"execFile\(\s*\n?\s*(\"(?:[^\"\\]|\\.)+\")", widget_text)
    if not match:
        return ""
    try:
        value = json.loads(match.group(1))
    except ValueError:
        return ""
    return value if isinstance(value, str) else ""


def hermes_tui_preflight(paths: OmhPaths) -> dict[str, Any]:
    """Inspect the Hermes side of the OMH TUI surface. Read-only."""
    install_dir = _hermes_install_dir(paths)
    install_found = install_dir.is_dir()

    loader_path = install_dir / _WIDGET_LOADER_RELATIVE
    bundle_path = install_dir / _PREBUILT_BUNDLE_RELATIVE
    loader_text = _read_text_bounded(loader_path) if install_found else None
    loader_marker = ""
    if loader_text is not None:
        loader_marker = "ui-tui-source"
    elif install_found and bundle_path.is_file():
        loader_marker = "prebuilt-bundle"

    missing_keys: list[str] = []
    sdk_checked = loader_text is not None
    if sdk_checked:
        missing_keys = _missing_sdk_keys(loader_text)

    config_text = _read_text_bounded(paths.hermes_config_path) or ""
    interface_value, interface_explicit = _display_interface(config_text)

    widget_path = paths.hermes_home / "tui-widgets" / WIDGET_FILENAME
    manifest_path = paths.hermes_home / "tui-widgets" / MANIFEST_FILENAME
    widget_text = _read_text_bounded(widget_path)
    interpreter = _widget_interpreter(widget_text) if widget_text is not None else ""
    interpreter_ok = bool(interpreter) and Path(interpreter).is_file()

    return {
        "schema_version": HERMES_TUI_PREFLIGHT_SCHEMA_VERSION,
        "install": {
            "found": install_found,
            "path": str(install_dir),
            "version": _hermes_version(install_dir) if install_found else "",
        },
        "widget_loader": {
            "present": bool(loader_marker),
            "marker": loader_marker,
        },
        "sdk_surface": {
            "checked": sdk_checked,
            "missing": missing_keys,
        },
        "display_interface": {
            "value": interface_value,
            "explicit": interface_explicit,
        },
        "widget": {
            "installed": widget_text is not None,
            "managed": manifest_path.is_file(),
            "interpreter": interpreter,
            "interpreter_ok": interpreter_ok,
        },
    }


def widget_render_blockers(preflight: dict[str, Any]) -> list[str]:
    """Human-readable reasons the OMH HUD cannot render, empty when it can."""
    blockers: list[str] = []
    install = preflight.get("install", {})
    loader = preflight.get("widget_loader", {})
    sdk = preflight.get("sdk_surface", {})
    interface = preflight.get("display_interface", {})
    widget = preflight.get("widget", {})
    if not install.get("found"):
        blockers.append("Hermes install not found under the Hermes home; HUD state is unknowable from here.")
        return blockers
    if not loader.get("present"):
        version = str(install.get("version") or "unknown version")
        blockers.append(
            f"this Hermes ({version}) has no TUI widget loader — it predates the modern TUI; run `hermes update`."
        )
    if sdk.get("checked") and sdk.get("missing"):
        missing = ", ".join(sdk["missing"])
        blockers.append(
            f"the Hermes widget SDK no longer exposes: {missing} — the loader will skip the OMH widget; "
            "update OMH (`omh update`) or report the incompatibility."
        )
    if interface.get("explicit") and interface.get("value") not in ("", "tui"):
        blockers.append(
            f"display.interface is set to {interface['value']!r} — the OMH HUD renders only in the modern TUI "
            "(`hermes --tui` still reaches it)."
        )
    elif not interface.get("explicit"):
        blockers.append(
            "display.interface is unset, so bare `hermes` opens the classic REPL where the HUD cannot render; "
            "run `omh setup` to default it to the TUI."
        )
    if not widget.get("installed"):
        blockers.append("the OMH status widget is not installed; run `omh setup`.")
    elif widget.get("interpreter") and not widget.get("interpreter_ok"):
        blockers.append(
            f"the installed widget points at a Python interpreter that no longer exists "
            f"({widget['interpreter']}); run `omh setup` to reinstall it."
        )
    return blockers
