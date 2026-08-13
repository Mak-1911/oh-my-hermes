from __future__ import annotations

import json
from pathlib import Path
import sys

from omh.coding.executor_progress import (
    append_progress_event,
    build_progress_binding,
    build_progress_event,
    write_progress_binding,
)
from omh.paths import OmhPaths


def main() -> int:
    omh_home = Path(sys.argv[1])
    hermes_home = Path(sys.argv[2])
    paths = OmhPaths(omh_home=omh_home, hermes_home=hermes_home)
    fixtures = [
        ("run-300-explore", "codex", "repo_exploration", "Inspecting Hermes widget layout.", "gpt-5.6-sol", "xhigh", 18_200),
        ("run-200-librarian", "hermes_local", "progress_observed", "Checking official widget contracts.", "kimi-k3", "", 4_300),
        ("run-100-architect", "claude_code", "executor_blocked", "Waiting for installer integrity review.", "claude-opus-5", "", None),
    ]
    for run_id, profile, event_type, summary, model, effort, tokens in fixtures:
        run_dir = paths.runtime_runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "skill": "ULW model routing review",
                    "phase": "executing",
                    "observation_status": "execution_observed",
                }
            ),
            encoding="utf-8",
        )
        binding = build_progress_binding(
            target_type="run",
            target_id=run_id,
            executor_profile=profile,
            observed_hermes_execution=profile == "hermes_local",
        )
        write_progress_binding(paths, binding)
        event = build_progress_event(
            binding,
            event_type=event_type,
            summary=summary,
            signal={
                "routed_model": model,
                "routed_reasoning_effort": effort,
                "tokens_total": tokens,
            },
        )
        append_progress_event(paths, binding, event)
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    paths.runtime_state_path.write_text(
        json.dumps({"schema_version": "omh_runtime_state/v1", "last_run_id": "run-300-explore"}),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
