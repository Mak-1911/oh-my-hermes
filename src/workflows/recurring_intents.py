"""Recurring-intent lifecycle records (`hermes_recurring_intent/v1`).

# Why this is a sibling record and not more fields on `hermes_ops_blueprint/v1`

There is one recurring-work concept in OMH, not two. A recurring intent is the
*lifecycle envelope* around a scheduled-ops blueprint: it never re-derives
cadence, delivery, or silence, it calls `build_scheduled_ops_blueprint` and
keeps the sub-records that builder produced. The blueprint stays the single
normalizer, and both records live under `.omh/hermes-ops/`.

The blueprint could not carry the lifecycle itself for three reasons:

1. `hermes_ops_blueprint/v1` is `projection_only` and write-once.
   `write_hermes_ops_blueprint` refuses to overwrite an existing id and there is
   no update path, because a projection of catalog metadata has nothing to
   update. A recurring intent is revised, activated, and accumulates occurrence
   links, so it needs a mutable record with a revision identity.
2. The blueprint validator refuses any nested `status` outside
   `{prepared, not_observed}` and any `*_status` that claims observation. An
   occurrence has to name an observed runtime run. Putting occurrences inside a
   blueprint would mean weakening exactly the guard that keeps blueprints
   honest, so occurrences live here and the guard itself is reused unchanged
   (`nested_status_boundary_errors`).
3. Blueprint identity is a timestamp plus a random suffix. Linking an
   occurrence to the exact intent it ran under needs a content digest, so a
   changed intent produces a different identifier on its own.

# What "paused" means structurally

`build_recurring_intent` has no parameter that can set an activation state or an
occurrence: a freshly built intent is not merely defaulted to paused, it has no
vocabulary for "an occurrence ran". The validator enforces the same rule for
records that arrive from disk or from a wrapper: with no recorded `activated`
transition, `occurrences` must be empty.

# What activation is

A recorded transition, never a flag flip. OMH runs no scheduler and no
background service. Activation is performed by an approved runtime surface
outside OMH; this record only stores who or what observed it, under which
approval reference, and at which revision. An activated intent is still not
execution evidence — each occurrence points at the runtime run that owns its
evidence.
"""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..hashutil import sha256_text
from ..local_store import atomic_write_json, ensure_dir, read_json_object, read_json_object_result, utc_now
from ..paths import OmhPaths
from .hermes_ops import (
    PROJECTION_SOURCE_REFS,
    build_scheduled_ops_blueprint,
    nested_status_boundary_errors,
)


RECURRING_INTENT_SCHEMA_VERSION = "hermes_recurring_intent/v1"
RECURRING_INTENT_INDEX_SCHEMA_VERSION = "hermes_recurring_intent_index/v1"
RECURRING_INTENT_VALIDATION_SCHEMA_VERSION = "hermes_recurring_intent_validation/v1"
RECURRING_INTENT_PREVIEW_SCHEMA_VERSION = "hermes_recurring_intent_preview/v1"
RECURRING_OCCURRENCE_SCHEMA_VERSION = "hermes_recurring_occurrence/v1"
RECURRING_INTENT_STATUS_CARD_SCHEMA_VERSION = "hermes_recurring_intent_status_card/v1"

RECURRING_INTENT_KINDS = ("recurring-intent",)
RECURRING_INTENT_STATUSES = ("prepared", "blocked", "archived")
RECURRING_INTENT_OBSERVATION_STATUSES = ("prepared", "not_observed")
LIFECYCLE_STATES = ("paused", "activated")
OWNER_KINDS = ("unassigned", "human", "team", "runtime_surface", "executor_profile")
OVERLAP_POSTURES = ("unspecified", "skip_when_running", "queue_after_running", "allow_concurrent")
ACTIVATION_OBSERVER_KINDS = ("human", "approved_runtime_surface")
OCCURRENCE_OBSERVER_KINDS = ("human", "approved_runtime_surface")
OCCURRENCE_OUTCOMES = ("ran", "failed", "skipped")
REQUIRED_APPROVAL_KIND = "human_or_approved_runtime_surface"
ACTIVATION_PERFORMED_BY = "approved_runtime_surface_outside_omh"

INTENT_SUMMARY_LIMIT = 240
# The runtime run owns the durable evidence for an occurrence, so this record
# keeps a bounded local index of the most recent links rather than growing one
# JSON file forever -- every mutation reads and rewrites the whole record.
# `occurrences_recorded_total` keeps the count honest after truncation.
RETAINED_OCCURRENCE_LIMIT = 50

RECURRING_INTENT_NOT_EVIDENCE = (
    "host_cron_created",
    "hermes_automation_enabled",
    "omh_scheduler_started",
    "occurrence_executed",
    "runtime_run_started",
    "gateway_delivery_sent",
    "review",
    "ci",
    "merge_readiness",
    "merge",
)
RECURRING_INTENT_OBSERVED_EVIDENCE_REQUIRED = (
    "An approval reference from a human or an approved runtime surface, recorded before activation.",
    "The approved runtime surface that performed activation, named in the activation transition.",
    "A runtime run reference for every occurrence, owned by the runtime that ran it.",
)
PREPARED_RECURRING_INTENT_IS_NOT = (
    "A Hermes recurring intent is local lifecycle metadata only. OMH runs no scheduler and no background "
    "service, so neither a paused nor an activated intent is host cron creation, scheduler startup, "
    "occurrence execution, gateway delivery, review, CI, merge-readiness, or merge evidence."
)
OCCURRENCE_CLAIM_BOUNDARY = (
    "The linked runtime run owns this execution evidence. This occurrence is only the local link back to the "
    "exact intent revision the run was started under."
)
ACTIVATION_REQUIREMENTS = (
    "explicit_overlap_posture",
    "recorded_approval_reference",
    "recorded_observer_of_the_activating_runtime_surface",
)

