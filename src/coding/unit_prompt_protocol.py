"""Verification discipline for prepared fanout unit prompts.

Three deterministic text blocks ride every dispatched unit prompt:

1. **Goal echo-back** — before any tool use the subagent restates the goal,
   its own deliverable, and the completion criteria, and stops to report (not
   guess) if its reading conflicts with the declared boundary.
2. **Pre-declared completion criteria** — "done" is defined BEFORE work
   starts, as a numbered list derived from the unit contract, so completion
   is a check against stated criteria rather than a feeling.
3. **Verification stop conditions** — verification is mandatory (exactly one
   full pass is the floor, never skipped) and bounded (after the criteria
   pass, re-verifying is forbidden; on failure, at most two fix-and-verify
   cycles before reporting the failing criterion instead of looping).

High-effort routes additionally get a per-family calibration block that
counters the known over-verification inertia of strong reasoning models.
Calibration is keyed by model family and selected only when the routed
reasoning effort is in the high tier; families the table has not met get the
generic block — no family carries richer guidance than another without a
stated reason, and no vendor is privileged.

Everything here is pure data and pure functions: the blocks land in prepared
prompts (subprocess argv), so the total prompt size is policy-gated by
`UNIT_PROMPT_MAX_BYTES` in tests rather than trimmed at runtime.
"""

from __future__ import annotations

from typing import Any, Final, Mapping

# Policy ceiling for a fully-assembled unit prompt (bytes of UTF-8). The
# worst-case combination across roles, owners, and calibration blocks is
# asserted under this in tests; runtime never truncates.
UNIT_PROMPT_MAX_BYTES: Final[int] = 8000

# Reasoning efforts that mark a route as high-effort for calibration purposes.
HIGH_EFFORT_TIER: Final[frozenset[str]] = frozenset({"high", "xhigh", "max"})

GOAL_ECHO_PROTOCOL: Final[str] = (
    "Before your first tool use, restate in your own words: (1) the overall goal in one sentence, "
    "(2) this unit's deliverable, and (3) the numbered completion criteria below. If your restatement "
    "conflicts with the declared boundary or criteria, stop and report the conflict instead of guessing."
)

VERIFICATION_STOP_PROTOCOL: Final[str] = (
    "Verification discipline: run exactly ONE full verification pass against the numbered criteria after "
    "finishing the work — verification is never skipped. A check failure blocks completion only when it "
    "violates a stated criterion; note anything else as an observation and move on. Once every criterion "
    "has passed, STOP: do not re-verify, do not add a just-to-be-sure pass, and do not restart verification "
    "after edits that no criterion covers. If a criterion still fails after two fix-and-verify cycles, "
    "commit what passes and report the failing criterion with its output instead of looping."
)

REVIEW_ROLE_PROTOCOL: Final[str] = (
    "Review discipline: a finding blocks only when it violates a stated success criterion of the reviewed "
    "work; list every other finding as non-blocking. Cap re-review at two rounds — after that, report the "
    "remaining criterion-cited blockers rather than starting another round."
)

# Per-family counters to the over-verification inertia of high-effort routes.
# Keyed by `model_family()` output; "generic" is the mandatory fallback so an
# unknown family never gets weaker discipline than a known one.
HIGH_EFFORT_CALIBRATIONS: Final[dict[str, str]] = {
    "gpt": (
        "High-effort calibration: your reasoning depth is for the hard parts of THIS unit, not for "
        "re-deriving settled facts. Once the decisive fact is in view, act on it; once a criterion has "
        "passed, it is settled evidence — reopen it only when new output contradicts it, never to "
        "reassure yourself."
    ),
    "claude": (
        "High-effort calibration: follow the numbered criteria as the complete checklist — do not grow "
        "the checklist mid-run. Deliberate deeply only where correctness is genuinely at risk; for "
        "mechanical steps, act directly and let the single verification pass prove them."
    ),
    "generic": (
        "High-effort calibration: reserve extended reasoning for genuine ambiguity with materially "
        "different outcomes. Decide once, act, verify once against the criteria, and stop — speed is "
        "never a reason to skip the verification pass, and thoroughness is never a reason to repeat it."
    ),
}


def completion_criteria_for_unit(unit: Mapping[str, Any]) -> list[str]:
    """Return the pre-declared, numbered 'done means' criteria for one unit.

    Derived deterministically from the frozen unit contract: boundary
    confinement and committed work are always criteria; the contract's
    integration checks become the unit-specific ones.
    """
    boundary = unit.get("boundary", {}) if isinstance(unit.get("boundary"), Mapping) else {}
    file_scope = ", ".join(str(path) for path in boundary.get("file_scope", []))
    criteria = [f"Every edit stays inside: {file_scope}." if file_scope else "Every edit stays inside the declared file scope."]
    for check in unit.get("integration_checks", []) or []:
        text = str(check).strip()
        if text:
            criteria.append(text[0].upper() + text[1:] if text[0].islower() else text)
    criteria.append("The work is committed on the unit branch; nothing else is merged or pushed.")
    return criteria


def calibration_for_route(model_route: Mapping[str, Any] | None) -> str:
    """Return the high-effort calibration block for a routed unit, or ''.

    Selected only when the route's effective reasoning effort is in the high
    tier; family comes from the already-recorded `model_family` (falling back
    to generic for unknown/blank families).
    """
    if not isinstance(model_route, Mapping):
        return ""
    effort = str(model_route.get("selected_reasoning_effort", "") or "").casefold()
    if effort not in HIGH_EFFORT_TIER:
        return ""
    family = str(model_route.get("model_family", "") or "").casefold()
    return HIGH_EFFORT_CALIBRATIONS.get(family, HIGH_EFFORT_CALIBRATIONS["generic"])


def unit_protocol_lines(unit: Mapping[str, Any]) -> list[str]:
    """Return the ordered protocol lines appended to a unit prompt."""
    criteria = completion_criteria_for_unit(unit)
    lines = [GOAL_ECHO_PROTOCOL, "Done means, and only means:"]
    lines.extend(f"{index}. {criterion}" for index, criterion in enumerate(criteria, start=1))
    lines.append(VERIFICATION_STOP_PROTOCOL)
    handoff = unit.get("handoff", {}) if isinstance(unit.get("handoff"), Mapping) else {}
    model_route = handoff.get("model_route") if isinstance(handoff.get("model_route"), Mapping) else None
    # Contract units carry the declared role inside the recorded route, not as
    # a top-level key; accept both so pre-contract unit dicts behave the same.
    role = str(unit.get("role", "") or "") or (str(model_route.get("role", "") or "") if model_route else "")
    if role == "review":
        lines.append(REVIEW_ROLE_PROTOCOL)
    calibration = calibration_for_route(model_route)
    if calibration:
        lines.append(calibration)
    return lines
