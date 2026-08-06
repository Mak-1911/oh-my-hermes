"""One decision path for task-scoped authority on the coding delegation lane.

Three independent "ask the user" ladders used to live side by side and none of
them knew about the others:

1. ``executor_selection.choice_required`` -> ``choose_executor``
2. ``permission_profile_required`` -> ``choose_permission_profile``
3. the operator-card ``confirm_*`` family (and, on the delegation lane, the
   ``send_to_executor`` go-ahead that ``ask_before_dispatch`` implies)

``evaluate_action_gate`` is the only place that decides. It runs exactly once
per delegation build and returns one verdict carrying:

* the safety preflight outcome (allow/deny plus rule id, field, correction),
* the derived task-scoped authority envelope (#811), and
* which single confirmation ladder — at most one — is armed, and why the
  others are suppressed.

``dispatchable`` and ``executor_selection.choice_required`` are then *derived
from* that verdict rather than recomputed, so a denial and a selection can
never disagree into an unconstructible record.

The envelope reuses the goal-loop vocabulary (``PERMISSION_PROFILES``,
``LOOP_ACTIONS``, ``merge_authority``, ``external_action_authority``) so the
loop lane and the handoff lane speak one language. ``omh.workflows.goal_loop``
is imported lazily because ``omh.runtime.records`` imports this module for
validation and the goal-loop import chain reaches ``omh.runtime.artifacts``,
which imports records back.

Authority is derived from user intent plus workspace policy only. Message text,
context packs, and recall packs are inspected for authority-shaped content and
the finding is reported as a surface name — never echoed back, never fed into
the allowed action set.

The same evaluation also produces the *handoff safety contract* (#818): the
task-scoped statement of what this delegation may touch, what it may never do,
and which of those boundaries is actually enforced today. Every boundary entry
carries an ``enforcement`` verdict plus either a real enforcing symbol or the
issue that must land first, because a contract that lists nine boundaries and
guards four reads as coverage that does not exist — strictly worse than no
contract at all.

A boundary is never justified by "no such capability exists". That claim cannot
be enforced and the tree can contradict it: ``omh setup --star`` really does
shell out to ``gh`` to star the repository. Every statement here is therefore
scoped to the surface it actually governs, and a real exception outside that
surface is named in the statement rather than left for a reader to discover.
"""

from __future__ import annotations

from typing import Any

from ..plugin_bundle.omh._governance_safety import classify_memory_admission
from ..workflows.domain_intelligence_admission import ensure_safe_opaque_ref_content


TASK_AUTHORITY_ENVELOPE_SCHEMA_VERSION = "task_authority_envelope/v1"
ACTION_GATE_SCHEMA_VERSION = "coding_action_gate/v1"
HANDOFF_SAFETY_CONTRACT_SCHEMA_VERSION = "handoff_safety_contract/v1"

AUTHORITY_SOURCES = ("user_intent", "workspace_policy")
UNTRUSTED_SURFACES = ("context_pack", "memory_recall_pack", "message")
AUTHORITY_CLASSIFIERS = (
    "plugin_bundle.omh._governance_safety.classify_memory_admission",
    "workflows.domain_intelligence_admission.ensure_safe_opaque_ref_content",
)
MUTATING_ACTIONS = ("external_posting", "merge", "pr_creation", "pr_revision", "repo_edit")
EXCLUSION_REASON_CODES = (
    "not_required_by_task",
    "outside_permission_profile",
    "safety_preflight_denied",
)
CONFIRMATION_LADDERS = ("executor_selection", "permission_profile", "operator_confirmation")
LADDER_ACTION_IDS = {
    "executor_selection": "choose_executor",
    "permission_profile": "choose_permission_profile",
    "operator_confirmation": "send_to_executor",
}
SINGLE_PROMPT_RULE = (
    "One intent arms at most one confirmation ladder. Precedence: a denial asks nothing, "
    "then executor_selection, then permission_profile, then operator_confirmation. "
    "Every ladder that could have fired is recorded as suppressed with the winner named."
)
ENVELOPE_CLAIM_BOUNDARY = (
    "This authority envelope is prepared scope only. It is not dispatch, implementation, "
    "review, CI, merge-readiness, or merge evidence, and it does not prove any action ran."
)
GATE_CLAIM_BOUNDARY = (
    "This action gate verdict is a prepared decision. It is not dispatch, execution, "
    "review, CI, or merge evidence."
)
UNTRUSTED_TEXT_POLICY = (
    "Authority comes from user intent and workspace policy only. Authority-shaped requests "
    "inside message text, a context pack, or a recall pack are inert."
)

TASK_AUTHORITY_ENVELOPE_KEYS = (
    "schema_version",
    "status",
    "permission_profile",
    "allowed_actions",
    "blocked_actions",
    "exclusions",
    "allowed_executors",
    "allowed_targets",
    "mutation_rights",
    "merge_authority",
    "external_action_authority",
    "expansion_policy",
    "untrusted_input_policy",
    "safety_profile_revision",
    "claim_boundary",
)
EXPANSION_POLICY_KEYS = (
    "widening_route",
    "confirmation_action",
    "authority_sources",
    "self_expansion_allowed",
)
UNTRUSTED_INPUT_POLICY_KEYS = (
    "policy",
    "text_cannot_expand_authority",
    "inspected_surfaces",
    "flagged_surfaces",
    "effect_on_authority",
    "classifiers",
)
EXCLUSION_KEYS = ("action", "reason_code", "explanation")
ACTION_GATE_KEYS = (
    "schema_version",
    "status",
    "outcome",
    "dispatchable",
    "choice_required",
    "executor_selection_status",
    "work_owner_mode",
    "selected_executor_profile",
    "dispatch_policy",
    "confirmation",
    "authority_envelope",
    "denial",
    "safety_profile_revision",
    "claim_boundary",
    # Transport only. `evaluate_action_gate` is the one place that runs per
    # delegation build, so the contract rides back on the verdict — but it is
    # *stored* once, beside `action_gate` on the delegation, never inside it.
    # `records._validate_coding_action_gate` refuses a stored gate that still
    # carries one, because two copies can disagree.
    "handoff_safety_contract",
)
CONFIRMATION_KEYS = (
    "required",
    "ladder",
    "action_id",
    "reason",
    "arbitration_rule",
    "candidate_ladders",
    "armed_ladders",
    "suppressed_ladders",
)
DENIAL_KEYS = ("rule_id", "field", "correction", "reason_codes", "source")

