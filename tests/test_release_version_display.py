"""`omh update` must show the version it moved between, on every channel.

Preview installs track a branch archive, so `release_version` stays empty and the
release identity used to fall back to the source ref. An operator upgrading
1.0.2 -> 1.0.3 saw `main -> main` and could not tell whether anything changed.
The package version is already recorded; these tests pin that it is used.
"""

from __future__ import annotations

import unittest

from omh.commands.setup import (
    _command_package_display_change,
    _release_card_identity,
    _release_update_status,
)
from omh.version import __version__

PREVIEW_URL = "https://github.com/rlaope/oh-my-hermes/archive/refs/heads/main.zip"


def _preview_state(package_version: str) -> dict[str, object]:
    return {
        "release_channel": "preview",
        "release_version": "",
        "release_package_url": PREVIEW_URL,
        "release_source_ref": "main",
        "package_version": package_version,
    }


def _status(
    previous: dict[str, object],
    *,
    channel: str = "preview",
    version: str = "",
    source_ref: str = "main",
    package_url: str = PREVIEW_URL,
    updated: bool = True,
) -> dict[str, object]:
    return _release_update_status(
        release_channel=channel,
        release_version=version,
        release_package_url=package_url,
        source_ref=source_ref,
        explicit_metadata=bool(version),
        previous=previous,
        command_package={"updated": updated, "status": "updated" if updated else "refreshed"},
        dry_run=False,
    )


def _command_line(status: dict[str, object], *, channel: str = "preview", package_url: str = PREVIEW_URL) -> str:
    return _command_package_display_change(
        {"release_channel": channel, "release_package_url": package_url},
        status,
    )


class PreviewChannelVersionDisplayTests(unittest.TestCase):
    def test_upgrade_reports_the_package_version_move(self) -> None:
        status = _status(_preview_state("1.0.2"))
        self.assertEqual(status["display"]["version_change"], f"1.0.2 -> {__version__}")
        self.assertEqual(_command_line(status), f"1.0.2 -> {__version__}")

    def test_release_cards_show_versions_not_the_branch_name(self) -> None:
        status = _status(_preview_state("1.0.2"))
        self.assertEqual(_release_card_identity(status["previous"], language="en"), "1.0.2")
        self.assertEqual(_release_card_identity(status["current"], language="en"), __version__)

    def test_source_ref_is_still_reported_separately(self) -> None:
        # The branch is real information; showing the version must not hide it.
        status = _status(_preview_state("1.0.2"))
        self.assertEqual(status["display"]["source_ref_change"], "main -> main")
        self.assertEqual(status["current"]["release_source_ref"], "main")

    def test_previous_package_version_is_carried_forward(self) -> None:
        status = _status(_preview_state("1.0.2"))
        self.assertEqual(status["previous"]["package_version"], "1.0.2")

    def test_rerun_without_a_version_move_is_not_reported_as_a_move(self) -> None:
        status = _status(_preview_state(__version__), updated=False)
        self.assertEqual(status["display"]["version_change"], f"{__version__} -> {__version__}")
        self.assertEqual(_command_line(status), f"{__version__} -> {__version__}")


class StableChannelVersionDisplayTests(unittest.TestCase):
    def test_pinned_version_still_wins_over_the_package_version(self) -> None:
        previous = {
            "release_channel": "stable",
            "release_version": "1.0.2",
            "release_package_url": "https://example.invalid/v1.0.2.zip",
            "release_source_ref": "v1.0.2",
            "package_version": "1.0.2",
        }
        status = _status(
            previous,
            channel="stable",
            version="1.0.3",
            source_ref="v1.0.3",
            package_url="https://example.invalid/v1.0.3.zip",
        )
        self.assertEqual(status["display"]["version_change"], "1.0.2 -> 1.0.3")
        self.assertEqual(_release_card_identity(status["current"], language="en"), "1.0.3")

    def test_pin_disagreeing_with_the_package_is_reported_as_pinned(self) -> None:
        # An operator pinning an older archive should see the pin they asked for,
        # not the version of the command that happens to be running.
        previous = {
            "release_channel": "stable",
            "release_version": "1.0.1",
            "release_source_ref": "v1.0.1",
            "package_version": "1.0.1",
        }
        status = _status(previous, channel="stable", version="1.0.2", source_ref="v1.0.2")
        self.assertEqual(_release_card_identity(status["current"], language="en"), "1.0.2")


class LegacyAndFirstRunTests(unittest.TestCase):
    def test_first_run_has_no_previous_version_to_report(self) -> None:
        status = _status({})
        self.assertEqual(_release_card_identity(status["current"], language="en"), __version__)
        self.assertEqual(status["previous"]["package_version"], "")

    def test_legacy_state_without_a_package_version_falls_back_to_the_ref(self) -> None:
        # Pre-existing installs never recorded package_version. The old version is
        # genuinely unknown, so the ref is the honest answer rather than a guess.
        legacy = {
            "release_channel": "preview",
            "release_version": "",
            "release_package_url": PREVIEW_URL,
            "release_source_ref": "main",
        }
        status = _status(legacy)
        self.assertEqual(_release_card_identity(status["previous"], language="en"), "main")
        self.assertEqual(_release_card_identity(status["current"], language="en"), __version__)


if __name__ == "__main__":
    unittest.main()
