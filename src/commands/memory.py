from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..installer import OmhError
from ..memory import (
    RejectedDecisionRecallRequest,
    apply_memory_update_batch,
    approve_project_memory_candidate,
    build_handoff_context_pack,
    build_memory_inspection,
    build_project_memory_recall_pack,
    build_project_memory_review,
    build_project_memory_status,
    capture_project_memory_candidate,
    read_memory_snapshot_file,
    reject_project_memory_candidate,
    build_rejected_decision_recall,
)
from .common import _paths, _print_json


def cmd_memory_status(args: argparse.Namespace) -> int:
    try:
        payload = build_project_memory_status(_paths(args))
    except (OSError, ValueError) as exc:
        raise OmhError(str(exc)) from exc
    _print_json(payload)
    return 0


def cmd_memory_capture(args: argparse.Namespace) -> int:
    try:
        summary = " ".join(args.summary).strip()
        content = sys.stdin.read() if args.stdin else str(args.content or "")
        if not summary:
            raise ValueError("memory capture requires a summary")
        payload = capture_project_memory_candidate(
            _paths(args),
            summary,
            content=content,
            record_type=args.type,
            scope_kind=args.scope_kind,
            scope_ref=args.scope_ref,
            source=args.source,
            source_ref=args.source_ref,
            tags=args.tag or [],
            ttl_days=args.ttl_days,
            stale_after_days=args.stale_after_days,
        )
    except (OSError, ValueError) as exc:
        raise OmhError(str(exc)) from exc
    _print_json(payload)
    return 0


def cmd_memory_review(args: argparse.Namespace) -> int:
    try:
        payload = build_project_memory_review(
            _paths(args),
            candidate_id=args.candidate,
            limit=_optional_positive_int(args.limit, "--limit") or 20,
        )
    except (OSError, ValueError) as exc:
        raise OmhError(str(exc)) from exc
    _print_json(payload)
    return 0


def cmd_memory_approve(args: argparse.Namespace) -> int:
    try:
        payload = approve_project_memory_candidate(_paths(args), args.candidate_id, approved_by=args.approved_by)
    except FileNotFoundError as exc:
        raise OmhError(f"memory candidate not found: {args.candidate_id}") from exc
    except (OSError, ValueError) as exc:
        raise OmhError(str(exc)) from exc
    _print_json(payload)
    return 0


def cmd_memory_reject(args: argparse.Namespace) -> int:
    try:
        payload = reject_project_memory_candidate(
            _paths(args),
            args.candidate_id,
            rejected_by=args.rejected_by,
            reason=args.reason,
        )
    except FileNotFoundError as exc:
        raise OmhError(f"memory candidate not found: {args.candidate_id}") from exc
    except (OSError, ValueError) as exc:
        raise OmhError(str(exc)) from exc
    _print_json(payload)
    return 0


def cmd_memory_recall(args: argparse.Namespace) -> int:
    try:
        query = " ".join(args.query).strip()
        payload = build_project_memory_recall_pack(
            _paths(args),
            query,
            executor_target=args.executor,
            session_id=args.session_id,
            scope_kind=args.scope_kind,
            scope_ref=args.scope_ref,
            limit=_optional_positive_int(args.limit, "--limit") or 6,
            include_stale=args.include_stale,
        )
    except (OSError, ValueError) as exc:
        raise OmhError(str(exc)) from exc
    _print_json(payload)
    return 0


def cmd_memory_rejected_recall(args: argparse.Namespace) -> int:
    try:
        request = RejectedDecisionRecallRequest(
            " ".join(args.query).strip(),
            args.scope_kind,
            args.scope_ref,
            tuple(args.tag or []),
            args.include_stale,
            args.limit,
        )
        payload = build_rejected_decision_recall(_paths(args), request)
    except (OSError, ValueError) as exc:
        raise OmhError(str(exc)) from exc
    _print_json(payload)
    return 0


def cmd_memory_inspect(args: argparse.Namespace) -> int:
    try:
        inspection = build_memory_inspection(
            _paths(args),
            wrapper_snapshot=_read_optional_json(args.fixture),
            scope_kind=args.scope_kind,
            scope_ref=args.scope_ref,
            session_limit=_optional_positive_int(args.session_limit, "--session-limit"),
            summary=args.summary,
            review_item_limit=_optional_positive_int(args.review_item_limit, "--review-item-limit"),
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise OmhError(str(exc)) from exc
    _print_json(inspection)
    return 0


def cmd_memory_pack(args: argparse.Namespace) -> int:
    try:
        paths = _paths(args)
        inspection = None
        wrapper_snapshot = _read_optional_json(args.fixture)
        if wrapper_snapshot is not None:
            inspection = build_memory_inspection(
                paths,
                wrapper_snapshot=wrapper_snapshot,
                scope_kind=args.scope_kind,
                scope_ref=args.scope_ref,
                session_limit=_optional_positive_int(args.session_limit, "--session-limit"),
                review_item_limit=_optional_positive_int(args.review_item_limit, "--review-item-limit"),
            )
        pack = build_handoff_context_pack(
            paths,
            inspection=inspection,
            executor_target=args.executor,
            session_id=args.session_id,
            scope_kind=args.scope_kind,
            scope_ref=args.scope_ref,
            session_limit=_optional_positive_int(args.session_limit, "--session-limit"),
            context_limit=_optional_positive_int(args.context_limit, "--context-limit") or 12,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise OmhError(str(exc)) from exc
    _print_json(pack)
    return 0


def cmd_memory_apply(args: argparse.Namespace) -> int:
    try:
        batch = _read_required_json(args.batch)
        result = apply_memory_update_batch(_paths(args), batch, dry_run=args.dry_run)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise OmhError(str(exc)) from exc
    _print_json(result)
    return 0


def _read_optional_json(path: str | None) -> dict[str, object] | None:
    if not path:
        return None
    return read_memory_snapshot_file(path)


def _read_required_json(path: str) -> dict[str, object]:
    raw = sys.stdin.read() if path == "-" else Path(path).expanduser().read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("memory JSON input must be an object")
    return data


def _optional_positive_int(value: int | None, flag: str) -> int | None:
    if value is None:
        return None
    if value < 1:
        raise ValueError(f"{flag} must be at least 1")
    return value


def _add_memory_commands(sub) -> None:
    from .memory_parser import add_memory_commands

    add_memory_commands(sub)
