"""The message gate: the provenance header OMH renders into a messenger body.

``messenger_rendering`` (``src/wrapper/contract.py``) is the SHAPE gate. It
decides chunk ceilings, Slack mrkdwn dialect, tables-to-bullets, and fence
handling, and it says nothing about WHAT a delegated response must disclose.
This module is the CONTENT gate for the same body: which skill ran, which model
and reasoning effort it ran on, what evidence class the answer belongs to, and
which prompt produced it.

Why render it here instead of asking for it. ``DELEGATE_MODEL_LABEL_RULE`` and
``DELEGATE_PROMPT_DISPLAY_RULE`` in ``src/skills/catalog_types.py`` already
state the ``(model effort)`` and fenced-prompt disciplines, but ``render.py``
gates that block to handoff-shaped skills, so it reaches 7 of 103 skill bodies,
and nothing anywhere checks that an agent actually emitted either shape. A
prose rule that no surface validates is a hope.
``goal_ledger.build_goal_status_card`` already reached the same conclusion
once, for one payload, after a live Slack session rendered a markdown table
that the surface silently dropped: it now hands back exact ``checkpoint_lines``
plus a ``render_guidance`` sentence. This module generalizes that one-off.

The gate fixes the header and the prompt block, and nothing else. The response
body stays free prose, and every field degrades to the literal ``unknown``
rather than being dropped or invented -- an absent model is a fact worth
printing, and an empty ``()`` is the one shape the rule names as forbidden.
"""

from __future__ import annotations

from typing import Any, Final

from ..coding.context_safety import bounded_prompt_preview
from ..coding.status_board import model_label_for

MESSAGE_GATE_SCHEMA_VERSION: Final[str] = "omh_message_gate/v1"

UNKNOWN: Final[str] = "unknown"

# Profiles are the two the shape gate already resolves; the gate switches on
# them rather than on the platform so a new source needs no change here.
RENDER_PROFILE_LIMITED_MARKDOWN: Final[str] = "limited_markdown"
RENDER_PROFILE_RICH_MARKDOWN: Final[str] = "rich_markdown"

# Field order and the MODEL/STATUS labels match `_COLUMNS` in
# `src/coding/status_board.py`: identity, then model, then status. A reader who
# has seen the status board should not have to learn a second vocabulary for
# the same four facts.
_FIELDS: Final[tuple[tuple[str, str], ...]] = (
    ("SKILL", "skill"),
    ("MODEL", "model"),
    ("STATUS", "status"),
    ("TASK", "task"),
    ("PROMPT", "prompt"),
)

_ROSTER_COLUMNS: Final[tuple[tuple[str, str], ...]] = (
    ("UNIT", "label"),
    ("MODEL", "model"),
    ("STATUS", "status"),
    ("TIME", "elapsed"),
)

# Bounded so a long skill name or a pasted model id cannot push the header past
# the tightest messenger ceiling on its own.
_VALUE_LIMIT: Final[int] = 96
# The PROMPT row carries a digest prefix, never the prompt. Twelve hex
# characters is what `omh coding fanout` already prints for a unit ref.
_DIGEST_PREFIX: Final[int] = 12
# A roster longer than this is a status-board question, not a header. Six is
# not arbitrary: the limited profile renders one bullet per field plus one per
# unit, and `messenger_rendering.density_policy` declares `max_bullets: 12`.
# Five fields + six units + the truncation line lands exactly on that ceiling,
# so the gate obeys the density policy OMH already publishes instead of being
# the first surface to break it.
_ROSTER_LIMIT: Final[int] = 6
# How much of the composed prompt the follow-on message shows. Long enough to
# recognize the order Hermes actually issued, short enough that the block stays
# well inside Discord's 1700-character soft ceiling next to a header.
PROMPT_PREVIEW_CHARS: Final[int] = 200

PROMPT_BLOCK_TITLE: Final[str] = "HERMES PROMPTING"

WARNING_MISSING_MODEL_LABEL: Final[str] = "message_gate_missing_model_label"
WARNING_EMPTY_PARENTHESES: Final[str] = "message_gate_empty_parentheses"
WARNING_MISSING_STATUS: Final[str] = "message_gate_missing_status"
WARNING_MISSING_PROMPT_REFERENCE: Final[str] = "message_gate_missing_prompt_reference"

