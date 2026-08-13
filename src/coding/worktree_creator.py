"""Worktree observation ledger helpers.

OMH does not create Git worktrees for chat-prepared handoffs. Upstream Hermes
Agent manages worktrees natively (Kanban worktree-per-task since v0.15.0,
Desktop Projects since v0.18.0), so a chat-side creation path is redundant and
can collide with the worktree Hermes is already managing for the same task.
This module retains the observation-side helpers (reading the local worktree
ledger, recording observed worktree evidence) plus one scoped exception:
`ensure_fanout_unit_worktree`, used only by the explicit opt-in
`omh coding fanout dispatch` bridge, which needs one isolated worktree per
fanout unit before spawning a local agent CLI. Worktrees are never
auto-deleted.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import threading
from typing import Any, Callable

from ..local_store import ensure_dir, ensure_file, file_lock, read_jsonl_objects, utc_now
from ..paths import OmhPaths, expand_path

WORKTREE_OBSERVATION_SCHEMA_VERSION = "omh_worktree_observation/v1"
WORKTREE_CLEANUP_EVENT = "worktree_cleanup"

_WORKTREE_ADD_LOCK = threading.Lock()

WORKTREE_CLAIM_BOUNDARY = (
    "An observed Git worktree is workspace-isolation evidence only. "
    "It is not executor dispatch, implementation, verification, review, CI, merge-readiness, or merge evidence."
)


def list_worktree_records(paths: OmhPaths, *, limit: int = 20) -> tuple[list[dict[str, Any]], list[str]]:
    records, errors = read_jsonl_objects(paths.runtime_worktrees_path)
    return list(reversed(records))[:limit], errors


def latest_observed_worktree_record(paths: OmhPaths, worktree_path: str | Path) -> dict[str, Any]:
    records, _errors = read_jsonl_objects(paths.runtime_worktrees_path)
    target = str(expand_path(worktree_path))
    for record in reversed(records):
        if not isinstance(record, dict):
            continue
        if (
            str(record.get("worktree_path", "")) == target
            and record.get("observed")
            and record.get("created")
        ):
            return record
    return {}


def _observation_record(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": WORKTREE_OBSERVATION_SCHEMA_VERSION,
        "status": result["status"],
        "observed": result["observed"],
        "created": result["created"],
        "repo_root": result["repo_root"],
        "branch": result["branch"],
        "worktree_path": result["worktree_path"],
        "from_ref": result["from_ref"],
        "evidence_refs": result["evidence_refs"],
        "reason": result.get("reason", ""),
        "message": result.get("message", ""),
        "recorded_at": result.get("recorded_at", utc_now()),
        "claim_boundary": WORKTREE_CLAIM_BOUNDARY,
        # Empty on the happy path; a named refusal identifier otherwise, so a
        # caller can branch on which invariant stopped the add rather than
        # substring-matching the human-readable reason.
        "refusal": result.get("refusal", ""),
    }


def _append_worktree_record(paths: OmhPaths, record: dict[str, Any]) -> None:
    ensure_dir(paths.runtime_dir, private=True)
    ensure_file(paths.runtime_worktrees_path, private=True)
    # Dispatch appends from concurrent unit threads; lock the shared ledger.
    with file_lock(paths.runtime_worktrees_path, private=True):
        with paths.runtime_worktrees_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _git(
    runner: Callable[..., Any],
    repo_root: Path,
    argv: list[str],
    *,
    timeout: int = 30,
) -> tuple[int, str, str]:
    """Run one read-only git query, returning (exit code, stdout, stderr).

    A git binary that cannot be run at all is reported as exit 127 rather than
    raised: every caller here is deciding whether an invariant HOLDS, and an
    unanswerable question is a refusal, not a crash.
    """
    try:
        completed = runner(argv, cwd=str(repo_root), text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)
    return (
        _exit_code(getattr(completed, "returncode", 1)),
        str(getattr(completed, "stdout", "") or ""),
        str(getattr(completed, "stderr", "") or ""),
    )


def _exit_code(value: Any) -> int:
    """A runner that reports no usable exit code answered nothing.

    Test doubles and wrappers hand back objects whose `returncode` is `None`
    or non-numeric. Treating that as success would let an unanswered invariant
    check pass; it is reported as a nonzero code so the caller refuses instead.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def _branch_checked_out_paths(runner: Callable[..., Any], repo_root: Path, branch: str) -> list[str]:
    """Worktree paths where `branch` is currently checked out.

    `git worktree add -b` already refuses a branch held by another worktree,
    but only after it has begun creating the new one; asking `git worktree
    list --porcelain` first turns that into a refusal with a name, before any
    directory exists to clean up.
    """
    code, stdout, _stderr = _git(runner, repo_root, ["git", "worktree", "list", "--porcelain"])
    if code != 0:
        return []
    target = f"refs/heads/{branch}"
    holders: list[str] = []
    current_path = ""
    for line in stdout.splitlines():
        if line.startswith("worktree "):
            current_path = line[len("worktree ") :].strip()
        elif line.startswith("branch ") and line[len("branch ") :].strip() == target:
            holders.append(current_path)
    return holders


