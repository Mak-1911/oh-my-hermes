"""Read-only per-unit roster for one fanout, projected from journal events.

This module observes; it never acts. It writes no state file, appends no
observation event, and offers no revive/steer/kill surface: a roster that could
restart a unit would be a control plane, and the only durable evidence this
layer trusts is what the dispatcher already recorded.

Only the observation journal is read. Executor stdout, dispatch summaries, and
in-flight markers are deliberately NOT consulted -- a summary is a report about
events, and a roster built from a report would echo a claim instead of
observing one. The unit rows therefore carry exactly what the journal knows:
which rung of the dispatch ladder has dispatcher-observed backing, who ran it,
where, how stale the last event is, and how many evidence refs it named.

Units are discovered through the `run_ref` convention frozen by
`build_fanout_contract` (`{fanout_id}-{unit_id}`, src/coding/fanout.py), so the
roster needs no contract read to know which runs belong to a fanout.

The journal is read in full, once, and never through `show_run`'s tail-bounded
view: that surface defaults to the last 20 events per run
(`DEFAULT_RUN_HISTORY_LIMIT`), and on a busy run the verification receipt is
exactly the event that falls off the end. A lifecycle conclusion drawn from a
tail would silently under-report a verified unit, so this projection reads every
event (the equivalent of `history_limit=None`) and pays one file read for the
whole roster instead of one per unit.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Mapping

from ..system.paths import OmhPaths
from ..workflows.observation_journal import (
    canonical_observation_event,
    project_run_lifecycle,
    read_observation_events_result,
)
from .fanout_contracts import FANOUT_ID_PATTERN

FANOUT_STATUS_SCHEMA_VERSION = "fanout_status_roster/v1"
FANOUT_STATUS_CLAIM_BOUNDARY = (
    "A fanout status roster projects dispatcher-observed journal events only. It is not verification, "
    "review, CI, merge-readiness, or merge evidence, and a unit's state never advances on an executor's "
    "own report."
)
# The ladder todo 3 froze for dispatch summaries, restated here as the roster's
# display vocabulary plus the two pre-success rungs a roster must be able to
# show: a unit nobody has dispatched yet, and one dispatched without an
# observed successful result.
FANOUT_UNIT_STATES = (
    "not_dispatched",
    "dispatched_not_succeeded",
    "process_succeeded",
    "result_schema_valid",
    "unit_verification_observed",
    "integration_ready",
)
_UNKNOWN = "unknown"

_FANOUT_ID_RE = re.compile(FANOUT_ID_PATTERN)
# Journal events that name a dispatched unit. `worker_dispatch` /
# `worker_result` are the legacy spellings; `canonical_observation_event`
# already folds them, so both journal generations land on the same rung.
_DISPATCH_EVENTS = ("executor_dispatch_observed", "worktree_creation_observed")
# Written by todo 6's sidecar intake. Absent from today's journals; folded here
# so a roster read after that lands reports the rung instead of skipping it.
_RESULT_VALIDATED_EVENT = "unit_result_validated"


def project_fanout_status(paths: OmhPaths, fanout_id: str) -> dict[str, Any]:
    """Project one fanout's unit roster from the observation journal.

    Raises `ValueError` naming the id when it is not a fanout id shape, or when
    the journal has never recorded a single event for it: a roster that silently
    rendered an empty table for a typo would report "nothing happened" for a
    fanout that does not exist.
    """
    validated_id = _validated_fanout_id(fanout_id)
    events, read_errors = read_observation_events_result(paths)
    fanout_events = [
        event for event in events if isinstance(event, Mapping) and _names_fanout(event, validated_id)
    ]
    if not fanout_events:
        raise ValueError(f"unknown fanout id: {validated_id} (no journal events name it)")

    events_by_unit: dict[str, list[dict[str, Any]]] = {}
    for event in fanout_events:
        unit_id = _unit_id_for_event(event, validated_id)
        if unit_id:
            events_by_unit.setdefault(unit_id, []).append(dict(event))

    units = [
        _unit_row(unit_id, events_by_unit[unit_id], validated_id)
        for unit_id in sorted(events_by_unit)
    ]
    _apply_merge_order_position(units)
    roster: dict[str, Any] = {
        "schema_version": FANOUT_STATUS_SCHEMA_VERSION,
        "fanout_id": validated_id,
        "unit_count": len(units),
        "units": units,
        "integration_ready_units": [
            unit["unit_id"] for unit in units if unit["lifecycle_state"] == "integration_ready"
        ],
        "journal_event_count": len(fanout_events),
        "claim_boundary": FANOUT_STATUS_CLAIM_BOUNDARY,
    }
    if read_errors:
        roster["journal_errors"] = read_errors
    return roster


def render_fanout_status_text(roster: Mapping[str, Any]) -> str:
    """Render the roster as plain English lines, one per unit."""
    fanout_id = str(roster.get("fanout_id", ""))
    units = [unit for unit in roster.get("units", []) if isinstance(unit, Mapping)]
    lines = [f"Fanout {fanout_id}: {len(units)} unit(s) observed in the journal."]
    if not units:
        lines.append("No unit events recorded yet; nothing has been dispatched under this fanout id.")
    for unit in units:
        lines.append(
            f"- {unit.get('unit_id', _UNKNOWN)}: {unit.get('lifecycle_state', _UNKNOWN)} "
            f"| owner {unit.get('owner', _UNKNOWN)} "
            f"| branch {unit.get('branch', _UNKNOWN)} "
            f"| worktree {unit.get('worktree_path', _UNKNOWN)} "
            f"| last event {unit.get('last_event', _UNKNOWN)} "
            f"{_age_phrase(unit.get('last_event_age_seconds'))} "
            f"| evidence refs {unit.get('evidence_ref_count', 0)}"
        )
    lines.append(str(roster.get("claim_boundary", FANOUT_STATUS_CLAIM_BOUNDARY)))
    return "\n".join(lines)


def _validated_fanout_id(value: object) -> str:
    fanout_id = str(value or "")
    if not _FANOUT_ID_RE.match(fanout_id):
        raise ValueError(f"invalid fanout id: {fanout_id!r} (expected {FANOUT_ID_PATTERN})")
    return fanout_id


def _names_fanout(event: Mapping[str, Any], fanout_id: str) -> bool:
    run_id = str(event.get("run_id", "") or event.get("target_id", ""))
    return run_id == fanout_id or run_id.startswith(f"{fanout_id}-")


def _unit_id_for_event(event: Mapping[str, Any], fanout_id: str) -> str:
    """The unit a journal event belongs to, or "" for fanout-level events.

    `worker_ref` is the current write site's field. Legacy events predate it, so
    the run id's frozen `{fanout_id}-{unit_id}` suffix is the fallback rather
    than a reason to drop the row.
    """
    worker_ref = str(event.get("worker_ref", "") or "")
    if worker_ref:
        return worker_ref
    run_id = str(event.get("run_id", "") or event.get("target_id", ""))
    prefix = f"{fanout_id}-"
    return run_id[len(prefix):] if run_id.startswith(prefix) else ""


def _unit_row(unit_id: str, events: list[dict[str, Any]], fanout_id: str) -> dict[str, Any]:
    ordered = sorted(events, key=lambda event: str(event.get("observed_at", "")))
    projection = project_run_lifecycle(ordered, run_id=f"{fanout_id}-{unit_id}")
    latest = ordered[-1]
    return {
        "unit_id": unit_id,
        "run_ref": f"{fanout_id}-{unit_id}",
        "lifecycle_state": _lifecycle_state(ordered, projection),
        "process_succeeded": bool(projection.get("execution_observed")),
        "result_schema_valid": _has_observed_event(ordered, _RESULT_VALIDATED_EVENT),
        "unit_verification_observed": bool(projection.get("unit_verification_observed")),
        "owner": _latest_field(ordered, "runtime_profile"),
        # `branch_ref` is an optional journal field. Today's dispatch write site
        # records the worktree path and not the branch, so this reads `unknown`
        # on current journals. It stays a column rather than being filled from
        # the contract's `branch_suggestion`: a suggestion is what was proposed,
        # not what git checked out, and this roster reports only what was seen.
        "branch": _latest_field(ordered, "branch_ref"),
        "worktree_path": _latest_field(ordered, "worktree_ref"),
        "last_event": canonical_observation_event(str(latest.get("event", ""))),
        "last_event_status": str(latest.get("status", "") or _UNKNOWN),
        "last_event_at": str(latest.get("observed_at", "") or _UNKNOWN),
        "last_event_age_seconds": _age_seconds(str(latest.get("observed_at", ""))),
        "evidence_ref_count": _evidence_ref_count(ordered),
        "journal_event_count": len(ordered),
    }


def _lifecycle_state(events: list[dict[str, Any]], projection: Mapping[str, Any]) -> str:
    """The highest rung with dispatcher-observed backing in this unit's events.

    Reported as the highest rung REACHED, not as a claim that every lower rung
    was observed: a unit can carry a verification receipt without a validated
    sidecar. `integration_ready` is never decided here -- it additionally needs
    the whole chain plus a merge-order position only the full roster can see, so
    it is folded afterwards by `_apply_merge_order_position`.
    """
    if projection.get("unit_verification_observed"):
        return "unit_verification_observed"
    if _has_observed_event(events, _RESULT_VALIDATED_EVENT):
        return "result_schema_valid"
    if projection.get("execution_observed"):
        return "process_succeeded"
    if any(_has_observed_event(events, name) for name in _DISPATCH_EVENTS):
        return "dispatched_not_succeeded"
    return "not_dispatched"


def _apply_merge_order_position(units: list[dict[str, Any]]) -> None:
    """Promote verified units to `integration_ready` in roster order.

    Mirrors `_apply_integration_readiness` in fanout_dispatch: a later unit
    cannot become integration eligible while an earlier one still lacks the
    complete dispatcher-observed chain. The journal carries no merge plan, so
    the roster's own deterministic (sorted) unit order is the position, and the
    roster says so rather than implying the contract's merge order.
    """
    position_satisfied = True
    for unit in units:
        chain_complete = bool(
            unit["process_succeeded"]
            and unit["result_schema_valid"]
            and unit["unit_verification_observed"]
        )
        integration_ready = chain_complete and position_satisfied
        if integration_ready:
            unit["lifecycle_state"] = "integration_ready"
        unit["integration_ready"] = integration_ready
        unit["merge_order_position_satisfied"] = position_satisfied
        unit["merge_order_basis"] = "roster_order_not_contract_merge_plan"
        position_satisfied = integration_ready


def _has_observed_event(events: list[dict[str, Any]], name: str) -> bool:
    return any(
        canonical_observation_event(str(event.get("event", ""))) == name
        and str(event.get("status", "observed")) == "observed"
        for event in events
    )


def _latest_field(events: list[dict[str, Any]], key: str) -> str:
    for event in reversed(events):
        value = str(event.get(key, "") or "")
        if value:
            return value
    return _UNKNOWN


def _evidence_ref_count(events: list[dict[str, Any]]) -> int:
    total = 0
    for event in events:
        refs = event.get("evidence_refs")
        if isinstance(refs, list):
            total += sum(1 for ref in refs if str(ref))
    return total


def _age_seconds(observed_at: str) -> int | None:
    moment = _parse_timestamp(observed_at)
    if moment is None:
        return None
    return max(0, int((datetime.now(timezone.utc) - moment).total_seconds()))


def _parse_timestamp(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _age_phrase(age_seconds: object) -> str:
    if not isinstance(age_seconds, int):
        return "(age unknown)"
    if age_seconds < 60:
        return f"({age_seconds}s ago)"
    if age_seconds < 3600:
        return f"({age_seconds // 60}m ago)"
    return f"({age_seconds // 3600}h ago)"