# Rendered once under the header, mirroring `goal_status_card.render_guidance`:
# the gate hands back exact lines, so an agent relaying them has no formatting
# decision left to get wrong.
RENDER_GUIDANCE: Final[str] = (
    "Render the provided gate lines verbatim, in order, above the response body, and post "
    "prompt_block as its own follow-on message. Never restate either as a markdown table: "
    "messenger surfaces drop tables."
)


def fence_marker_for(text: str) -> str:
    """Backtick fence for embedding ``text``: one longer than the longest
    backtick run inside it, minimum three, so embedded ``` fences nest safely."""
    longest = 0
    run = 0
    for character in text:
        if character == "`":
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return "`" * max(3, longest + 1)


def build_message_gate(
    *,
    skill: str = "",
    executor: str = "",
    model: str = "",
    reasoning_effort: str = "",
    model_label: str = "",
    status: str = "",
    task: str = "",
    prompt_sha256: str = "",
    prompt_chars: Any = None,
    composed_prompt: str = "",
    units: object = (),
) -> dict[str, Any]:
    """Project one response's execution provenance into a gate payload.

    ``model_label`` wins when a caller already resolved the label through the
    status-board convention (``_status_model_label``); otherwise the label is
    composed here from ``model`` plus ``reasoning_effort`` so both entry points
    produce the identical string.

    ``task`` and ``composed_prompt`` are the caller's decision, not this
    module's: the chat envelope declares ``redaction_policy: metadata_only``
    unless the wrapper opted into ``include_message``, so a caller that has not
    opted in passes ``""`` and those surfaces are omitted. An omitted row is not
    an unknown one -- the fact was never admitted to this surface, so printing
    ``unknown`` would misdescribe a redaction as a gap.
    """
    resolved_label = str(model_label or "").strip()
    if not resolved_label and (str(model or "").strip() or str(reasoning_effort or "").strip()):
        resolved_label = model_label_for(model, reasoning_effort)
    fields: dict[str, str] = {
        "skill": _bounded(skill) or UNKNOWN,
        "model": _model_field(executor, resolved_label),
        "status": _bounded(status) or UNKNOWN,
        "prompt": _prompt_reference(prompt_sha256, prompt_chars),
    }
    bounded_task = _bounded(task)
    if bounded_task:
        fields["task"] = bounded_task
    payload: dict[str, Any] = {
        "schema_version": MESSAGE_GATE_SCHEMA_VERSION,
        "fields": fields,
        "field_order": [key for _, key in _FIELDS if key in fields],
        "render_guidance": RENDER_GUIDANCE,
    }
    roster = _normalize_units(units)
    if roster:
        payload["roster"] = roster
        payload["roster_count"] = len(roster)
        # The observed total, not the rendered count: a reader must be able to
        # tell a complete roster from a capped one without opening the board.
        payload["roster_total"] = _unit_total(units)
    prompt_block = _prompt_block(composed_prompt, fields["model"])
    if prompt_block:
        payload["prompt_block"] = prompt_block
    payload["warnings"] = message_gate_warnings(payload)
    return payload


def render_message_gate_lines(
    payload: dict[str, Any], *, render_profile: str = RENDER_PROFILE_LIMITED_MARKDOWN
) -> list[str]:
    """The exact lines to print above a response body, one per element.

    ``rich_markdown`` gets an aligned block inside a single fence, because
    alignment is the whole reason a fence is worth its vertical cost, and two
    adjacent fences read as a rendering fault rather than as two sections.
    ``limited_markdown`` gets flat bullets -- the same branch
    ``status_board_messenger_body`` already makes, and for the same reason: a
    monospace block shrinks the font on a narrow phone client, where the header
    is read most.
    """
    fields = _fields(payload)
    if not fields:
        return []
    rows = _roster_rows(payload)
    omission = _roster_omission_line(payload, rows)
    if render_profile == RENDER_PROFILE_RICH_MARKDOWN:
        block = _aligned_pairs(fields, payload)
        if rows:
            block = [*block, "", *_aligned_roster(rows)]
            if omission:
                block.append(omission)
        return ["```", *block, "```"]
    labels = {key: label for label, key in _FIELDS}
    lines = [
        f"- {labels[key].lower()} — {fields[key]}"
        for key in _field_order(payload)
        if key in fields
    ]
    lines.extend(
        f"- {row['label']} — {row['model']} — {row['status']} — {row['elapsed']}" for row in rows
    )
    if omission:
        lines.append(f"- {omission}")
    return lines


