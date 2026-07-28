"""Deterministic local model inventory (`model_inventory/v1`).

Reporting-only observation of which coding models the user has locally
activated: agent CLIs on PATH, models named by the oh-my-openagent (omo)
config, opencode provider config, and opencode auth provider names. The
inventory answers "what does this user actually have?" before any delegation
or routing decision is proposed.

Boundaries, in order of importance:

- Reporting only. Nothing here enters a model route payload, a frozen fanout
  contract, or persisted state — the inventory is a read-time observation and
  routing stays pure (`model_routing` never imports this module; a test pins
  that direction).
- Metadata only. Model ids, provider names, and variant labels are read;
  secret values never are. Every identifier passes
  `require_opaque_metadata_ref` before it may appear in the payload; anything
  rejected is counted, never echoed. Unreadable sources report a status, not
  a path or an error text.
- Local-file evidence only. Presence in the inventory is configuration
  evidence, not entitlement, quota, or login truth — the provider owns those
  and adjudicates at execution time.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Final, Mapping

from ..system.local_store import utc_now
from ..system.metadata_safety import require_opaque_metadata_ref
from .executor_auth_signals import executor_auth_signals
from .model_routing import model_family

MODEL_INVENTORY_SCHEMA_VERSION: Final[str] = "model_inventory/v1"

MODEL_INVENTORY_CLAIM_BOUNDARY: Final[str] = (
    "A model inventory is a read-time observation of local configuration files and PATH presence. "
    "It is reporting-only advisory context: not entitlement, quota, or login truth, not a route, "
    "and never dispatch, execution, review, CI, or merge evidence."
)

MODEL_INVENTORY_SOURCE_STATUSES: Final[tuple[str, ...]] = ("present", "absent", "unreadable")

# Fixed probe table: agent CLI command names checked for PATH presence only.
# Presence of a wrapper CLI (opencode) is how provider-hosted models
# (gemini/grok/kimi/glm-style) become locally runnable without their own CLI.
CLI_PRESENCE_COMMANDS: Final[tuple[str, ...]] = (
    "codex",
    "claude",
    "opencode",
    "gemini",
    "grok",
    "qwen",
)

# Static advisory notes mapping work domains to model families with a known
# edge there (for example X/Twitter platform data belongs to the grok family's
# home platform). Closed vocabulary, report-only: these notes never rank,
# reorder, or route — they exist so a wrapper proposing a split can mention
# which locally-present family fits a domain. Deliberately NOT named
# "capability": `KNOWN_CAPABILITY_NAMES` (executor runtime capabilities) and
# `capabilities/families.py` (skill families) are different vocabularies.
MODEL_DOMAIN_AFFINITIES: Final[dict[str, tuple[str, ...]]] = {
    "x_platform_data": ("grok",),
    "multimodal_vision": ("gemini", "gpt", "claude"),
}

MODEL_DOMAIN_AFFINITY_CLAIM_BOUNDARY: Final[str] = (
    "Domain affinity notes are static editorial defaults, not observed, benchmarked, or measured "
    "capability — OMH never evaluates a model. They carry no routing effect and never remove or "
    "rank an option; the user's explicit choice always wins."
)

_OMO_AGENT_CONFIG_RELATIVE: Final[str] = ".config/opencode/oh-my-openagent.json"
_OPENCODE_CONFIG_RELATIVE: Final[str] = ".config/opencode/opencode.json"
_OPENCODE_AUTH_RELATIVE: Final[str] = ".local/share/opencode/auth.json"

# Narrow by design (mirrors `_claude_marker`): a failure to read or parse a
# config marks the source `unreadable` and nothing else — no broad except.
_READ_ERRORS = (OSError, UnicodeDecodeError, json.JSONDecodeError)


def local_model_inventory(home: Path | None = None) -> dict[str, object]:
    """Return the metadata-only inventory of locally-activated coding models."""
    base = home if home is not None else Path.home()
    cli_presence = {command: shutil.which(command) is not None for command in CLI_PRESENCE_COMMANDS}
    omo_source, omo_models = _omo_agent_config_source(base / _OMO_AGENT_CONFIG_RELATIVE)
    provider_source = _top_level_key_source(base / _OPENCODE_CONFIG_RELATIVE, section="provider")
    auth_source = _top_level_key_source(base / _OPENCODE_AUTH_RELATIVE, section="")
    auth_signals = executor_auth_signals(base)
    signal_profiles = auth_signals.get("profiles", {})
    login_markers = {
        profile: str(entry.get("login_marker", "unknown"))
        for profile, entry in signal_profiles.items()
        if isinstance(entry, Mapping)
    }
    available_models = _aggregated_models(omo_models)
    families = sorted({str(entry["family"]) for entry in available_models if entry["family"]})
    return {
        "schema_version": MODEL_INVENTORY_SCHEMA_VERSION,
        "observed_at": utc_now(),
        "sources": {
            "cli_presence": {
                "status": "present" if any(cli_presence.values()) else "absent",
                "commands": cli_presence,
            },
            "omo_agent_config": omo_source,
            "opencode_config_providers": provider_source,
            "opencode_auth_providers": auth_source,
            "executor_auth_signals": {"status": "present", "login_markers": login_markers},
        },
        "available_models": available_models,
        "families_present": families,
        "domain_affinity_notes": [
            {
                "domain": domain,
                "affine_families": list(affine),
                "locally_present": sorted(set(affine) & set(families)),
            }
            for domain, affine in sorted(MODEL_DOMAIN_AFFINITIES.items())
        ],
        "domain_affinity_claim_boundary": MODEL_DOMAIN_AFFINITY_CLAIM_BOUNDARY,
        "claim_boundary": MODEL_INVENTORY_CLAIM_BOUNDARY,
    }


def _omo_agent_config_source(path: Path) -> tuple[dict[str, object], list[tuple[str, str, str]]]:
    """Read (source payload, [(provider, model_id, variant), ...]) from the omo config."""
    parsed = _read_json(path)
    if parsed is None:
        return {"status": "absent" if not path.is_file() else "unreadable", "model_count": 0, "rejected": 0}, []
    entries: list[tuple[str, str, str]] = []
    rejected = 0
    for section in ("agents", "categories"):
        table = parsed.get(section)
        if not isinstance(table, Mapping):
            continue
        for spec in table.values():
            if not isinstance(spec, Mapping):
                continue
            candidates = [spec]
            fallbacks = spec.get("fallback_models")
            if isinstance(fallbacks, list):
                candidates.extend(entry for entry in fallbacks if isinstance(entry, Mapping))
            for candidate in candidates:
                if "model" not in candidate:
                    continue
                accepted = _accepted_model_entry(candidate)
                if accepted is None:
                    # Present but shape-rejected data is counted, never echoed.
                    rejected += 1
                else:
                    entries.append(accepted)
    return {"status": "present", "model_count": len(entries), "rejected": rejected}, entries


def _accepted_model_entry(candidate: Mapping[str, object]) -> tuple[str, str, str] | None:
    """Validate one `{model, variant?}` config entry into (provider, model_id, variant)."""
    raw_model = candidate.get("model")
    raw_variant = candidate.get("variant", "")
    try:
        reference = require_opaque_metadata_ref(raw_model, field="model")
        variant = require_opaque_metadata_ref(raw_variant, field="variant") if raw_variant else ""
    except ValueError:
        return None
    provider, separator, model_id = reference.partition("/")
    if not separator or not provider or not model_id or "/" in model_id:
        return None
    return provider, model_id, variant


def _top_level_key_source(path: Path, *, section: str) -> dict[str, object]:
    """Report top-level key NAMES of a JSON object (or of one nested section).

    Values are never read: providers are identified by key name alone, which
    is what keeps auth files presence-only.
    """
    parsed = _read_json(path)
    if parsed is None:
        return {"status": "absent" if not path.is_file() else "unreadable", "providers": [], "rejected": 0}
    table = parsed.get(section) if section else parsed
    if not isinstance(table, Mapping):
        return {"status": "present", "providers": [], "rejected": 0}
    providers: list[str] = []
    rejected = 0
    for key in table:
        try:
            providers.append(require_opaque_metadata_ref(key, field="provider"))
        except ValueError:
            rejected += 1
    return {"status": "present", "providers": sorted(providers), "rejected": rejected}


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        if not path.is_file():
            return None
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except _READ_ERRORS:
        return None
    return parsed if isinstance(parsed, dict) else None


def _aggregated_models(entries: list[tuple[str, str, str]]) -> list[dict[str, object]]:
    variants_by_model: dict[tuple[str, str], set[str]] = {}
    for provider, model_id, variant in entries:
        variants = variants_by_model.setdefault((provider, model_id), set())
        if variant:
            variants.add(variant)
    return [
        {
            "provider": provider,
            "model_id": model_id,
            "variants": sorted(variants),
            "family": model_family(model_id),
        }
        for (provider, model_id), variants in sorted(variants_by_model.items())
    ]
