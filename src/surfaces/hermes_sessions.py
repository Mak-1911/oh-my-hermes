from __future__ import annotations

import json
import sqlite3
from json import JSONDecodeError
from typing import Any

from ..paths import OmhPaths


HERMES_SESSION_SCHEMA_VERSION = "hermes_session_observation/v1"
_CLAIM_BOUNDARY = (
    "Session counts are a read-only observation of Hermes' own session store; "
    "they are not execution, review, CI, merge, or token-usage evidence."
)


def observe_hermes_sessions(paths: OmhPaths) -> dict[str, Any]:
    db_path = paths.hermes_home / "state.db"
    if not db_path.exists():
        return _unobserved("state_db_missing")

    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1.0)
        try:
            cursor = connection.cursor()
            total = int(
                cursor.execute(
                    "select count(*) from sessions where archived = 0 and hidden = 0"
                ).fetchone()[0]
            )
            live = int(
                cursor.execute(
                    "select count(*) from sessions where archived = 0 and hidden = 0 and ended_at is null"
                ).fetchone()[0]
            )
            current_row = cursor.execute(
                "select model, model_config from sessions where archived = 0 and hidden = 0 and ended_at is null "
                "order by coalesce(last_activity_at, started_at) desc limit 1"
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return _unobserved("state_db_unreadable")

    return {
        "schema_version": HERMES_SESSION_SCHEMA_VERSION,
        "observed": True,
        "reason": "",
        "live": live,
        "total": total,
        "current_model": _current_model(current_row),
        "source": "hermes_state_db_readonly",
        "claim_boundary": _CLAIM_BOUNDARY,
    }


def _current_model(row: tuple[Any, Any] | None) -> dict[str, Any]:
    if row is None:
        return _current_model_payload()

    value = row[0] if isinstance(row[0], str) else ""
    provider = ""
    effort = ""
    try:
        model_config = json.loads(row[1])
    except (TypeError, ValueError, JSONDecodeError):
        model_config = {}

    if isinstance(model_config, dict):
        configured_provider = model_config.get("provider")
        if isinstance(configured_provider, str):
            provider = configured_provider
        reasoning_config = model_config.get("reasoning_config")
        if isinstance(reasoning_config, dict):
            configured_effort = reasoning_config.get("effort")
            if isinstance(configured_effort, str):
                effort = configured_effort

    return _current_model_payload(value=value, effort=effort, provider=provider)


def _current_model_payload(*, value: str = "", effort: str = "", provider: str = "") -> dict[str, Any]:
    return {
        "observed": bool(value),
        "value": value,
        "effort": effort,
        "provider": provider,
        "label": f"{value}:{effort}" if value and effort else value or "not observed",
    }


def _unobserved(reason: str) -> dict[str, Any]:
    return {
        "schema_version": HERMES_SESSION_SCHEMA_VERSION,
        "observed": False,
        "reason": reason,
        "live": 0,
        "total": 0,
        "current_model": _current_model_payload(),
        "source": "hermes_state_db_readonly",
        "claim_boundary": _CLAIM_BOUNDARY,
    }
