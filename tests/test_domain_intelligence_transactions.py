from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from _local_package import load_local_package

load_local_package()
from omh.paths import resolve_paths
from omh.workflows.domain_intelligence import (
    approve_domain_candidate,
    canonical_profile_digest,
    capture_domain_candidate,
    reject_domain_candidate,
)


LIFECYCLE = "omh.workflows.domain_intelligence_lifecycle"


def _snapshot(root: Path) -> dict[str, bytes]:
    store = root / ".omh" / "memory" / "domain-intelligence"
    return {str(path.relative_to(store)): path.read_bytes() for path in sorted(store.rglob("*.json"))}


class DomainIntelligenceTransactionTests(unittest.TestCase):
    def _replacement(self, root: Path):
        paths = resolve_paths(root / ".omh", root / ".hermes")
        first = capture_domain_candidate(
            paths,
            scope_kind="project",
            scope_ref="transaction-repo",
            domain_id="sales",
            mappings=[("pipeline", "pipeline")],
        )["candidate"]
        approve_domain_candidate(paths, str(first["candidate_id"]))
        replacement = capture_domain_candidate(
            paths,
            scope_kind="project",
            scope_ref="transaction-repo",
            domain_id="sales",
            mappings=[("forecast", "forecast")],
        )["candidate"]
        return paths, replacement

    def test_approval_recovers_idempotently_after_every_write_boundary(self) -> None:
        boundaries = (
            "write_approval_operation",
            "write_archive_idempotent",
            "write_review_idempotent",
            "write_profile_resumable",
            "write_candidate_resumable",
            "delete_approval_operation",
        )
        for boundary in boundaries:
            with self.subTest(boundary=boundary), TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths, candidate = self._replacement(root)
                with patch(f"{LIFECYCLE}.{boundary}", side_effect=OSError(f"fault:{boundary}")):
                    with self.assertRaisesRegex(OSError, f"fault:{boundary}"):
                        approve_domain_candidate(paths, str(candidate["candidate_id"]), approved_by="operator")

                recovered = approve_domain_candidate(paths, str(candidate["candidate_id"]), approved_by="operator")
                self.assertEqual(recovered["candidate"]["status"], "approved")
                self.assertEqual(recovered["profile"]["revision"], 2)
                operations = root / ".omh" / "memory" / "domain-intelligence" / "operations"
                self.assertEqual(list(operations.glob("*.json")), [])
                self.assertEqual(len(list((operations.parent / "history").glob("*.json"))), 1)

    def test_legacy_profile_and_review_partial_state_finalizes_pending_candidate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, candidate = self._replacement(root)
            with patch(f"{LIFECYCLE}.write_candidate_resumable", side_effect=OSError("candidate fault")):
                with self.assertRaisesRegex(OSError, "candidate fault"):
                    approve_domain_candidate(paths, str(candidate["candidate_id"]))

            operation = next((root / ".omh" / "memory" / "domain-intelligence" / "operations").glob("*.json"))
            operation.unlink()
            recovered = approve_domain_candidate(paths, str(candidate["candidate_id"]))
            self.assertEqual(recovered["candidate"]["status"], "approved")
            self.assertEqual(recovered["profile"]["candidate_id"], candidate["candidate_id"])

    def test_legacy_reconciliation_rejects_coordinated_profile_review_tamper(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, candidate = self._replacement(root)
            with patch(f"{LIFECYCLE}.write_candidate_resumable", side_effect=OSError("candidate fault")):
                with self.assertRaisesRegex(OSError, "candidate fault"):
                    approve_domain_candidate(paths, str(candidate["candidate_id"]))
            store = root / ".omh" / "memory" / "domain-intelligence"
            next((store / "operations").glob("*.json")).unlink()
            profile_path = next((store / "profiles").glob("*.json"))
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["workflow_hints"] = ["deep-interview"]
            profile["payload_digest"] = canonical_profile_digest(profile)
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            review_path = store / "reviews" / f"direview_{profile['profile_id']}_r{profile['revision']}.json"
            review = json.loads(review_path.read_text(encoding="utf-8"))
            review["payload_digest"] = profile["payload_digest"]
            review_path.write_text(json.dumps(review), encoding="utf-8")
            before = _snapshot(root)

            with self.assertRaisesRegex(ValueError, "candidate_already_approved_conflict"):
                approve_domain_candidate(paths, str(candidate["candidate_id"]))
            self.assertEqual(_snapshot(root), before)

    def test_rejection_refuses_candidate_with_approval_commit_or_operation(self) -> None:
        for boundary in ("write_archive_idempotent", "write_candidate_resumable"):
            with self.subTest(boundary=boundary), TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths, candidate = self._replacement(root)
                with patch(f"{LIFECYCLE}.{boundary}", side_effect=OSError("approval interrupted")):
                    with self.assertRaisesRegex(OSError, "approval interrupted"):
                        approve_domain_candidate(paths, str(candidate["candidate_id"]))
                with self.assertRaisesRegex(ValueError, "approval_in_progress|candidate_already_approved"):
                    reject_domain_candidate(paths, str(candidate["candidate_id"]))

    def test_recovery_conflict_preserves_store_byte_for_byte(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, candidate = self._replacement(root)
            with patch(f"{LIFECYCLE}.write_review_idempotent", side_effect=OSError("review fault")):
                with self.assertRaisesRegex(OSError, "review fault"):
                    approve_domain_candidate(paths, str(candidate["candidate_id"]))

            profile_path = next((root / ".omh" / "memory" / "domain-intelligence" / "profiles").glob("*.json"))
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["payload_digest"] = "0" * 64
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            before = _snapshot(root)
            with self.assertRaisesRegex(ValueError, "approval_profile_state_conflict"):
                approve_domain_candidate(paths, str(candidate["candidate_id"]))
            self.assertEqual(_snapshot(root), before)

    def test_immutable_history_and_review_conflicts_fail_closed(self) -> None:
        for artifact in ("history", "review"):
            with self.subTest(artifact=artifact), TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths, candidate = self._replacement(root)
                with patch(f"{LIFECYCLE}.write_archive_idempotent", side_effect=OSError("archive fault")):
                    with self.assertRaisesRegex(OSError, "archive fault"):
                        approve_domain_candidate(paths, str(candidate["candidate_id"]))
                store = root / ".omh" / "memory" / "domain-intelligence"
                operation = json.loads(next((store / "operations").glob("*.json")).read_text(encoding="utf-8"))
                if artifact == "history":
                    target = store / "history" / f"{operation['profile_id']}_r{operation['base_profile_revision']}.json"
                else:
                    target = store / "reviews" / f"{operation['target_review']['review_id']}.json"
                target.write_text('{"conflict": true}\n', encoding="utf-8")
                before = _snapshot(root)
                with self.assertRaisesRegex(ValueError, f"approval_{artifact}_state_conflict"):
                    approve_domain_candidate(paths, str(candidate["candidate_id"]))
                self.assertEqual(_snapshot(root), before)

    def test_operation_record_requires_exact_schema_and_digest(self) -> None:
        for violation, expected in (
            ("schema", "approval_operation_schema_mismatch"),
            ("digest", "approval_operation_digest_mismatch"),
        ):
            with self.subTest(violation=violation), TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths, candidate = self._replacement(root)
                with patch(f"{LIFECYCLE}.write_archive_idempotent", side_effect=OSError("archive fault")):
                    with self.assertRaisesRegex(OSError, "archive fault"):
                        approve_domain_candidate(paths, str(candidate["candidate_id"]))
                operation_path = next(
                    (root / ".omh" / "memory" / "domain-intelligence" / "operations").glob("*.json")
                )
                operation = json.loads(operation_path.read_text(encoding="utf-8"))
                if violation == "schema":
                    operation["unexpected"] = "metadata"
                else:
                    operation["target_revision"] = int(operation["target_revision"]) + 1
                operation_path.write_text(json.dumps(operation), encoding="utf-8")
                before = _snapshot(root)
                with self.assertRaisesRegex(ValueError, expected):
                    approve_domain_candidate(paths, str(candidate["candidate_id"]))
                self.assertEqual(_snapshot(root), before)

    def test_operation_symlink_is_rejected_without_mutating_domain_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, candidate = self._replacement(root)
            operations = root / ".omh" / "memory" / "domain-intelligence" / "operations"
            operations.mkdir(mode=0o700, exist_ok=True)
            outside = root / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            (operations / f"approve_{candidate['candidate_id']}.json").symlink_to(outside)
            before = _snapshot(root)
            with self.assertRaisesRegex(ValueError, "symlink"):
                approve_domain_candidate(paths, str(candidate["candidate_id"]))
            self.assertEqual(_snapshot(root), before)


if __name__ == "__main__":
    unittest.main()
