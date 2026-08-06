"""Deterministic, fail-closed safety preflight for prepared coding work.

A deliberate sibling of `skill_governance.py`, built in its idiom: ordered
precedence levels, a closed reason-code vocabulary, and a content digest that
pins the decision. The direction is inverted. `skill_governance` resolves what
a policy SELECTS, so a later level overrides an earlier one. Safety preflight
resolves what a request is PERMITTED to prepare, so no level may widen what
`builtin_omh` denies -- a level can only add denials.

Naming, on purpose: there is no "guard" anywhere in this module. `routing/
policy.py` owns ~60 `*_guard_applies` helpers and every one of them keys off
words in a user message. A safety rule wired into that vocabulary would make a
safety decision depend on user text. Rules, preflight, and verdicts live here;
guards stay in routing.

Pre-expansion by construction. Every input is a bounded metadata field that
exists BEFORE a prompt template is expanded. `coding_delegation`'s
`message_context_mode="full"` path can interpolate the raw user message
verbatim into the prompt; a check that inspected the emitted `*_preview` fields
would be blind exactly there. So the mode and the raw-content admission flag
are inputs, and the raw text never is -- a request carrying message bodies,
code, or credentials is denied before any rule reads it.

Each rule reads one field class, not every string. `FIELD_CLASSES` says which
class each request field belongs to, and the classes are what make the rules
mean anything: an opaque metadata ref is free-form caller text, so
credential-shape detection belongs there; a target path is a source location
the user named, so `token_store.py` is a filename and not a credential; a
closed vocabulary already denies every value outside it. Only the body-shape
bound is universal, because a body is a body in any field.

No model, no network, no new dependency: the whole evaluator is stdlib
`hashlib` plus `re` over caller-supplied metadata.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import re
from typing import Final

from ..coding.project_governance import ORG_SAFETY_RULE_SOURCE_REASON_CODES
from ..system.metadata_safety import (
    is_body_shaped_metadata_text,
    is_sensitive_metadata_text,
    require_opaque_metadata_ref,
)

SAFETY_PROFILE_SCHEMA_VERSION: Final = "omh_safety_profile/v1"
SAFETY_PREFLIGHT_VERDICT_SCHEMA_VERSION: Final = "omh_safety_preflight_verdict/v1"
SAFETY_PREFLIGHT_RECHECK_SCHEMA_VERSION: Final = "omh_safety_preflight_recheck/v1"

SAFETY_PREFLIGHT_CLAIM_BOUNDARY: Final = (
    "Passing safety preflight is permission to prepare this work; it is not compliance, "
    "execution, review, CI, or merge evidence."
)

# Strongest first. `builtin_omh` is the floor and the only level that can
# allow; `org` (issue #802) is opt-in and deny-only; `native_hermes` is a
# recommendation surface that never decides, exactly as in `skill_governance`.
SAFETY_PREFLIGHT_PRECEDENCE: Final = ("builtin_omh", "org", "native_hermes")

MAX_FIELD_CHARS: Final = 200
MAX_PATH_CHARS: Final = 240
MAX_TARGET_PATHS: Final = 32
MAX_REMOTE_TARGETS: Final = 8
MAX_PERSISTED_CONTENT_REFS: Final = 8
MAX_EVIDENCE_CLAIMS: Final = 8
MAX_OBSERVED_RECORD_REFS: Final = 8

MESSAGE_CONTEXT_MODES: Final = ("bounded", "full")
REMOTE_TARGET_KINDS: Final = ("git_remote", "issue_tracker", "package_registry", "public_internet")
EVIDENCE_CLAIMS: Final = (
    "prepared_not_observed",
    "dispatch_observed",
    "result_observed",
    "review_observed",
    "ci_observed",
    "merge_observed",
)
_OBSERVED_EVIDENCE_CLAIMS: Final = frozenset(EVIDENCE_CLAIMS) - {"prepared_not_observed"}

# The closed request shape. A key outside this set is a denial, which is what
# keeps code bodies, credentials, and raw prompts from ever reaching a rule.
REQUEST_FIELDS: Final = (
    "owner",
    "approved_scope",
    "message_context_mode",
    "raw_content_included",
    "target_paths",
    "remote_targets",
    "persisted_content_refs",
    "evidence_claims",
    "observed_record_refs",
)

# The field classes. `opaque_ref` is free-form caller text carrying an
# identifier, `path` is a source location the caller named, `vocabulary` is a
# closed value set whose own rule denies every non-member. Every request field
# has exactly one class, and an unclassified string is read as `opaque_ref`,
# the strictest of the three.
FIELD_CLASS_OPAQUE_REF: Final = "opaque_ref"
FIELD_CLASS_PATH: Final = "path"
FIELD_CLASS_VOCABULARY: Final = "vocabulary"

FIELD_CLASSES: Final = {
    "owner": FIELD_CLASS_OPAQUE_REF,
    "approved_scope": FIELD_CLASS_OPAQUE_REF,
    "message_context_mode": FIELD_CLASS_VOCABULARY,
    "raw_content_included": FIELD_CLASS_OPAQUE_REF,
    "target_paths": FIELD_CLASS_PATH,
    "remote_targets": FIELD_CLASS_OPAQUE_REF,
    "persisted_content_refs": FIELD_CLASS_OPAQUE_REF,
    "evidence_claims": FIELD_CLASS_VOCABULARY,
    "observed_record_refs": FIELD_CLASS_OPAQUE_REF,
}
# `remote_targets` entries are objects: the kind is a closed vocabulary, the
# ref is an opaque metadata ref. Any other key inherits the field's own class.
REMOTE_TARGET_FIELD_CLASSES: Final = {
    "kind": FIELD_CLASS_VOCABULARY,
    "ref": FIELD_CLASS_OPAQUE_REF,
}

# Credential shape is read on caller-supplied identifiers only. A path is a
# file the caller named, and a closed vocabulary denies non-members by
# membership, so reading either as a possible credential denies ordinary work
# without adding any protection.
SECRET_SHAPE_FIELD_CLASSES: Final = (FIELD_CLASS_OPAQUE_REF,)

RULE_INPUT_METADATA_BOUNDED: Final = "input_metadata_bounded"
RULE_OWNER_DECLARED: Final = "owner_declared"
RULE_APPROVED_SCOPE_DECLARED: Final = "approved_scope_declared"
RULE_RAW_CONTEXT_DECLARED: Final = "raw_context_declared"
RULE_TARGET_PATHS_BOUNDED: Final = "target_paths_bounded"
RULE_SECRETS_ABSENT: Final = "secrets_absent"
RULE_REMOTE_TARGETS_DECLARED: Final = "remote_targets_declared"
RULE_PERSISTED_CONTENT_REFERENCED: Final = "persisted_content_referenced"
RULE_EVIDENCE_CLAIM_BOUNDED: Final = "evidence_claim_bounded"
RULE_ORG_RULE_SOURCE: Final = "org_rule_source"

# (rule id, axis, level, reason codes). Rule ids are stable strings and the
# order is the denial precedence: the first rule that denies is the
# responsible rule, so the same input always names the same rule.
_RULES: Final = (
    (
        RULE_INPUT_METADATA_BOUNDED,
        "input",
        "builtin_omh",
        ("request_not_an_object", "unknown_request_field", "body_shaped_request_value"),
    ),
    (RULE_SECRETS_ABSENT, "secrets", "builtin_omh", ("secret_shaped_value",)),
    (RULE_OWNER_DECLARED, "owner", "builtin_omh", ("owner_missing", "owner_not_opaque_ref")),
    (
        RULE_APPROVED_SCOPE_DECLARED,
        "approved_scope",
        "builtin_omh",
        ("approved_scope_missing", "approved_scope_not_opaque_ref"),
    ),
    (
        RULE_RAW_CONTEXT_DECLARED,
        "raw_context",
        "builtin_omh",
        ("raw_context_mode_unknown", "raw_context_undeclared"),
    ),
    (
        RULE_TARGET_PATHS_BOUNDED,
        "paths",
        "builtin_omh",
        (
            "target_path_not_bounded",
            "target_path_count_exceeded",
            "target_path_absolute",
            "target_path_escapes_project",
        ),
    ),
    (
        RULE_REMOTE_TARGETS_DECLARED,
        "remote_targets",
        "builtin_omh",
        (
            "remote_target_not_bounded",
            "remote_target_count_exceeded",
            "remote_target_kind_unknown",
            "remote_target_ref_missing",
        ),
    ),
    (
        RULE_PERSISTED_CONTENT_REFERENCED,
        "persisted_content",
        "builtin_omh",
        ("persisted_content_count_exceeded", "persisted_content_inline"),
    ),
    (
        RULE_EVIDENCE_CLAIM_BOUNDED,
        "evidence_claims",
        "builtin_omh",
        (
            "evidence_claim_count_exceeded",
            "evidence_claim_unknown",
            "evidence_claim_unobserved",
            "observed_record_ref_invalid",
        ),
    ),
    (
        RULE_ORG_RULE_SOURCE,
        "org_rules",
        "org",
        (
            *(code for code in ORG_SAFETY_RULE_SOURCE_REASON_CODES if code != "org_source_available"),
            "org_rule_unknown_value",
            "org_rule_denied",
            "org_widening_ignored",
        ),
    ),
)

# One correction per reason code: what the caller must change to be allowed.
_CORRECTIONS: Final = {
    "request_not_an_object": "Pass a safety preflight request object with the declared metadata fields.",
    "unknown_request_field": f"Remove the field; only {', '.join(REQUEST_FIELDS)} may be evaluated.",
    "body_shaped_request_value": f"Replace the body with a single bounded reference of at most {MAX_FIELD_CHARS} characters.",
    "secret_shaped_value": "Remove the credential-shaped value and pass an opaque reference instead.",
    "owner_missing": "Name the responsible owner in the owner field.",
    "owner_not_opaque_ref": "Use a short opaque owner reference without spaces, bodies, or credentials.",
    "approved_scope_missing": "Declare the approved scope this work is permitted to touch.",
    "approved_scope_not_opaque_ref": "Use a short opaque approved-scope reference.",
    "raw_context_mode_unknown": f"Set message_context_mode to one of {', '.join(MESSAGE_CONTEXT_MODES)}.",
    "raw_context_undeclared": "Declare raw_content_included as a boolean, and declare it true only under the full message context mode.",
    "target_path_not_bounded": f"Pass target paths as bounded strings of at most {MAX_PATH_CHARS} characters.",
    "target_path_count_exceeded": f"Reduce target_paths to at most {MAX_TARGET_PATHS} entries.",
    "target_path_absolute": "Use a project-relative target path instead of an absolute or home-anchored path.",
    "target_path_escapes_project": "Remove the parent-directory segment so the path stays inside the project.",
    "remote_target_not_bounded": "Pass each remote target as an object with exactly a kind and a ref.",
    "remote_target_count_exceeded": f"Reduce remote_targets to at most {MAX_REMOTE_TARGETS} entries.",
    "remote_target_kind_unknown": f"Declare a remote target kind from {', '.join(REMOTE_TARGET_KINDS)}.",
    "remote_target_ref_missing": "Give the remote target a short opaque reference.",
    "persisted_content_count_exceeded": f"Reduce persisted_content_refs to at most {MAX_PERSISTED_CONTENT_REFS} entries.",
    "persisted_content_inline": "Persist the content separately and pass its opaque reference, not the content.",
    "evidence_claim_count_exceeded": f"Reduce evidence_claims to at most {MAX_EVIDENCE_CLAIMS} entries.",
    "evidence_claim_unknown": f"Use an evidence claim from {', '.join(EVIDENCE_CLAIMS)}.",
    "evidence_claim_unobserved": "Attach the observed record reference that backs the claim, or claim prepared_not_observed.",
    "observed_record_ref_invalid": f"Pass at most {MAX_OBSERVED_RECORD_REFS} short opaque observed record references.",
    "org_source_missing": "Create the configured org rule source file or turn the org rule source off.",
    "org_source_unsafe": "Point the org rule source at a regular file that is not a symlink.",
    "org_source_unreadable": "Grant read access to the configured org rule source file.",
    "org_source_oversized": "Shrink the org rule source below the configured byte bound.",
    "org_source_timed_out": "Serve the org rule source from local storage that reads within the time bound.",
    "org_source_malformed": "Fix the org rule source so it parses as the bounded rule document.",
    "org_source_unknown_version": "Set the org rule source schema_version to the supported version.",
    "org_source_unknown_fields": "Remove the unsupported field from the org rule source.",
    "org_source_unsafe_metadata": "Remove the credential-shaped or body-shaped value from the org rule source.",
    "org_rule_unknown_value": "Use an org rule value this profile revision understands, or the rule cannot be honoured.",
    "org_rule_denied": "The org rule source narrows this profile; change the request or the org rule source.",
    "org_widening_ignored": "No change is required; a wider org value was discarded because the org level can only narrow.",
    "allowed": "",
}


def safety_rule_profile() -> dict[str, object]:
    """The full rule profile: the content the safety-profile revision pins."""
    return {
        "schema_version": SAFETY_PROFILE_SCHEMA_VERSION,
        "precedence": list(SAFETY_PREFLIGHT_PRECEDENCE),
        "rules": [
            {"id": rule_id, "axis": axis, "level": level, "reason_codes": list(codes)}
            for rule_id, axis, level, codes in _RULES
        ],
        "corrections": {code: _CORRECTIONS[code] for code in sorted(_CORRECTIONS)},
        "bounds": {
            "max_field_chars": MAX_FIELD_CHARS,
            "max_path_chars": MAX_PATH_CHARS,
            "max_target_paths": MAX_TARGET_PATHS,
            "max_remote_targets": MAX_REMOTE_TARGETS,
            "max_persisted_content_refs": MAX_PERSISTED_CONTENT_REFS,
            "max_evidence_claims": MAX_EVIDENCE_CLAIMS,
            "max_observed_record_refs": MAX_OBSERVED_RECORD_REFS,
        },
        "vocabularies": {
            "request_fields": list(REQUEST_FIELDS),
            "message_context_modes": list(MESSAGE_CONTEXT_MODES),
            "remote_target_kinds": list(REMOTE_TARGET_KINDS),
            "evidence_claims": list(EVIDENCE_CLAIMS),
        },
        # Pinned by the digest on purpose: which rule reads which field is part
        # of the profile a prepared artifact was cleared under, not an
        # implementation detail a later revision can change silently.
        "field_classes": dict(FIELD_CLASSES),
        "remote_target_field_classes": dict(REMOTE_TARGET_FIELD_CLASSES),
        "secret_shape_field_classes": list(SECRET_SHAPE_FIELD_CLASSES),
        "claim_boundary": SAFETY_PREFLIGHT_CLAIM_BOUNDARY,
    }


def safety_profile_digest(profile: Mapping[str, object]) -> str:
    """Content hash of a rule profile, used as the safety-profile revision."""
    # Stable recursive encoding rather than json.dumps, for the reason
    # `skill_governance.policy_decision_digest` records: this digest runs on
    # the prepared-artifact path and the efficiency contract forbids JSON
    # serialization there. Sorted keys keep it order-independent.
    return hashlib.sha256(_stable_encode(profile).encode("utf-8")).hexdigest()


def safety_profile_revision() -> str:
    """The revision a prepared artifact pins so drift is detectable later."""
    return safety_profile_digest(safety_rule_profile())


def evaluate_safety_preflight(
    request: Mapping[str, object] | None,
    *,
    org_rule_source: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return one verdict for a pre-expansion request.

    `request` is bounded metadata only (see `REQUEST_FIELDS`). `org_rule_source`
    is the result of `project_governance.read_org_safety_rule_source`, or None
    when the org level is not opted in. A denial names the responsible rule, the
    offending field, and the correction. Passing is permission to prepare, never
    evidence that anything ran.
    """
    revision = safety_profile_revision()
    levels = ["builtin_omh"]
    org_codes: list[str] = []
    org_denial: _Denial | None = None
    limits = _default_limits()
    if org_rule_source is not None:
        levels.append("org")
        org_denial, org_codes, limits = _org_level(org_rule_source)
    denial = _builtin_denial(request)
    if denial is None:
        denial = org_denial
    # Narrowing runs only when the org level participated, so a verdict can
    # never name a level that `levels_applied` does not list.
    if denial is None and org_rule_source is not None and isinstance(request, Mapping):
        denial = _org_narrowing_denial(request, limits)
        if denial is not None:
            org_codes = [*org_codes, denial[2]]
    return _verdict(denial, revision=revision, levels=levels, org_reason_codes=org_codes)