HANDOFF_SAFETY_CONTRACT_KEY = "handoff_safety_contract"
HANDOFF_SAFETY_CONTRACT_KEYS = (
    "schema_version",
    "status",
    "produced_offline",
    "input_sources",
    "boundaries",
    "evidence_requirements",
    "prohibited_actions",
    "allowed_executors",
    "allowed_targets",
    "merge_authority",
    "external_action_authority",
    "safety_profile_revision",
    "claim_boundary",
)
SAFETY_BOUNDARY_KEYS = ("boundary", "statement", "enforcement", "enforced_by", "blocked_by")
EVIDENCE_REQUIREMENT_KEYS = ("stage", "claim", "observation_event", "enforcement", "enforced_by", "blocked_by")
ENFORCEMENT_LEVELS = ("declared_not_enforced", "enforced")
# Every local metadata surface the contract is derived from. All three are
# already in process when `evaluate_action_gate` runs, which is what makes the
# contract producible offline: no file, no process, no socket, no model.
HANDOFF_CONTRACT_INPUT_SOURCES = (
    "isolation_plan",
    "safety_preflight_verdict",
    "task_authority_envelope",
)
HANDOFF_CONTRACT_CLAIM_BOUNDARY = (
    "This safety contract is prepared metadata. It is not dispatch, execution, review, CI, or merge "
    "evidence, and an enforced boundary means a refusing check exists — not that any action ran."
)
REVIEW_RECEIPT_BLOCKER = "#844"

# (boundary, statement, enforcement, enforced_by, blocked_by).
#
# The `enforced_by` refs are dotted import paths that must resolve; the test
# suite imports every one of them. That is what stops this table drifting into
# fiction as the enforcing code moves or is deleted. An entry is only
# `enforced` when naming a symbol that refuses something; anything else is
# `declared_not_enforced` with the issue that must land first.
#
# Statements are scoped to the surface they govern. "No such capability exists"
# is never a justification: it cannot be enforced, and the tree can contradict
# it — `omh setup --star` really does shell out to `gh`. Where a real exception
# exists outside the governed surface, the statement names it exactly rather
# than rounding it away.
_SAFETY_BOUNDARIES: tuple[tuple[str, str, str, tuple[str, ...], str], ...] = (
    (
        "confirmation_answered",
        "Nothing records that a user answered a confirmation. The artifact proves a ladder was armed, "
        "not that consent was given, so an armed ladder must never be read as an approval.",
        "declared_not_enforced",
        (),
        "#807",
    ),
    (
        "confirmation_arming",
        "One intent arms at most one confirmation ladder, and every ladder that could have fired is "
        "recorded as suppressed with the winner named.",
        "enforced",
        (
            "omh.coding.action_gate.SINGLE_PROMPT_RULE",
            "omh.coding.action_gate.validate_action_gate_verdict",
        ),
        "",
    ),
    (
        "credential",
        "Credential-shaped values are refused in the opaque-reference field class before any rule reads "
        "them, so a secret cannot enter a prepared handoff as metadata. The chat delegation lane builds "
        "its request from closed vocabularies, so the rule is live for direct evaluator callers and "
        "structurally unreachable from a chat message.",
        "enforced",
        (
            "omh.quality.safety_preflight.RULE_SECRETS_ABSENT",
            "omh.system.metadata_safety.is_sensitive_metadata_text",
        ),
        "",
    ),
    (
        "dispatch",
        "The delegation lane spawns no executor unless the envelope allows executor_dispatch under a "
        "dispatchable parent and the owner has an entry in the local dispatch command allowlist. Every "
        "other owner receives a prepared prompt and is never spawned.",
        "enforced",
        (
            "omh.coding.action_gate.validate_task_authority_envelope",
            "omh.coding.fanout_dispatch.DISPATCH_COMMAND_TEMPLATES",
        ),
        "",
    ),
    (
        "evidence_separation",
        "Prepared metadata is not observed execution. Each claim rung requires its own observation, the "
        "observation journal refuses an out-of-order lifecycle event, and CI and merge additionally "
        "require an external effect receipt that observed that effect succeed.",
        "enforced",
        (
            "omh.runtime.claims.allowed_runtime_claims",
            "omh.workflows.external_effect_receipts.receipt_satisfies_success_claim",
            "omh.workflows.observation_journal.append_observation_event",
        ),
        "",
    ),
    (
        "file",
        "Target paths are bounded, project-relative, and contained: an absolute or home-anchored path, a "
        "path that escapes the project, an over-long path, or more paths than the bound allows is denied "
        "before a handoff is prepared.",
        "enforced",
        (
            "omh.quality.safety_preflight.RULE_TARGET_PATHS_BOUNDED",
            "omh.quality.safety_preflight.evaluate_safety_preflight",
        ),
        "",
    ),
    (
        "merge",
        "No delegation merges anything. merge_authority is disabled on every delegation this lane builds, "
        "fanout dispatch records auto_merge false, and a merged claim is refused unless an external "
        "effect receipt observed this run's merge succeed.",
        "enforced",
        (
            "omh.coding.action_gate.validate_task_authority_envelope",
            "omh.coding.fanout_dispatch.dispatch_fanout",
            "omh.runtime.claims._receipt_cited",
        ),
        "",
    ),
    (
        "network",
        "The coding delegation lane holds no network client and no remote-mutation path: "
        "external_action_authority is pinned to prepare_only, so no prepared handoff can post, publish, "
        "or open a pull request. One executed remote call exists in the tree, outside this lane and "
        "outside any delegation: `omh setup --star` runs `gh api -X PUT "
        "/user/starred/rlaope/oh-my-hermes` from commands.setup behind an explicit --star flag. It adds "
        "only the operator's own star, cannot reach repository contents, and its exact argv is pinned by "
        "a test, so changing it fails the suite.",
        "enforced",
        ("omh.coding.action_gate.validate_task_authority_envelope",),
        "",
    ),
    (
        "profile_revision",
        "A prepared artifact pins the safety-profile revision it was cleared under, and a later boundary "
        "refuses to act once the live revision no longer matches.",
        "enforced",
        (
            "omh.coding.action_gate.recheck_safety_profile_revision",
            "omh.coding.fanout_dispatch.verify_safety_profile_matches_contract",
        ),
        "",
    ),
    (
        "prohibited_actions",
        "Blocked actions are the exact complement of the allowed set over the whole action vocabulary, and "
        "every blocked action carries a reason code and a written explanation.",
        "enforced",
        ("omh.coding.action_gate.validate_task_authority_envelope",),
        "",
    ),
    (
        "recovery",
        "No recovery anchor is attached to risky work, so nothing records how to undo a prepared handoff "
        "once it has been dispatched.",
        "declared_not_enforced",
        (),
        "#821",
    ),
    (
        "review_receipt",
        "A review claim needs an observed review record but, unlike CI and merge, no external effect "
        "receipt. A local record saying review passed is accepted as the evidence for itself.",
        "declared_not_enforced",
        (),
        REVIEW_RECEIPT_BLOCKER,
    ),
    (
        "start_evidence",
        "runtime_start is recordable but is neither a claim rung nor a journal prerequisite, so a run can "
        "claim dispatch and execution with no observed start.",
        "declared_not_enforced",
        (),
        "#826",
    ),
    (
        "storage_content",
        "Persisted records carry bounded metadata only — the message as a sha256 digest and a length, "
        "prompts as templates — and every record key set is closed, so a verbatim prompt or message body "
        "cannot be stored.",
        "enforced",
        (
            "omh.runtime.records.CODING_DELEGATION_RECORD_KEYS",
            "omh.runtime.records.validate_coding_delegation_record",
            "omh.workflows.observation_journal.OBSERVATION_PRIVACY",
        ),
        "",
    ),
    (
        "storage_retention",
        "Run artifacts persist until the operator deletes them. No retention window, expiry, or cleanup "
        "exists, so a prepared handoff and its metadata stay on disk indefinitely.",
        "declared_not_enforced",
        (),
        "#835",
    ),
    (
        "untrusted_input",
        "Authority comes from user intent and workspace policy only. Message text, context packs, and "
        "recall packs are inspected and reported as flagged surface names; nothing they contain widens "
        "the allowed action set.",
        "enforced",
        (
            "omh.coding.action_gate.flagged_untrusted_surfaces",
            "omh.coding.action_gate.validate_task_authority_envelope",
        ),
        "",
    ),
    (
        "workspace",
        "allowed_targets is derived from the isolation plan, but nothing binds a running executor to it. "
        "The target is a declaration the executor is trusted to honour, not a constraint applied to it.",
        "declared_not_enforced",
        (),
        "#820",
    ),
)
SAFETY_BOUNDARY_NAMES = tuple(entry[0] for entry in _SAFETY_BOUNDARIES)

