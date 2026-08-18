"""Full-width diff bands via the Hermes ``transform_tool_result`` seam.

The Hermes TUI paints diff add/delete lines with a text-run background, so
the colored band ends wherever each line's text ends — a ragged highlighter
look the owner rejected. The fill geometry is renderer-owned and OMH never
patches Hermes, but Hermes ships an explicit canonicalization seam for
exactly this: ``transform_tool_result`` receives the final tool-result
string and may replace it.

OMH's transform pads every painted diff line (``+``/``-``) with trailing
spaces to the diff block's widest line, measured in TERMINAL CELLS (East
Asian wide characters occupy two), so the text-run background renders as one
uniform rectangle. Content is unchanged beyond trailing whitespace — the
diff still applies, the model reads the same change — and any parse doubt
returns ``None`` so the result passes through untouched (the seam is
fail-open by contract).
"""

from __future__ import annotations

import json
from typing import Any

# Padding stops at this cell width: lines wider than the cap wrap in the TUI
# anyway, and padding everything to a pathological outlier would bloat every
# other line. A capped block still reads as a uniform band for normal diffs.
MAX_BAND_CELLS = 160

_PAINTED_PREFIXES = ("+", "-")


def _cell_width(text: str) -> int:
    """Terminal cell width with the same wide ranges the HUD widget uses."""
    width = 0
    for char in text:
        code = ord(char)
        wide = code >= 0x1100 and (
            code <= 0x115F
            or code in (0x2329, 0x232A)
            or 0x2E80 <= code <= 0xA4CF
            or 0xAC00 <= code <= 0xD7A3
            or 0xF900 <= code <= 0xFAFF
            or 0xFE10 <= code <= 0xFE6F
            or 0xFF00 <= code <= 0xFF60
            or 0xFFE0 <= code <= 0xFFE6
        )
        width += 2 if wide else 1
    return width


def _looks_like_diff(text: str) -> bool:
    lines = text.splitlines()
    has_hunk = any(line.startswith("@@") for line in lines)
    has_marker = any(line.startswith(("--- ", "+++ ")) for line in lines)
    painted = sum(1 for line in lines if line.startswith(_PAINTED_PREFIXES))
    return (has_hunk or has_marker) and painted >= 2


def pad_diff_lines(text: str) -> str:
    """Pad painted diff lines to the block's widest line, in cells."""
    lines = text.splitlines()
    band = min(
        MAX_BAND_CELLS,
        max((_cell_width(line) for line in lines), default=0),
    )
    padded = []
    for line in lines:
        if line.startswith(_PAINTED_PREFIXES):
            gap = band - _cell_width(line)
            padded.append(line + " " * gap if gap > 0 else line)
        else:
            padded.append(line)
    trailer = "\n" if text.endswith("\n") else ""
    return "\n".join(padded) + trailer


def transform_tool_result(**kwargs: Any) -> str | None:
    """Return a padded replacement result, or ``None`` to leave it alone."""
    result = kwargs.get("result")
    if not isinstance(result, str) or "@@" not in result and "--- " not in result:
        return None
    try:
        parsed = json.loads(result)
    except (ValueError, TypeError):
        parsed = None
    if isinstance(parsed, dict):
        diff = parsed.get("diff")
        if not isinstance(diff, str) or not _looks_like_diff(diff):
            return None
        padded = pad_diff_lines(diff)
        if padded == diff:
            return None
        parsed["diff"] = padded
        try:
            return json.dumps(parsed, ensure_ascii=False)
        except (TypeError, ValueError):
            return None
    if _looks_like_diff(result):
        padded = pad_diff_lines(result)
        return padded if padded != result else None
    return None