def recheck_safety_preflight_revision(carried: object) -> dict[str, object]:
    """Cheap drift check for a later boundary such as dispatch.

    Compares a carried revision -- either a verdict or the revision string --
    against the live profile without re-running any rule. `dispatchable` here
    means only that the revision still matches; the carried verdict's own
    `status` still has to be an allow.
    """
    live = safety_profile_revision()
    value = carried.get("safety_profile_revision") if isinstance(carried, Mapping) else carried
    text = value if isinstance(value, str) else ""
    if not text:
        status, reason_code = "missing", "revision_missing"
    elif text == live:
        status, reason_code = "current", "revision_current"
    else:
        status, reason_code = "drifted", "revision_drifted"
    return {
        "schema_version": SAFETY_PREFLIGHT_RECHECK_SCHEMA_VERSION,
        "status": status,
        "reason_code": reason_code,
        "carried_revision": text,
        "live_revision": live,
        "dispatchable": status == "current",
        "claim_boundary": SAFETY_PREFLIGHT_CLAIM_BOUNDARY,
    }


# (rule id, field, reason code, level)
_Denial = tuple[str, str, str, str]

_ABSOLUTE_PATH_RE: Final = re.compile(r"^(?:[/\\~]|[A-Za-z]:)")


def _default_limits() -> dict[str, object]:
    return {"max_target_paths": MAX_TARGET_PATHS, "denied_remote_target_kinds": ()}