_CLAIM_LADDER_ENFORCERS = (
    "omh.runtime.claims.allowed_runtime_claims",
    "omh.workflows.observation_journal.append_observation_event",
)
_RECEIPT_ENFORCERS = (
    *_CLAIM_LADDER_ENFORCERS,
    "omh.workflows.external_effect_receipts.receipt_satisfies_success_claim",
)

# (stage, claim, observation_event, enforcement, enforced_by, blocked_by).
# The six stages #818 names. `start` is the honest gap: the event exists and is
# recordable, but no claim rung and no journal prerequisite reads it, so the
# contract declares it unenforced instead of implying a gate.
_EVIDENCE_REQUIREMENTS: tuple[tuple[str, str, str, str, tuple[str, ...], str], ...] = (
    ("start", "", "runtime_start_observed", "declared_not_enforced", (), "#826"),
    ("execution", "execution_observed", "executor_result_observed", "enforced", _CLAIM_LADDER_ENFORCERS, ""),
    (
        "verification",
        "verification_observed",
        "verification_result_observed",
        "enforced",
        _CLAIM_LADDER_ENFORCERS,
        "",
    ),
    ("review", "review_observed", "review_result_observed", "enforced", _CLAIM_LADDER_ENFORCERS, ""),
    ("ci", "ci_observed", "ci_result_observed", "enforced", _RECEIPT_ENFORCERS, ""),
    ("merge", "merged", "merge_observed", "enforced", _RECEIPT_ENFORCERS, ""),
)
HANDOFF_EVIDENCE_STAGES = tuple(entry[0] for entry in _EVIDENCE_REQUIREMENTS)

REVISION_DRIFT_RULE_ID = "safety_profile_revision_drift"
REVISION_DRIFT_FIELD = "safety_profile_revision"
REVISION_DRIFT_CORRECTION = (
    "Re-run the safety preflight against the current workspace policy and rebuild the handoff; "
    "the carried safety profile revision no longer matches the live one."
)

# Bounded on purpose: the classifiers walk every character for bidi and control
# marks, and this runs on every delegation build. A prefix is enough to decide
# whether a surface carries authority-shaped content, and the bound keeps the
# decision deterministic across machines.
_MAX_SURFACE_CHARS = 2000
_MAX_SURFACE_FRAGMENTS = 200

_AUTHORITY_CUE_PHRASES = (
    "act as system",
    "auto-merge",
    "bypass approval",
    "bypass the gate",
    "developer mode",
    "disregard instructions",
    "disregard previous",
    "elevate permissions",
    "enable auto dispatch",
    "enable auto-dispatch",
    "full access",
    "full permissions",
    "grant full",
    "grant yourself",
    "ignore previous",
    "no confirmation needed",
    "override the policy",
    "reveal the system prompt",
    "skip confirmation",
    "without asking",
    "you are now",
    "you have permission to",
    "you may merge",
)


def loop_actions() -> tuple[str, ...]:
    """The goal-loop action vocabulary, imported lazily to keep records importable."""
    from ..workflows.goal_loop import LOOP_ACTIONS

    return LOOP_ACTIONS


def permission_profiles() -> tuple[str, ...]:
    from ..workflows.goal_loop import PERMISSION_PROFILES

    return PERMISSION_PROFILES


def _loop_envelope(profile: str, *, executors: list[str], forbid: list[str]) -> dict[str, Any]:
    from ..workflows.goal_loop import build_authority_envelope

    return build_authority_envelope(
        permission_profile=profile,
        allowed_executors=executors,
        forbid_actions=forbid,
    )


def permission_profile_for(
    *,
    denied: bool,
    delegation_action: str,
    work_owner_mode: str,
    dispatchable: bool,
    choice_required: bool,
) -> str:
    """The permission profile a delegation collapses to, from intent and policy only."""
    if denied or delegation_action != "delegate" or choice_required or work_owner_mode == "retained_hermes":
        return "observe_only"
    if dispatchable:
        return "execute_with_gates"
    return "handoff_only"


def required_actions_for(
    *,
    denied: bool,
    delegation_action: str,
    intent: str,
    review_required: bool,
    dispatchable: bool,
    choice_required: bool,
) -> set[str]:
    """The smallest action set this task needs — the "only required authority" rule."""
    required = {"research", "planning"}
    if denied or delegation_action != "delegate" or choice_required:
        return required
    required.add("executor_handoff")
    if dispatchable:
        required.add("executor_dispatch")
    if intent in {"coding", "cleanup", "docs"}:
        required.add("repo_edit")
    if review_required or intent == "review":
        required.add("review_fix_loop")
    return required


