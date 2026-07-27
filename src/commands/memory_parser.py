from __future__ import annotations

import argparse

from . import memory


def add_memory_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    command = sub.add_parser("memory", help="Capture, review, recall, inspect, or pack OMH project memory/context artifacts.")
    memory_sub = command.add_subparsers(dest="memory_command", required=True)

    status = memory_sub.add_parser("status", help="Show OMH project-memory policy, store paths, and review counts.")
    status.set_defaults(func=memory.cmd_memory_status)

    capture = memory_sub.add_parser("capture", help="Capture an OMH project-memory candidate for review.")
    capture.add_argument("summary", nargs="*", help="Short reviewed-memory summary to capture.")
    capture.add_argument("--type", choices=("fact", "decision", "lesson", "procedure", "episode"), default="fact", help="Typed memory record category.")
    capture.add_argument("--content", default="", help="Optional raw source text. It is hashed/length-counted, not persisted raw.")
    capture.add_argument("--stdin", action="store_true", help="Read optional raw source text from stdin without persisting it raw.")
    capture.add_argument("--scope-kind", choices=("project", "target", "thread", "run"), default="project")
    capture.add_argument("--scope-ref", default="default")
    capture.add_argument("--source", default="cli")
    capture.add_argument("--source-ref", default="")
    capture.add_argument("--tag", action="append", default=[])
    capture.add_argument("--ttl-days", type=int, default=None)
    capture.add_argument("--stale-after-days", type=int, default=None)
    capture.set_defaults(func=memory.cmd_memory_capture)

    review = memory_sub.add_parser("review", help="Return review cards for pending OMH project-memory candidates.")
    review.add_argument("--candidate", default=None, help="Limit review output to one candidate id.")
    review.add_argument("--limit", type=int, default=20)
    review.set_defaults(func=memory.cmd_memory_review)

    approve = memory_sub.add_parser("approve", help="Approve a reviewed project-memory candidate.")
    approve.add_argument("candidate_id")
    approve.add_argument("--approved-by", default="operator")
    approve.set_defaults(func=memory.cmd_memory_approve)

    reject = memory_sub.add_parser("reject", help="Reject a project-memory candidate.")
    reject.add_argument("candidate_id")
    reject.add_argument("--rejected-by", default="operator")
    reject.add_argument("--reason", default="")
    reject.set_defaults(func=memory.cmd_memory_reject)

    recall = memory_sub.add_parser("recall", help="Recall reviewed OMH project memory for a task as prepared context.")
    recall.add_argument("query", nargs="*", help="Task/query text used for deterministic keyword recall.")
    recall.add_argument("--executor", default="generic", help="Executor target label to record in the recall pack.")
    recall.add_argument("--session-id", default="", help="Optional wrapper session id to bind to the recall pack.")
    recall.add_argument("--scope-kind", choices=("project", "target", "thread", "run"), default=None)
    recall.add_argument("--scope-ref", default=None)
    recall.add_argument("--limit", type=int, default=6)
    recall.add_argument("--include-stale", action="store_true")
    recall.set_defaults(func=memory.cmd_memory_recall)

    rejected_recall = memory_sub.add_parser(
        "rejected-recall",
        help="Recall reviewed rejected-decision metadata as OMH-local context.",
    )
    rejected_recall.add_argument("query", nargs="*", help="Decision/query text used for deterministic keyword recall.")
    rejected_recall.add_argument("--scope-kind", choices=("project", "target", "thread", "run"), required=True)
    rejected_recall.add_argument("--scope-ref", required=True)
    rejected_recall.add_argument("--tag", action="append", default=[])
    rejected_recall.add_argument("--include-stale", action="store_true")
    rejected_recall.add_argument("--limit", type=int, default=6)
    rejected_recall.set_defaults(func=memory.cmd_memory_rejected_recall)

    inspect = memory_sub.add_parser("inspect")
    inspect.add_argument("--fixture", default=None, help="Optional memory_snapshot/v1 JSON fixture supplied by a wrapper for deterministic inspection.")
    inspect.add_argument("--scope-kind", choices=("project", "target", "thread", "run"), default=None, help="Only inspect snapshots from this scope kind.")
    inspect.add_argument("--scope-ref", default=None, help="Only inspect snapshots with this scope reference.")
    inspect.add_argument("--session-limit", type=int, default=None, help="Maximum recent wrapper session snapshots to inspect.")
    inspect.add_argument("--review-item-limit", type=int, default=None, help="Maximum review items to return.")
    inspect.add_argument("--summary", action="store_true", help="Return snapshot summaries instead of full snapshot items.")
    inspect.set_defaults(func=memory.cmd_memory_inspect)

    pack = memory_sub.add_parser("pack")
    pack.add_argument("--fixture", default=None, help="Optional memory_snapshot/v1 JSON fixture supplied by a wrapper before packing handoff context.")
    pack.add_argument("--executor", default="generic", help="Executor target label to record in the context pack.")
    pack.add_argument("--session-id", default="", help="Optional wrapper session id to bind to the context pack.")
    pack.add_argument("--scope-kind", choices=("project", "target", "thread", "run"), default=None, help="Only pack context from this scope kind.")
    pack.add_argument("--scope-ref", default=None, help="Only pack context with this scope reference.")
    pack.add_argument("--session-limit", type=int, default=None, help="Maximum recent wrapper session snapshots to inspect.")
    pack.add_argument("--review-item-limit", type=int, default=None, help="Maximum review items to build when a fixture is supplied.")
    pack.add_argument("--context-limit", type=int, default=12, help="Maximum context items to include in the handoff pack.")
    pack.set_defaults(func=memory.cmd_memory_pack)

    apply = memory_sub.add_parser("apply")
    apply.add_argument("--batch", required=True, help="Path to memory_update_batch/v1 JSON, or '-' to read from stdin.")
    apply.add_argument("--dry-run", action="store_true", help="Validate and preview the batch without writing .omh/memory.")
    apply.set_defaults(func=memory.cmd_memory_apply)
