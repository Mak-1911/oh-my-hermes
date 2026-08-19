"""Read-only observation of Hermes-native subagent delegations.

`delegate_task` children are first-class work the HUD must show live: Hermes
already records everything needed — the child session's model and reasoning
effort in `state.db` (`sessions.model_config`, with `_delegate_from` naming
the parent), token/cache/cost tallies in `session_model_usage`, background
lifecycle in `async_delegations`, and an append-only live transcript plus
`manifest.json` per delegation under `cache/delegation/live/`. This module
joins those surfaces into HUD activity rows without writing anything and
without importing Hermes code.

Everything here is observation of another product's on-disk state, so every
read degrades to "nothing observed" instead of raising: a locked SQLite file,
a torn manifest, or a missing directory must render as an idle HUD segment,
never as a widget error.

The category label is a *projection*, not an observed routing record: Hermes
does not persist which OMH mixture category (if any) chose the child's model,
so the label is derived by matching the observed model+effort against the
shipped mixture chains. A child running the parent session's own model is
labeled ``inherit`` — deliberately, so a delegation wave that never engaged
mixture routing is visible as such instead of masquerading as a routed one.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

# Mirrors SHIPPED_MODEL_RECOMMENDATIONS["categories"] in
# src/coding/model_recommendations.py, projected to (model_alias,
# reasoning_effort) pairs in chain order. The plugin bundle ships standalone
# into $HERMES_HOME/plugins and cannot import src/coding, so the chains are
# embedded; tests/test_plugin_hermes_delegation.py holds the dict-parity gate.
HERMES_MIXTURE_CATEGORY_CHAINS: dict[str, tuple[tuple[str, str], ...]] = {
    "ultrabrain": (("gpt-5.6-sol", "xhigh"),),
    "deep": (("gpt-5.6-terra", "high"),),
    # Architecture/system-design lanes: full-depth effort across three
    # provider ecosystems. Fable and Kimi appear in other chains only at
    # low/high, so at xhigh `mixture_category_for` labels them architect;
    # Sol at xhigh stays labeled ultrabrain (its canonical head), which is
    # the honest projection when the chain falls through to it.
    "architect": (
        ("claude-fable-5", "xhigh"),
        ("gpt-5.6-sol", "xhigh"),
        ("kimi-k3", "xhigh"),
    ),
    "unspecified-high": (("kimi-k3", "medium"), ("claude-opus-5", "medium")),
    # A chain that would otherwise sit in one provider ecosystem ends with a
    # comparable-tier candidate from another (owner rule, 2026-08-19), so one
    # rejected ecosystem cannot exhaust the whole chain.
    "unspecified-low": (
        ("glm-5.2", "low"),
        ("glm-5.2-ultrafast", "low"),
        ("claude-opus-5", "low"),
    ),
    "quick": (
        ("glm-5.2-ultrafast", "low"),
        ("kimi-k3", "low"),
        ("gpt-5.6-luna", "low"),
        ("claude-fable-5", "low"),
    ),
    "writing": (
        ("kimi-k3", "medium"),
        ("qwen3-coder", "medium"),
        ("gemini-3.1-pro", "medium"),
    ),
    "visual-engineering": (("claude-fable-5", "high"), ("kimi-k3", "high")),
    "artistry": (
        ("gemini-3.1-pro", "high"),
        ("claude-fable-5", "high"),
        ("kimi-k3", "high"),
    ),
}

# Rough USD-per-million-token list prices used ONLY when the host recorded no
# cost (subscription billing bills nothing per call; the owner asked for an
# approximation there instead of a blank). These are editable ballpark figures,
# not billing evidence — every cost derived from them is flagged approximate
# and rendered with a `~`. Cache reads are charged at a tenth of input.
APPROX_PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-5.6-sol": (1.25, 10.0),
    "gpt-5.6-terra": (1.25, 10.0),
    "gpt-5.6-luna": (0.25, 2.0),
    "claude-opus-5": (15.0, 75.0),
    "claude-fable-5": (25.0, 100.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "kimi-k3": (0.6, 2.5),
    "glm-5.2": (0.6, 2.2),
    "glm-5.2-ultrafast": (0.3, 1.2),
    "gemini-3.1-pro": (1.25, 10.0),
    "qwen3-coder": (0.4, 1.6),
}


def _approximate_cost_usd(
    model: str, input_tokens: float, output_tokens: float, cache_read_tokens: float
) -> float | None:
    prices = APPROX_PRICE_PER_MTOK.get(_text(model).casefold())
    if not prices or (input_tokens + output_tokens) <= 0:
        return None
    input_price, output_price = prices
    return (
        input_tokens * input_price
        + cache_read_tokens * input_price * 0.1
        + output_tokens * output_price
    ) / 1_000_000


# A child is "running" while its newest observable signal (live transcript
# mtime, usage last_seen, session start) is at most this old. The live log
# streams one line per child event, so an actively working child refreshes
# well inside this window; a child that stalls longer than this reads as done
# rather than spinning forever.
RECENT_ACTIVITY_SECONDS = 150
# Finished children linger as "done" rows for this long so the operator sees
# what just completed — same shape as the todo panel's finished-plan linger.
COMPLETED_LINGER_SECONDS = 15 * 60
# Children older than this are history, not HUD material, regardless of state.
_SESSION_WINDOW_SECONDS = 6 * 3600
_ACTION_LIMIT = 140
_ROW_LIMIT = 8


def _text(value: Any, limit: int = 80) -> str:
    return str(value or "").strip()[:limit]


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value == value and abs(value) != float("inf"):
        return float(value)
    return None


def mixture_category_for(model: str, effort: str, *, parent_model: str = "") -> str:
    """Project an observed child model+effort onto a mixture category label.

    ``inherit`` wins over any chain match: a child on the parent session's own
    model was not routed, whatever chain its model also appears in. Otherwise
    the first category (canonical chain order) whose head matches wins, then
    the first category containing the model anywhere; a chain entry that
    declares a reasoning effort only matches that effort.
    """
    observed_model = _text(model).casefold()
    observed_effort = _text(effort, limit=40).casefold()
    if not observed_model:
        return ""
    if parent_model and observed_model == _text(parent_model).casefold():
        return "inherit"

    def _entry_matches(entry: tuple[str, str]) -> bool:
        alias, chain_effort = entry
        if alias.casefold() != observed_model:
            return False
        return not chain_effort or chain_effort.casefold() == observed_effort

    for category, chain in HERMES_MIXTURE_CATEGORY_CHAINS.items():
        if chain and _entry_matches(chain[0]):
            return category
    for category, chain in HERMES_MIXTURE_CATEGORY_CHAINS.items():
        if any(_entry_matches(entry) for entry in chain):
            return category
    return ""


def _read_manifests(live_root: Path, *, now: float) -> list[dict[str, Any]]:
    """Load recent delegation manifests plus each task log's mtime."""
    manifests: list[dict[str, Any]] = []
    try:
        candidates = sorted(
            (path for path in live_root.iterdir() if path.is_dir()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:_ROW_LIMIT]
    except OSError:
        return []
    for directory in candidates:
        manifest_path = directory / "manifest.json"
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(raw, dict):
            continue
        started = _parse_local_timestamp(str(raw.get("started", "")))
        tasks_raw = raw.get("tasks", [])
        tasks: list[dict[str, Any]] = []
        newest_log_mtime = 0.0
        for task in tasks_raw if isinstance(tasks_raw, list) else []:
            if not isinstance(task, dict):
                continue
            log_mtime = 0.0
            log_path = _text(task.get("log", ""), limit=512)
            if log_path:
                try:
                    log_mtime = Path(log_path).stat().st_mtime
                except OSError:
                    log_mtime = 0.0
            newest_log_mtime = max(newest_log_mtime, log_mtime)
            tasks.append(
                {
                    "goal": _text(task.get("goal", ""), limit=_ACTION_LIMIT),
                    "log_mtime": log_mtime,
                }
            )
        if started and now - max(started, newest_log_mtime) > _SESSION_WINDOW_SECONDS:
            continue
        manifests.append(
            {
                "delegation_id": _text(raw.get("delegation_id", directory.name)),
                "started": started,
                "tasks": tasks,
            }
        )
    return manifests


def _parse_local_timestamp(value: str) -> float:
    # Manifest `started` is "YYYY-MM-DD HH:MM:SS" in local time (written by
    # delegation_live_log with time.strftime).
    try:
        return time.mktime(time.strptime(value.strip(), "%Y-%m-%d %H:%M:%S"))
    except (ValueError, OverflowError):
        return 0.0


def _query_state_db(state_db: Path, *, now: float) -> dict[str, Any]:
    """Read child sessions, usage tallies, and delegation states, read-only."""
    result: dict[str, Any] = {"children": [], "delegation_states": {}, "parent_models": {}}
    try:
        connection = sqlite3.connect(
            f"file:{state_db}?mode=ro", uri=True, timeout=0.25
        )
    except sqlite3.Error:
        return result
    try:
        cursor = connection.execute(
            """
            SELECT id, model, model_config, started_at
            FROM sessions
            WHERE model_config LIKE '%_delegate_from%' AND started_at >= ?
            ORDER BY started_at DESC LIMIT 32
            """,
            (now - _SESSION_WINDOW_SECONDS,),
        )
        rows = cursor.fetchall()
        parents_needed: set[str] = set()
        children: list[dict[str, Any]] = []
        for session_id, model, model_config, started_at in rows:
            config: dict[str, Any] = {}
            try:
                parsed = json.loads(model_config or "{}")
                if isinstance(parsed, dict):
                    config = parsed
            except (ValueError, TypeError):
                config = {}
            parent_id = _text(config.get("_delegate_from", ""))
            if not parent_id:
                continue
            reasoning = config.get("reasoning_config", {})
            effort = ""
            if isinstance(reasoning, dict) and reasoning.get("enabled"):
                effort = _text(reasoning.get("effort", ""), limit=40)
            parents_needed.add(parent_id)
            children.append(
                {
                    "session_id": _text(session_id),
                    "parent_id": parent_id,
                    "model": _text(model),
                    "effort": effort,
                    "started_at": _finite(started_at) or 0.0,
                }
            )
        result["children"] = children

        for parent_id in parents_needed:
            cursor = connection.execute(
                "SELECT model FROM sessions WHERE id = ?", (parent_id,)
            )
            row = cursor.fetchone()
            if row:
                result["parent_models"][parent_id] = _text(row[0])

        if children:
            placeholders = ",".join("?" for _ in children)
            cursor = connection.execute(
                f"""
                SELECT session_id, SUM(api_call_count), SUM(input_tokens),
                       SUM(output_tokens), SUM(cache_read_tokens),
                       SUM(actual_cost_usd), SUM(estimated_cost_usd),
                       MIN(first_seen), MAX(last_seen)
                FROM session_model_usage
                WHERE session_id IN ({placeholders})
                GROUP BY session_id
                """,
                tuple(child["session_id"] for child in children),
            )
            usage: dict[str, dict[str, Any]] = {}
            for row in cursor.fetchall():
                usage[str(row[0])] = {
                    "api_calls": _finite(row[1]),
                    "input_tokens": _finite(row[2]),
                    "output_tokens": _finite(row[3]),
                    "cache_read_tokens": _finite(row[4]),
                    "actual_cost_usd": _finite(row[5]),
                    "estimated_cost_usd": _finite(row[6]),
                    "first_seen": _finite(row[7]),
                    "last_seen": _finite(row[8]),
                }
            for child in children:
                child["usage"] = usage.get(child["session_id"], {})

        cursor = connection.execute(
            "SELECT delegation_id, state FROM async_delegations WHERE dispatched_at >= ?",
            (now - _SESSION_WINDOW_SECONDS,),
        )
        result["delegation_states"] = {
            str(row[0]): _text(row[1], limit=40) for row in cursor.fetchall()
        }
    except sqlite3.Error:
        # A schema Hermes has since changed, a lock we lost the race for: the
        # partial result still distinguishes "observed nothing" from success.
        pass
    finally:
        try:
            connection.close()
        except sqlite3.Error:
            pass
    return result


def _iso_utc(epoch: float) -> str:
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))
    except (ValueError, OverflowError, OSError):
        return ""


