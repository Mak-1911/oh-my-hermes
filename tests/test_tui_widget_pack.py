from __future__ import annotations

import json
import os
import sys
import unittest
from importlib import resources
from pathlib import Path
from tempfile import TemporaryDirectory

from _cli_harness import run_cli
from omh.tui_widget_pack import TuiWidgetInstallError, install_tui_widget, widget_payload


class TuiWidgetPackTests(unittest.TestCase):
    def test_setup_installs_byte_correct_widget_without_overwriting_unrelated_widget(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            omh_home = root / ".omh"
            hermes_home = root / ".hermes"
            widget_dir = hermes_home / "tui-widgets"
            widget_dir.mkdir(parents=True)
            unrelated = widget_dir / "personal-dashboard.mjs"
            unrelated_bytes = b"export default function register() {}\n"
            unrelated.write_bytes(unrelated_bytes)

            status, stdout, stderr = run_cli(
                [
                    "--omh-home",
                    str(omh_home),
                    "--hermes-home",
                    str(hermes_home),
                    "setup",
                    "--json",
                ],
                output_json=False,
            )

            self.assertEqual(stderr, "")
            self.assertEqual(status, 0)
            payload = json.loads(stdout)
            expected = widget_payload(Path(sys.executable))
            self.assertEqual((widget_dir / "omh-status.mjs").read_bytes(), expected)
            self.assertEqual(unrelated.read_bytes(), unrelated_bytes)
            self.assertEqual(payload["steps"]["tui_widget"]["status"], "installed")

    def test_update_restores_an_installed_widget(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            omh_home = root / ".omh"
            hermes_home = root / ".hermes"
            common = [
                "--omh-home",
                str(omh_home),
                "--hermes-home",
                str(hermes_home),
            ]
            setup_status, _, setup_stderr = run_cli([*common, "setup", "--json"], output_json=False)
            self.assertEqual((setup_status, setup_stderr), (0, ""))
            widget = hermes_home / "tui-widgets" / "omh-status.mjs"
            widget.unlink()

            status, _, stderr = run_cli(
                [
                    *common,
                    "update",
                    "--source",
                    str(Path(__file__).parents[1]),
                    "--channel",
                    "local",
                    "--json",
                ],
                output_json=False,
            )

            self.assertEqual((status, stderr), (0, ""))
            expected = widget_payload(Path(sys.executable))
            self.assertEqual(widget.read_bytes(), expected)

    def test_installer_rejects_symlinked_widget_destination_and_parent(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hermes_home = root / ".hermes"
            widget_dir = hermes_home / "tui-widgets"
            widget_dir.mkdir(parents=True)
            victim = root / "victim.mjs"
            victim_bytes = b"do not overwrite\n"
            victim.write_bytes(victim_bytes)
            destination = widget_dir / "omh-status.mjs"
            destination.symlink_to(victim)

            with self.assertRaises(TuiWidgetInstallError):
                install_tui_widget(hermes_home)
            self.assertEqual(victim.read_bytes(), victim_bytes)

            destination.unlink()
            widget_dir.rmdir()
            external_dir = root / "external-widgets"
            external_dir.mkdir()
            widget_dir.symlink_to(external_dir, target_is_directory=True)
            with self.assertRaises(TuiWidgetInstallError):
                install_tui_widget(hermes_home)
            self.assertEqual(list(external_dir.iterdir()), [])

    def test_installer_refuses_unmanaged_existing_widget(self) -> None:
        with TemporaryDirectory() as tmp:
            hermes_home = Path(tmp) / ".hermes"
            destination = hermes_home / "tui-widgets" / "omh-status.mjs"
            destination.parent.mkdir(parents=True)
            user_bytes = b"export default function userOwned() {}\n"
            destination.write_bytes(user_bytes)

            with self.assertRaises(TuiWidgetInstallError):
                install_tui_widget(hermes_home)
            self.assertEqual(destination.read_bytes(), user_bytes)

    def test_widget_uses_setup_interpreter_not_path_python(self) -> None:
        payload = widget_payload(Path(sys.executable)).decode()

        self.assertIn(json.dumps(os.path.realpath(sys.executable)), payload)
        self.assertNotIn("spawnSync('python3'", payload)

    def test_full_uninstall_removes_only_managed_widget(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            omh_home = root / ".omh"
            hermes_home = root / ".hermes"
            common = ["--omh-home", str(omh_home), "--hermes-home", str(hermes_home)]
            status, _, stderr = run_cli([*common, "setup", "--json"], output_json=False)
            self.assertEqual((status, stderr), (0, ""))
            destination = hermes_home / "tui-widgets" / "omh-status.mjs"
            unrelated = destination.parent / "personal.mjs"
            unrelated.write_text("personal\n", encoding="utf-8")

            status, stdout, stderr = run_cli(
                [*common, "uninstall", "--all", "--keep-command", "--json"],
                output_json=False,
            )

            self.assertEqual((status, stderr), (0, ""))
            self.assertFalse(destination.exists())
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "personal\n")
            self.assertEqual(json.loads(stdout)["tui_widget"]["status"], "removed")

    def test_widget_is_full_width_and_omits_host_status_fields(self) -> None:
        widget = resources.files("omh.tui_widgets").joinpath("omh-status.mjs").read_text()

        self.assertIn("zone: 'dock-bottom'", widget)
        self.assertIn("width: '100%'", widget)
        self.assertIn("[OMH]", widget)
        self.assertIn("MAESTRO", widget)
        self.assertIn("routed", widget)
        self.assertIn("execFile(", widget)
        self.assertIn("Symbol.for(", widget)
        self.assertIn("generationKey", widget)
        self.assertIn("generation !== globalThis[generationKey]", widget)
        self.assertIn("clearTimeout(", widget)
        self.assertNotIn("spawnSync(", widget)
        self.assertNotIn("setInterval(", widget)
        for forbidden in ("payload.cwd", "payload.branch", "payload.context", "payload.cost"):
            self.assertNotIn(forbidden, widget)


if __name__ == "__main__":
    unittest.main()
