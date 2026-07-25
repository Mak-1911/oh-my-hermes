"""Mechanical backstop for the anti-polling / no-raw-log-dumping policy.

`build_coding_progress_reporting_policy` declares `timed_polling_rejected` and
`raw_log_dumping_rejected`, but declarative text loses to a supervising agent
under pressure. This module keeps a small local ledger of how many bytes each
run's observe/show surfaces have already emitted into agent context. Past the
budget the surfaces degrade to summary-only output plus artifact pointers, so
the policy becomes mechanically true instead of aspirational.

The ledger is local, metadata-only, and best-effort: a ledger write failure
never blocks an observation surface.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..context_safety import RUN_CONTEXT_BUDGET_BYTES
from ..local_store import atomic_write_json, ensure_dir, read_json_object, utc_now
from ..paths import OmhPaths


RUN_CONTEXT_BUDGET_SCHEMA_VERSION = "omh_run_context_budget/v1"
RUN_UNCHANGED_SCHEMA_VERSION = "omh_run_show_unchanged/v1"
CONTEXT_BUDGET_LEDGER_NAME = "context_budget.json"


def payload_fingerprint(payload: Any) -> str:
    """Hash the observable content of a projection.

    Fingerprint the projection itself, never the emitted envelope: the envelope
    carries the budget, which changes on every call and would make every
    emission look new.
    """
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def context_budget_ledger_path(paths: OmhPaths) -> Path:
    return paths.runtime_dir / CONTEXT_BUDGET_LEDGER_NAME


def _ledger(paths: OmhPaths) -> dict[str, Any]:
    ledger = read_json_object(context_budget_ledger_path(paths)) or {}
    runs = ledger.get("runs")
    return {"runs": runs if isinstance(runs, dict) else {}}


def _entry(ledger: dict[str, Any], run_id: str) -> dict[str, Any]:
    entry = ledger["runs"].get(run_id)
    if not isinstance(entry, dict):
        return {"emitted_bytes": 0, "call_count": 0, "surfaces": {}, "payload_fingerprints": {}}
    surfaces = entry.get("surfaces")
    fingerprints = entry.get("payload_fingerprints")
    return {
        "emitted_bytes": max(0, int(entry.get("emitted_bytes", 0) or 0)),
        "call_count": max(0, int(entry.get("call_count", 0) or 0)),
        "surfaces": {str(key): int(value) for key, value in surfaces.items()} if isinstance(surfaces, dict) else {},
        "payload_fingerprints": (
            {str(key): str(value) for key, value in fingerprints.items()} if isinstance(fingerprints, dict) else {}
        ),
    }


def run_context_budget(paths: OmhPaths, run_id: str, *, surface: str = "") -> dict[str, Any]:
    """Report how much agent context this run's observe surfaces already spent."""
    entry = _entry(_ledger(paths), run_id)
    emitted = entry["emitted_bytes"]
    exhausted = emitted >= RUN_CONTEXT_BUDGET_BYTES
    return {
        "schema_version": RUN_CONTEXT_BUDGET_SCHEMA_VERSION,
        "run_id": run_id,
        "surface": surface,
        "budget_bytes": RUN_CONTEXT_BUDGET_BYTES,
        "emitted_bytes": emitted,
        "remaining_bytes": max(0, RUN_CONTEXT_BUDGET_BYTES - emitted),
        "observe_call_count": entry["call_count"],
        "surfaces": entry["surfaces"],
        "last_payload_fingerprint": entry["payload_fingerprints"].get(surface, ""),
        "exhausted": exhausted,
        "enforcement": "degrade_to_summary_only_with_artifact_pointers",
        "policy": "timed_polling_rejected; raw_log_dumping_rejected",
    }


