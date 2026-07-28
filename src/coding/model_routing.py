"""Deterministic model routing for prepared coding handoffs.

`resolve_model_route` is a pure function: same inputs, byte-identical payload,
no I/O, no clock, no environment reads. It prepares metadata only — omh never
invokes a model, never retries, and never switches models at runtime.

Reading provenance back from a persisted route MUST go through
`route_provenance` — it is the sole sanctioned accessor. Frozen fanout
contracts may carry `coding_model_route/v1` payloads whose `source` vocabulary
predates chains; that recorded value is returned verbatim, never translated
into v2 vocabulary, because restating a frozen record would make it say
something that never happened.

Effort precedence: requested effort > chain-entry effort > none.
`effort_change.requested` always holds the USER's request and the field is
absent when no effort was requested; chain-supplied efforts never appear in
`effort_change`.

Throughout this module, "profile" means a key of `EXECUTOR_MODEL_OPTIONS`.
Profiles without a catalog entry (hermes, generic, the runtime profiles) are
never matrix cells and never require chains; the executor CLI default applies.
"""

from __future__ import annotations

from typing import Final, Mapping

CODING_MODEL_ROUTE_SCHEMA_VERSION: Final[str] = "coding_model_route/v2"
# The frozen v1 identifier: referenced only for reading persisted payloads.
CODING_MODEL_ROUTE_V1_SCHEMA_VERSION: Final[str] = "coding_model_route/v1"
CODING_MODEL_ROUTE_SUPPORTED_SCHEMA_VERSIONS: Final[tuple[str, ...]] = (
    CODING_MODEL_ROUTE_SCHEMA_VERSION,
    CODING_MODEL_ROUTE_V1_SCHEMA_VERSION,
)

# Roles are the subagent shapes a fanout/handoff unit can declare. They name the
# kind of work, never a vendor, so per-role defaults stay executor-neutral.
MODEL_ROLES: Final[tuple[str, ...]] = (
    "brain",
    "implementation",
    "design_visual",
    "review",
    "docs",
)

MODEL_ROUTE_STATUSES: Final[tuple[str, ...]] = (
    "routed",
    "choice_required",
    "model_unrouted",
    "no_model_catalog",
)

MODEL_ROUTE_PROVENANCES: Final[tuple[str, ...]] = (
    "request_named_model",
    "role_chain_head",
    "role_unchained",
    "executor_default",
    "no_catalog",
)

# The frozen v1 vocabulary. Not aspirational documentation: `route_provenance`
# validates persisted v1 payloads against it, and the v1 fixture test consumes
# it. A v1 `source` outside this tuple is malformed and reads as "unknown".
_V1_MODEL_ROUTE_SOURCES: Final[tuple[str, ...]] = (
    "request_named_model",
    "role_catalog_default",
    "role_catalog_candidates",
    "executor_default",
    "no_catalog",
)

EFFORT_CHANGE_KINDS: Final[tuple[str, ...]] = (
    "unchanged",
    "ladder_downgrade",
    "catalog_no_authority_passthrough",
    "unknown_vocabulary_passthrough",
    "rejected_unsafe_shape",
)

CODING_MODEL_ROUTE_CLAIM_BOUNDARY: Final[str] = (
    "A model route is prepared metadata for a coding handoff or dispatch argv. Model availability, "
    "entitlement, pricing, and quota are provider truth omh does not observe, and a routed model is "
    "not execution, verification, review, CI, or merge evidence. Entries after the selected one are "
    "prepared next-candidate advice; omh never retries or switches models itself."
)

# Built-in default candidates per dispatchable/prompt-handoff executor profile.
# Claude Code accepts stable tier aliases that track the newest model in each
# tier; Codex takes vendor model ids. Both CLIs also accept ids this catalog
# has never heard of, so requested models always pass through unvalidated —
# the catalog is a default candidate list, not an allowlist.
MODEL_CATALOG_KIND: Final[str] = "built_in_defaults"

# Closed vocabulary for a route's catalog basis. `local_inventory` marks a
# catalog derived from the user's own local configuration at observation time;
# such routes additionally carry `catalog_fingerprint` so a frozen record
# names the exact basis it was resolved from.
MODEL_CATALOG_KINDS: Final[tuple[str, ...]] = ("built_in_defaults", "local_inventory")