def _verdict(
    denial: _Denial | None,
    *,
    revision: str,
    levels: list[str],
    org_reason_codes: list[str],
) -> dict[str, object]:
    rule_id, field, reason_code, level = denial if denial is not None else ("", "", "allowed", "")
    return {
        "schema_version": SAFETY_PREFLIGHT_VERDICT_SCHEMA_VERSION,
        "status": "allow" if denial is None else "deny",
        "rule_id": rule_id,
        "field": field,
        "reason_code": reason_code,
        "correction": _CORRECTIONS[reason_code],
        "level": level,
        "safety_profile_revision": revision,
        "profile_schema_version": SAFETY_PROFILE_SCHEMA_VERSION,
        "levels_applied": list(levels),
        "org_reason_codes": list(org_reason_codes),
        "claim_boundary": SAFETY_PREFLIGHT_CLAIM_BOUNDARY,
    }


def _builtin_denial(request: object) -> _Denial | None:
    if not isinstance(request, Mapping):
        return (RULE_INPUT_METADATA_BOUNDED, "request", "request_not_an_object", "builtin_omh")
    unknown = sorted(str(key) for key in request if key not in REQUEST_FIELDS)
    if unknown:
        return (RULE_INPUT_METADATA_BOUNDED, unknown[0], "unknown_request_field", "builtin_omh")
    admission = _admission_denial(request)
    if admission is not None:
        return admission
    for check in (
        _owner_denial,
        _approved_scope_denial,
        _raw_context_denial,
        _target_paths_denial,
        _remote_targets_denial,
        _persisted_content_denial,
        _evidence_claims_denial,
    ):
        denial = check(request)
        if denial is not None:
            return denial
    return None