def record_context_emission(
    paths: OmhPaths,
    run_id: str,
    *,
    surface: str,
    byte_count: int,
    payload_fingerprint_value: str = "",
) -> dict[str, Any]:
    """Add one observe/show emission to the run's ledger. Best-effort."""
    ledger = _ledger(paths)
    entry = _entry(ledger, run_id)
    entry["emitted_bytes"] += max(0, int(byte_count))
    entry["call_count"] += 1
    entry["surfaces"][surface] = entry["surfaces"].get(surface, 0) + 1
    if payload_fingerprint_value:
        entry["payload_fingerprints"][surface] = payload_fingerprint_value
    entry["updated_at"] = utc_now()
    ledger["runs"][run_id] = entry
    payload = {
        "schema_version": RUN_CONTEXT_BUDGET_SCHEMA_VERSION,
        "updated_at": entry["updated_at"],
        "runs": ledger["runs"],
    }
    try:
        ensure_dir(paths.runtime_dir)
        atomic_write_json(context_budget_ledger_path(paths), payload)
    except OSError:
        return run_context_budget(paths, run_id, surface=surface)
    return run_context_budget(paths, run_id, surface=surface)


def unchanged_run_payload(shown: dict[str, Any], budget: dict[str, Any]) -> dict[str, Any]:
    """Replacement for a projection identical to the one already emitted.

    A supervising agent that polls an unchanged run gets the whole projection
    back every time and narrates it again, which is how one delegated session
    turned twelve fix/test cycles into hundreds of chat messages. Returning the
    lifecycle position plus an explicit "nothing changed" marker removes the
    material to re-narrate without hiding anything: by definition this payload
    carries no information the previous emission did not already carry.

    `--full` bypasses this entirely, so an explicit request still gets
    everything.
    """
    run = shown.get("run") if isinstance(shown.get("run"), dict) else {}
    run_id = str(budget.get("run_id", ""))
    return {
        "schema_version": RUN_UNCHANGED_SCHEMA_VERSION,
        "run": {
            "run_id": run_id,
            "status": str(run.get("status", "")),
            "phase": str(run.get("phase", "")),
            "observation_status": str(run.get("observation_status", "")),
            "updated_at": str(run.get("updated_at", "")),
        },
        "unchanged_since_last_emission": True,
        "delta": {},
        "context_budget": budget,
        "next_action": "wait_for_new_observed_evidence_instead_of_repeating_this_command",
        "full_output_command": f"omh runtime show {run_id} --full",
        "claim_boundary": (
            "Nothing observable changed since the previous emission for this run. This is not "
            "execution, review, CI, merge-readiness, or merge evidence, and repeating the command "
            "will not produce new evidence."
        ),
    }


def degrade_run_payload(shown: dict[str, Any], budget: dict[str, Any]) -> dict[str, Any]:
    """Summary-only replacement for a full `show_run` projection."""
    run = shown.get("run") if isinstance(shown.get("run"), dict) else {}
    history = shown.get("history") if isinstance(shown.get("history"), dict) else {}
    journal_events = shown.get("journal_events") if isinstance(shown.get("journal_events"), list) else []
    latest = journal_events[-1] if journal_events and isinstance(journal_events[-1], dict) else {}
    run_id = str(budget.get("run_id", ""))
    return {
        "schema_version": "omh_run_show_summary_only/v1",
        "run": {
            "run_id": run_id,
            "skill": str(run.get("skill", "")),
            "harness": str(run.get("harness", "")),
            "status": str(run.get("status", "")),
            "phase": str(run.get("phase", "")),
            "observation_status": str(run.get("observation_status", "")),
            "updated_at": str(run.get("updated_at", "")),
        },
        "lifecycle": shown.get("lifecycle", {}),
        "history": history,
        "latest_journal_event": {
            "event": str(latest.get("event", "")),
            "status": str(latest.get("status", "")),
            "observed_at": str(latest.get("observed_at", "")),
        },
        "context_budget": budget,
        "degraded": True,
        "degraded_reason": "run_context_budget_exhausted",
        "next_action": "read_full_history_from_artifacts_instead_of_repeating_this_command",
        "full_history_command": f"omh runtime show {run_id} --full",
        "claim_boundary": (
            "Summary-only projection emitted after this run exhausted its observe-context budget. "
            "It is not execution, review, CI, merge-readiness, or merge evidence; read the listed "
            "artifacts for the full record."
        ),
    }