EXECUTOR_MODEL_OPTIONS: Final[dict[str, tuple[dict[str, object], ...]]] = {
    "codex": (
        {
            "model_id": "gpt-5-codex",
            "label": "Codex frontier coding model",
            "tier": "frontier",
            "recommended_roles": ("brain", "review", "design_visual"),
            "reasoning_efforts": ("low", "medium", "high", "xhigh"),
        },
        {
            "model_id": "gpt-5",
            "label": "General frontier model",
            "tier": "standard",
            "recommended_roles": ("implementation", "docs", "review"),
            "reasoning_efforts": ("low", "medium", "high", "xhigh"),
        },
    ),
    "claude-code": (
        {
            "model_id": "opus",
            "label": "Claude frontier tier alias",
            "tier": "frontier",
            "recommended_roles": ("brain", "review", "design_visual"),
            "reasoning_efforts": ("low", "medium", "high", "xhigh", "max"),
        },
        {
            "model_id": "sonnet",
            "label": "Claude standard tier alias",
            "tier": "standard",
            "recommended_roles": ("implementation",),
            "reasoning_efforts": ("low", "medium", "high", "xhigh", "max"),
        },
        {
            "model_id": "haiku",
            "label": "Claude fast tier alias",
            "tier": "fast",
            "recommended_roles": ("docs",),
            "reasoning_efforts": ("low", "medium", "high", "xhigh", "max"),
        },
    ),
}

# Ordered per-role chains: head is the deterministic selection, later entries
# are prepared next-candidate advice. An entry's reasoning_effort applies only
# when the user requested none (requested > chain-entry > none). Every profile
# in EXECUTOR_MODEL_OPTIONS carries a chain for every role and every chain
# model_id exists in that profile's catalog — both directions are policy-gated.
ROLE_MODEL_CHAINS: Final[dict[str, dict[str, tuple[dict[str, str], ...]]]] = {
    "codex": {
        "brain": (
            {"model_id": "gpt-5-codex", "reasoning_effort": "high"},
            {"model_id": "gpt-5", "reasoning_effort": "high"},
        ),
        "implementation": (
            {"model_id": "gpt-5", "reasoning_effort": ""},
            {"model_id": "gpt-5-codex", "reasoning_effort": ""},
        ),
        "design_visual": (
            {"model_id": "gpt-5-codex", "reasoning_effort": ""},
            {"model_id": "gpt-5", "reasoning_effort": ""},
        ),
        "review": (
            {"model_id": "gpt-5-codex", "reasoning_effort": ""},
            {"model_id": "gpt-5", "reasoning_effort": ""},
        ),
        "docs": (
            {"model_id": "gpt-5", "reasoning_effort": ""},
        ),
    },
    "claude-code": {
        "brain": (
            {"model_id": "opus", "reasoning_effort": "high"},
            {"model_id": "sonnet", "reasoning_effort": "high"},
        ),
        "implementation": (
            {"model_id": "sonnet", "reasoning_effort": ""},
            {"model_id": "opus", "reasoning_effort": ""},
        ),
        "design_visual": (
            {"model_id": "opus", "reasoning_effort": ""},
            {"model_id": "sonnet", "reasoning_effort": ""},
        ),
        "review": (
            {"model_id": "opus", "reasoning_effort": ""},
            {"model_id": "sonnet", "reasoning_effort": ""},
        ),
        "docs": (
            {"model_id": "haiku", "reasoning_effort": ""},
            {"model_id": "sonnet", "reasoning_effort": ""},
        ),
    },
}

# Model-family prefixes mirror the dynamic-workflow target classifier so both
# surfaces name families the same way; bare Claude tier aliases fold into the
# claude family because the claude CLI resolves them to concrete claude models.
_MODEL_FAMILY_PREFIXES: Final[tuple[tuple[str, str], ...]] = (
    ("gpt-", "gpt"),
    ("glm-", "glm"),
    ("claude-", "claude"),
    ("openai-", "openai"),
    ("anthropic-", "anthropic"),
    ("gemini-", "gemini"),
    ("grok-", "grok"),
    ("qwen-", "qwen"),
    ("kimi-", "kimi"),
    ("mistral-", "mistral"),
    ("llama-", "llama"),
    ("deepseek-", "deepseek"),
    ("codestral-", "codestral"),
)
_CLAUDE_TIER_ALIASES: Final[frozenset[str]] = frozenset({"opus", "sonnet", "haiku"})