def _registered_worktree_paths(runner: Callable[..., Any], repo_root: Path) -> set[str]:
    code, stdout, _stderr = _git(runner, repo_root, ["git", "worktree", "list", "--porcelain"])
    if code != 0:
        return set()
    return {
        line[len("worktree ") :].strip()
        for line in stdout.splitlines()
        if line.startswith("worktree ")
    }


def _pre_add_refusal(
    runner: Callable[..., Any],
    *,
    repo_root: Path,
    branch: str,
    base_sha: str,
    source_ref: str,
    worktree_path: Path,
) -> tuple[str, str]:
    """The invariants checked BEFORE `git worktree add`, in refusal order.

    Returns `(refusal_name, reason)`, or `("", "")` when the add may proceed.
    """
    if worktree_path.exists() or str(worktree_path) in _registered_worktree_paths(runner, repo_root):
        return (
            "worktree_path_already_exists",
            f"worktree path already exists: {worktree_path}; remove it or dispatch --unit selectively",
        )
    code, _stdout, _stderr = _git(runner, repo_root, ["git", "check-ref-format", f"refs/heads/{branch}"])
    if code != 0:
        return ("branch_name_malformed", f"branch name is not a valid git ref: {branch!r}")
    if source_ref:
        # The freeze is runtime-shaped: `fanout_contract/v1` stores no base SHA,
        # so the only way to know the caller's `base_sha` still describes the
        # branch it was resolved from is to re-resolve that branch here, at
        # add time. A mismatch means the source branch moved between contract
        # freeze and dispatch, and the unit would silently build on a base
        # nobody agreed to.
        code, stdout, stderr = _git(runner, repo_root, ["git", "rev-parse", "--verify", f"{source_ref}^{{commit}}"])
        if code != 0:
            return (
                "source_ref_unresolvable",
                f"could not resolve source ref {source_ref!r} in {repo_root}: {stderr.strip()[-200:]}",
            )
        observed_sha = stdout.strip()
        if observed_sha != base_sha:
            return (
                "base_sha_drifted_from_source_ref",
                (
                    f"base_sha {base_sha} no longer matches source ref {source_ref!r} "
                    f"(now {observed_sha}); re-run fanout prepare against the current base"
                ),
            )
    code, _stdout, _stderr = _git(runner, repo_root, ["git", "rev-parse", "--verify", f"refs/heads/{branch}"])
    if code == 0:
        holders = _branch_checked_out_paths(runner, repo_root, branch)
        if holders:
            return (
                "branch_checked_out_in_worktree",
                f"branch {branch!r} is already checked out in: {', '.join(holders)}",
            )
        return (
            "branch_already_exists",
            f"branch {branch!r} already exists; delete it or dispatch --unit selectively",
        )
    return ("", "")


def _append_cleanup_receipt(
    paths: OmhPaths,
    *,
    unit_id: str,
    run_ref: str,
    refusal: str,
    reason: str,
    worktree_path: Path,
    removed: str,
    left: str,
) -> None:
    """Record what a refused or failed creation removed and left behind.

    OMH never auto-deletes a worktree, so `removed` is always "nothing" today;
    the field exists because a receipt that cannot say "nothing was removed" is
    a receipt nobody can trust when something is.
    """
    from ..runtime.artifacts import append_journal_observation

    summary = (
        f"{refusal}: removed {removed}; left {left}; worktree {worktree_path}; {reason}"
    )
    append_journal_observation(
        paths,
        {
            "target_type": "run" if run_ref else "runtime",
            "target_id": run_ref or unit_id,
            "run_id": run_ref,
            "event": WORKTREE_CLEANUP_EVENT,
            "status": "observed",
            "summary": summary,
            "worker_ref": unit_id,
            "worktree_ref": str(worktree_path),
            "source": "fanout_worktree_creator",
        },
    )