def _admission_denial(request: Mapping[str, object]) -> _Denial | None:
    """Refuse credentials and body-shaped values before any rule reads them.

    Credential shape is read on the opaque-ref class only. The body-shape bound
    is read on every string, with the path class carrying the longer bound.
    """
    for field, text, field_class in _bounded_strings(request):
        if field_class in SECRET_SHAPE_FIELD_CLASSES and is_sensitive_metadata_text(text):
            return (RULE_SECRETS_ABSENT, field, "secret_shaped_value", "builtin_omh")
        limit = MAX_PATH_CHARS if field_class == FIELD_CLASS_PATH else MAX_FIELD_CHARS
        if is_body_shaped_metadata_text(text, limit=limit):
            return (RULE_INPUT_METADATA_BOUNDED, field, "body_shaped_request_value", "builtin_omh")
    return None


def _bounded_strings(request: Mapping[str, object]) -> list[tuple[str, str, str]]:
    """Every string in the request, paired with the field class it belongs to."""
    found: list[tuple[str, str, str]] = []
    for field in REQUEST_FIELDS:
        field_class = FIELD_CLASSES.get(field, FIELD_CLASS_OPAQUE_REF)
        value = request.get(field)
        if isinstance(value, str):
            found.append((field, value, field_class))
        elif _is_sequence(value):
            for index, item in enumerate(value):
                if isinstance(item, str):
                    found.append((f"{field}[{index}]", item, field_class))
                elif isinstance(item, Mapping):
                    found.extend(
                        (
                            f"{field}[{index}].{key}",
                            entry,
                            REMOTE_TARGET_FIELD_CLASSES.get(str(key), field_class)
                            if field == "remote_targets"
                            else field_class,
                        )
                        for key, entry in sorted(item.items())
                        if isinstance(entry, str)
                    )
    return found


