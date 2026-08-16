from __future__ import annotations

import re
from typing import Any

from ..paths import OmhPaths


HERMES_MODEL_SETTINGS_SCHEMA_VERSION = "hermes_model_settings/v1"
HERMES_AUX_ALIASES = (
    "vision",
    "web_extract",
    "compression",
    "skills_hub",
    "approval",
    "mcp",
    "title_generation",
    "memory_query_rewrite",
    "tts_audio_tags",
    "triage_specifier",
    "kanban_decomposer",
    "profile_describer",
    "goal_judge",
    "curator",
)

_KEY = re.compile(r"^([a-z_]+):")
_CLAIM_BOUNDARY = (
    "Model settings are read from Hermes configuration; a configured alias is not evidence "
    "that a request used that model."
)


def _scalar_value(line: str) -> str:
    value = line.partition(":")[2].strip()
    if not value:
        return ""
    if value[0] in {'"', "'"}:
        quote = value[0]
        for index in range(len(value) - 1, 0, -1):
            if value[index] == quote:
                remainder = value[index + 1 :].strip()
                if not remainder or remainder.startswith("#"):
                    value = value[: index + 1]
                    break
    elif " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _parse_settings(config_text: str) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    settings: dict[str, str] = {}
    auxiliary: dict[str, dict[str, str]] = {}
    top_level = ""
    auxiliary_task = ""
    for line in config_text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            match = _KEY.match(line)
            top_level = match.group(1) if match else ""
            auxiliary_task = ""
            continue
        if top_level == "auxiliary" and line.startswith("  ") and not line.startswith("    "):
            match = _KEY.match(line[2:])
            auxiliary_task = match.group(1) if match else ""
            continue
        if top_level in {"model", "agent"} and line.startswith("  ") and not line.startswith("    "):
            match = _KEY.match(line[2:])
            if match:
                key = match.group(1)
                if (top_level, key) in {
                    ("model", "default"),
                    ("model", "provider"),
                    ("agent", "reasoning_effort"),
                }:
                    settings[f"{top_level}.{key}"] = _scalar_value(line)
            continue
        if top_level == "auxiliary" and auxiliary_task and line.startswith("    ") and not line.startswith("      "):
            match = _KEY.match(line[4:])
            if match and match.group(1) in {"model", "reasoning_effort"}:
                auxiliary.setdefault(auxiliary_task, {})[match.group(1)] = _scalar_value(line)
    return settings, auxiliary


def _alias_entry(*, alias: str, model: str, effort: str, source: str) -> dict[str, Any]:
    label = f"{model}:{effort}" if model and effort else model or "inherit"
    return {
        "alias": alias,
        "model": model,
        "effort": effort,
        "source": source,
        "configured": bool(model),
        "label": label,
    }


def _unreadable_result() -> dict[str, Any]:
    return {
        "schema_version": HERMES_MODEL_SETTINGS_SCHEMA_VERSION,
        "observed": False,
        "reason": "config_unreadable",
        "provider": "",
        "aliases": [],
        "configured_count": 0,
        "inherit_count": 0,
        "claim_boundary": _CLAIM_BOUNDARY,
    }


def read_hermes_model_settings(paths: OmhPaths) -> dict[str, Any]:
    try:
        config_text = (paths.hermes_home / "config.yaml").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _unreadable_result()

    settings, auxiliary = _parse_settings(config_text)
    aliases = [
        _alias_entry(
            alias="main",
            model=settings.get("model.default", ""),
            effort=settings.get("agent.reasoning_effort", ""),
            source="config.model.default",
        )
    ]
    for alias in HERMES_AUX_ALIASES:
        alias_settings = auxiliary.get(alias, {})
        aliases.append(
            _alias_entry(
                alias=alias,
                model=alias_settings.get("model", ""),
                effort=alias_settings.get("reasoning_effort", ""),
                source=f"config.auxiliary.{alias}",
            )
        )
    configured_count = sum(1 for entry in aliases if entry["configured"])
    return {
        "schema_version": HERMES_MODEL_SETTINGS_SCHEMA_VERSION,
        "observed": True,
        "reason": "",
        "provider": settings.get("model.provider", ""),
        "aliases": aliases,
        "configured_count": configured_count,
        "inherit_count": len(aliases) - configured_count,
        "claim_boundary": _CLAIM_BOUNDARY,
    }