def read_hermes_native_subagents(
    hermes_home: str | Path | None = None,
    *,
    now: float | None = None,
    limit: int = _ROW_LIMIT,
) -> dict[str, Any]:
    """Project live Hermes-native delegation children into HUD activity rows."""
    current = float(now) if now is not None else time.time()
    home = Path(hermes_home).expanduser() if hermes_home else Path.home() / ".hermes"
    payload: dict[str, Any] = {
        "status": "idle",
        "rows": [],
        "active": 0,
        "running": 0,
        "blocked": 0,
        "completed": 0,
    }
    state = _query_state_db(home / "state.db", now=current)
    children = state.get("children", [])
    if not children:
        return payload
    manifests = _read_manifests(home / "cache" / "delegation" / "live", now=current)

    # Children of one manifest, oldest-first, pair with the manifest's tasks
    # by dispatch order; the pairing is best-effort context (goal text and
    # log mtime), never row identity — the child session id is the identity.
    matched_tasks: dict[str, dict[str, Any]] = {}
    matched_delegations: dict[str, str] = {}
    for manifest in manifests:
        window_children = sorted(
            (
                child
                for child in children
                if child["started_at"] >= manifest["started"] - 5
                and (
                    child["session_id"] not in matched_delegations
                )
            ),
            key=lambda child: child["started_at"],
        )[: len(manifest["tasks"])]
        for task, child in zip(manifest["tasks"], window_children):
            matched_tasks[child["session_id"]] = task
            matched_delegations[child["session_id"]] = manifest["delegation_id"]

    rows: list[dict[str, Any]] = []
    running = 0
    blocked = 0
    completed = 0
    for child in sorted(children, key=lambda item: item["started_at"], reverse=True):
        usage = child.get("usage", {})
        task = matched_tasks.get(child["session_id"], {})
        delegation_id = matched_delegations.get(child["session_id"], "")
        delegation_state = state.get("delegation_states", {}).get(delegation_id, "")
        last_activity = max(
            child["started_at"],
            usage.get("last_seen") or 0.0,
            task.get("log_mtime") or 0.0,
        )
        age = current - last_activity
        if age > COMPLETED_LINGER_SECONDS:
            continue
        if delegation_state in {"completed", "failed", "cancelled"}:
            row_state = "failed" if delegation_state == "failed" else "done"
        elif age <= RECENT_ACTIVITY_SECONDS:
            row_state = "running"
        else:
            row_state = "done"
        # A terminal child with NO recorded model usage never completed a
        # single API call, yet Hermes still marks the delegation "completed"
        # and delivers the provider error text as a normal result (observed
        # live: HTTP 400 "model is not supported when using Codex with a
        # ChatGPT account" rendering as a ✓ done row). No usage means no
        # work happened: project the row as failed, never done.
        failure_hint = ""
        if row_state == "done" and not usage:
            row_state = "failed"
            failure_hint = "no model usage observed"

        input_tokens = usage.get("input_tokens") or 0.0
        output_tokens = usage.get("output_tokens") or 0.0
        cache_read = usage.get("cache_read_tokens") or 0.0
        tokens_total = int(input_tokens + output_tokens)
        first_seen = usage.get("first_seen")
        last_seen = usage.get("last_seen")
        tokens_per_second = None
        if output_tokens and first_seen and last_seen and last_seen > first_seen:
            tokens_per_second = output_tokens / (last_seen - first_seen)
        cache_hit = None
        if cache_read and (cache_read + input_tokens) > 0:
            cache_hit = round(100.0 * cache_read / (cache_read + input_tokens), 1)
        cost = usage.get("actual_cost_usd") or usage.get("estimated_cost_usd")
        # Subscription-billed hosts record no per-call cost; the owner asked
        # for an approximation there rather than a blank. Token-derived, and
        # flagged approximate so the widget can render it as `~$…`.
        cost_approximate = False
        if not cost:
            approx = _approximate_cost_usd(child["model"], input_tokens, output_tokens, cache_read)
            if approx is not None:
                cost = approx
                cost_approximate = True

        parent_model = state.get("parent_models", {}).get(child["parent_id"], "")
        session_tail = child["session_id"].rsplit("_", 1)[-1][:8]
        # A finished child's elapsed is frozen at its last activity: a done
        # task should not keep aging, and a byte-stable lingering row is what
        # lets the widget skip repaints so the dock stays drag-copyable.
        elapsed_until = last_activity if row_state != "running" else current
        row: dict[str, Any] = {
            "state": row_state,
            "task_id": session_tail,
            "role": "hermes-native",
            "action": _text(task.get("goal", ""), limit=_ACTION_LIMIT),
            "model": child["model"],
            "effort": child["effort"],
            "tokens": tokens_total if tokens_total else None,
            "elapsed_seconds": max(0.0, elapsed_until - child["started_at"]),
            "observed_at": _iso_utc(last_activity),
            "category": mixture_category_for(
                child["model"], child["effort"], parent_model=parent_model
            ),
            "delegation_id": delegation_id,
        }
        if failure_hint:
            row["failure_hint"] = failure_hint
        api_calls = usage.get("api_calls")
        if api_calls is not None:
            row["turn_count"] = int(api_calls)
        if cost is not None:
            row["cost_usd"] = cost
            if cost_approximate:
                row["cost_approximate"] = True
        if tokens_per_second is not None:
            row["tokens_per_second"] = tokens_per_second
        if cache_hit is not None:
            row["cache_hit_percentage"] = cache_hit
        rows.append(row)
        if row_state == "running":
            running += 1
        elif row_state == "failed":
            blocked += 1
        elif row_state == "done":
            completed += 1

    rows = rows[: max(1, int(limit))]
    payload["rows"] = rows
    payload["running"] = running
    payload["blocked"] = blocked
    payload["completed"] = completed
    payload["active"] = running + blocked
    payload["status"] = "observed" if rows else "idle"
    return payload