def _owner_denial(request: Mapping[str, object]) -> _Denial | None:
    owner = request.get("owner")
    if not isinstance(owner, str) or not owner.strip():
        return (RULE_OWNER_DECLARED, "owner", "owner_missing", "builtin_omh")
    if not _is_opaque_ref(owner, field="owner"):
        return (RULE_OWNER_DECLARED, "owner", "owner_not_opaque_ref", "builtin_omh")
    return None


def _approved_scope_denial(request: Mapping[str, object]) -> _Denial | None:
    scope = request.get("approved_scope")
    if not isinstance(scope, str) or not scope.strip():
        return (RULE_APPROVED_SCOPE_DECLARED, "approved_scope", "approved_scope_missing", "builtin_omh")
    if not _is_opaque_ref(scope, field="approved_scope"):
        return (RULE_APPROVED_SCOPE_DECLARED, "approved_scope", "approved_scope_not_opaque_ref", "builtin_omh")
    return None


def _raw_context_denial(request: Mapping[str, object]) -> _Denial | None:
    """The pre-expansion admission decision, not the post-expansion preview.

    `coding_delegation` decides verbatim interpolation here, before the prompt
    exists, so this is the only place a rule can see it.

    The check is one-directional, because `raw_content_included` is what the
    caller will actually do with the raw message rather than a restatement of
    the mode. `full` is a ceiling: a caller may prepare a narrower artifact than
    the mode permits, and the coding lane does exactly that whenever the
    prepared payload carries no verbatim message. Requiring equality would deny
    that ordinary case while proving nothing, since a value re-derived from the
    mode can never disagree with it. Declaring verbatim raw content under a
    bounded mode is the real contradiction, and it denies.
    """
    mode = request.get("message_context_mode")
    if mode not in MESSAGE_CONTEXT_MODES:
        return (RULE_RAW_CONTEXT_DECLARED, "message_context_mode", "raw_context_mode_unknown", "builtin_omh")
    included = request.get("raw_content_included")
    if not isinstance(included, bool) or (included and mode != "full"):
        return (RULE_RAW_CONTEXT_DECLARED, "raw_content_included", "raw_context_undeclared", "builtin_omh")
    return None


