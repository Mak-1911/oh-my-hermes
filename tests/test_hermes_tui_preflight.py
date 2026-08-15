from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from omh.maintenance.doctor import run_doctor
from omh.maintenance.hermes_tui import (
    REQUIRED_WIDGET_SDK_KEYS,
    hermes_tui_preflight,
    widget_render_blockers,
)
from omh.paths import OmhPaths
from omh.tui_widget_pack import install_tui_widget


_MODERN_SDK_SOURCE = """
import { Box, Text } from '@hermes/ink'
export const widgetSdk = {
  Box,
  Text,
  defineWidgetApp,
  h: React.createElement,
  openWidget,
  updateWidget,
  useShimmerPhase
} as const
"""


def _make_paths(root: Path) -> OmhPaths:
    # macOS TemporaryDirectory lives under the /var -> /private/var symlink,
    # which install_tui_widget rejects by design; resolve before building paths.
    resolved = root.resolve()
    return OmhPaths(resolved / ".omh", resolved / ".hermes")


def _make_hermes_install(
    hermes_home: Path,
    *,
    version: str = "0.20.1",
    sdk_source: str | None = _MODERN_SDK_SOURCE,
) -> Path:
    install = hermes_home / "hermes-agent"
    (install / "hermes_cli").mkdir(parents=True)
    (install / "hermes_cli" / "__init__.py").write_text(
        f'__version__ = "{version}"\n', encoding="utf-8"
    )
    if sdk_source is not None:
        loader = install / "ui-tui" / "src" / "sdk"
        loader.mkdir(parents=True)
        (loader / "userWidgets.ts").write_text(sdk_source, encoding="utf-8")
    return install


def _write_display_interface(hermes_home: Path, value: str) -> None:
    hermes_home.mkdir(parents=True, exist_ok=True)
    (hermes_home / "config.yaml").write_text(
        f"display:\n  interface: {value}\n", encoding="utf-8"
    )


