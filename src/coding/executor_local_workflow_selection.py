from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import re
from typing import Callable, Final, TypeAlias

from ..skills.catalog_types import omh_skill_display_name


JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
WorkflowRecord: TypeAlias = dict[str, JsonValue]
WorkflowInput: TypeAlias = Mapping[str, JsonValue]
CandidateSpec: TypeAlias = tuple[str, str, str, Callable[[str], str]]

_WORKFLOW_RE: Final = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?")
_SENSITIVE_RE: Final = re.compile(
    r"(?:api[_-]?key|authorization|bearer\s|password|private[_-]?token|secret|token|sk-|gh[opsu]_|xox[bp]-)",
    re.IGNORECASE,
)
_LOCAL_PATH_RE: Final = re.compile(r"^(?:/|~[/\\]|[a-z]:[/\\]|file://)", re.IGNORECASE)
_MAX_TEXT: Final = 240
_CANDIDATE_SPECS: Final[dict[str, CandidateSpec]] = {
    "codex": ("codex_skill", "command_template", "$skill", lambda skill: f"${skill} {{message}}"),
    "hermes": (
        "hermes_installed_skill",
        "display_only",
        "Hermes installed skill",
        lambda skill: f"/{omh_skill_display_name(skill)} {{message}}",
    ),
    "omx-runtime": ("omx_skill", "display_only", "$skill", lambda skill: f"${skill} {{message}}"),
    "omo-runtime": ("omo_skill_reference", "skill_reference", "canonical_skill_id", lambda _skill: ""),
    "omc-runtime": ("omc_skill_descriptor", "descriptor_only", "canonical_skill_id", lambda _skill: ""),
}


def candidate_for(profile: str, workflow: str) -> WorkflowRecord | None:
    if not is_workflow(workflow):
        return None
    spec = _CANDIDATE_SPECS.get(profile)
    if spec is None:
        return None
    kind, mode, syntax, render_template = spec
    template = render_template(workflow)
    return {
        "kind": kind,
        "skill_id": workflow,
        "invocation": {
            "mode": mode,
            "syntax": syntax,
            "template": template,
            "message_placeholder": "{message}" if template else "",
        },
        "rationale": "This is the final guarded workflow mapped to the selected executor profile.",
        "selection_basis": "final_guarded_recommended_workflow",
    }


def availability_for(profile: str, skill_id: str, evidence: WorkflowInput | None) -> WorkflowRecord:
    unknown: WorkflowRecord = {
        "status": "unknown",
        "basis": "prepared_mapping",
        "profile": profile,
        "skill_id": skill_id,
        "scope": {},
        "observed_at": "",
        "evidence_ref": "",
    }
    if evidence is None or set(evidence) != {"status", "scope", "observed_at", "evidence_ref"}:
        return unknown
    scope = evidence.get("scope")
    if not isinstance(scope, Mapping) or set(scope) != {"profile", "skill_id", "environment"}:
        return unknown
    if scope.get("profile") != profile or scope.get("skill_id") != skill_id:
        return unknown
    environment = scope.get("environment")
    observed_at = evidence.get("observed_at")
    evidence_ref = evidence.get("evidence_ref")
    if not bounded_safe(environment) or not timestamp(observed_at) or not bounded_safe(evidence_ref):
        return unknown
    observed_status = evidence.get("status")
    if not isinstance(observed_status, str):
        return unknown
    status = {"host_observed": "observed_available", "unavailable": "observed_unavailable"}.get(observed_status)
    if status is None:
        return unknown
    return {
        "status": status,
        "basis": "operator_recorded_snapshot",
        "profile": profile,
        "skill_id": skill_id,
        "scope": {"environment": environment},
        "observed_at": observed_at,
        "evidence_ref": evidence_ref,
    }


def dispatchability_for(profile: str, status: str, parent: bool) -> WorkflowRecord:
    candidate_dispatchable = profile == "codex" and status == "observed_available" and parent
    if status == "unknown":
        reason = "availability_not_observed"
    elif status == "observed_unavailable":
        reason = "candidate_observed_unavailable"
    elif profile in {"omo-runtime", "omc-runtime"}:
        reason = "descriptor_only"
    elif not parent:
        reason = "parent_handoff_prepare_only"
    else:
        reason = "observed_available_ask_before_dispatch"
    return {
        "handoff_dispatchable": parent,
        "candidate_invocation_dispatchable": candidate_dispatchable,
        "reason": reason,
    }


def is_workflow(value: JsonValue | None) -> bool:
    return isinstance(value, str) and bool(_WORKFLOW_RE.fullmatch(value))


def bounded_safe(value: JsonValue | None) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= _MAX_TEXT
        and _SENSITIVE_RE.search(value) is None
        and _LOCAL_PATH_RE.search(value.strip()) is None
    )


def timestamp(value: JsonValue | None) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None