def message_gate_body(
    payload: dict[str, Any],
    *,
    render_profile: str = RENDER_PROFILE_LIMITED_MARKDOWN,
    body: str = "",
) -> str:
    """The gate lines joined above ``body``, or ``body`` unchanged when empty."""
    lines = render_message_gate_lines(payload, render_profile=render_profile)
    if not lines:
        return body
    header = "\n".join(lines)
    return f"{header}\n\n{body}" if body else header


def message_gate_messages(
    payload: dict[str, Any],
    *,
    render_profile: str = RENDER_PROFILE_LIMITED_MARKDOWN,
    body: str = "",
) -> list[str]:
    """Ordered messages an adapter posts: the header+body, then the prompt block.

    The prompt block is a separate message rather than more of the first one
    because it answers a different question ("what was actually ordered?") and
    because a fenced block appended to a status body is the shape that pushes a
    Discord message over its ceiling and gets split at an arbitrary point.
    """
    messages = [message_gate_body(payload, render_profile=render_profile, body=body)]
    block = str(payload.get("prompt_block", "") or "")
    if block:
        messages.append(block)
    return [message for message in messages if message]


def message_gate_warnings(payload: dict[str, Any]) -> list[str]:
    """Name the shapes that broke the disclosure rule, without refusing them.

    Warnings, not errors, for the reason ``native_commands._unsafe_rendering_warnings``
    gives: a response that discloses less than it should is still a response the
    user is waiting on. What must not happen is that it degrades silently.
    """
    fields = _fields(payload)
    warnings: list[str] = []
    model = fields.get("model", "")
    if not model or model == UNKNOWN:
        warnings.append(WARNING_MISSING_MODEL_LABEL)
    if "()" in model:
        warnings.append(WARNING_EMPTY_PARENTHESES)
    if fields.get("status", UNKNOWN) == UNKNOWN:
        warnings.append(WARNING_MISSING_STATUS)
    if fields.get("prompt", UNKNOWN) == UNKNOWN:
        warnings.append(WARNING_MISSING_PROMPT_REFERENCE)
    for row in _roster_rows(payload):
        label = row.get("model", "")
        if not label or label == UNKNOWN or "()" in label:
            warnings.append(WARNING_MISSING_MODEL_LABEL)
            break
    return sorted(set(warnings))


def _prompt_block(composed_prompt: str, model_field: str) -> str:
    """The composed order Hermes issued, bounded and fenced, or "" when absent.

    Bounded through ``bounded_prompt_preview`` so the truncation marker is the
    exact ``... [truncated, N chars total]`` shape ``DELEGATE_PROMPT_DISPLAY_RULE``
    promises, and fenced through a content-derived marker so a prompt that
    itself contains a fence still nests.
    """
    text = str(composed_prompt or "").strip()
    if not text:
        return ""
    preview = bounded_prompt_preview(text, max_chars=PROMPT_PREVIEW_CHARS)
    fence = fence_marker_for(preview)
    title = PROMPT_BLOCK_TITLE
    if model_field and model_field != UNKNOWN:
        title = f"{title} — {model_field}"
    return "\n".join([title, fence, preview, fence])


def _model_field(executor: str, model_label: str) -> str:
    """``codex (gpt-5-codex xhigh)`` -- executor and model as ONE visual field.

    The parenthetical is never emitted empty: ``DELEGATE_MODEL_LABEL_RULE``
    names that exact shape as forbidden. A known executor with no resolved route
    is ``codex (executor default)``, which is what the status board already
    prints; knowing neither is ``unknown``, not a default label OMH cannot back.
    """
    owner = _bounded(executor)
    label = _bounded(model_label)
    if not owner:
        return label or UNKNOWN
    return f"{owner} ({label or model_label_for('', '')})"


def _prompt_reference(prompt_sha256: str, prompt_chars: Any) -> str:
    """``sha256:533d406a4863 · 412 chars`` -- a reference, never the prompt.

    OMH deliberately does not persist the raw task (``_composed_prompt_handoff_text``),
    and the chat envelope's ``metadata_only`` redaction policy says the same
    about echoing it. A digest plus a length still answers "is this the prompt I
    typed?" without carrying the content.
    """
    digest = "".join(
        character for character in str(prompt_sha256 or "").strip() if character.isalnum()
    )
    if not digest:
        return UNKNOWN
    reference = f"sha256:{digest[:_DIGEST_PREFIX]}"
    if isinstance(prompt_chars, int) and not isinstance(prompt_chars, bool) and prompt_chars >= 0:
        return f"{reference} · {prompt_chars} chars"
    return reference


