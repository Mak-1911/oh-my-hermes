from __future__ import annotations

import json

from ..host_observation import observe_plugin_hook_call
from ..omh_roles import extract_role_marker, resolve_role_name, role_aliases, role_names


def pre_tool_call(**kwargs) -> dict[str, object] | None:
    """Return only host-supported pre-tool directives or role warnings."""
    observe_plugin_hook_call("pre_tool_call", kwargs)
    context_parts: list[str] = []
    payload: dict[str, object] = {}
    role_warning = _delegate_role_warning(kwargs)
    if role_warning:
        context_parts.append(role_warning)

    if not context_parts:
        return None
    payload["context"] = "\n\n".join(context_parts)
    return payload


def _delegate_role_warning(kwargs: dict) -> str:
    if str(kwargs.get("tool_name", "") or "") != "delegate_task":
        return ""
    tool_input = kwargs.get("tool_input") or {}
    if isinstance(tool_input, str):
        try:
            parsed = json.loads(tool_input)
        except json.JSONDecodeError:
            return ""
        tool_input = parsed if isinstance(parsed, dict) else {}
    if not isinstance(tool_input, dict):
        return ""
    marker = extract_role_marker(str(tool_input.get("goal", "") or ""))
    if not marker:
        return ""
    available = role_names()
    aliases = role_aliases()
    if marker in available or resolve_role_name(marker) in available:
        return ""
    return (
        f"[OMH Role Warning] Unknown role '{marker}' in delegate_task goal. "
        f"Available roles: {', '.join(available) or '(none)'}. "
        f"Legacy aliases: {', '.join(sorted(aliases)) or '(none)'}. "
        "No OMH role context will be injected for that subagent."
    )
