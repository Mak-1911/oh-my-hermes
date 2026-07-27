from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from _cli_harness import run_cli
from _local_package import load_local_package


load_local_package()
from omh.local_store import atomic_write_json
from omh.memory import (
    RejectedDecisionRecallRequest,
    build_rejected_decision_recall,
    capture_project_memory_candidate,
    reject_project_memory_candidate,
)
from omh.paths import resolve_paths


class RejectedDecisionRecallTests(unittest.TestCase):
    def test_recall_returns_only_matching_nonstale_rejected_candidate_metadata(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = resolve_paths(Path(tmp) / ".omh", Path(tmp) / ".hermes")
            relevant = capture_project_memory_candidate(
                paths,
                "Reject SQLite storage for decision history",
                record_type="decision",
                scope_kind="project",
                scope_ref="alpha",
                tags=["memory", "storage"],
            )["candidate"]
            reject_project_memory_candidate(paths, relevant["candidate_id"], reason="JSON metadata is sufficient")
            stale = capture_project_memory_candidate(
                paths,
                "Reject SQLite database retry design",
                record_type="decision",
                scope_kind="project",
                scope_ref="alpha",
                tags=["memory", "storage"],
                stale_after_days=-1,
            )["candidate"]
            reject_project_memory_candidate(paths, stale["candidate_id"], reason="Stale comparison")
            other_scope = capture_project_memory_candidate(
                paths,
                "Reject SQLite storage in another project",
                record_type="decision",
                scope_kind="project",
                scope_ref="beta",
                tags=["memory", "storage"],
            )["candidate"]
            reject_project_memory_candidate(paths, other_scope["candidate_id"], reason="Wrong scope")

            payload = build_rejected_decision_recall(
                paths,
                RejectedDecisionRecallRequest("sqlite storage", "project", "alpha", ("memory", "storage")),
            )

            self.assertEqual(set(payload), {"schema_version", "query", "scope", "requested_tags", "include_stale", "limit", "matches", "claim_boundary"})
            self.assertEqual(payload["schema_version"], "rejected_decision_recall/v1")
            self.assertEqual(payload["scope"], {"kind": "project", "ref": "alpha"})
            self.assertEqual(payload["requested_tags"], ["memory", "storage"])
            self.assertFalse(payload["include_stale"])
            self.assertEqual(payload["limit"], 6)
            self.assertEqual(len(payload["matches"]), 1)
            match = payload["matches"][0]
            self.assertEqual(
                set(match),
                {"candidate_id", "record_type", "summary", "rejection_reason", "scope", "tags", "reviewed_at", "stale", "match_score"},
            )
            self.assertEqual(match["candidate_id"], relevant["candidate_id"])
            self.assertEqual(match["record_type"], "decision")
            self.assertEqual(match["stale"], False)
            self.assertGreater(match["match_score"], 0)
            boundary = str(payload["claim_boundary"]).lower()
            self.assertIn("not approved memory", boundary)
            self.assertIn("hermes memory", boundary)
            self.assertIn("execution evidence", boundary)

    def test_include_stale_never_includes_expired_candidates(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = resolve_paths(Path(tmp) / ".omh", Path(tmp) / ".hermes")
            stale = capture_project_memory_candidate(
                paths,
                "Reject stale storage migration",
                record_type="decision",
                tags=["storage"],
                stale_after_days=-1,
            )["candidate"]
            reject_project_memory_candidate(paths, stale["candidate_id"], reason="Needs a fresh comparison")
            expired = capture_project_memory_candidate(
                paths,
                "Reject expired storage migration",
                record_type="decision",
                tags=["storage"],
                ttl_days=-1,
            )["candidate"]
            reject_project_memory_candidate(paths, expired["candidate_id"], reason="Expired decision")

            payload = build_rejected_decision_recall(
                paths,
                RejectedDecisionRecallRequest("storage", "project", "default", include_stale=True, limit=20),
            )

            self.assertEqual([match["candidate_id"] for match in payload["matches"]], [stale["candidate_id"]])
            self.assertTrue(payload["matches"][0]["stale"])

    def test_recall_rejects_symlinked_memory_roots_and_candidate_directories(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = resolve_paths(root / ".omh", root / ".hermes")
            paths.omh_home.mkdir()
            outside = root / "outside"
            outside.mkdir()
            paths.memory_dir.symlink_to(outside, target_is_directory=True)
            request = RejectedDecisionRecallRequest("storage", "project", "default")

            with self.assertRaisesRegex(ValueError, "must not be a symlink"):
                build_rejected_decision_recall(paths, request)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = resolve_paths(root / ".omh", root / ".hermes")
            paths.memory_dir.mkdir(parents=True)
            outside = root / "outside"
            outside.mkdir()
            (paths.memory_dir / "candidates").symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "must not be a symlink"):
                build_rejected_decision_recall(
                    paths,
                    RejectedDecisionRecallRequest("storage", "project", "default"),
                )

    def test_recall_redacts_secret_shaped_text_and_skips_secret_shaped_metadata(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = resolve_paths(Path(tmp) / ".omh", Path(tmp) / ".hermes")
            candidates = paths.memory_dir / "candidates"
            candidates.mkdir(parents=True)
            atomic_write_json(
                candidates / "safe.json",
                {
                    "candidate_id": "cand_safe",
                    "status": "rejected",
                    "record_type": "decision",
                    "summary": "AIzaSyDUMMYABCDEFGHIJKLMNOPQRSTUVWX123",
                    "rejection_reason": "whsec_12345678901234567890",
                    "scope": {"kind": "project", "ref": "default"},
                    "tags": ["storage"],
                    "reviewed_at": "2026-07-27T00:00:00Z",
                },
            )
            atomic_write_json(
                candidates / "unsafe.json",
                {
                    "candidate_id": "gho_12345678901234567890",
                    "status": "rejected",
                    "record_type": "decision",
                    "summary": "Storage decision",
                    "scope": {"kind": "project", "ref": "default"},
                    "tags": ["storage"],
                    "reviewed_at": "2026-07-27T00:00:00Z",
                },
            )

            payload = build_rejected_decision_recall(
                paths,
                RejectedDecisionRecallRequest("", "project", "default"),
            )

            self.assertEqual(len(payload["matches"]), 1)
            self.assertEqual(payload["matches"][0]["summary"], "[redacted]")
            self.assertEqual(payload["matches"][0]["rejection_reason"], "[redacted]")

    def test_cli_returns_rejected_decision_recall_without_approved_memory_claims(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            omh_home = root / ".omh"
            hermes_home = root / ".hermes"
            paths = resolve_paths(omh_home, hermes_home)
            candidate = capture_project_memory_candidate(
                paths,
                "Reject shell interception for efficiency work",
                record_type="decision",
                scope_kind="run",
                scope_ref="run-1",
                tags=["efficiency"],
            )["candidate"]
            reject_project_memory_candidate(paths, candidate["candidate_id"], reason="Prepared reports must not intercept tools")

            status, stdout, stderr = run_cli(
                [
                    "--omh-home",
                    str(omh_home),
                    "--hermes-home",
                    str(hermes_home),
                    "memory",
                    "rejected-recall",
                    "shell",
                    "interception",
                    "--scope-kind",
                    "run",
                    "--scope-ref",
                    "run-1",
                    "--tag",
                    "efficiency",
                ]
            )

            self.assertEqual(status, 0, stderr)
            self.assertEqual(stderr, "")
            payload = json.loads(stdout)
            self.assertEqual(payload["matches"][0]["candidate_id"], candidate["candidate_id"])
            self.assertIn("not approved memory", payload["claim_boundary"].lower())


if __name__ == "__main__":
    unittest.main()
