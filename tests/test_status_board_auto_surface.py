"""Automatic surfacing of the running-work board in `pre_llm_call`.

Multi-session coding work in flight should be visible to Hermes without the
user asking for it. `read_running_work_board` (a standalone plugin-bundle
reader; it cannot import `omh.*`, see `status_board_reader.py`'s module
docstring) walks the same in-flight markers and dispatch summaries
`omh.coding.status_board` does, and `pre_llm_call` appends a compact block
whenever two or more units are observed running -- a count, never a keyword,
because no fixed phrasing can catch every way a user's message might arrive
while multi-session work is in flight.

Harness rule (matches `tests/test_degradation_signal.py`): both awareness
`lru_cache`s are cleared in `setUp`, and each hook-level test uses a distinct
neutral message so no test's cached match result leaks into another.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from _local_package import load_local_package

load_local_package()

from omh.coding.inflight import write_inflight_marker
from omh.plugin_bundle.omh import awareness as awareness_module
from omh.plugin_bundle.omh.hooks.llm_hooks import pre_llm_call
from omh.plugin_bundle.omh.status_board_reader import (
    DEFAULT_LIMIT,
    RUNNING_WORK_BOARD_SCHEMA_VERSION,
    last_running_work_board_fingerprint,
    read_running_work_board,
    record_running_work_board_emission,
    render_running_work_block_text,
    running_work_board_fingerprint,
)
from omh.system.paths import OmhPaths

_FANOUT_ID = "fanout-0123456789ab"


def _paths(root: Path) -> OmhPaths:
    return OmhPaths(omh_home=root / ".omh", hermes_home=root / ".hermes")


def _fields(**overrides: str) -> dict[str, str]:
    fields = {
        "owner": "codex",
        "owner_host": "local",
        "model": "gpt-5-codex",
        "reasoning_effort": "medium",
        "run_ref": "run-core",
        "worktree": "/tmp/worktrees/core",
        "started_at": "2026-08-03T09:00:00Z",
    }
    fields.update(overrides)
    return fields


class RunningWorkBoardReaderTests(unittest.TestCase):
    def test_no_markers_report_an_empty_board(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            board = read_running_work_board(paths.omh_home)
            self.assertEqual(board["schema_version"], RUNNING_WORK_BOARD_SCHEMA_VERSION)
            self.assertEqual(board["running_count"], 0)
            self.assertEqual(board["unit_count"], 0)
            self.assertEqual(board["units"], [])
            self.assertFalse(board["truncated"])
            self.assertEqual(board["sources"]["fanout_root"], "absent")

    def test_two_running_markers_are_both_reported(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            write_inflight_marker(paths, _FANOUT_ID, "core", _fields())
            write_inflight_marker(paths, _FANOUT_ID, "docs", _fields(run_ref="run-docs"))
            board = read_running_work_board(paths.omh_home)
            self.assertEqual(board["running_count"], 2)
            self.assertEqual(board["unit_count"], 2)
            self.assertEqual({unit["unit_id"] for unit in board["units"]}, {"core", "docs"})
            for unit in board["units"]:
                self.assertEqual(unit["status"], "running")
                self.assertEqual(unit["model_label"], "gpt-5-codex medium")
            self.assertEqual(board["sources"]["fanout_root"], "present")

    def test_more_units_than_the_limit_states_truncation(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            for index in range(DEFAULT_LIMIT + 3):
                write_inflight_marker(paths, _FANOUT_ID, f"unit-{index}", _fields(run_ref=f"run-{index}"))
            board = read_running_work_board(paths.omh_home)
            self.assertEqual(board["running_count"], DEFAULT_LIMIT + 3)
            self.assertEqual(board["unit_count"], DEFAULT_LIMIT + 3)
            self.assertEqual(len(board["units"]), DEFAULT_LIMIT)
            self.assertTrue(board["truncated"])
            self.assertEqual(board["omitted_count"], 3)
            text = render_running_work_block_text(board)
            self.assertIn("3 not shown because of the display limit", text)

    def test_a_malformed_marker_is_skipped_without_raising(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            write_inflight_marker(paths, _FANOUT_ID, "core", _fields())
            broken_path = paths.omh_home / "coding" / "fanout" / _FANOUT_ID / "inflight" / "broken.json"
            broken_path.write_text("{not json", encoding="utf-8")
            board = read_running_work_board(paths.omh_home)
            self.assertEqual(board["running_count"], 1)
            self.assertEqual(board["unit_count"], 1)
            self.assertEqual(board["sources"]["inflight_markers_unreadable"], 1)

    def test_absent_root_and_unreadable_root_are_distinguishable(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            absent_board = read_running_work_board(paths.omh_home)
            self.assertEqual(absent_board["sources"]["fanout_root"], "absent")

        with TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            fanout_root = paths.omh_home / "coding" / "fanout"
            fanout_root.parent.mkdir(parents=True, exist_ok=True)
            fanout_root.write_text("a file where the fanout directory belongs", encoding="utf-8")
            unreadable_board = read_running_work_board(paths.omh_home)
            self.assertEqual(unreadable_board["sources"]["fanout_root"], "unreadable")


class RunningWorkBoardSuppressionLedgerTests(unittest.TestCase):
    def test_fingerprint_changes_when_the_board_changes(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            write_inflight_marker(paths, _FANOUT_ID, "core", _fields())
            write_inflight_marker(paths, _FANOUT_ID, "docs", _fields(run_ref="run-docs"))
            board = read_running_work_board(paths.omh_home)
            write_inflight_marker(paths, _FANOUT_ID, "tests", _fields(run_ref="run-tests"))
            grown_board = read_running_work_board(paths.omh_home)
            self.assertNotEqual(
                running_work_board_fingerprint(board),
                running_work_board_fingerprint(grown_board),
            )

    def test_a_recorded_emission_is_read_back(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            write_inflight_marker(paths, _FANOUT_ID, "core", _fields())
            write_inflight_marker(paths, _FANOUT_ID, "docs", _fields(run_ref="run-docs"))
            board = read_running_work_board(paths.omh_home)
            fingerprint = running_work_board_fingerprint(board)
            self.assertEqual(last_running_work_board_fingerprint(paths.omh_home), "")
            record_running_work_board_emission(paths.omh_home, byte_count=120, fingerprint=fingerprint)
            self.assertEqual(last_running_work_board_fingerprint(paths.omh_home), fingerprint)


class PreLlmCallAutoSurfaceTests(unittest.TestCase):
    """Whether `pre_llm_call` surfaces the board on its own, without a keyword match."""

    def setUp(self) -> None:
        awareness_module._awareness_context_matches_message_cached.cache_clear()
        awareness_module._awareness_route_hint_cached.cache_clear()

    def test_no_markers_produce_no_block(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            result = pre_llm_call(
                omh_home=str(paths.omh_home),
                hermes_home=str(paths.hermes_home),
                user_message="tell me a short joke about a lighthouse keeper",
                is_first_turn=False,
            )
            self.assertIsNone(result)

    def test_one_running_unit_stays_below_the_threshold(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            write_inflight_marker(paths, _FANOUT_ID, "core", _fields())
            result = pre_llm_call(
                omh_home=str(paths.omh_home),
                hermes_home=str(paths.hermes_home),
                user_message="tell me a short joke about a single sleepy cat",
                is_first_turn=False,
            )
            self.assertIsNone(result)

    def test_two_running_units_surface_a_block_with_both_rows(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            write_inflight_marker(paths, _FANOUT_ID, "core", _fields())
            write_inflight_marker(paths, _FANOUT_ID, "docs", _fields(run_ref="run-docs"))
            result = pre_llm_call(
                omh_home=str(paths.omh_home),
                hermes_home=str(paths.hermes_home),
                user_message="tell me a short joke about two racing snails",
                is_first_turn=False,
            )
            self.assertIsNotNone(result)
            context = str(result["context"])
            self.assertIn("Running coding work: 2 running of 2 observed", context)
            self.assertIn("fanout-0123456789ab/core", context)
            self.assertIn("fanout-0123456789ab/docs", context)

    def test_an_unchanged_board_is_suppressed_on_the_second_call(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = _paths(Path(tmp))
            write_inflight_marker(paths, _FANOUT_ID, "core", _fields())
            write_inflight_marker(paths, _FANOUT_ID, "docs", _fields(run_ref="run-docs"))
            call_kwargs = {
                "omh_home": str(paths.omh_home),
                "hermes_home": str(paths.hermes_home),
                "user_message": "tell me a short joke about a patient turtle",
                "is_first_turn": False,
            }

            first = pre_llm_call(**call_kwargs)
            self.assertIsNotNone(first)
            self.assertIn("Running coding work", str(first["context"]))

            second = pre_llm_call(**call_kwargs)
            self.assertIsNone(second)


if __name__ == "__main__":
    unittest.main()