def _explanation(action: str, reason_code: str, profile: str) -> str:
    if reason_code == "safety_preflight_denied":
        return f"`{action}` was withdrawn because the safety preflight denied this request."
    if reason_code == "outside_permission_profile":
        return f"`{action}` is not granted by the `{profile}` permission profile, so it stays an approval checkpoint."
    # Deliberately no "omh " token: chat cards assert they never surface an
    # internal command-shaped string, and this text is rendered onto them.
    return f"`{action}` is outside the task scope derived from the request, so the handoff never carries it."


def _allowed_targets_for(isolation_plan: dict[str, Any] | None, allowed: set[str]) -> list[str]:
    if "repo_edit" not in allowed:
        return []
    strategy = str((isolation_plan or {}).get("strategy", ""))
    if strategy == "worktree_required":
        return ["isolated_worktree"]
    if strategy == "worktree_recommended":
        return ["current_workspace", "isolated_worktree"]
    return ["current_workspace"]


def _surface_fragments(value: Any, fragments: list[str]) -> None:
    if len(fragments) >= _MAX_SURFACE_FRAGMENTS:
        return
    if isinstance(value, str):
        if value.strip():
            fragments.append(value)
        return
    if isinstance(value, dict):
        for key in sorted(value):
            _surface_fragments(value[key], fragments)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _surface_fragments(item, fragments)


def surface_text(value: Any) -> str:
    """Flatten a surface into one deterministic, bounded blob for classification."""
    if value is None:
        return ""
    fragments: list[str] = []
    _surface_fragments(value, fragments)
    return "\n".join(fragments)[:_MAX_SURFACE_CHARS]


def is_authority_shaped(text: str) -> bool:
    """True when a surface carries authority-shaped or injection-shaped content.

    Purely a report: nothing downstream of this reads the result to widen the
    allowed action set.
    """
    if not text.strip():
        return False
    lowered = " ".join(text.lower().split())
    if any(cue in lowered for cue in _AUTHORITY_CUE_PHRASES):
        return True
    if classify_memory_admission(text).get("status") != "safe":
        return True
    try:
        ensure_safe_opaque_ref_content(text, "delegation_surface")
    except ValueError:
        return True
    return False


def flagged_untrusted_surfaces(
    *,
    message: str,
    context_pack: dict[str, Any] | None,
    memory_recall_pack: dict[str, Any] | None,
) -> list[str]:
    surfaces = {
        "message": message,
        "context_pack": context_pack,
        "memory_recall_pack": memory_recall_pack,
    }
    return sorted(name for name, value in surfaces.items() if is_authority_shaped(surface_text(value)))


def build_task_authority_envelope(
    *,
    denied: bool,
    delegation_action: str,
    intent: str,
    review_required: bool,
    work_owner_mode: str,
    selected_executor_profile: str | None,
    dispatchable: bool,
    choice_required: bool,
    isolation_plan: dict[str, Any] | None = None,
    message: str = "",
    context_pack: dict[str, Any] | None = None,
    memory_recall_pack: dict[str, Any] | None = None,
    safety_profile_revision: str = "",
) -> dict[str, Any]:
    """Derive the task-scoped authority envelope from intent and policy only."""
    profile = permission_profile_for(
        denied=denied,
        delegation_action=delegation_action,
        work_owner_mode=work_owner_mode,
        dispatchable=dispatchable,
        choice_required=choice_required,
    )
    required = required_actions_for(
        denied=denied,
        delegation_action=delegation_action,
        intent=intent,
        review_required=review_required,
        dispatchable=dispatchable,
        choice_required=choice_required,
    )
    # What the same request would have required had the preflight allowed it —
    # only used to label exclusions, never to widen the allowed set.
    undenied = required_actions_for(
        denied=False,
        delegation_action=delegation_action,
        intent=intent,
        review_required=review_required,
        dispatchable=dispatchable,
        choice_required=choice_required,
    )
    vocabulary = set(loop_actions())
    executors = [selected_executor_profile] if selected_executor_profile else []
    base = _loop_envelope(profile, executors=executors, forbid=sorted(vocabulary - required))
    allowed = set(base["allowed_actions"])
    blocked = sorted(vocabulary - allowed)

    exclusions: list[dict[str, str]] = []
    for action in blocked:
        if denied and action in undenied:
            reason_code = "safety_preflight_denied"
        elif action in required:
            reason_code = "outside_permission_profile"
        else:
            reason_code = "not_required_by_task"
        exclusions.append(
            {
                "action": action,
                "reason_code": reason_code,
                "explanation": _explanation(action, reason_code, profile),
            }
        )

    return {
        "schema_version": TASK_AUTHORITY_ENVELOPE_SCHEMA_VERSION,
        "status": "prepared_not_observed",
        "permission_profile": profile,
        "allowed_actions": sorted(allowed),
        "blocked_actions": blocked,
        "exclusions": exclusions,
        "allowed_executors": list(base["allowed_executors"]),
        "allowed_targets": _allowed_targets_for(isolation_plan, allowed),
        "mutation_rights": sorted(allowed & set(MUTATING_ACTIONS)),
        "merge_authority": str(base["merge_authority"]),
        "external_action_authority": str(base["external_action_authority"]),
        "expansion_policy": {
            "widening_route": "confirmation_required",
            "confirmation_action": LADDER_ACTION_IDS["permission_profile"],
            "authority_sources": list(AUTHORITY_SOURCES),
            "self_expansion_allowed": False,
        },
        "untrusted_input_policy": {
            "policy": UNTRUSTED_TEXT_POLICY,
            "text_cannot_expand_authority": True,
            "inspected_surfaces": list(UNTRUSTED_SURFACES),
            "flagged_surfaces": flagged_untrusted_surfaces(
                message=message,
                context_pack=context_pack,
                memory_recall_pack=memory_recall_pack,
            ),
            "effect_on_authority": "none",
            "classifiers": list(AUTHORITY_CLASSIFIERS),
        },
        "safety_profile_revision": str(safety_profile_revision or ""),
        "claim_boundary": ENVELOPE_CLAIM_BOUNDARY,
    }