def _target_paths_denial(request: Mapping[str, object]) -> _Denial | None:
    paths = request.get("target_paths", ())
    if not _is_str_sequence(paths):
        return (RULE_TARGET_PATHS_BOUNDED, "target_paths", "target_path_not_bounded", "builtin_omh")
    if len(paths) > MAX_TARGET_PATHS:
        return (RULE_TARGET_PATHS_BOUNDED, "target_paths", "target_path_count_exceeded", "builtin_omh")
    for index, item in enumerate(paths):
        field = f"target_paths[{index}]"
        if not item.strip():
            return (RULE_TARGET_PATHS_BOUNDED, field, "target_path_not_bounded", "builtin_omh")
        if _ABSOLUTE_PATH_RE.match(item):
            return (RULE_TARGET_PATHS_BOUNDED, field, "target_path_absolute", "builtin_omh")
        if ".." in item.replace("\\", "/").split("/"):
            return (RULE_TARGET_PATHS_BOUNDED, field, "target_path_escapes_project", "builtin_omh")
    return None


def _remote_targets_denial(request: Mapping[str, object]) -> _Denial | None:
    remotes = request.get("remote_targets", ())
    if not _is_sequence(remotes):
        return (RULE_REMOTE_TARGETS_DECLARED, "remote_targets", "remote_target_not_bounded", "builtin_omh")
    if len(remotes) > MAX_REMOTE_TARGETS:
        return (RULE_REMOTE_TARGETS_DECLARED, "remote_targets", "remote_target_count_exceeded", "builtin_omh")
    for index, item in enumerate(remotes):
        field = f"remote_targets[{index}]"
        if not isinstance(item, Mapping) or set(item) != {"kind", "ref"}:
            return (RULE_REMOTE_TARGETS_DECLARED, field, "remote_target_not_bounded", "builtin_omh")
        if item["kind"] not in REMOTE_TARGET_KINDS:
            return (RULE_REMOTE_TARGETS_DECLARED, f"{field}.kind", "remote_target_kind_unknown", "builtin_omh")
        if not _is_opaque_ref(item["ref"], field=f"{field}.ref"):
            return (RULE_REMOTE_TARGETS_DECLARED, f"{field}.ref", "remote_target_ref_missing", "builtin_omh")
    return None