def model_family(model_id: str) -> str:
    normalized = str(model_id or "").strip().casefold()
    if not normalized:
        return ""
    # Provider-prefixed ids (`opencode/kimi-k3`, `anthropic/claude-opus-5`)
    # classify by the model segment: the provider names where it runs, the
    # family names what it is.
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[1]
    if normalized in _CLAUDE_TIER_ALIASES:
        return "claude"
    for prefix, family in _MODEL_FAMILY_PREFIXES:
        if normalized.startswith(prefix):
            return family
    return "unknown"


def resolve_model_route(
    executor_profile: str,
    *,
    requested_model: str = "",
    requested_effort: str = "",
    role: str = "",
    requested_domain: str = "",
    chains: Mapping[str, Mapping[str, tuple[Mapping[str, str], ...]]] | None = None,
    local_catalog: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return the deterministic prepared model route for one executor profile.

    Four stages, each recorded in `attempted[]`: an explicitly requested model
    always wins (passthrough, never rejected); otherwise a declared role routes
    to its chain head; a role whose chain is missing is an explicit choice;
    no data leaves the executor CLI default in place as a named outcome.

    Injection precedence — the two parameters never apply to the same profile:
    `chains` (tests only) overrides role chains for profiles WITH a built-in
    catalog; `local_catalog` (a `local_model_catalog/v1` payload derived by
    the caller from an observed inventory — I/O stays in the caller, this
    function remains pure) is consulted ONLY when the profile has no built-in
    catalog and the payload names this profile. A route resolved from a local
    catalog records `catalog_kind: "local_inventory"` plus the catalog's
    `fingerprint` so the frozen record names its exact basis, and a local
    catalog never gains effort authority — observed config variants are
    evidence of use, not of a model's effort vocabulary. An absent
    `catalog_fingerprint` on any route means "no local basis was consulted",
    never "unknown basis" — v1 routes and built-in-catalog routes correctly
    carry none.

    `requested_domain` is explicit unit data (never inferred from text). When
    a locally-derived chain resolves and the catalog's affinity vocabulary
    knows the domain, chain entries from affine families are stably reordered
    to the front — an advisory reorder recorded in `attempted[]`, never a
    veto: every entry stays in the chain and a requested model still wins.
    Outside a local catalog the domain is recorded and explicitly skipped.
    """
    profile = str(executor_profile or "").strip().casefold()
    raw_role = str(role or "").strip()
    normalized_role = _normalized_role(raw_role)
    role_reasons: list[str] = []
    if raw_role and not normalized_role:
        # A declared role that fails to normalize must be named, not erased:
        # this reason lands in frozen contracts, so "no role was requested"
        # would be a false statement about the request.
        role_reasons.append(
            f"Role {raw_role!r} is not a known role ({', '.join(MODEL_ROLES)}); it was ignored."
        )
    model = str(requested_model or "").strip()
    effort = str(requested_effort or "").strip().casefold()
    options = EXECUTOR_MODEL_OPTIONS.get(profile, ())
    catalog_kind = MODEL_CATALOG_KIND
    catalog_fingerprint: dict[str, object] | None = None
    effort_authoritative = True
    local_chains: Mapping[str, tuple[Mapping[str, str], ...]] = {}
    if not options and _local_catalog_applies(profile, local_catalog):
        raw_options = local_catalog.get("options", []) if isinstance(local_catalog, Mapping) else []
        resolved_options = tuple(option for option in raw_options if isinstance(option, Mapping))
        if resolved_options:
            # The local basis is claimed only once it demonstrably exists: an
            # empty or corrupt payload must fall through to the executor
            # default WITHOUT a fingerprint, or the frozen record would name
            # a basis that never adjudicated anything.
            options = resolved_options
            raw_chains = local_catalog.get("chains", {}) if isinstance(local_catalog, Mapping) else {}
            local_chains = raw_chains if isinstance(raw_chains, Mapping) else {}
            raw_fingerprint = local_catalog.get("fingerprint") if isinstance(local_catalog, Mapping) else None
            catalog_fingerprint = dict(raw_fingerprint) if isinstance(raw_fingerprint, Mapping) else None
            catalog_kind = "local_inventory"
            effort_authoritative = False
        else:
            role_reasons.append(
                "A local model catalog was offered but carried no usable options; it was not consulted."
            )
    candidates = [dict(option) for option in options]
    if catalog_kind == "local_inventory":
        role_chain = tuple(local_chains.get(normalized_role, ())) if normalized_role else ()
    else:
        chain_table = ROLE_MODEL_CHAINS if chains is None else chains
        role_chain = tuple(chain_table.get(profile, {}).get(normalized_role, ())) if normalized_role else ()
    attempted: list[dict[str, str]] = []
    domain = str(requested_domain or "").strip().casefold().replace("-", "_")
    if domain:
        role_chain = _domain_ordered_chain(
            domain,
            role_chain,
            local_catalog if catalog_kind == "local_inventory" else None,
            attempted,
        )

    if model:
        attempted.append(
            {"stage": "requested_model", "outcome": "selected", "reason": f"request names `{model}`"}
        )
        selected_effort, effort_change = _selected_effort(
            options, effort, "", model, authoritative=effort_authoritative
        )
        return _route_payload(
            profile,
            status="routed",
            provenance="request_named_model",
            role=normalized_role,
            selected_model=model,
            selected_reasoning_effort=selected_effort,
            effort_change=effort_change,
            catalog_kind=catalog_kind,
            catalog_fingerprint=catalog_fingerprint,
            domain=domain,
            chain=_chain_payload(options, role_chain, selected_model=""),
            attempted=attempted,
            candidates=candidates,
            reasons=role_reasons + [f"The request names `{model}` directly, so the catalog is advisory only."],
        )
    attempted.append({"stage": "requested_model", "outcome": "skipped", "reason": "no model requested"})

    if not options:
        attempted.append(
            {"stage": "role_chain", "outcome": "skipped", "reason": "profile has no model catalog"}
        )
        attempted.append(
            {"stage": "executor_default", "outcome": "selected", "reason": "no catalog; executor CLI default applies"}
        )
        selected_effort, effort_change = _selected_effort(
            options, effort, "", "", authoritative=effort_authoritative
        )
        return _route_payload(
            profile,
            status="no_model_catalog",
            provenance="no_catalog",
            role=normalized_role,
            selected_reasoning_effort=selected_effort,
            effort_change=effort_change,
            catalog_kind=catalog_kind,
            catalog_fingerprint=catalog_fingerprint,
            domain=domain,
            chain=[],
            attempted=attempted,
            candidates=[],
            reasons=role_reasons
            + [
                f"No built-in model catalog exists for `{profile or 'unknown'}`; the executor CLI default applies.",
            ],
        )

    if normalized_role:
        if role_chain:
            head = role_chain[0]
            selected = str(head.get("model_id", ""))
            attempted.append(
                {"stage": "role_chain", "outcome": "selected", "reason": f"chain head `{selected}` for role `{normalized_role}`"}
            )
            selected_effort, effort_change = _selected_effort(
                options, effort, str(head.get("reasoning_effort", "") or ""), selected,
                authoritative=effort_authoritative,
            )
            return _route_payload(
                profile,
                status="routed",
                provenance="role_chain_head",
                role=normalized_role,
                selected_model=selected,
                selected_reasoning_effort=selected_effort,
                effort_change=effort_change,
                catalog_kind=catalog_kind,
                catalog_fingerprint=catalog_fingerprint,
                domain=domain,
                chain=_chain_payload(options, role_chain, selected_model=selected),
                attempted=attempted,
                candidates=candidates,
                reasons=role_reasons
                + [
                    f"Role `{normalized_role}` routes to its ordered chain head for `{profile}`.",
                ],
            )
        # Unreachable-by-construction under the bidirectional parity gate
        # (every catalog profile carries a chain for every role); kept as a
        # structural net so a future catalog edit fails loudly instead of
        # guessing. Tested via a constructed chain-gap dict.
        attempted.append(
            {"stage": "role_chain", "outcome": "unavailable", "reason": f"no chain declared for role `{normalized_role}`"}
        )
        selected_effort, effort_change = _selected_effort(
            options, effort, "", "", authoritative=effort_authoritative
        )
        return _route_payload(
            profile,
            status="choice_required",
            provenance="role_unchained",
            role=normalized_role,
            selected_reasoning_effort=selected_effort,
            effort_change=effort_change,
            catalog_kind=catalog_kind,
            catalog_fingerprint=catalog_fingerprint,
            domain=domain,
            chain=[],
            attempted=attempted,
            candidates=candidates,
            reasons=role_reasons
            + [
                f"Role `{normalized_role}` has no declared chain for `{profile}`; "
                f"pick one of the {len(candidates)} catalog options or name a model.",
            ],
        )
    attempted.append({"stage": "role_chain", "outcome": "skipped", "reason": "no role declared"})

    attempted.append(
        {"stage": "executor_default", "outcome": "selected", "reason": "no model or role; executor CLI default applies"}
    )
    unrouted_reason = (
        "No model or role was requested, so the executor CLI default model applies."
        if not raw_role
        else "No usable model or role remained, so the executor CLI default model applies."
    )
    selected_effort, effort_change = _selected_effort(
        options, effort, "", "", authoritative=effort_authoritative
    )
    return _route_payload(
        profile,
        status="model_unrouted",
        provenance="executor_default",
        role=normalized_role,
        selected_reasoning_effort=selected_effort,
        effort_change=effort_change,
        catalog_kind=catalog_kind,
        catalog_fingerprint=catalog_fingerprint,
        domain=domain,
        chain=[],
        attempted=attempted,
        candidates=candidates,
        reasons=role_reasons + [unrouted_reason],
    )


def model_route_for_unit(
    unit: Mapping[str, object],
    executor_target: str,
    local_catalog: Mapping[str, object] | None = None,
) -> dict[str, object] | None:
    """Return the prepared model route for a fanout unit, or None when unrouted.

    `local_catalog` is passed through verbatim; this function stays pure and
    the resolver's precedence rules decide whether it applies.
    """
    model = str(unit.get("model", "") or "").strip()
    effort = str(unit.get("reasoning_effort", "") or "").strip()
    role = str(unit.get("role", "") or "").strip()
    if not model and not effort and not role:
        # A declared domain alone never triggers routing: it advises chain
        # order, it does not request a model.
        return None
    return resolve_model_route(
        executor_target,
        requested_model=model,
        requested_effort=effort,
        role=role,
        requested_domain=str(unit.get("domain", "") or "").strip(),
        local_catalog=local_catalog,
    )


def route_provenance(route: Mapping[str, object] | object) -> tuple[str, str]:
    """Return (value, vocabulary) for a route of any schema version.

    The sole sanctioned accessor for reading provenance back from a route —
    including v1 payloads embedded in frozen fanout contracts. A v1 `source`
    is returned verbatim (never translated into v2 chain vocabulary: the
    record must keep saying exactly what was written). vocabulary is one of
    "v1" | "v2" | "unknown"; anything malformed reads ("unknown", "unknown").
    """
    if not isinstance(route, Mapping):
        return ("unknown", "unknown")
    version = str(route.get("schema_version", "") or "")
    if version == CODING_MODEL_ROUTE_SCHEMA_VERSION:
        value = str(route.get("provenance", "") or "")
        if value in MODEL_ROUTE_PROVENANCES:
            return (value, "v2")
        return ("unknown", "unknown")
    if version == CODING_MODEL_ROUTE_V1_SCHEMA_VERSION:
        value = str(route.get("source", "") or "")
        if value in _V1_MODEL_ROUTE_SOURCES:
            return (value, "v1")
        return ("unknown", "unknown")
    return ("unknown", "unknown")


def _normalized_role(role: str) -> str:
    normalized = str(role or "").strip().casefold().replace("-", "_")
    return normalized if normalized in MODEL_ROLES else ""


def _domain_ordered_chain(
    domain: str,
    role_chain: tuple[Mapping[str, str], ...],
    local_catalog: Mapping[str, object] | None,
    attempted: list[dict[str, str]],
) -> tuple[Mapping[str, str], ...]:
    """Stably move affine-family chain entries to the front for a declared domain.

    Advisory only: every entry stays in the chain, the reorder (or the reason
    none happened) is recorded in `attempted[]`, and outside a locally-derived
    catalog the domain is explicitly skipped — built-in chains stay curated.
    """
    if local_catalog is None:
        attempted.append(
            {
                "stage": "domain_affinity",
                "outcome": "skipped",
                "reason": f"domain `{domain}` recorded; affinity reordering applies to locally-derived chains only",
            }
        )
        return role_chain
    affinities = local_catalog.get("domain_affinities", {})
    affine = (
        tuple(str(family) for family in affinities.get(domain, ()))
        if isinstance(affinities, Mapping)
        else ()
    )
    if not affine:
        attempted.append(
            {
                "stage": "domain_affinity",
                "outcome": "unknown_domain",
                "reason": f"domain `{domain}` is not in the catalog's affinity vocabulary; chain order unchanged",
            }
        )
        return role_chain
    if not role_chain:
        attempted.append(
            {"stage": "domain_affinity", "outcome": "skipped", "reason": "no chain to reorder"}
        )
        return role_chain
    front = tuple(entry for entry in role_chain if model_family(str(entry.get("model_id", ""))) in affine)
    rest = tuple(entry for entry in role_chain if model_family(str(entry.get("model_id", ""))) not in affine)
    if not front:
        attempted.append(
            {
                "stage": "domain_affinity",
                "outcome": "no_affine_candidate",
                "reason": f"no chain entry belongs to an affine family ({', '.join(affine)}) for domain `{domain}`",
            }
        )
        return role_chain
    reordered = front + rest
    if reordered == role_chain:
        attempted.append(
            {
                "stage": "domain_affinity",
                "outcome": "already_ordered",
                "reason": f"affine families ({', '.join(affine)}) already lead the chain for domain `{domain}`",
            }
        )
        return role_chain
    attempted.append(
        {
            "stage": "domain_affinity",
            "outcome": "reordered",
            "reason": f"affine families ({', '.join(affine)}) moved ahead for domain `{domain}`; no entry removed",
        }
    )
    return reordered


def _local_catalog_applies(profile: str, local_catalog: Mapping[str, object] | None) -> bool:
    """A local catalog applies only to the profile it names — never to a
    profile with a built-in catalog (the caller gate) and never to a payload
    resolved for some other executor."""
    if not isinstance(local_catalog, Mapping):
        return False
    return str(local_catalog.get("executor_profile", "") or "").strip().casefold() == profile


def _supported_efforts(
    options: tuple[Mapping[str, object], ...], model_id: str
) -> tuple[tuple[str, ...], str]:
    """Return (efforts, authority) with authority "exact_model" | "profile_union".

    Only an exact catalog match grants the catalog authority over a model's
    effort vocabulary. The union fallback exists so a requested effort is never
    silently dropped for a model the catalog has not met — the catalog
    disclaims authority there, so its answer is advisory, never adjudicating.
    An empty options tuple returns ((), "profile_union").
    """
    for option in options:
        if str(option.get("model_id", "")).casefold() == str(model_id or "").casefold():
            return tuple(str(value) for value in option.get("reasoning_efforts", ())), "exact_model"
    union: list[str] = []
    for option in options:
        for value in option.get("reasoning_efforts", ()):
            if str(value) not in union:
                union.append(str(value))
    return tuple(union), "profile_union"


# Ordered strongest-first; a downgrade walks DOWN from the requested rung to
# the first supported one. Ladder order is the authority, not adjacency in any
# particular model's supported list.
_EFFORT_LADDER: Final[tuple[str, ...]] = ("max", "xhigh", "high", "medium", "low")

# Efforts are a closed vocabulary shape, unlike model ids: an effort value is
# embedded into a codex `--config key=value` composite, so free text here would
# lean on the third-party TOML parser for containment. Off-catalog efforts are
# accepted only in this shape; anything else falls back to the CLI default.
_EFFORT_SHAPE_CHARSET: Final[frozenset[str]] = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")


def _selected_effort(
    options: tuple[Mapping[str, object], ...],
    requested_effort: str,
    chain_effort: str,
    model_id: str,
    *,
    authoritative: bool = True,
) -> tuple[str, dict[str, str] | None]:
    """Resolve the effort and its typed change record.

    Precedence: requested > chain-entry > none. The change record exists only
    when the user requested an effort; chain-supplied efforts never appear in
    it. The ladder downgrades only under exact-model catalog authority — the
    catalog never adjudicates a model it has not met, and a non-authoritative
    catalog (local inventory) never adjudicates at all.
    """
    if requested_effort:
        supported, authority = _supported_efforts(options, model_id)
        if not authoritative:
            authority = "profile_union"
        if requested_effort in supported:
            return requested_effort, _effort_change(requested_effort, requested_effort, "unchanged", "supported as requested")
        if requested_effort in _EFFORT_LADDER and authority == "exact_model":
            for rung in _EFFORT_LADDER[_EFFORT_LADDER.index(requested_effort) :]:
                if rung in supported:
                    return rung, _effort_change(
                        requested_effort,
                        rung,
                        "ladder_downgrade",
                        f"`{requested_effort}` is not supported by `{model_id}`; stepped down to `{rung}`",
                    )
            return "", _effort_change(
                requested_effort, "", "ladder_downgrade", f"no supported rung at or below `{requested_effort}`"
            )
        if requested_effort in _EFFORT_LADDER:
            return requested_effort, _effort_change(
                requested_effort,
                requested_effort,
                "catalog_no_authority_passthrough",
                "the catalog has no exact entry for this model, so it does not adjudicate the effort",
            )
        if set(requested_effort) <= _EFFORT_SHAPE_CHARSET:
            # Unknown-but-effort-shaped values still pass through so a newer
            # CLI vocabulary is not blocked by a stale catalog.
            return requested_effort, _effort_change(
                requested_effort, requested_effort, "unknown_vocabulary_passthrough", "effort-shaped but off-vocabulary"
            )
        return "", _effort_change(
            requested_effort, "", "rejected_unsafe_shape", "not an effort-shaped value; CLI default applies"
        )
    if chain_effort:
        return chain_effort, None
    return "", None


def _effort_change(requested: str, selected: str, kind: str, reason: str) -> dict[str, str]:
    return {"requested": requested, "selected": selected, "kind": kind, "reason": reason}


def _chain_payload(
    options: tuple[Mapping[str, object], ...],
    role_chain: tuple[Mapping[str, str], ...],
    *,
    selected_model: str,
) -> list[dict[str, object]]:
    by_model: dict[str, Mapping[str, object]] = {
        str(option.get("model_id", "")): option for option in options
    }
    payload: list[dict[str, object]] = []
    for position, entry in enumerate(role_chain):
        model_id = str(entry.get("model_id", ""))
        option = by_model.get(model_id, {})
        payload.append(
            {
                "position": position,
                "model_id": model_id,
                "reasoning_effort": str(entry.get("reasoning_effort", "") or ""),
                "tier": str(option.get("tier", "")),
                "label": str(option.get("label", "")),
                "selected": bool(selected_model) and model_id == selected_model and position == 0,
            }
        )
    return payload


def _route_payload(
    profile: str,
    *,
    status: str,
    provenance: str,
    role: str,
    chain: list[dict[str, object]],
    attempted: list[dict[str, str]],
    candidates: list[dict[str, object]],
    reasons: list[str],
    selected_model: str = "",
    selected_reasoning_effort: str = "",
    effort_change: dict[str, str] | None = None,
    catalog_kind: str = MODEL_CATALOG_KIND,
    catalog_fingerprint: dict[str, object] | None = None,
    domain: str = "",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": CODING_MODEL_ROUTE_SCHEMA_VERSION,
        "executor_profile": profile,
        "status": status,
        "provenance": provenance,
        "role": role,
        "selected_model": selected_model,
        "selected_reasoning_effort": selected_reasoning_effort,
        "model_family": model_family(selected_model),
        "chain": chain,
        "attempted": list(attempted),
        "candidates": [
            {
                "model_id": str(option.get("model_id", "")),
                "label": str(option.get("label", "")),
                "tier": str(option.get("tier", "")),
                "recommended_roles": list(option.get("recommended_roles", ())),
                "reasoning_efforts": list(option.get("reasoning_efforts", ())),
            }
            for option in candidates
        ],
        "catalog_kind": catalog_kind,
        "reasons": list(reasons),
        "claim_boundary": CODING_MODEL_ROUTE_CLAIM_BOUNDARY,
    }
    if domain:
        # Present only when the unit declared a domain: existing payloads
        # stay byte-identical.
        payload["domain"] = domain
    if catalog_fingerprint is not None:
        payload["catalog_fingerprint"] = catalog_fingerprint
    if effort_change is not None:
        payload["effort_change"] = effort_change
    return payload
