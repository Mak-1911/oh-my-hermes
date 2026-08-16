"""The managed OMH identity skin: install discipline and activation rules.

The skin is the owner-directed identity default — installing OMH opts into the
OH-MY-HERMES look the way installing oh-my-zsh restyles the shell — so these
tests pin the two edges that keep it honest: the file is only ever overwritten
when a manifest proves OMH wrote it, and `display.skin` is only ever written
in the unset case. An explicit user skin wins forever, in both places.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from omh.install.config_adapter import display_skin_selection, ensure_omh_skin
from omh.skin_pack import (
    SKIN_FILENAME,
    SKIN_NAME,
    install_skin,
    skin_payload,
    uninstall_skin,
)


class SkinPayloadTests(unittest.TestCase):
    def test_the_shipped_skin_carries_the_identity_contract(self) -> None:
        text = skin_payload().decode("utf-8")
        self.assertIn("name: omh", text)
        # The rename is the point: Hermes' banner title and welcome line read
        # OH-MY-HERMES through skin branding alone, never through a patch.
        self.assertIn('agent_name: "OH-MY-HERMES"', text)
        self.assertIn("banner_logo:", text)
        # The palette anchors on the README badge turquoise.
        self.assertIn('"#00CED1"', text)

    def test_the_logo_rows_are_equally_wide(self) -> None:
        # A block logo with ragged rows renders as visible corruption in the
        # banner; alignment is a contract, not cosmetics.
        import re

        text = skin_payload().decode("utf-8")
        # No strip: the O and the closing S rows legitimately begin with a
        # space, and eating it is exactly the misalignment this test exists
        # to catch. Only the rich markup and the uniform YAML block indent go.
        rows = [
            re.sub(r"\[[^\]]*\]", "", line).removeprefix("  ")
            for line in text.splitlines()
            if "██" in line or "╚" in line
        ]
        self.assertTrue(rows)
        self.assertEqual(len({len(row) for row in rows}), 1)


class SkinInstallTests(unittest.TestCase):
    def test_install_writes_skin_and_manifest(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp).resolve()
            result = install_skin(home)
            self.assertEqual(result["status"], "installed")
            destination = home / "skins" / SKIN_FILENAME
            self.assertEqual(destination.read_bytes(), skin_payload())
            manifest = json.loads((home / "skins" / ".omh-skin.manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["filename"], SKIN_FILENAME)

    def test_reinstall_is_idempotent(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp).resolve()
            install_skin(home)
            self.assertEqual(install_skin(home)["status"], "unchanged")

    def test_a_user_authored_skin_file_is_never_replaced(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp).resolve()
            destination = home / "skins" / SKIN_FILENAME
            destination.parent.mkdir(parents=True)
            destination.write_text("name: omh\n# mine\n", encoding="utf-8")
            self.assertEqual(install_skin(home)["status"], "kept_unmanaged")
            self.assertEqual(destination.read_text(encoding="utf-8"), "name: omh\n# mine\n")

    def test_uninstall_removes_only_the_managed_file(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp).resolve()
            install_skin(home)
            self.assertEqual(uninstall_skin(home)["status"], "removed")
            self.assertFalse((home / "skins" / SKIN_FILENAME).exists())

    def test_uninstall_keeps_a_user_authored_file(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp).resolve()
            destination = home / "skins" / SKIN_FILENAME
            destination.parent.mkdir(parents=True)
            destination.write_text("name: omh\n", encoding="utf-8")
            self.assertEqual(uninstall_skin(home)["status"], "kept_unmanaged")
            self.assertTrue(destination.exists())


class EnsureOmhSkinTests(unittest.TestCase):
    def test_unset_skin_defaults_to_omh(self) -> None:
        change = ensure_omh_skin("display:\n  compact: true\n", SKIN_NAME)
        self.assertTrue(change.changed)
        self.assertEqual(display_skin_selection(change.text), SKIN_NAME)
        self.assertIn("  compact: true", change.text)

    def test_missing_display_section_is_appended(self) -> None:
        change = ensure_omh_skin("plugins:\n  enabled:\n    - omh\n", SKIN_NAME)
        self.assertTrue(change.changed)
        self.assertEqual(display_skin_selection(change.text), SKIN_NAME)

    def test_an_explicit_skin_choice_is_never_rewritten(self) -> None:
        # `hermes skin use ares` after setup must stick across every future
        # update; rewriting it would repeat the display.interface mistake.
        text = "display:\n  skin: ares\n"
        change = ensure_omh_skin(text, SKIN_NAME)
        self.assertFalse(change.changed)
        self.assertEqual(change.text, text)

    def test_already_omh_is_unchanged(self) -> None:
        change = ensure_omh_skin("display:\n  skin: omh\n", SKIN_NAME)
        self.assertFalse(change.changed)

    def test_dotted_key_is_user_owned(self) -> None:
        change = ensure_omh_skin("display.skin: ares\n", SKIN_NAME)
        self.assertFalse(change.changed)

    def test_duplicate_display_sections_are_left_alone(self) -> None:
        change = ensure_omh_skin("display:\n  compact: true\ndisplay:\n  streaming: true\n", SKIN_NAME)
        self.assertFalse(change.changed)


if __name__ == "__main__":
    unittest.main()