# Meaningful fields of the intent, in the order they enter the revision digest.
# Deliberately excluded: intent_id, created_at, updated_at, the revision block
# itself, approval grant state, lifecycle transitions, and occurrences. Times
# never enter the digest -- they are passed in as parameters so the same intent
# always digests to the same revision. Approval grant state is excluded so that
# activating an intent cannot silently orphan the occurrences recorded under it.
REVISION_DIGEST_FIELDS = (
    "title",
    "request_summary",
    "schedule_intent.cadence",
    "schedule_intent.time_hint",
    "schedule_intent.explicit_schedule",
    "delivery_intent.surfaces",
    "delivery_intent.explicit_delivery",
    "silence_policy.mode",
    "silence_policy.explicit_policy",
    "scope.summary",
    "scope.explicit_scope",
    "owner_profile.owner",
    "owner_profile.owner_kind",
    "overlap_posture.posture",
    "required_approval.required",
    "required_approval.approval_kind",
)

_INTENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,159}$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def build_recurring_intent(
    request: str,
    *,
    title: str = "",
    schedule: str = "",
    delivery: str = "",
    silence: str = "",
    scope: str = "",
    owner: str = "",
    owner_kind: str = "unassigned",
    overlap_posture: str = "unspecified",
    source: str = "",
    intent_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Prepare a paused recurring intent from a natural-language request.

    There is no activation or occurrence parameter on purpose: the returned
    record cannot express "an occurrence ran" no matter what the caller passes.
    """
    clean_request = " ".join(str(request).split())
    if not clean_request:
        raise ValueError("recurring intent request is required")
    if owner_kind not in OWNER_KINDS:
        raise ValueError(f"unsupported recurring intent owner_kind: {owner_kind}")
    if overlap_posture not in OVERLAP_POSTURES:
        raise ValueError(f"unsupported recurring intent overlap_posture: {overlap_posture}")
    created = created_at or utc_now()
    hints = {"schedule": schedule.strip(), "delivery": delivery.strip(), "silence": silence.strip()}
    derived = _derived_intents(clean_request, hints, created)
    record: dict[str, Any] = {
        "schema_version": RECURRING_INTENT_SCHEMA_VERSION,
        "intent_id": intent_id or new_recurring_intent_id(clean_request, created),
        "kind": "recurring-intent",
        "title": title.strip() or _default_title(clean_request),
        "status": "prepared",
        "observation_status": "prepared",
        "created_at": created,
        "updated_at": created,
        "source": source.strip(),
        "request_summary": _preview(clean_request, limit=INTENT_SUMMARY_LIMIT),
        "derived_from": {
            "schema_version": "hermes_ops_blueprint/v1",
            "authority": "projection_only",
            "normalizer": "build_scheduled_ops_blueprint",
            "source_refs": list(PROJECTION_SOURCE_REFS),
        },
        "derivation_hints": hints,
        "schedule_intent": derived["schedule_intent"],
        "delivery_intent": derived["delivery_intent"],
        "silence_policy": derived["silence_policy"],
        "scope": _scope(clean_request, scope=scope),
        "owner_profile": _owner_profile(owner=owner, owner_kind=owner_kind),
        "overlap_posture": _overlap_posture(overlap_posture),
        "required_approval": {
            "required": True,
            "approval_kind": REQUIRED_APPROVAL_KIND,
            "granted": False,
            "approval_ref": "",
        },
        "lifecycle": {
            "state": "paused",
            "activation_requires": list(ACTIVATION_REQUIREMENTS),
            "activation_performed_by": ACTIVATION_PERFORMED_BY,
            "transitions": [],
        },
        "occurrences": [],
        "occurrences_recorded_total": 0,
        "revision_history": [],
        "not_evidence_until_observed": list(RECURRING_INTENT_NOT_EVIDENCE),
        "observed_evidence_required": list(RECURRING_INTENT_OBSERVED_EVIDENCE_REQUIRED),
        "prepared_is_not": PREPARED_RECURRING_INTENT_IS_NOT,
        "claim_boundary": _claim_boundary(),
    }
    _refresh_derived_blocks(record, revised_at=created)
    errors = validate_recurring_intent(record)
    if errors:
        raise ValueError("; ".join(errors))
    return record


def preview_recurring_intent(record: dict[str, Any]) -> dict[str, Any]:
    """Wrap a prepared intent as a preview a wrapper can show before saving.

    The user described recurring work in chat; this payload is what Hermes reads
    back to them. `save.requires_user_command` is false because confirming the
    summary is the whole user action -- the command below it is the agent-facing
    surface, not something the user types.
    """
    return {
        "schema_version": RECURRING_INTENT_PREVIEW_SCHEMA_VERSION,
        "preview_only": True,
        "saved": False,
        "human_summary": record["human_summary"],
        "open_decisions": list(record["open_decisions"]),
        "save": {
            "requires_user_command": False,
            "user_action": "confirm_or_correct_the_summary",
            "entry_action": "prepare_scheduled_ops_blueprint",
            "agent_surface": "omh ops recurring-intent",
        },
        "intent": record,
        "claim_boundary": dict(record["claim_boundary"]),
    }


def revise_recurring_intent(
    record: dict[str, Any],
    *,
    revised_at: str | None = None,
    title: str | None = None,
    schedule: str | None = None,
    delivery: str | None = None,
    silence: str | None = None,
    scope: str | None = None,
    owner: str | None = None,
    owner_kind: str | None = None,
    overlap_posture: str | None = None,
) -> dict[str, Any]:
    """Return a revised copy with a new revision id, paused again if it was active.

    Revising an activated intent pauses it: the approved runtime surface
    approved a specific revision, and re-activation must record a fresh
    observer against the revision that will actually run.
    """
    if owner_kind is not None and owner_kind not in OWNER_KINDS:
        raise ValueError(f"unsupported recurring intent owner_kind: {owner_kind}")
    if overlap_posture is not None and overlap_posture not in OVERLAP_POSTURES:
        raise ValueError(f"unsupported recurring intent overlap_posture: {overlap_posture}")
    revised = revised_at or utc_now()
    updated = _clone(record)
    previous_revision = str(updated["revision"]["revision_id"])
    if title is not None:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("recurring intent title must not be blank")
        updated["title"] = clean_title
    hints = dict(updated.get("derivation_hints", {}))
    for key, value in (("schedule", schedule), ("delivery", delivery), ("silence", silence)):
        if value is not None:
            hints[key] = value.strip()
    if hints != updated.get("derivation_hints"):
        updated["derivation_hints"] = hints
        # The record deliberately does not retain the raw request (metadata-only
        # by default), so a revision re-derives from the bounded request_summary.
        # For a request longer than INTENT_SUMMARY_LIMIT that is the truncated
        # text, which is why the explicit hints exist.
        updated.update(_derived_intents(str(updated["request_summary"]), hints, revised))
    if scope is not None:
        updated["scope"] = _scope(str(updated["request_summary"]), scope=scope)
    if owner is not None or owner_kind is not None:
        profile = updated["owner_profile"]
        updated["owner_profile"] = _owner_profile(
            owner=str(profile["owner"]) if owner is None else owner,
            owner_kind=str(profile["owner_kind"]) if owner_kind is None else owner_kind,
        )
    if overlap_posture is not None:
        updated["overlap_posture"] = _overlap_posture(overlap_posture)
    updated["updated_at"] = revised
    _refresh_derived_blocks(updated, revised_at=revised)
    if str(updated["revision"]["revision_id"]) == previous_revision:
        raise ValueError("recurring intent revision must change at least one meaningful field")
    updated["revision_history"] = [
        *record.get("revision_history", []),
        {"revision_id": previous_revision, "superseded_at": revised},
    ]
    if str(updated["lifecycle"]["state"]) == "activated":
        updated["lifecycle"]["state"] = "paused"
        updated["lifecycle"]["transitions"] = [
            *updated["lifecycle"]["transitions"],
            {
                "transition": "paused_by_revision",
                "intent_revision_id": str(updated["revision"]["revision_id"]),
                "observer": "",
                "observer_kind": "local_policy",
                "approval_ref": "",
                "activation_surface": "",
                "reason": "intent fields changed; re-activation must record a new observer against this revision",
                "recorded_at": revised,
            },
        ]
        updated["required_approval"] = {
            **updated["required_approval"],
            "granted": False,
            "approval_ref": "",
        }
    _refresh_derived_blocks(updated, revised_at=revised)
    errors = validate_recurring_intent(updated)
    if errors:
        raise ValueError("; ".join(errors))
    return updated


def activate_recurring_intent(
    record: dict[str, Any],
    *,
    observer: str,
    approval_ref: str,
    activation_surface: str,
    observer_kind: str = "approved_runtime_surface",
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Record that an approved runtime surface activated this intent revision.

    OMH does not activate anything here. This appends the transition that says
    who or what observed the activation, so a later occurrence can be read
    against a named observer instead of an anonymous flag.
    """
    if not str(observer).strip():
        raise ValueError("recurring intent activation requires a recorded observer")
    if observer_kind not in ACTIVATION_OBSERVER_KINDS:
        raise ValueError(f"unsupported recurring intent activation observer_kind: {observer_kind}")
    if not str(approval_ref).strip():
        raise ValueError("recurring intent activation requires a recorded approval reference")
    if not str(activation_surface).strip():
        raise ValueError("recurring intent activation requires the approved runtime surface that performed it")
    if str(record["overlap_posture"]["posture"]) == "unspecified":
        raise ValueError("recurring intent activation requires an explicit overlap posture")
    if str(record["lifecycle"]["state"]) == "activated":
        raise ValueError("recurring intent is already activated")
    observed = observed_at or utc_now()
    updated = _clone(record)
    updated["lifecycle"]["state"] = "activated"
    updated["lifecycle"]["transitions"] = [
        *updated["lifecycle"]["transitions"],
        {
            "transition": "activated",
            "intent_revision_id": str(updated["revision"]["revision_id"]),
            "observer": str(observer).strip(),
            "observer_kind": observer_kind,
            "approval_ref": str(approval_ref).strip(),
            "activation_surface": str(activation_surface).strip(),
            "reason": "approved runtime surface reported activation",
            "recorded_at": observed,
        },
    ]
    updated["required_approval"] = {
        **updated["required_approval"],
        "granted": True,
        "approval_ref": str(approval_ref).strip(),
    }
    updated["updated_at"] = observed
    _refresh_derived_blocks(updated, revised_at=str(updated["revision"]["revised_at"]))
    errors = validate_recurring_intent(updated)
    if errors:
        raise ValueError("; ".join(errors))
    return updated


def record_recurring_intent_occurrence(
    record: dict[str, Any],
    *,
    runtime_run_ref: str,
    runtime_surface: str,
    observer: str,
    observer_kind: str = "approved_runtime_surface",
    outcome: str = "ran",
    observed_at: str | None = None,
    occurrence_id: str | None = None,
) -> dict[str, Any]:
    """Link one observed runtime run back to the exact intent revision it ran under."""
    if str(record["lifecycle"]["state"]) != "activated":
        raise ValueError(
            "a paused recurring intent cannot record an occurrence: activate it with a recorded observer first"
        )
    if outcome not in OCCURRENCE_OUTCOMES:
        raise ValueError(f"unsupported recurring intent occurrence outcome: {outcome}")
    if observer_kind not in OCCURRENCE_OBSERVER_KINDS:
        raise ValueError(f"unsupported recurring intent occurrence observer_kind: {observer_kind}")
    if not str(runtime_run_ref).strip():
        raise ValueError("recurring intent occurrence requires a runtime run reference")
    if not str(runtime_surface).strip():
        raise ValueError("recurring intent occurrence requires the runtime surface that ran it")
    if not str(observer).strip():
        raise ValueError("recurring intent occurrence requires a recorded observer")
    observed = observed_at or utc_now()
    updated = _clone(record)
    clean_run_ref = str(runtime_run_ref).strip()
    if any(str(item.get("runtime_run", {}).get("run_ref", "")) == clean_run_ref for item in updated["occurrences"]):
        raise ValueError(f"runtime run {clean_run_ref} is already linked to this recurring intent")
    revision_id = str(updated["revision"]["revision_id"])
    occurrence = {
        "schema_version": RECURRING_OCCURRENCE_SCHEMA_VERSION,
        "occurrence_id": occurrence_id or new_recurring_occurrence_id(revision_id, observed),
        "intent_id": str(updated["intent_id"]),
        "intent_revision_id": revision_id,
        "outcome": outcome,
        "observer": str(observer).strip(),
        "observer_kind": observer_kind,
        "observed_at": observed,
        "runtime_run": {"surface": str(runtime_surface).strip(), "run_ref": clean_run_ref},
        "evidence_authority": "linked_runtime_run",
        "claim_boundary": OCCURRENCE_CLAIM_BOUNDARY,
    }
    updated["occurrences"] = [*updated["occurrences"], occurrence][-RETAINED_OCCURRENCE_LIMIT:]
    updated["occurrences_recorded_total"] = int(updated["occurrences_recorded_total"]) + 1
    updated["updated_at"] = observed
    _refresh_derived_blocks(updated, revised_at=str(updated["revision"]["revised_at"]))
    errors = validate_recurring_intent(updated)
    if errors:
        raise ValueError("; ".join(errors))
    return updated


def recurring_intent_revision_id(record: dict[str, Any]) -> str:
    """Deterministic revision id for the intent's meaningful fields.

    No wall clock enters the digest, so the same intent always produces the same
    revision and any meaningful change produces a different one.
    """
    material = {field: _digest_value(record, field) for field in REVISION_DIGEST_FIELDS}
    canonical = json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return f"rev-{sha256_text(canonical)[:16]}"


def new_recurring_intent_id(request: str, now: datetime | str | None = None) -> str:
    stamp = _stamp(now)
    slug = _slugify(request)[:48] or "recurring-intent"
    return f"{stamp}-recurring-intent-{slug}-{secrets.token_hex(3)}"


def new_recurring_occurrence_id(revision_id: str, now: datetime | str | None = None) -> str:
    return f"{_stamp(now)}-occurrence-{_slugify(revision_id)[:32]}-{secrets.token_hex(3)}"


def validate_recurring_intent(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if record.get("schema_version") != RECURRING_INTENT_SCHEMA_VERSION:
        errors.append("schema_version must be hermes_recurring_intent/v1")
    if record.get("kind") not in RECURRING_INTENT_KINDS:
        errors.append(f"unsupported recurring intent kind: {record.get('kind', '')}")
    intent_id = str(record.get("intent_id", ""))
    if not intent_id.strip():
        errors.append("intent_id is required")
    elif not _valid_intent_id(intent_id):
        errors.append("intent_id must contain only letters, digits, and hyphens, and must not contain path separators")
    if not str(record.get("title", "")).strip():
        errors.append("title is required")
    if record.get("status") not in RECURRING_INTENT_STATUSES:
        errors.append(f"unsupported recurring intent status: {record.get('status', '')}")
    if record.get("observation_status") not in RECURRING_INTENT_OBSERVATION_STATUSES:
        errors.append(f"unsupported recurring intent observation_status: {record.get('observation_status', '')}")
    derived_from = record.get("derived_from")
    if not isinstance(derived_from, dict):
        errors.append("derived_from must be an object")
    else:
        if derived_from.get("schema_version") != "hermes_ops_blueprint/v1":
            errors.append("derived_from.schema_version must be hermes_ops_blueprint/v1")
        if derived_from.get("authority") != "projection_only":
            errors.append("derived_from.authority must be projection_only")
    for key in (
        "schedule_intent",
        "delivery_intent",
        "silence_policy",
        "scope",
        "owner_profile",
        "overlap_posture",
        "required_approval",
        "revision",
        "lifecycle",
        "claim_boundary",
        "status_card",
    ):
        if not isinstance(record.get(key), dict):
            errors.append(f"{key} must be an object")
    for key in (
        "occurrences",
        "revision_history",
        "open_decisions",
        "not_evidence_until_observed",
        "observed_evidence_required",
    ):
        if not isinstance(record.get(key), list):
            errors.append(f"{key} must be a list")
    if errors:
        return errors
    if record["owner_profile"].get("owner_kind") not in OWNER_KINDS:
        errors.append(f"unsupported owner_profile.owner_kind: {record['owner_profile'].get('owner_kind', '')}")
    if record["overlap_posture"].get("posture") not in OVERLAP_POSTURES:
        errors.append(f"unsupported overlap_posture.posture: {record['overlap_posture'].get('posture', '')}")
    if record["required_approval"].get("required") is not True:
        errors.append("required_approval.required must stay true: activation always needs an approval reference")
    if record["required_approval"].get("approval_kind") != REQUIRED_APPROVAL_KIND:
        errors.append(f"required_approval.approval_kind must be {REQUIRED_APPROVAL_KIND}")
    expected_revision = recurring_intent_revision_id(record)
    if str(record["revision"].get("revision_id", "")) != expected_revision:
        errors.append(
            f"revision.revision_id must be the digest of the intent's meaningful fields ({expected_revision})"
        )
    if not set(RECURRING_INTENT_NOT_EVIDENCE).issubset(set(_string_list(record["not_evidence_until_observed"]))):
        errors.append("not_evidence_until_observed must include the default prepared-vs-observed guard list")
    errors.extend(_lifecycle_errors(record))
    errors.extend(_occurrence_errors(record))
    errors.extend(nested_status_boundary_errors(record))
    return errors


def write_recurring_intent(paths: OmhPaths, record: dict[str, Any]) -> dict[str, Any]:
    errors = validate_recurring_intent(record)
    if errors:
        raise ValueError("; ".join(errors))
    intent_id = str(record["intent_id"])
    if recurring_intent_exists(paths, intent_id):
        raise ValueError(f"recurring intent already exists: {intent_id}")
    atomic_write_json(_intent_path(paths, intent_id), record, private=True)
    _write_index_cache(paths)
    return record


def update_recurring_intent(paths: OmhPaths, record: dict[str, Any]) -> dict[str, Any]:
    """Replace a stored intent in place; unlike a blueprint, an intent has a lifecycle."""
    errors = validate_recurring_intent(record)
    if errors:
        raise ValueError("; ".join(errors))
    intent_id = str(record["intent_id"])
    if not recurring_intent_exists(paths, intent_id):
        raise FileNotFoundError(intent_id)
    atomic_write_json(_intent_path(paths, intent_id), record, private=True)
    _write_index_cache(paths)
    return record


def list_recurring_intents(paths: OmhPaths, *, limit: int | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for intent_path in sorted(paths.recurring_intents_dir.glob("*.json")):
        record, error = read_json_object_result(intent_path)
        if error:
            continue
        if record:
            records.append(record)
    records.sort(key=lambda item: str(item.get("created_at", "")))
    if limit is not None:
        if limit < 1:
            return []
        records = records[-limit:]
    return records


def show_recurring_intent(paths: OmhPaths, intent_id: str) -> dict[str, Any]:
    if not _valid_intent_id(intent_id):
        raise FileNotFoundError(intent_id)
    record = read_json_object(_intent_path(paths, intent_id))
    if record:
        return record
    raise FileNotFoundError(intent_id)


def recurring_intent_exists(paths: OmhPaths, intent_id: str) -> bool:
    return _valid_intent_id(intent_id) and _intent_path(paths, intent_id).exists()


def summarize_recurring_intent(record: dict[str, Any]) -> dict[str, Any]:
    revision_id = str(record.get("revision", {}).get("revision_id", ""))
    occurrences = record.get("occurrences", [])
    occurrences = occurrences if isinstance(occurrences, list) else []
    return {
        "intent_id": str(record.get("intent_id", "")),
        "kind": str(record.get("kind", "")),
        "title": str(record.get("title", "")),
        "status": str(record.get("status", "")),
        "observation_status": str(record.get("observation_status", "")),
        "lifecycle_state": str(record.get("lifecycle", {}).get("state", "")),
        "revision_id": revision_id,
        "updated_at": str(record.get("updated_at", "")),
        "cadence": str(record.get("schedule_intent", {}).get("cadence", "unspecified")),
        "overlap_posture": str(record.get("overlap_posture", {}).get("posture", "unspecified")),
        "owner": str(record.get("owner_profile", {}).get("owner", "")),
        "occurrence_count": int(record.get("occurrences_recorded_total", 0) or 0),
        "retained_occurrence_count": len(occurrences),
        "current_revision_occurrence_count": sum(
            1 for item in occurrences if isinstance(item, dict) and str(item.get("intent_revision_id", "")) == revision_id
        ),
        "summary": _preview(str(record.get("request_summary", "")), limit=INTENT_SUMMARY_LIMIT),
    }


def validate_recurring_intent_store(paths: OmhPaths) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    for intent_path in sorted(paths.recurring_intents_dir.glob("*.json")):
        record, error = read_json_object_result(intent_path)
        if error:
            errors.append(f"{intent_path}: {error}")
            continue
        if record:
            records.append(record)
    for record in records:
        intent_id = str(record.get("intent_id", ""))
        if intent_id in seen:
            errors.append(f"duplicate intent_id: {intent_id}")
        seen.add(intent_id)
        for error in validate_recurring_intent(record):
            errors.append(f"{intent_id or '<unknown>'}: {error}")
    index = read_json_object(paths.recurring_intents_index_path)
    if index and index.get("schema_version") != RECURRING_INTENT_INDEX_SCHEMA_VERSION:
        errors.append("recurring intent index cache has unsupported schema_version")
    return {
        "schema_version": RECURRING_INTENT_VALIDATION_SCHEMA_VERSION,
        "ok": not errors,
        "intent_count": len(records),
        "errors": errors,
        "index_authority": "cache_only",
    }


def render_recurring_intent_text(record: dict[str, Any]) -> str:
    schedule = record["schedule_intent"]
    time_hint = str(schedule["time_hint"])
    cadence = str(schedule["cadence"]) + (f" ({time_hint})" if time_hint else "")
    approval = record["required_approval"]
    approval_line = f"granted, ref {approval['approval_ref']}" if approval["granted"] else "required, not granted"
    owner = str(record["owner_profile"]["owner"]) or "unassigned"
    linked = summarize_recurring_intent(record)["current_revision_occurrence_count"]
    lines = [
        str(record["title"]),
        f"  id: {record['intent_id']}",
        f"  revision: {record['revision']['revision_id']}",
        f"  lifecycle: {record['lifecycle']['state']}",
        f"  cadence: {cadence}",
        f"  delivery: {', '.join(_string_list(record['delivery_intent']['surfaces'])) or 'unspecified'}",
        f"  silence: {record['silence_policy']['mode']}",
        f"  scope: {record['scope']['summary']}",
        f"  owner: {owner} ({record['owner_profile']['owner_kind']})",
        f"  overlap posture: {record['overlap_posture']['posture']}",
        f"  approval: {approval_line}",
        f"  occurrences linked to this revision: {linked}",
        "",
        record["human_summary"],
    ]
    if record["open_decisions"]:
        lines.append("")
        lines.append("Still needs a decision:")
        lines.extend(f"  - {item}" for item in record["open_decisions"])
    lines.append("")
    lines.append(f"Not observed: {', '.join(record['not_evidence_until_observed'])}")
    lines.append(record["prepared_is_not"])
    return "\n".join(lines)


def render_recurring_intent_list_text(payload: dict[str, Any]) -> str:
    intents = payload.get("intents", [])
    if not intents:
        return "No recurring intents recorded."
    lines = [f"Recurring intents: {payload['count']} of {payload['total_count']}"]
    for item in intents:
        lines.append(
            f"  [{item['lifecycle_state']}] {item['title']} ({item['intent_id']}) "
            f"cadence={item['cadence']} overlap={item['overlap_posture']} "
            f"occurrences={item['current_revision_occurrence_count']}/{item['occurrence_count']}"
        )
    lines.append("A recurring intent is prepared lifecycle metadata; OMH runs no scheduler.")
    return "\n".join(lines)


def _derived_intents(request: str, hints: dict[str, str], created_at: str) -> dict[str, Any]:
    """Take cadence, delivery, and silence from the blueprint builder, never re-derive them."""
    blueprint = build_scheduled_ops_blueprint(
        request,
        schedule=hints.get("schedule", ""),
        delivery=hints.get("delivery", ""),
        silence=hints.get("silence", ""),
        created_at=created_at,
    )
    return {
        "schedule_intent": dict(blueprint["schedule_intent"]),
        "delivery_intent": dict(blueprint["delivery_intent"]),
        "silence_policy": dict(blueprint["silence_policy"]),
    }


def _scope(request: str, *, scope: str) -> dict[str, object]:
    explicit = scope.strip()
    return {
        "status": "prepared",
        "summary": explicit or _preview(request, limit=160),
        "explicit_scope": explicit,
        "requires_confirmation": not explicit,
    }


def _owner_profile(*, owner: str, owner_kind: str) -> dict[str, object]:
    clean_owner = owner.strip()
    return {
        "status": "prepared",
        "owner": clean_owner,
        "owner_kind": owner_kind,
        "accountable_for": [
            "approving activation",
            "answering for every occurrence recorded under this intent",
        ],
        "requires_confirmation": not clean_owner or owner_kind == "unassigned",
    }


def _overlap_posture(posture: str) -> dict[str, object]:
    return {
        "status": "prepared",
        "posture": posture,
        "explicit": posture != "unspecified",
        "requires_confirmation": posture == "unspecified",
        "failure_policy_owner": "tracked separately; this record carries the posture, not the overrun handling",
    }


def _claim_boundary() -> dict[str, object]:
    return {
        "prepared_is_not_observed": True,
        "activated_is_not_executed": True,
        "omh_runs_no_scheduler": True,
        "occurrence_evidence_authority": "linked_runtime_run",
        "statement": PREPARED_RECURRING_INTENT_IS_NOT,
    }


def _refresh_derived_blocks(record: dict[str, Any], *, revised_at: str) -> None:
    """Recompute the blocks that are a function of the rest of the record."""
    record["revision"] = {
        "revision_id": recurring_intent_revision_id(record),
        "digest_algorithm": "sha256",
        "digest_inputs": list(REVISION_DIGEST_FIELDS),
        "revised_at": revised_at,
    }
    record["open_decisions"] = _open_decisions(record)
    record["human_summary"] = _human_summary(record)
    record["claim_boundary"] = _claim_boundary()
    record["status_card"] = _status_card(record)


def _open_decisions(record: dict[str, Any]) -> list[str]:
    decisions: list[str] = []
    if record["schedule_intent"].get("requires_confirmation"):
        decisions.append("confirm the exact schedule and timezone")
    if record["silence_policy"].get("requires_confirmation"):
        decisions.append("confirm whether to report every occurrence or only changes")
    if record["delivery_intent"].get("requires_observed_gateway_evidence"):
        decisions.append("confirm the delivery target and where its observed gateway evidence comes from")
    if record["scope"].get("requires_confirmation"):
        decisions.append("confirm the scope this recurring work is allowed to touch")
    if record["owner_profile"].get("requires_confirmation"):
        decisions.append("name the owner accountable for this recurring work")
    if record["overlap_posture"].get("requires_confirmation"):
        decisions.append(
            "choose the overlap posture: skip_when_running, queue_after_running, or allow_concurrent"
        )
    return decisions


def _human_summary(record: dict[str, Any]) -> str:
    schedule = record["schedule_intent"]
    cadence = str(schedule["cadence"])
    when = "On an unconfirmed cadence" if cadence == "unspecified" else cadence.capitalize()
    if schedule["time_hint"]:
        when = f"{when} {schedule['time_hint']}"
    surfaces = ", ".join(_string_list(record["delivery_intent"]["surfaces"])) or "the current Hermes thread"
    reporting = (
        "only when something changed"
        if record["silence_policy"]["mode"] == "only_report_changes"
        else "after every occurrence"
    )
    owner = str(record["owner_profile"]["owner"]) or "nobody yet"
    if str(record["lifecycle"]["state"]) == "activated":
        closing = (
            "It is activated by an approved runtime surface; OMH still runs no scheduler, and each occurrence "
            "counts only when that runtime records a run reference here."
        )
    else:
        closing = (
            "It is paused: OMH runs no scheduler, so nothing happens until an approved runtime surface "
            "activates it with a recorded observer and approval reference."
        )
    return (
        f"{when}: {record['request_summary']} Report to {surfaces}, {reporting}. "
        f"Owner: {owner}. {closing}"
    )


def _status_card(record: dict[str, Any]) -> dict[str, object]:
    activated = str(record["lifecycle"]["state"]) == "activated"
    return {
        "schema_version": RECURRING_INTENT_STATUS_CARD_SCHEMA_VERSION,
        "headline": "Recurring intent activated by an approved runtime surface"
        if activated
        else "Recurring intent prepared and paused",
        "lifecycle_state": str(record["lifecycle"]["state"]),
        "revision_id": str(record["revision"]["revision_id"]),
        "prepared": [
            "cadence and time hint",
            "delivery target",
            "silence policy",
            "scope",
            "owner profile",
            "overlap posture",
            "required approval",
        ],
        "not_observed": list(RECURRING_INTENT_NOT_EVIDENCE),
        "next": list(record["open_decisions"])
        or (
            ["record each occurrence with the runtime run reference that owns its evidence"]
            if activated
            else ["hand activation to an approved runtime surface and record its observer"]
        ),
    }


def _lifecycle_errors(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    lifecycle = record["lifecycle"]
    state = str(lifecycle.get("state", ""))
    if state not in LIFECYCLE_STATES:
        errors.append(f"unsupported lifecycle.state: {state}")
    transitions = lifecycle.get("transitions")
    if not isinstance(transitions, list):
        return [*errors, "lifecycle.transitions must be a list"]
    activations = [item for item in transitions if isinstance(item, dict) and item.get("transition") == "activated"]
    for index, transition in enumerate(activations):
        path = f"$.lifecycle.transitions[{index}]"
        if not str(transition.get("observer", "")).strip():
            errors.append(f"{path} records an activation without a recorded observer")
        if transition.get("observer_kind") not in ACTIVATION_OBSERVER_KINDS:
            errors.append(f"{path} activation observer_kind must be human or approved_runtime_surface")
        if not str(transition.get("approval_ref", "")).strip():
            errors.append(f"{path} records an activation without a recorded approval reference")
        if not str(transition.get("activation_surface", "")).strip():
            errors.append(f"{path} records an activation without the approved runtime surface that performed it")
    if state == "activated":
        if not activations:
            errors.append("an activated recurring intent must carry a recorded activation transition")
        if str(record["overlap_posture"].get("posture", "")) == "unspecified":
            errors.append("an activated recurring intent must carry an explicit overlap posture")
        if record["required_approval"].get("granted") is not True:
            errors.append("an activated recurring intent must record its approval as granted")
    return errors


def _occurrence_errors(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    occurrences = record["occurrences"]
    total = record.get("occurrences_recorded_total")
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        errors.append("occurrences_recorded_total must be a non-negative integer")
    elif total < len(occurrences):
        errors.append("occurrences_recorded_total must not be lower than the retained occurrence count")
    if len(occurrences) > RETAINED_OCCURRENCE_LIMIT:
        errors.append(f"occurrences must retain at most the {RETAINED_OCCURRENCE_LIMIT} most recent links")
    transitions = record["lifecycle"].get("transitions", [])
    ever_activated = any(
        isinstance(item, dict) and item.get("transition") == "activated"
        for item in (transitions if isinstance(transitions, list) else [])
    )
    if occurrences and not ever_activated:
        errors.append(
            "a recurring intent with no recorded activation transition must not carry occurrences: "
            "it cannot claim that any occurrence ran"
        )
    known_revisions = {str(record["revision"].get("revision_id", ""))}
    for item in record["revision_history"]:
        if isinstance(item, dict):
            known_revisions.add(str(item.get("revision_id", "")))
    for index, occurrence in enumerate(occurrences):
        path = f"$.occurrences[{index}]"
        if not isinstance(occurrence, dict):
            errors.append(f"{path} must be an object")
            continue
        if occurrence.get("schema_version") != RECURRING_OCCURRENCE_SCHEMA_VERSION:
            errors.append(f"{path}.schema_version must be {RECURRING_OCCURRENCE_SCHEMA_VERSION}")
        if occurrence.get("outcome") not in OCCURRENCE_OUTCOMES:
            errors.append(f"{path}.outcome must be one of {', '.join(OCCURRENCE_OUTCOMES)}")
        if not str(occurrence.get("observer", "")).strip():
            errors.append(f"{path} must name the observer that reported the run")
        runtime_run = occurrence.get("runtime_run")
        if not isinstance(runtime_run, dict) or not str(runtime_run.get("run_ref", "")).strip():
            errors.append(f"{path} must link a runtime run reference: preparation is never execution")
        revision_id = str(occurrence.get("intent_revision_id", ""))
        if revision_id not in known_revisions:
            errors.append(f"{path} names unknown intent revision {revision_id or '<missing>'}")
    return errors


def _digest_value(record: dict[str, Any], field: str) -> object:
    value: object = record
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, bool) or value is None:
        return value
    return str(value)


def _intent_path(paths: OmhPaths, intent_id: str) -> Path:
    if not _valid_intent_id(intent_id):
        raise ValueError("intent_id must contain only letters, digits, and hyphens, and must not contain path separators")
    path = paths.recurring_intents_dir / f"{intent_id}.json"
    root = paths.recurring_intents_dir.resolve()
    resolved = path.resolve()
    if resolved.parent != root:
        raise ValueError("intent_id escapes recurring intent storage")
    return path


def _write_index_cache(paths: OmhPaths) -> None:
    records = list_recurring_intents(paths)
    ensure_dir(paths.recurring_intents_root, private=True)
    atomic_write_json(
        paths.recurring_intents_index_path,
        {
            "schema_version": RECURRING_INTENT_INDEX_SCHEMA_VERSION,
            "updated_at": utc_now(),
            "authority": "cache_only",
            "intents": [summarize_recurring_intent(record) for record in records],
        },
        private=True,
    )


def _clone(record: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(record))


def _default_title(text: str) -> str:
    return f"Recurring intent: {_preview(text, limit=72)}"


def _stamp(value: datetime | str | None) -> str:
    if value is None:
        value = datetime.now(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return _slugify(value)[:32] or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return _stamp(parsed)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _slugify(value: str) -> str:
    return (_SLUG_RE.sub("-", value.casefold()).strip("-") or "recurring-intent")[:64].strip("-")


def _valid_intent_id(value: str) -> bool:
    return bool(_INTENT_ID_RE.fullmatch(str(value)))


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, tuple):
        value = list(value)
    if not isinstance(value, list):
        return [str(value).strip()] if str(value).strip() else []
    return [str(item).strip() for item in value if str(item).strip()]


def _preview(value: str, *, limit: int) -> str:
    clean = " ".join(str(value).split())
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 3)].rstrip() + "..."