def _normalize_units(units: object) -> list[dict[str, str]]:
    """Normalize parallel lanes into the board's own row vocabulary.

    Shape matches ``_fanout_brief_unit_line``'s join order so a roster line and
    an ``omh coding fanout brief`` line describe a unit the same way. Called
    once, at build time; readers use ``_roster_rows`` and never re-normalize.
    """
    if not isinstance(units, (list, tuple)):
        return []
    rows: list[dict[str, str]] = []
    for unit in units[:_ROSTER_LIMIT]:
        if not isinstance(unit, dict):
            continue
        label = _bounded(unit.get("label", "") or unit.get("unit_id", ""))
        if not label:
            continue
        model_label = str(unit.get("model_label", "") or "").strip()
        model = str(unit.get("model", "") or "").strip()
        effort = str(unit.get("reasoning_effort", "") or "").strip()
        # Same guard the header field needs: `model_label_for` answers
        # `executor default` for empty input, which is a claim about a resolved
        # executor. A lane that reported neither owner nor model has nothing to
        # default, so it must stay unknown and raise the warning.
        if not model_label and (model or effort):
            model_label = model_label_for(model, effort)
        rows.append(
            {
                "label": label,
                "model": _model_field(
                    str(unit.get("owner", "") or unit.get("runtime", "") or ""), model_label
                ),
                "status": _bounded(unit.get("status", "")) or UNKNOWN,
                "elapsed": _bounded(unit.get("elapsed_text", "")) or UNKNOWN,
            }
        )
    return rows


def _unit_total(units: object) -> int:
    if not isinstance(units, (list, tuple)):
        return 0
    return sum(1 for unit in units if isinstance(unit, dict) and (unit.get("label") or unit.get("unit_id")))


def _roster_omission_line(payload: dict[str, Any], rows: list[dict[str, str]]) -> str:
    """State a capped roster as its own line, never silently.

    Same rule ``_fanout_brief_overflow_line`` follows: a truncated roster that
    does not say so reads as a complete one.
    """
    total = payload.get("roster_total")
    if not isinstance(total, int) or isinstance(total, bool):
        return ""
    omitted = total - len(rows)
    if omitted <= 0:
        return ""
    return f"… +{omitted} more units — omh coding status-board"


def _roster_rows(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Already-normalized roster rows straight off the payload.

    Deliberately not ``_normalize_units``: rows leave the builder keyed
    ``elapsed``, and re-running the raw-unit normalizer over them would look for
    ``elapsed_text``, find nothing, and silently rewrite every observed time to
    ``unknown``.
    """
    roster = payload.get("roster")
    if not isinstance(roster, (list, tuple)):
        return []
    rows: list[dict[str, str]] = []
    for row in roster:
        if not isinstance(row, dict):
            continue
        rows.append({key: str(row.get(key, "") or UNKNOWN) for _, key in _ROSTER_COLUMNS})
    return rows


def _aligned_pairs(fields: dict[str, str], payload: dict[str, Any]) -> list[str]:
    width = max(len(label) for label, key in _FIELDS if key in fields)
    order = _field_order(payload)
    labels = {key: label for label, key in _FIELDS}
    return [f"{labels[key].ljust(width)}  {fields[key]}" for key in order if key in fields]


def _aligned_roster(rows: list[dict[str, str]]) -> list[str]:
    widths = [
        max(len(header), *(len(row[key]) for row in rows)) for header, key in _ROSTER_COLUMNS
    ]
    lines = [
        "  ".join(header.ljust(widths[index]) for index, (header, _) in enumerate(_ROSTER_COLUMNS)).rstrip()
    ]
    lines.extend(
        "  ".join(row[key].ljust(widths[index]) for index, (_, key) in enumerate(_ROSTER_COLUMNS)).rstrip()
        for row in rows
    )
    return lines


def _fields(payload: dict[str, Any]) -> dict[str, str]:
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        return {}
    return {str(key): str(value) for key, value in fields.items() if str(value)}


def _field_order(payload: dict[str, Any]) -> list[str]:
    order = payload.get("field_order")
    if isinstance(order, (list, tuple)):
        return [str(key) for key in order]
    return [key for _, key in _FIELDS]


def _bounded(value: object) -> str:
    """Single-line and length-capped: a newline in a header breaks every row below it."""
    text = " ".join(str(value or "").split())
    if len(text) <= _VALUE_LIMIT:
        return text
    return f"{text[: _VALUE_LIMIT - 1].rstrip()}…"