def build_task_handoff_safety_contract(envelope: dict[str, Any]) -> dict[str, Any]:
    """The task-scoped handoff safety contract, derived from the envelope alone.

    Offline by construction: the boundary and evidence tables are module data
    and every task-specific value is read off the authority envelope this same
    build just produced. Nothing here opens a file, spawns a process, resolves a
    host, or consults a model, so the contract is reproducible on a machine with
    no network and byte-identical across repeated builds of the same delegation.

    Reading the envelope rather than re-deriving from intent and policy is
    deliberate: a contract that recomputed its own numbers could disagree with
    the envelope it describes, and the validator would have nothing to compare.
    """
    return {
        "schema_version": HANDOFF_SAFETY_CONTRACT_SCHEMA_VERSION,
        "status": "prepared_not_observed",
        "produced_offline": True,
        "input_sources": list(HANDOFF_CONTRACT_INPUT_SOURCES),
        "boundaries": [
            {
                "boundary": boundary,
                "statement": statement,
                "enforcement": enforcement,
                "enforced_by": list(enforced_by),
                "blocked_by": blocked_by,
            }
            for boundary, statement, enforcement, enforced_by, blocked_by in _SAFETY_BOUNDARIES
        ],
        "evidence_requirements": [
            {
                "stage": stage,
                "claim": claim,
                "observation_event": observation_event,
                "enforcement": enforcement,
                "enforced_by": list(enforced_by),
                "blocked_by": blocked_by,
            }
            for stage, claim, observation_event, enforcement, enforced_by, blocked_by in _EVIDENCE_REQUIREMENTS
        ],
        "prohibited_actions": list(envelope.get("blocked_actions", [])),
        "allowed_executors": list(envelope.get("allowed_executors", [])),
        "allowed_targets": list(envelope.get("allowed_targets", [])),
        "merge_authority": str(envelope.get("merge_authority", "")),
        "external_action_authority": str(envelope.get("external_action_authority", "")),
        "safety_profile_revision": str(envelope.get("safety_profile_revision", "")),
        "claim_boundary": HANDOFF_CONTRACT_CLAIM_BOUNDARY,
    }


