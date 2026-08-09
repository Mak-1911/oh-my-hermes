from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..installer import OmhError
from ..runtime.run_health import (
    build_run_health_summary,
    parse_run_health_input,
    render_run_health_summary_text,
    validate_run_health_summary,
)
from .common import _print_json, _wants_json


def cmd_runtime_health_summary(args: argparse.Namespace) -> int:
    try:
        raw = json.loads(Path(args.input).expanduser().read_text(encoding="utf-8"))
        summary = build_run_health_summary(parse_run_health_input(raw))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise OmhError(str(exc)) from exc
    # A projection this surface just built should never fail its own validator.
    # Checking anyway is what keeps the read path and the write path from
    # drifting: the CLI refuses to render a summary it could not read back.
    errors = validate_run_health_summary(summary)
    if errors:
        raise OmhError("; ".join(errors))
    if _wants_json(args):
        _print_json(summary)
        return 0
    print(render_run_health_summary_text(summary))
    return 0


def add_runtime_health_summary_command(runtime_sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    health = runtime_sub.add_parser(
        "health-summary",
        help="Explain one run's health in owner-neutral terms from normalized progress events.",
    )
    health.add_argument("--input", required=True, help="Path to a run_health_input/v1 JSON file.")
    health.add_argument("--json", action="store_true", help="Emit the machine payload instead of plain text.")
    health.set_defaults(func=cmd_runtime_health_summary)