class HermesTuiPreflightTests(unittest.TestCase):
    def test_healthy_modern_install_reports_no_blockers(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = _make_paths(Path(tmp))
            _make_hermes_install(paths.hermes_home)
            _write_display_interface(paths.hermes_home, "tui")
            install_tui_widget(paths.hermes_home)

            preflight = hermes_tui_preflight(paths)

            self.assertTrue(preflight["install"]["found"])
            self.assertEqual(preflight["install"]["version"], "0.20.1")
            self.assertEqual(preflight["widget_loader"]["marker"], "ui-tui-source")
            self.assertEqual(preflight["sdk_surface"]["missing"], [])
            self.assertEqual(preflight["display_interface"]["value"], "tui")
            self.assertTrue(preflight["widget"]["installed"])
            self.assertTrue(preflight["widget"]["managed"])
            self.assertEqual(preflight["widget"]["interpreter"], str(Path(sys.executable).resolve()))
            self.assertTrue(preflight["widget"]["interpreter_ok"])
            self.assertEqual(widget_render_blockers(preflight), [])

    def test_old_hermes_without_widget_loader_names_hermes_update(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = _make_paths(Path(tmp))
            _make_hermes_install(paths.hermes_home, version="0.8.0", sdk_source=None)
            _write_display_interface(paths.hermes_home, "tui")
            install_tui_widget(paths.hermes_home)

            preflight = hermes_tui_preflight(paths)
            blockers = widget_render_blockers(preflight)

            self.assertFalse(preflight["widget_loader"]["present"])
            self.assertFalse(preflight["sdk_surface"]["checked"])
            self.assertEqual(len(blockers), 1)
            self.assertIn("0.8.0", blockers[0])
            self.assertIn("hermes update", blockers[0])

    def test_stripped_sdk_surface_reports_each_missing_key(self) -> None:
        stripped = _MODERN_SDK_SOURCE.replace("  useShimmerPhase\n", "").replace(
            "  updateWidget,\n", ""
        )
        with TemporaryDirectory() as tmp:
            paths = _make_paths(Path(tmp))
            _make_hermes_install(paths.hermes_home, sdk_source=stripped)
            _write_display_interface(paths.hermes_home, "tui")
            install_tui_widget(paths.hermes_home)

            preflight = hermes_tui_preflight(paths)
            blockers = widget_render_blockers(preflight)

            self.assertEqual(
                preflight["sdk_surface"]["missing"], ["updateWidget", "useShimmerPhase"]
            )
            self.assertEqual(len(blockers), 1)
            self.assertIn("updateWidget, useShimmerPhase", blockers[0])

    def test_unset_display_interface_is_a_blocker_and_explicit_cli_is_user_owned(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = _make_paths(Path(tmp))
            _make_hermes_install(paths.hermes_home)
            paths.hermes_home.mkdir(parents=True, exist_ok=True)
            (paths.hermes_home / "config.yaml").write_text("model: something\n", encoding="utf-8")
            install_tui_widget(paths.hermes_home)

            unset = hermes_tui_preflight(paths)
            self.assertFalse(unset["display_interface"]["explicit"])
            self.assertEqual(
                [blocker for blocker in widget_render_blockers(unset) if "omh setup" in blocker and "classic REPL" in blocker],
                widget_render_blockers(unset),
            )

            _write_display_interface(paths.hermes_home, "cli")
            explicit = hermes_tui_preflight(paths)
            blockers = widget_render_blockers(explicit)
            self.assertTrue(explicit["display_interface"]["explicit"])
            self.assertEqual(len(blockers), 1)
            self.assertIn("hermes --tui", blockers[0])

    def test_stale_widget_interpreter_is_a_blocker(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = _make_paths(Path(tmp))
            _make_hermes_install(paths.hermes_home)
            _write_display_interface(paths.hermes_home, "tui")
            install_tui_widget(paths.hermes_home)
            widget = paths.hermes_home / "tui-widgets" / "omh-status.mjs"
            gone = str(Path(tmp).resolve() / "missing-python")
            widget.write_text(
                widget.read_text(encoding="utf-8").replace(
                    str(Path(sys.executable).resolve()), gone
                ),
                encoding="utf-8",
            )

            preflight = hermes_tui_preflight(paths)
            blockers = widget_render_blockers(preflight)

            self.assertEqual(preflight["widget"]["interpreter"], gone)
            self.assertFalse(preflight["widget"]["interpreter_ok"])
            self.assertEqual(len(blockers), 1)
            self.assertIn("omh setup", blockers[0])

    def test_missing_install_reports_single_unknowable_blocker(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = _make_paths(Path(tmp))
            preflight = hermes_tui_preflight(paths)
            blockers = widget_render_blockers(preflight)
            self.assertFalse(preflight["install"]["found"])
            self.assertEqual(len(blockers), 1)
            self.assertIn("unknowable", blockers[0])

    def test_required_sdk_keys_match_the_installed_widget_destructure(self) -> None:
        from importlib import resources

        widget_source = (
            resources.files("omh.tui_widgets").joinpath("omh-status.mjs").read_text(encoding="utf-8")
        )
        destructure = widget_source.split("= sdk", 1)[0]
        for key in REQUIRED_WIDGET_SDK_KEYS:
            self.assertIn(key, destructure, f"widget no longer destructures {key}")


class DoctorHermesTuiChecksTests(unittest.TestCase):
    def _checks_by_name(self, paths: OmhPaths) -> dict[str, object]:
        return {check.name: check for check in run_doctor(paths)}

    def test_doctor_reports_all_four_checks_ok_on_modern_install(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = _make_paths(Path(tmp))
            _make_hermes_install(paths.hermes_home)
            _write_display_interface(paths.hermes_home, "tui")
            install_tui_widget(paths.hermes_home)

            checks = self._checks_by_name(paths)

            for name in (
                "hermes_tui_support",
                "hermes_tui_sdk_surface",
                "hermes_tui_interface_default",
                "hermes_tui_widget_state",
            ):
                self.assertIn(name, checks)
                self.assertTrue(checks[name].ok, name)

    def test_doctor_warns_with_hermes_update_next_action_on_old_hermes(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = _make_paths(Path(tmp))
            _make_hermes_install(paths.hermes_home, version="0.8.0", sdk_source=None)
            _write_display_interface(paths.hermes_home, "tui")

            checks = self._checks_by_name(paths)
            support = checks["hermes_tui_support"]

            self.assertFalse(support.ok)
            self.assertEqual(support.severity, "warning")
            self.assertIn("hermes update", support.next_action)
            self.assertNotIn("hermes_tui_sdk_surface", checks)

    def test_doctor_skips_quietly_when_hermes_install_is_absent(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = _make_paths(Path(tmp))
            checks = self._checks_by_name(paths)
            support = checks["hermes_tui_support"]
            self.assertTrue(support.ok)
            self.assertFalse(support.observed)


if __name__ == "__main__":
    unittest.main()
