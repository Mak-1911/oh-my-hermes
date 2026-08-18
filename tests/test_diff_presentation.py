"""Contracts for the full-width diff band transform.

`transform_tool_result` pads painted diff lines (+/-) with trailing spaces to
the block's widest line measured in terminal cells, so the TUI's text-run
background renders as one uniform rectangle. Anything that is not clearly a
diff passes through untouched (None), because the seam replaces the result
the model reads too.
"""

import json
import unittest

from omh.plugin_bundle.omh.hooks.diff_presentation import (
    MAX_BAND_CELLS,
    pad_diff_lines,
    transform_tool_result,
)

DIFF = (
    "--- a/plan.md\n"
    "+++ b/plan.md\n"
    "@@ -1,2 +1,2 @@\n"
    " context stays\n"
    "-short\n"
    "+the replacement line is much longer\n"
)


class PadDiffLinesTest(unittest.TestCase):
    def test_painted_lines_align_to_the_widest_line(self):
        padded = pad_diff_lines(DIFF).splitlines()
        widths = {len(line) for line in padded if line.startswith(("+", "-"))}
        self.assertEqual(len(widths), 1)
        self.assertEqual(widths.pop(), len("+the replacement line is much longer"))

    def test_context_and_hunk_lines_are_untouched(self):
        padded = pad_diff_lines(DIFF).splitlines()
        self.assertIn(" context stays", padded)
        self.assertIn("@@ -1,2 +1,2 @@", padded)

    def test_wide_characters_count_as_two_cells(self):
        # Band = the widest line in CELLS, hunk header included (11 here).
        # "-가나다" is 1 + 3*2 = 7 cells → +4 spaces; "+abcdef" is 7 cells →
        # +4 spaces. Counting characters instead of cells would have given
        # the CJK line 6 spaces and misaligned the band.
        diff = "@@ -1 +1 @@\n-가나다\n+abcdef\n"
        padded = pad_diff_lines(diff).splitlines()
        self.assertEqual(padded[1], "-가나다" + " " * 4)
        self.assertEqual(padded[2], "+abcdef" + " " * 4)

    def test_the_band_is_capped(self):
        diff = "@@ -1 +1 @@\n-" + "x" * 500 + "\n+short\n"
        lines = pad_diff_lines(diff).splitlines()
        self.assertEqual(len(lines[2]), MAX_BAND_CELLS)


class TransformToolResultTest(unittest.TestCase):
    def test_a_json_result_with_a_diff_field_is_padded_in_place(self):
        result = json.dumps({"success": True, "diff": DIFF}, ensure_ascii=False)
        transformed = transform_tool_result(result=result)
        self.assertIsNotNone(transformed)
        parsed = json.loads(transformed)
        self.assertTrue(parsed["success"])
        widths = {
            len(line)
            for line in parsed["diff"].splitlines()
            if line.startswith(("+", "-"))
        }
        self.assertEqual(len(widths), 1)

    def test_a_plain_unified_diff_result_is_padded(self):
        transformed = transform_tool_result(result=DIFF)
        self.assertIsNotNone(transformed)
        self.assertTrue(transformed.startswith("--- a/plan.md"))

    def test_non_diff_results_pass_through(self):
        self.assertIsNone(transform_tool_result(result=json.dumps({"output": "ok"})))
        self.assertIsNone(transform_tool_result(result="plain text with no markers"))
        self.assertIsNone(transform_tool_result(result=None))

    def test_an_already_uniform_diff_returns_none(self):
        uniform = "@@ -1 +1 @@\n-aaaa\n+bbbb\n"
        # Band is the hunk header (11 cells); painted lines gain padding on
        # the first pass and the padded text is then stable.
        first = transform_tool_result(result=uniform)
        self.assertIsNotNone(first)
        self.assertIsNone(transform_tool_result(result=first))

    def test_a_json_result_without_a_real_diff_passes_through(self):
        result = json.dumps({"diff": "not really --- a diff"})
        self.assertIsNone(transform_tool_result(result=result))


if __name__ == "__main__":
    unittest.main()