def _persisted_content_denial(request: Mapping[str, object]) -> _Denial | None:
    refs = request.get("persisted_content_refs", ())
    if not _is_str_sequence(refs):
        return (RULE_PERSISTED_CONTENT_REFERENCED, "persisted_content_refs", "persisted_content_inline", "builtin_omh")
    if len(refs) > MAX_PERSISTED_CONTENT_REFS:
        return (
            RULE_PERSISTED_CONTENT_REFERENCED,
            "persisted_content_refs",
            "persisted_content_count_exceeded",
            "builtin_omh",
        )
    for index, item in enumerate(refs):
        field = f"persisted_content_refs[{index}]"
        if not _is_opaque_ref(item, field=field):
            return (RULE_PERSISTED_CONTENT_REFERENCED, field, "persisted_content_inline", "builtin_omh")
    return None


def _evidence_claims_denial(request: Mapping[str, object]) -> _Denial | None:
    observed_refs = request.get("observed_record_refs", ())
    if not _is_str_sequence(observed_refs) or len(observed_refs) > MAX_OBSERVED_RECORD_REFS:
        return (RULE_EVIDENCE_CLAIM_BOUNDED, "observed_record_refs", "observed_record_ref_invalid", "builtin_omh")
    for index, item in enumerate(observed_refs):
        field = f"observed_record_refs[{index}]"
        if not _is_opaque_ref(item, field=field):
            return (RULE_EVIDENCE_CLAIM_BOUNDED, field, "observed_record_ref_invalid", "builtin_omh")
    claims = request.get("evidence_claims", ())
    if not _is_str_sequence(claims):
        return (RULE_EVIDENCE_CLAIM_BOUNDED, "evidence_claims", "evidence_claim_unknown", "builtin_omh")
    if len(claims) > MAX_EVIDENCE_CLAIMS:
        return (RULE_EVIDENCE_CLAIM_BOUNDED, "evidence_claims", "evidence_claim_count_exceeded", "builtin_omh")
    for index, claim in enumerate(claims):
        field = f"evidence_claims[{index}]"
        if claim not in EVIDENCE_CLAIMS:
            return (RULE_EVIDENCE_CLAIM_BOUNDED, field, "evidence_claim_unknown", "builtin_omh")
        if claim in _OBSERVED_EVIDENCE_CLAIMS and not observed_refs:
            return (RULE_EVIDENCE_CLAIM_BOUNDED, field, "evidence_claim_unobserved", "builtin_omh")
    return None


