from __future__ import annotations

import json
from importlib import resources
import os
import sys
import unittest
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
            self.assertIn(
                "display:\n  interface: tui\n",
                (hermes_home / "config.yaml").read_text(encoding="utf-8"),
            )

    def test_setup_defaults_existing_config_without_display_interface_to_tui(self) -> None:
        # Upgraders whose config predates display.interface get the same TUI
        # default as fresh installs; only an explicit choice is user-owned.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            omh_home = root / ".omh"
            hermes_home = root / ".hermes"
            config = hermes_home / "config.yaml"
            config.parent.mkdir(parents=True)
            config.write_text("display:\n  compact: true\n", encoding="utf-8")

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

            self.assertEqual((status, stderr), (0, ""))
            config_text = config.read_text(encoding="utf-8")
            self.assertIn("  compact: true", config_text)
            self.assertIn("  interface: tui", config_text)
            tui_interface = json.loads(stdout)["steps"]["apply"]["tui_interface"]
            self.assertTrue(tui_interface["changed"])
            self.assertEqual(tui_interface["selected"], "tui")

    def test_setup_preserves_an_explicit_classic_interface(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            omh_home = root / ".omh"
            hermes_home = root / ".hermes"
            config = hermes_home / "config.yaml"
            config.parent.mkdir(parents=True)
            config.write_text("display:\n  interface: classic\n", encoding="utf-8")

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

            self.assertEqual((status, stderr), (0, ""))
            config_text = config.read_text(encoding="utf-8")
            self.assertIn("display:\n  interface: classic\n", config_text)
            self.assertEqual(config_text.count("interface:"), 1)
            self.assertEqual(json.loads(stdout)["steps"]["apply"]["tui_interface"]["selected"], "classic")

    def test_update_restores_widget_without_overriding_display_preference(self) -> None:
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
            config = hermes_home / "config.yaml"
            config.write_text(
                config.read_text(encoding="utf-8").replace("interface: tui", "interface: cli"),
                encoding="utf-8",
            )

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
            self.assertIn("display:\n  interface: cli\n", config.read_text(encoding="utf-8"))

    def test_setup_reports_config_changed_when_only_plugin_enablement_changes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            omh_home = root / ".omh"
            hermes_home = root / ".hermes"
            common = ["--omh-home", str(omh_home), "--hermes-home", str(hermes_home)]
            setup_status, _, setup_stderr = run_cli([*common, "setup", "--json"], output_json=False)
            self.assertEqual((setup_status, setup_stderr), (0, ""))
            config = hermes_home / "config.yaml"
            config.write_text(
                config.read_text(encoding="utf-8").replace("plugins:\n  enabled:\n    - omh\n", ""),
                encoding="utf-8",
            )

            status, stdout, stderr = run_cli([*common, "setup", "--json"], output_json=False)

            self.assertEqual((status, stderr), (0, ""))
            apply = json.loads(stdout)["steps"]["apply"]
            self.assertTrue(apply["plugin_enabled"]["changed"])
            self.assertTrue(apply["changed"])

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
        self.assertIn("['-I', '-c', READER]", payload)
        self.assertIn("const READER_ENV =", payload)
        self.assertNotIn("...process.env", payload)

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

    def test_widget_is_bottom_docked_and_omits_host_status_fields(self) -> None:
        widget = resources.files("omh.tui_widgets").joinpath("omh-status.mjs").read_text(encoding="utf-8")

        self.assertIn("zone: 'dock-bottom'", widget)
        self.assertNotIn("zone: 'top-right'", widget)
        # The todo checklist is the one dock-top app; the status app stays
        # dock-bottom so the panel renders above the prompt input and the
        # activity rows below it.
        self.assertEqual(widget.count("zone: 'dock-top'"), 1)
        self.assertIn("id: 'omh-todo'", widget)
        self.assertIn("TodoPanel", widget)
        self.assertIn("truncateCells(item.text", widget)
        self.assertIn("safeText(todo.title)", widget)
        # An installed OMH stays discoverable from an idle session: only the
        # activity rows are gated on live work, never the header.
        self.assertNotIn("|| !payload.active", widget)
        self.assertIn("const active = !!payload.active", widget)
        self.assertIn("width: '100%'", widget)
        self.assertIn("marginTop: 1", widget)
        # Panel chrome, changed on purpose (this used to assert
        # `assertNotIn("borderStyle:")`). The borderless design rendered the
        # HUD as loose text floating around the prompt instead of a piece of
        # the TUI. Both apps now draw a bordered, padded card, and the border
        # colour must come from the ACTIVE THEME the host hands `render` — a
        # literal hex would freeze the panel on one palette while the rest of
        # the TUI followed the user's skin.
        self.assertIn("borderStyle: 'round'", widget)
        self.assertIn("borderColor: t.color.primary", widget)
        self.assertIn("paddingX: 1", widget)
        self.assertNotIn("color: '#", widget)
        # One panel definition serves the status HUD and both todo states, so
        # the chrome can never drift between them.
        self.assertEqual(widget.count("panelProps(t)"), 3)
        # Border + padding are chrome, not content: both apps budget against
        # the inner card, not the raw terminal.
        self.assertIn("cols - PANEL_CHROME_COLUMNS", widget)
        self.assertIn("rows - PANEL_CHROME_ROWS", widget)
        self.assertNotIn("metricRow", widget)
        self.assertIn("...rows.map", widget)
        self.assertNotIn("...maestroRows.map", widget)
        self.assertNotIn("latest ? h(Text", widget)
        self.assertIn("const version = safeText(payload.version)", widget)
        self.assertIn("`[OMH] ${version}`", widget)
        self.assertIn("}, '-'),", widget)
        self.assertIn("'Oh My Hermes'", widget)
        self.assertIn("'Ultra Work'", widget)
        self.assertIn("'Ready'", widget)
        self.assertIn("SPINNER_FRAMES", widget)
        self.assertIn("useShimmerPhase", widget)
        self.assertNotIn("Number.MAX_SAFE_INTEGER", widget)
        self.assertIn("useShimmerPhase(30_000)", widget)
        self.assertIn("Math.min(3,", widget)
        self.assertNotIn("spinnerTimerKey", widget)
        self.assertIn("ActivityRow", widget)
        self.assertIn("truncateCells", widget)
        self.assertIn("category:", widget)
        self.assertIn("tools", widget)
        self.assertIn("tok/s", widget)
        self.assertIn("cache_hit_percentage", widget)
        self.assertIn("context_percentage", widget)
        self.assertIn("uncollected", widget)
        self.assertIn("'MAIN'", widget)
        self.assertIn("maestro.rows", widget)
        self.assertIn("fallback:", widget)
        self.assertIn("'•'", widget)
        self.assertIn("execFile(", widget)
        self.assertIn("Symbol.for(", widget)
        self.assertIn("generationKey", widget)
        self.assertIn("generation !== globalThis[generationKey]", widget)
        self.assertIn("clearTimeout(", widget)
        self.assertNotIn("payload ? { payload } : state", widget)
        # One immutable snapshot-apply helper feeds both widget apps, and both
        # the initial read and the refresh timer go through it.
        self.assertEqual(widget.count("{ ...state, payload, tick: state.tick + 1 }"), 1)
        self.assertEqual(widget.count("applySnapshot(payload)"), 2)
        self.assertNotIn("friendlyWorkflow", widget)
        self.assertNotIn("'fanout-unit': 'Parallel work'", widget)
        self.assertIn("t.color.ok", widget)
        self.assertIn("t.color.error", widget)
        self.assertIn("t.color.warn", widget)
        self.assertNotIn("t.color.warning", widget)
        self.assertNotIn("spawnSync(", widget)
        self.assertNotIn("setInterval(", widget)
        for forbidden in ("payload.cwd", "payload.branch", "payload.context", "payload.cost"):
            self.assertNotIn(forbidden, widget)


if __name__ == "__main__":
    unittest.main()