def split_handoff_safety_contract(gate: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Separate the stored verdict from the safety contract it carried back.

    The contract is stored once, beside `action_gate` on the delegation, never
    inside it. Two copies of the same statement can disagree after a partial
    rebuild, and a reader has no way to tell which one is current.
    """
    verdict = {key: value for key, value in gate.items() if key != HANDOFF_SAFETY_CONTRACT_KEY}
    contract = gate.get(HANDOFF_SAFETY_CONTRACT_KEY)
    return verdict, contract if isinstance(contract, dict) else {}


_ALLOW_OUTCOMES = frozenset({"allow", "allowed", "ok", "pass", "passed"})
_DENY_OUTCOMES = frozenset({"block", "blocked", "deny", "denied", "refuse", "refused"})
_OUTCOME_KEYS = ("outcome", "status", "verdict", "allowed", "allow")


def normalize_safety_preflight(value: Any) -> dict[str, Any]:
    """Adapt the #804/#802 preflight verdict to the fields this gate consumes.

    The evaluator is owned elsewhere, so the field names are read tolerantly.
    Two different absences are treated differently on purpose: *no verdict at
    all* (no evaluator installed) allows, because a missing lane must not brick
    delegation, while a verdict whose outcome this adapter cannot read denies —
    an unrecognized outcome is the case where failing open would silently hand
    out the authority the verdict was supposed to withhold.
    """
    normalized = {
        "outcome": "allow",
        "rule_id": "",
        "field": "",
        "correction": "",
        "reason_codes": [],
        "safety_profile_revision": "",
        "claim_boundary": "",
    }
    if not isinstance(value, dict):
        return normalized
    outcome = str(value.get("outcome", value.get("status", value.get("verdict", "")))).strip().lower()
    allowed = value.get("allowed", value.get("allow"))
    if allowed is False or outcome in _DENY_OUTCOMES:
        normalized["outcome"] = "deny"
    elif allowed is True or outcome in _ALLOW_OUTCOMES:
        normalized["outcome"] = "allow"
    elif any(key in value for key in _OUTCOME_KEYS):
        normalized["outcome"] = "deny"
        normalized["rule_id"] = "safety_preflight_outcome_unreadable"
        normalized["field"] = "status"
        normalized["correction"] = (
            "The safety preflight returned an outcome this delegation lane cannot read; "
            "upgrade the lane or re-run the preflight before preparing a handoff."
        )
    normalized["rule_id"] = str(value.get("rule_id", value.get("rule", "")) or "") or normalized["rule_id"]
    normalized["field"] = str(value.get("field", value.get("field_path", "")) or "") or normalized["field"]
    normalized["correction"] = (
        str(value.get("correction", value.get("remediation", value.get("fix", ""))) or "") or normalized["correction"]
    )
    codes: list[str] = []
    single = value.get("reason_code")
    if isinstance(single, str) and single:
        codes.append(single)
    for key in ("reason_codes", "org_reason_codes", "org_source_reason_codes"):
        listed = value.get(key)
        if isinstance(listed, (list, tuple)):
            codes.extend(str(code) for code in listed)
    normalized["reason_codes"] = sorted(dict.fromkeys(codes))
    normalized["safety_profile_revision"] = str(
        value.get("safety_profile_revision", value.get("revision", "")) or ""
    )
    normalized["claim_boundary"] = str(value.get("claim_boundary", "") or "")
    return normalized


def _denial_from_preflight(preflight: dict[str, Any]) -> dict[str, Any]:
    return {
        "rule_id": preflight["rule_id"] or "safety_preflight_denied",
        "field": preflight["field"] or "message",
        "correction": preflight["correction"]
        or "Narrow the request to what the workspace safety policy allows, then ask again.",
        "reason_codes": list(preflight["reason_codes"]),
        "source": "safety_preflight",
    }


def _revision_drift_denial(carried: str, live: str) -> dict[str, Any]:
    return {
        "rule_id": REVISION_DRIFT_RULE_ID,
        "field": REVISION_DRIFT_FIELD,
        "correction": REVISION_DRIFT_CORRECTION,
        "reason_codes": [f"carried:{carried or 'none'}", f"live:{live or 'none'}"],
        "source": REVISION_DRIFT_RULE_ID,
    }


def _arbitrate_confirmation(
    *,
    denied: bool,
    choice_required: bool,
    expansion_requested: bool,
    dispatchable: bool,
) -> dict[str, Any]:
    """Pick at most one ladder and record why every other one stayed silent."""
    if denied:
        winner = ""
        reason = "A denied request is corrected, not confirmed; no ladder is armed."
    elif choice_required:
        winner = "executor_selection"
        reason = "The coding agent that owns this work is not chosen yet, so nothing downstream can be confirmed."
    elif expansion_requested:
        winner = "permission_profile"
        reason = "The request asks for authority outside the derived envelope, so widening routes through one profile choice."
    elif dispatchable:
        winner = "operator_confirmation"
        reason = "The envelope already allows dispatch, so only the act itself needs a go-ahead."
    else:
        winner = ""
        reason = "Nothing in this handoff needs an authority decision from the user."

    suppressed = []
    for ladder in CONFIRMATION_LADDERS:
        if ladder == winner:
            continue
        if denied:
            suppressed.append({"ladder": ladder, "reason": "suppressed_by:denial"})
        elif winner:
            suppressed.append({"ladder": ladder, "reason": f"superseded_by:{winner}"})
        else:
            suppressed.append({"ladder": ladder, "reason": "not_applicable_to_this_intent"})
    return {
        "required": bool(winner),
        "ladder": winner or "none",
        "action_id": LADDER_ACTION_IDS.get(winner, ""),
        "reason": reason,
        "arbitration_rule": SINGLE_PROMPT_RULE,
        "candidate_ladders": list(CONFIRMATION_LADDERS),
        "armed_ladders": [winner] if winner else [],
        "suppressed_ladders": suppressed,
    }


def evaluate_action_gate(
    *,
    message: str,
    delegation_action: str,
    intent: str,
    review_required: bool,
    work_owner_mode: str,
    selected_executor_profile: str | None,
    dispatch_policy: str,
    dispatchable: bool,
    choice_required: bool,
    executor_selection_status: str,
    isolation_plan: dict[str, Any] | None = None,
    context_pack: dict[str, Any] | None = None,
    memory_recall_pack: dict[str, Any] | None = None,
    safety_preflight: dict[str, Any] | None = None,
    live_safety_profile_revision: str | None = None,
    requested_actions: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """The single decision path: preflight, envelope, and one confirmation ladder.

    The safety-profile revision re-check runs *before* the confirmation is
    arbitrated, so a user never pays a prompt for work that then hard-fails on
    drift.
    """
    preflight = normalize_safety_preflight(safety_preflight)
    denial: dict[str, Any] | None = None
    if preflight["outcome"] == "deny":
        denial = _denial_from_preflight(preflight)
    elif live_safety_profile_revision is not None and preflight["safety_profile_revision"] and str(
        live_safety_profile_revision
    ) != preflight["safety_profile_revision"]:
        denial = _revision_drift_denial(preflight["safety_profile_revision"], str(live_safety_profile_revision))
    denied = denial is not None

    effective_dispatchable = bool(dispatchable) and not denied
    effective_choice_required = bool(choice_required) and not denied
    envelope = build_task_authority_envelope(
        denied=denied,
        delegation_action=delegation_action,
        intent=intent,
        review_required=review_required,
        work_owner_mode="retained_hermes" if denied else work_owner_mode,
        selected_executor_profile=None if denied else selected_executor_profile,
        # The *proposed* values, not the collapsed ones: a denied envelope must
        # still be able to say which actions the denial withdrew, and both the
        # profile and the required set already collapse on `denied` internally.
        dispatchable=bool(dispatchable),
        choice_required=bool(choice_required),
        isolation_plan={} if denied else isolation_plan,
        message=message,
        context_pack=context_pack,
        memory_recall_pack=memory_recall_pack,
        safety_profile_revision=preflight["safety_profile_revision"],
    )
    requested = {str(action) for action in (requested_actions or [])}
    expansion_requested = bool(requested - set(envelope["allowed_actions"]))
    confirmation = _arbitrate_confirmation(
        denied=denied,
        choice_required=effective_choice_required,
        expansion_requested=expansion_requested,
        dispatchable=effective_dispatchable,
    )
    verdict: dict[str, Any] = {
        "schema_version": ACTION_GATE_SCHEMA_VERSION,
        "status": "prepared_not_observed",
        "outcome": "deny" if denied else "allow",
        "dispatchable": effective_dispatchable,
        "choice_required": effective_choice_required,
        "executor_selection_status": "retained_hermes" if denied else executor_selection_status,
        "work_owner_mode": "retained_hermes" if denied else work_owner_mode,
        "selected_executor_profile": None if denied else selected_executor_profile,
        "dispatch_policy": "prepare_only" if denied else dispatch_policy,
        "confirmation": confirmation,
        "authority_envelope": envelope,
        "safety_profile_revision": preflight["safety_profile_revision"],
        "claim_boundary": GATE_CLAIM_BOUNDARY,
        # Built here because this is the one place that runs exactly once per
        # delegation build. The delegation lifts it out before storing, so the
        # contract lives beside the gate rather than inside it.
        HANDOFF_SAFETY_CONTRACT_KEY: build_task_handoff_safety_contract(envelope),
    }
    if denial is not None:
        verdict["denial"] = denial
    return verdict


def recheck_safety_profile_revision(carried: str, live: str | None) -> str:
    """Cheap re-check helper: return a drift reason, or "" when the revision holds."""
    carried_value = str(carried or "")
    if not carried_value:
        return ""
    live_value = str(live or "")
    if live_value == carried_value:
        return ""
    return f"safety profile revision drifted: carried {carried_value or 'none'}, live {live_value or 'none'}"


def _string_list_errors(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return [f"{label} must be a list of strings"]
    return []


def validate_task_authority_envelope(
    value: Any,
    label: str = "task_authority_envelope",
    *,
    lane: str | None = None,
    parent_dispatchable: Any = None,
) -> list[str]:
    """Validate one envelope, including the child-cannot-exceed-parent lattice."""
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    errors: list[str] = []
    if set(value) != set(TASK_AUTHORITY_ENVELOPE_KEYS):
        errors.append(f"{label} keys are invalid")
    if value.get("schema_version") != TASK_AUTHORITY_ENVELOPE_SCHEMA_VERSION:
        errors.append(f"{label} schema_version is invalid")
    if value.get("status") != "prepared_not_observed":
        errors.append(f"{label} status is invalid")
    if value.get("permission_profile") not in permission_profiles():
        errors.append(f"{label} permission_profile is unsupported")
    vocabulary = set(loop_actions())
    allowed = value.get("allowed_actions")
    blocked = value.get("blocked_actions")
    if not isinstance(allowed, list) or not set(allowed) <= vocabulary or sorted(set(allowed)) != allowed:
        errors.append(f"{label} allowed_actions is invalid")
        allowed = []
    if not isinstance(blocked, list) or sorted(vocabulary - set(allowed)) != blocked:
        errors.append(f"{label} blocked_actions must be the sorted complement of allowed_actions")
        blocked = []
    exclusions = value.get("exclusions")
    if not isinstance(exclusions, list):
        errors.append(f"{label} exclusions must be a list")
    else:
        if [entry.get("action") for entry in exclusions if isinstance(entry, dict)] != blocked:
            errors.append(f"{label} exclusions must explain exactly the blocked actions")
        for index, entry in enumerate(exclusions):
            if not isinstance(entry, dict) or set(entry) != set(EXCLUSION_KEYS):
                errors.append(f"{label} exclusions[{index}] keys are invalid")
                continue
            if entry.get("reason_code") not in EXCLUSION_REASON_CODES:
                errors.append(f"{label} exclusions[{index}].reason_code is unsupported")
            if not str(entry.get("explanation", "")).strip():
                errors.append(f"{label} exclusions[{index}].explanation is required")
    errors.extend(_string_list_errors(value.get("allowed_executors"), f"{label} allowed_executors"))
    errors.extend(_string_list_errors(value.get("allowed_targets"), f"{label} allowed_targets"))
    mutation_rights = value.get("mutation_rights")
    if not isinstance(mutation_rights, list) or not set(mutation_rights) <= set(allowed) & set(MUTATING_ACTIONS):
        errors.append(f"{label} mutation_rights must be allowed mutating actions")
    if value.get("merge_authority") != ("granted" if "merge" in allowed else "disabled"):
        errors.append(f"{label} merge_authority must match the allowed action set")
    expected_external = "publish_allowed" if "external_posting" in allowed else "prepare_only"
    if value.get("external_action_authority") != expected_external:
        errors.append(f"{label} external_action_authority must match the allowed action set")
    expansion = value.get("expansion_policy")
    if not isinstance(expansion, dict) or set(expansion) != set(EXPANSION_POLICY_KEYS):
        errors.append(f"{label} expansion_policy keys are invalid")
    else:
        if expansion.get("widening_route") != "confirmation_required":
            errors.append(f"{label} expansion_policy must route widening through confirmation")
        if expansion.get("self_expansion_allowed") is not False:
            errors.append(f"{label} expansion_policy must not allow self expansion")
        if list(expansion.get("authority_sources", [])) != list(AUTHORITY_SOURCES):
            errors.append(f"{label} expansion_policy authority_sources are invalid")
    untrusted = value.get("untrusted_input_policy")
    if not isinstance(untrusted, dict) or set(untrusted) != set(UNTRUSTED_INPUT_POLICY_KEYS):
        errors.append(f"{label} untrusted_input_policy keys are invalid")
    else:
        if untrusted.get("text_cannot_expand_authority") is not True:
            errors.append(f"{label} untrusted_input_policy must mark text as unable to expand authority")
        if untrusted.get("effect_on_authority") != "none":
            errors.append(f"{label} untrusted_input_policy effect_on_authority must be none")
        if list(untrusted.get("inspected_surfaces", [])) != list(UNTRUSTED_SURFACES):
            errors.append(f"{label} untrusted_input_policy inspected_surfaces are invalid")
        flagged = untrusted.get("flagged_surfaces")
        if not isinstance(flagged, list) or not set(flagged) <= set(UNTRUSTED_SURFACES) or sorted(set(flagged)) != flagged:
            errors.append(f"{label} untrusted_input_policy flagged_surfaces are invalid")
    if not isinstance(value.get("safety_profile_revision"), str):
        errors.append(f"{label} safety_profile_revision must be a string")
    if "not dispatch" not in str(value.get("claim_boundary", "")).lower():
        errors.append(f"{label} claim_boundary must preserve the dispatch boundary")
    if "executor_dispatch" in allowed and parent_dispatchable is not True:
        errors.append(f"{label} executor_dispatch requires a dispatchable parent handoff")
    if lane in {"runtime_handoff", "prompt_handoff"} and "executor_dispatch" in allowed:
        errors.append(f"{label} {lane} cannot grant executor dispatch authority")
    return errors


def _enforcement_errors(
    entry: dict[str, Any],
    label: str,
) -> list[str]:
    """The anti-decoration rule, applied to one boundary or evidence entry.

    An `enforced` entry must name at least one dotted symbol that a reader can
    open, and must not name a blocker. A `declared_not_enforced` entry must name
    a blocker and must not name an enforcer. Anything else is a claim of
    coverage nobody can check, which is what this contract exists to prevent.
    """
    errors: list[str] = []
    enforcement = entry.get("enforcement")
    if enforcement not in ENFORCEMENT_LEVELS:
        return [f"{label}.enforcement is unsupported"]
    enforced_by = entry.get("enforced_by")
    blocked_by = entry.get("blocked_by")
    if not isinstance(enforced_by, list) or not all(isinstance(item, str) for item in enforced_by):
        errors.append(f"{label}.enforced_by must be a list of strings")
        enforced_by = []
    if not isinstance(blocked_by, str):
        errors.append(f"{label}.blocked_by must be a string")
        blocked_by = ""
    if enforcement == "enforced":
        if not enforced_by:
            errors.append(f"{label} claims enforcement but names no enforcing symbol")
        if blocked_by:
            errors.append(f"{label} is enforced, so it must not name a blocker")
    else:
        if enforced_by:
            errors.append(f"{label} is not enforced, so it must not name an enforcing symbol")
        if not blocked_by.strip():
            errors.append(f"{label} is not enforced, so it must name the blocker that must land first")
    for index, symbol in enumerate(enforced_by):
        if not symbol.startswith("omh.") or symbol.count(".") < 2:
            errors.append(f"{label}.enforced_by[{index}] must be a dotted omh symbol reference")
    return errors


def _handoff_contract_boundary_errors(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        return [f"{label} boundaries must be a list"]
    names = [entry.get("boundary") for entry in value if isinstance(entry, dict)]
    errors: list[str] = []
    if names != list(SAFETY_BOUNDARY_NAMES):
        # One message covers unknown, missing, duplicated, and reordered names:
        # the boundary set is the contract, so any difference is the same defect.
        errors.append(f"{label} boundaries must be exactly {list(SAFETY_BOUNDARY_NAMES)} in order")
    for index, entry in enumerate(value):
        entry_label = f"{label} boundaries[{index}]"
        if not isinstance(entry, dict) or set(entry) != set(SAFETY_BOUNDARY_KEYS):
            errors.append(f"{entry_label} keys are invalid")
            continue
        if not str(entry.get("statement", "")).strip():
            errors.append(f"{entry_label}.statement is required")
        errors.extend(_enforcement_errors(entry, entry_label))
    return errors


def _handoff_contract_evidence_errors(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        return [f"{label} evidence_requirements must be a list"]
    stages = [entry.get("stage") for entry in value if isinstance(entry, dict)]
    errors: list[str] = []
    if stages != list(HANDOFF_EVIDENCE_STAGES):
        errors.append(f"{label} evidence_requirements must cover exactly {list(HANDOFF_EVIDENCE_STAGES)} in order")
    for index, entry in enumerate(value):
        entry_label = f"{label} evidence_requirements[{index}]"
        if not isinstance(entry, dict) or set(entry) != set(EVIDENCE_REQUIREMENT_KEYS):
            errors.append(f"{entry_label} keys are invalid")
            continue
        if not str(entry.get("observation_event", "")).strip():
            errors.append(f"{entry_label}.observation_event is required")
        if entry.get("enforcement") == "enforced" and not str(entry.get("claim", "")).strip():
            errors.append(f"{entry_label} claims enforcement, so it must name the claim rung it gates")
        errors.extend(_enforcement_errors(entry, entry_label))
    return errors


def validate_handoff_safety_contract(
    value: Any,
    label: str = "handoff_safety_contract",
    *,
    envelope: Any = None,
) -> list[str]:
    """Validate one handoff safety contract against the envelope it describes.

    Two failure classes matter. The first is decoration: a boundary that claims
    enforcement without naming an enforcer, or a boundary name nobody has an
    entry for. The second is disagreement: a contract whose prohibited actions,
    executors, targets, or authority values no longer match the envelope stored
    beside it, which is how a stale copy is spotted.
    """
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    errors: list[str] = []
    if set(value) != set(HANDOFF_SAFETY_CONTRACT_KEYS):
        errors.append(f"{label} keys are invalid")
    if value.get("schema_version") != HANDOFF_SAFETY_CONTRACT_SCHEMA_VERSION:
        errors.append(f"{label} schema_version is invalid")
    if value.get("status") != "prepared_not_observed":
        errors.append(f"{label} status is invalid")
    if value.get("produced_offline") is not True:
        errors.append(f"{label} produced_offline must be true")
    if list(value.get("input_sources", [])) != list(HANDOFF_CONTRACT_INPUT_SOURCES):
        errors.append(f"{label} input_sources must be the allowlisted local metadata surfaces")
    errors.extend(_handoff_contract_boundary_errors(value.get("boundaries"), label))
    errors.extend(_handoff_contract_evidence_errors(value.get("evidence_requirements"), label))
    for key in ("prohibited_actions", "allowed_executors", "allowed_targets"):
        errors.extend(_string_list_errors(value.get(key), f"{label} {key}"))
    for key in ("merge_authority", "external_action_authority", "safety_profile_revision"):
        if not isinstance(value.get(key), str):
            errors.append(f"{label} {key} must be a string")
    if "not dispatch" not in str(value.get("claim_boundary", "")).lower():
        errors.append(f"{label} claim_boundary must preserve the dispatch boundary")
    if isinstance(envelope, dict):
        for contract_key, envelope_key in (
            ("prohibited_actions", "blocked_actions"),
            ("allowed_executors", "allowed_executors"),
            ("allowed_targets", "allowed_targets"),
            ("merge_authority", "merge_authority"),
            ("external_action_authority", "external_action_authority"),
            ("safety_profile_revision", "safety_profile_revision"),
        ):
            if value.get(contract_key) != envelope.get(envelope_key):
                errors.append(f"{label} {contract_key} must match the authority envelope {envelope_key}")
    return errors


def validate_action_gate_verdict(value: Any, label: str = "action_gate") -> list[str]:
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    errors: list[str] = []
    extra = sorted(set(value) - set(ACTION_GATE_KEYS))
    if extra:
        errors.append(f"{label} has unsupported keys: {extra}")
    if value.get("schema_version") != ACTION_GATE_SCHEMA_VERSION:
        errors.append(f"{label} schema_version is invalid")
    if value.get("status") != "prepared_not_observed":
        errors.append(f"{label} status is invalid")
    if value.get("outcome") not in {"allow", "deny"}:
        errors.append(f"{label} outcome is invalid")
    for key in ("dispatchable", "choice_required"):
        if not isinstance(value.get(key), bool):
            errors.append(f"{label} {key} must be boolean")
    if "not dispatch" not in str(value.get("claim_boundary", "")).lower():
        errors.append(f"{label} claim_boundary must preserve the dispatch boundary")
    errors.extend(
        validate_task_authority_envelope(
            value.get("authority_envelope"),
            f"{label} authority_envelope",
            parent_dispatchable=value.get("dispatchable"),
        )
    )
    confirmation = value.get("confirmation")
    if not isinstance(confirmation, dict) or set(confirmation) != set(CONFIRMATION_KEYS):
        errors.append(f"{label} confirmation keys are invalid")
    else:
        armed = confirmation.get("armed_ladders")
        suppressed = confirmation.get("suppressed_ladders")
        if not isinstance(armed, list) or len(armed) > 1 or not set(armed) <= set(CONFIRMATION_LADDERS):
            errors.append(f"{label} confirmation must arm at most one ladder")
            armed = []
        if confirmation.get("required") is not bool(armed):
            errors.append(f"{label} confirmation.required must match the armed ladder")
        if not isinstance(suppressed, list) or len(armed) + len(suppressed) != len(CONFIRMATION_LADDERS):
            errors.append(f"{label} confirmation must account for every candidate ladder")
        if confirmation.get("action_id") != (LADDER_ACTION_IDS.get(armed[0], "") if armed else ""):
            errors.append(f"{label} confirmation.action_id must match the armed ladder")
    denial = value.get("denial")
    if value.get("outcome") == "deny":
        if not isinstance(denial, dict) or set(denial) != set(DENIAL_KEYS):
            errors.append(f"{label} denial keys are invalid")
        else:
            for key in ("rule_id", "field", "correction"):
                if not str(denial.get(key, "")).strip():
                    errors.append(f"{label} denial.{key} is required")
            errors.extend(_string_list_errors(denial.get("reason_codes"), f"{label} denial.reason_codes"))
        if value.get("dispatchable") is not False or value.get("choice_required") is not False:
            errors.append(f"{label} a denied verdict must not stay dispatchable or ask for a choice")
    elif denial is not None:
        errors.append(f"{label} denial is only allowed on a denied verdict")
    return errors