def _org_level(org_rule_source: object) -> tuple[_Denial | None, list[str], dict[str, object]]:
    """Apply the opt-in org level: deny-only, never widening, fail-closed."""
    limits = _default_limits()
    if not isinstance(org_rule_source, Mapping):
        return _org_unavailable("org_source_malformed", "org_rule_source"), ["org_source_malformed"], limits
    reason = org_rule_source.get("reason_code")
    if reason not in ORG_SAFETY_RULE_SOURCE_REASON_CODES:
        return (
            _org_unavailable("org_source_malformed", "org_rule_source.reason_code"),
            ["org_source_malformed"],
            limits,
        )
    codes = [str(reason)]
    if org_rule_source.get("status") != "available":
        field = str(org_rule_source.get("field") or "org_rule_source")
        return (RULE_ORG_RULE_SOURCE, field, str(reason), "org"), codes, limits
    rules = org_rule_source.get("rules")
    if not isinstance(rules, Mapping):
        return _org_unavailable("org_source_malformed", "org_rule_source.rules"), [*codes, "org_source_malformed"], limits
    kinds = rules.get("denied_remote_target_kinds", ())
    if not _is_str_sequence(kinds) or any(kind not in REMOTE_TARGET_KINDS for kind in kinds):
        return (
            (RULE_ORG_RULE_SOURCE, "org_rule_source.denied_remote_target_kinds", "org_rule_unknown_value", "org"),
            [*codes, "org_rule_unknown_value"],
            limits,
        )
    cap = rules.get("max_target_paths")
    if cap is not None and (not isinstance(cap, int) or isinstance(cap, bool) or cap < 0):
        return (
            (RULE_ORG_RULE_SOURCE, "org_rule_source.max_target_paths", "org_rule_unknown_value", "org"),
            [*codes, "org_rule_unknown_value"],
            limits,
        )
    if isinstance(cap, int) and not isinstance(cap, bool):
        # Narrowing only. A larger org cap is recorded and discarded, so the
        # org level can never widen what the built-in profile allows.
        if cap > MAX_TARGET_PATHS:
            codes.append("org_widening_ignored")
        else:
            limits["max_target_paths"] = cap
    limits["denied_remote_target_kinds"] = tuple(kinds)
    return None, codes, limits


def _org_narrowing_denial(request: Mapping[str, object], limits: Mapping[str, object]) -> _Denial | None:
    paths = request.get("target_paths", ())
    cap = limits["max_target_paths"]
    if _is_str_sequence(paths) and isinstance(cap, int) and len(paths) > cap:
        return (RULE_ORG_RULE_SOURCE, "target_paths", "org_rule_denied", "org")
    denied = set(limits["denied_remote_target_kinds"])
    remotes = request.get("remote_targets", ())
    if denied and _is_sequence(remotes):
        for index, item in enumerate(remotes):
            if isinstance(item, Mapping) and item.get("kind") in denied:
                return (RULE_ORG_RULE_SOURCE, f"remote_targets[{index}].kind", "org_rule_denied", "org")
    return None


def _org_unavailable(reason_code: str, field: str) -> _Denial:
    return (RULE_ORG_RULE_SOURCE, field, reason_code, "org")


def _is_opaque_ref(value: object, *, field: str) -> bool:
    try:
        require_opaque_metadata_ref(value, field=field)
    except ValueError:
        return False
    return True


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _is_str_sequence(value: object) -> bool:
    return _is_sequence(value) and all(isinstance(item, str) for item in value)


def _stable_encode(value: object) -> str:
    if isinstance(value, Mapping):
        return "{" + "\x1f".join(f"{key}\x1e{_stable_encode(value[key])}" for key in sorted(value)) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + "\x1f".join(_stable_encode(item) for item in value) + "]"
    return f"{type(value).__name__}:{value}"
