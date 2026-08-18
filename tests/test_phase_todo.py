"""Contracts for the phase-structured todo (todo init) surfaces.

A plan declared before engine work bounds the run: phases with tasks, one
active item, HUD shows the current phase's checklist. These tests pin the
store's optional `phase` field, the current-phase selection in the HUD
projection, and the unphased fallback.
"""

import tempfile
import unittest
from pathlib import Path

from omh.plugin_bundle.omh.runtime_reader import read_omh_hud
from omh.plugin_bundle.omh.todo_store import (
    MAX_TODO_PHASE_CHARS,
    TodoValidationError,
    build_todo_record,
    validate_todo_items,
    write_todo,
)

PHASED_ITEMS = [
    {"text": "Inventory repositories", "state": "active", "phase": "Internal Context"},
    {"text": "Identify evaluation data", "state": "pending", "phase": "Internal Context"},
    {"text": "Define comparison workflow", "state": "pending", "phase": "Product Fit"},
    {"text": "Select MVP boundary", "state": "pending", "phase": "Product Fit"},
    {"text": "Present product direction", "state": "pending", "phase": "Delivery"},
]


def _projected_todo(items):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "omh").mkdir()
        (root / "hermes").mkdir()
        write_todo(root / "omh", build_todo_record("init", items, source="test"))
        return read_omh_hud(root / "omh", root / "hermes")["todo"]


class PhaseFieldStoreTest(unittest.TestCase):
    def test_the_phase_field_is_optional_and_absent_when_empty(self):
        validated = validate_todo_items([{"text": "task", "phase": ""}])
        self.assertEqual(validated, [{"text": "task", "state": "pending"}])

    def test_a_phase_is_kept_control_stripped(self):
        validated = validate_todo_items([{"text": "task", "phase": "Inter\x1bnal"}])
        self.assertEqual(validated[0]["phase"], "Internal")

    def test_an_oversized_phase_is_refused(self):
        with self.assertRaises(TodoValidationError):
            validate_todo_items([{"text": "task", "phase": "x" * (MAX_TODO_PHASE_CHARS + 1)}])


class PhaseProjectionTest(unittest.TestCase):
    def test_the_current_phase_is_the_one_holding_the_active_item(self):
        todo = _projected_todo(PHASED_ITEMS)
        self.assertEqual(todo["status"], "established")
        self.assertEqual(todo["counts"]["phases"], 3)
        self.assertEqual(todo["display_phase"], "Internal Context")
        self.assertEqual(
            [item["text"] for item in todo["display_items"]],
            ["Inventory repositories", "Identify evaluation data"],
        )
        # +N more covers the remaining work in later phases.
        self.assertEqual(todo["more_count"], 3)

    def test_a_finished_phase_advances_the_display_to_the_next_phase_with_work(self):
        items = [dict(item) for item in PHASED_ITEMS]
        items[0]["state"] = "done"
        items[1]["state"] = "done"
        items[2]["state"] = "active"
        todo = _projected_todo(items)
        self.assertEqual(todo["display_phase"], "Product Fit")
        self.assertEqual(
            [item["text"] for item in todo["display_items"]],
            ["Define comparison workflow", "Select MVP boundary"],
        )

    def test_an_unphased_plan_keeps_the_flat_collapse(self):
        todo = _projected_todo(
            [
                {"text": "one", "state": "done"},
                {"text": "two", "state": "active"},
                {"text": "three", "state": "pending"},
            ]
        )
        self.assertEqual(todo["display_phase"], "")
        self.assertEqual(todo["counts"]["phases"], 0)
        self.assertEqual(
            [item["text"] for item in todo["display_items"]], ["one", "two", "three"]
        )


if __name__ == "__main__":
    unittest.main()