def ensure_fanout_unit_worktree(
    paths: OmhPaths,
    *,
    repo_root: Path,
    unit_id: str,
    branch: str,
    base_sha: str,
    source_ref: str = "",
    run_ref: str = "",
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    """Create the per-unit worktree for the opt-in fanout dispatch bridge.

    A pre-existing branch or worktree path is an error, never silently reused:
    building on divergent state defeats the contract's isolation guarantee. The
    same holds for a branch some other registered worktree already holds, a
    branch name git would reject, and — when `source_ref` is given — a
    `base_sha` that no longer matches that ref in the live repository.

    Every refusal is recorded, never raised: dispatch reports the unit as
    `worktree_failed` and the operator keeps whatever was already on disk.
    Completed units are skipped by dispatch before this helper is called.
    """
    worktree_path = repo_root.parent / f"{repo_root.name}-fanout-{unit_id}"
    result: dict[str, Any] = {
        "status": "failed",
        "observed": False,
        "created": False,
        "repo_root": str(repo_root),
        "branch": branch,
        "worktree_path": str(worktree_path),
        "from_ref": base_sha,
        "evidence_refs": [],
        "recorded_at": utc_now(),
        "refusal": "",
    }

    def refuse(refusal: str, reason: str, *, left: str) -> dict[str, Any]:
        result["refusal"] = refusal
        result["reason"] = reason
        _append_worktree_record(paths, _observation_record(result))
        _append_cleanup_receipt(
            paths,
            unit_id=unit_id,
            run_ref=run_ref,
            refusal=refusal,
            reason=reason,
            worktree_path=worktree_path,
            removed="nothing",
            left=left,
        )
        return result

    refusal, reason = _pre_add_refusal(
        runner,
        repo_root=repo_root,
        branch=branch,
        base_sha=base_sha,
        source_ref=source_ref,
        worktree_path=worktree_path,
    )
    if refusal:
        left = (
            f"pre-existing worktree path {worktree_path}"
            if refusal == "worktree_path_already_exists"
            else "nothing (refused before git worktree add)"
        )
        return refuse(refusal, reason, left=left)
    try:
        # Dispatch creates unit worktrees from a thread pool, and concurrent
        # `git worktree add` calls against one repository contend on shared
        # repo-level lock files (packed-refs/config), which fails
        # intermittently on slow filesystems. Creation is cheap relative to
        # the agent run, so it is serialized process-wide.
        with _WORKTREE_ADD_LOCK:
            completed = runner(
                ["git", "worktree", "add", str(worktree_path), "-b", branch, base_sha],
                cwd=str(repo_root),
                text=True,
                capture_output=True,
                timeout=120,
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return refuse(
            "worktree_add_failed",
            f"git worktree add failed to run: {exc}",
            left=_partial_add_state(worktree_path),
        )
    if _exit_code(getattr(completed, "returncode", 1)) != 0:
        stderr_tail = str(getattr(completed, "stderr", "") or "")[-300:]
        return refuse(
            "worktree_add_failed",
            f"git worktree add exited nonzero: {stderr_tail}",
            left=_partial_add_state(worktree_path),
        )
    result.update({"status": "created", "observed": True, "created": True, "evidence_refs": [f"git-worktree:{branch}"]})
    _append_worktree_record(paths, _observation_record(result))
    return result


def _partial_add_state(worktree_path: Path) -> str:
    """What a failed `git worktree add` left on disk, named for the receipt.

    Nothing is deleted here even when the directory is half-built: a directory
    this process did not finish creating may still hold work a previous run
    left, and no automatic delete is worth that risk (`git worktree prune` and
    an explicit operator `rm -rf` remain the recovery path).
    """
    if worktree_path.exists():
        return f"partially created worktree directory {worktree_path} (not deleted; run `git worktree prune` after removing it)"
    return "nothing on disk"
