from __future__ import annotations

import unittest

from _local_package import load_local_package

load_local_package()
from omh.commands.main import build_parser


class MemoryParserTests(unittest.TestCase):
    def test_new_memory_control_commands_parse_with_explicit_gates(self) -> None:
        cases = (
            (["memory", "inventory"], "cmd_memory_inventory"),
            (["memory", "inventory", "--write-ledger"], "cmd_memory_inventory"),
            (["memory", "reactivate", "legacy-record", "--revision", "1", "--review-id", "review-record"], "cmd_memory_reactivate"),
            (["memory", "batch-stage", "--batch", "batch.json"], "cmd_memory_batch_stage"),
            (["memory", "batch-review", "batch-one", "--decisions", "decisions.json"], "cmd_memory_batch_review"),
            (["memory", "batch-apply", "batch-one", "--apply"], "cmd_memory_batch_apply"),
            (["memory", "restore", "record-one", "--revision", "1"], "cmd_memory_restore"),
            (["memory", "prune", "record-one", "--revision", "1", "--apply", "--confirm-hard-delete-local"], "cmd_memory_prune"),
            (["memory", "correct", "record-one", "--revision", "1", "Corrected summary"], "cmd_memory_correct"),
        )

        for argv, handler_name in cases:
            with self.subTest(argv=argv):
                args = build_parser().parse_args(argv)
                self.assertEqual(args.func.__name__, handler_name)

    def test_memory_capture_rejects_invalid_source_class_at_parser_boundary(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            build_parser().parse_args(["memory", "capture", "--source-class", "unknown", "summary"])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
