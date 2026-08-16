from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERMES_PROCESS_SCHEMA_VERSION = "hermes_process_observation/v1"
_SHELL_NAMES = {"sh", "bash", "zsh", "dash"}
_CLAIM_BOUNDARY = (
    "Local process observation is bounded, best-effort, and is not execution, review, CI, or merge evidence."
)


def observe_hermes_processes(
    *,
    now: datetime | str | None = None,
    ps_output: str | None = None,
) -> dict[str, Any]:
    observed_at = _format_datetime(_coerce_datetime(now) or datetime.now(timezone.utc))
    if ps_output is None:
        try:
            result = subprocess.run(
                ["ps", "-axo", "pid=,ppid=,command="],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return _observation(observed=False, reason="ps_unavailable", rows=[], observed_at=observed_at)
        if result.returncode != 0:
            return _observation(observed=False, reason="ps_unavailable", rows=[], observed_at=observed_at)
        ps_output = result.stdout

    kept = _process_rows(ps_output)
    kept_pids = {row["pid"] for row in kept}
    rows = [
        {
            "pid": row["pid"],
            "ppid": row["ppid"],
            "role": "child" if row["ppid"] in kept_pids else "agent",
            "label": _process_label(row["command"]),
        }
        for row in kept
    ]
    return _observation(observed=True, reason="", rows=rows, observed_at=observed_at)


def _process_rows(ps_output: str) -> list[dict[str, Any]]:
    self_pids = {os.getpid(), os.getppid()}
    rows: list[dict[str, Any]] = []
    for raw_line in ps_output.splitlines():
        parts = raw_line.strip().split(None, 2)
        if len(parts) != 3:
            continue
        raw_pid, raw_ppid, command = parts
        try:
            pid = int(raw_pid)
            ppid = int(raw_ppid)
        except ValueError:
            continue
        if pid in self_pids or _is_filtered_command(command):
            continue
        if not _is_hermes_command(command):
            continue
        rows.append({"pid": pid, "ppid": ppid, "command": command})
    return rows


def _is_hermes_command(command: str) -> bool:
    argv = command.split()
    if not argv:
        return False

    executable = Path(argv[0]).name
    if _is_python_executable(executable):
        if len(argv) >= 2 and Path(argv[1]).parts[-2:] == ("hermes-agent", "hermes"):
            return True
        return len(argv) >= 3 and argv[1] == "-m" and argv[2] in {
            "hermes_cli.main",
            "tui_gateway.entry",
        }

    if executable == "node":
        entrypoint = next((argument for argument in argv[1:] if not argument.startswith("-")), "")
        return Path(entrypoint).parts[-3:] == ("ui-tui", "dist", "entry.js")

    return False


def _is_python_executable(executable: str) -> bool:
    suffix = executable.removeprefix("python")
    return executable.startswith("python") and (not suffix or all(part.isdigit() for part in suffix.split(".")))


def _is_filtered_command(command: str) -> bool:
    tokens = command.split()
    if not tokens:
        return True
    if Path(tokens[0]).name in _SHELL_NAMES or " -c " in command:
        return True
    return "grep " in command or "rg " in command


def _process_label(command: str) -> str:
    tokens = command.split()
    names = [Path(token).name for token in tokens[:2]]
    return _short_text(" ".join(names), limit=40)


def _short_text(value: str, *, limit: int) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _coerce_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _observation(
    *,
    observed: bool,
    reason: str,
    rows: list[dict[str, Any]],
    observed_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": HERMES_PROCESS_SCHEMA_VERSION,
        "observed": observed,
        "reason": reason,
        "agent_count": sum(1 for row in rows if row.get("role") == "agent"),
        "process_count": len(rows),
        "rows": rows,
        "source": "local_process_scan",
        "observed_at": observed_at,
        "claim_boundary": _CLAIM_BOUNDARY,
    }


__all__ = ["HERMES_PROCESS_SCHEMA_VERSION", "observe_hermes_processes"]
