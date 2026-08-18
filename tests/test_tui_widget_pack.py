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
            # `display.interface` is Hermes-owned. Installing the widget must
            # not move the user's terminal to make that widget reachable.
            self.assertNotIn(
                "interface:",
                (hermes_home / "config.yaml").read_text(encoding="utf-8"),
            )

    def test_setup_never_writes_display_interface(self) -> None:
        # Inverted deliberately. OMH used to write `display.interface: tui`
        # here so its widget -- which Hermes loads only in the Ink TUI -- would
        # be reachable. That moved the user off Hermes' own default classic
        # REPL, and with it the banner, status line, and the rules framing the
        # prompt, to serve an OMH surface. `display.interface` is Hermes-owned:
        # OMH reads it and adapts, and never writes it.
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
            self.assertNotIn("interface:", config_text)
            tui_interface = json.loads(stdout)["steps"]["apply"]["tui_interface"]
            self.assertFalse(tui_interface["changed"])

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
            # The identity skin default lands in the same display section, so
            # the interface line is no longer adjacent to the header; what this
            # test protects is that the explicit classic choice SURVIVES setup.
            self.assertIn("  interface: classic\n", config_text)
            self.assertIn("  skin: omh\n", config_text)
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
            # Authored here rather than derived from a value OMH wrote: OMH no
            # longer writes display.interface at all, so the explicit classic
            # preference this test protects has to come from the user.
            config.write_text(
                config.read_text(encoding="utf-8") + "\ndisplay:\n  interface: cli\n",
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
        # The Rule frame replaced the marginTop spacer: the docks carry the
        # classic composer frame, rules sitting tight against the input --
        # padding was tried at one and two rows and the owner picked none.
        self.assertIn("const Rule = ", widget)
        self.assertNotIn("Gap", widget)
        self.assertEqual(widget.count("h(Rule, { columns, t })"), 4)
        # Text, not chrome — changed on purpose a second time, by owner
        # direction after living with the bordered card: the OMH surface reads
        # like the host's own status line, dense text in the TUI's idiom. The
        # border that briefly asserted the panel identity now marks the
        # RETIRED design, and colours still resolve only through the active
        # theme — a literal hex would freeze the surface on one palette while
        # the rest of the TUI followed the user's skin.
        self.assertNotIn("borderStyle:", widget)
        self.assertNotIn("panelProps", widget)
        self.assertNotIn("color: '#", widget)
        # The bracket tags are the shared grammar between the two docks.
        self.assertIn("'⚚ [OMH]'", widget)
        self.assertEqual(widget.count("'[Plan]'"), 2)
        self.assertIn("const SEPARATOR = ' │ '", widget)
        self.assertNotIn("metricRow", widget)
        self.assertIn("...rows.map", widget)
        self.assertNotIn("...maestroRows.map", widget)
        self.assertNotIn("latest ? h(Text", widget)
        self.assertIn("const version = safeText(payload.version)", widget)
        # Header composition, changed on purpose (this used to assert the
        # literal "`[OMH] ${version}`"). That header named the product twice
        # and then claimed "Ultra Work Ready" whether or not anything was
        # running, so it read identically at four active agents and at zero.
        # What matters now is the contract, not the wording: the version is
        # still shown, every colour still resolves through the active theme,
        # and the state segment is derived rather than fixed.
        self.assertIn("` v${version}`", widget)
        self.assertIn("hudStateLabel(active, agents)", widget)
        self.assertIn("if (!active) return 'ready'", widget)
        # Hermes-native delegation rows linger after finishing: a done row
        # carries a check mark instead of spinning forever, and a linger-only
        # block says "N done" rather than the dishonest "0 agents".
        self.assertIn("done ? '✓'", widget)
        self.assertIn("if (!running && !blocked && done) return `${done} done`", widget)
        # A phase-structured plan (todo init) shows the current phase's name
        # above its checklist and the phase count next to done/total.
        self.assertIn("safeText(todo.display_phase)", widget)
        self.assertIn("` · ${phaseCount} phases`", widget)
        # The todo panel renders the plan from todo.items: a single-task phase
        # stays merged on one line, a dense phase renders a header with one
        # item per row, subtasks (depth 1..3) indent beneath their parent, and
        # past seven visible items the window anchors at current work with
        # muted "... (N earlier/later tasks)" fold lines.
        self.assertIn("Array.isArray(todo.items)", widget)
        self.assertIn("last.phase === phase", widget)
        self.assertIn("${truncateCells(group.phase, budget)} `", widget)
        self.assertIn("const TODO_DISPLAY_ROWS = 7", widget)
        self.assertIn("depthOf", widget)
        self.assertIn("'  '.repeat(depthOf(item))", widget)
        self.assertIn("task${count === 1 ? '' : 's'}", widget)
        self.assertIn("'todo-earlier'", widget)
        self.assertIn("'todo-later'", widget)
        self.assertNotIn("todo.display_items", widget)
        self.assertNotIn("more_count", widget)
        self.assertNotIn("more}", widget)
        # Drag-copy contract: an unchanged snapshot must not repaint the docks
        # (repaints clear an in-progress terminal selection), there is NO
        # animation subscription at all (the spinner advances one frame per
        # applied snapshot), and metric-only drift on a running wave repaints
        # at most once per throttle window instead of on every 2s poll.
        self.assertIn("if (serialized === lastSnapshot) return", widget)
        self.assertNotIn("AnimatedActivity", widget)
        self.assertIn("h(ActivityRows, { columns, mainRows", widget)
        self.assertIn("const METRICS_REPAINT_MS = 30_000", widget)
        self.assertIn(
            "if (structural === lastStructural && Date.now() - lastPaintAt < METRICS_REPAINT_MS) return",
            widget,
        )
        for volatile in (
            "'cache_hit_percentage'",
            "'context_percentage'",
            "'cost_usd'",
            "'elapsed_seconds'",
            "'observed_at'",
            "'tokens'",
            "'tokens_per_second'",
            "'tool_count'",
            "'turn_count'",
        ):
            self.assertIn(volatile, widget)
        # (bracket-tag grammar asserted above replaces the BRAND_MARK pair)
        # The old header's literal pieces ("-", "Oh My Hermes", "Ultra Work",
        # "Ready") are gone on purpose; asserting them back would re-pin the
        # wording this change exists to replace. The separator is now shared
        # between both panels instead of hand-written per segment.
        self.assertNotIn("'Ultra Work'", widget)
        # Static running cues: no spinner and no seconds counter on running
        # rows — under throttled repaints anything "animated" freezes and
        # lurches, which read as jank. The running marker is a fixed glyph
        # and running elapsed is minute-coarse.
        self.assertNotIn("SPINNER_FRAMES", widget)
        self.assertIn("done ? '✓' : '▸'", widget)
        self.assertIn("elapsedCoarse", widget)
        self.assertIn("'<1m'", widget)
        self.assertNotIn("useShimmerPhase", widget)
        self.assertNotIn("Number.MAX_SAFE_INTEGER", widget)
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
