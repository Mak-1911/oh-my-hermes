from __future__ import annotations

import hashlib
import json
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from _local_package import load_local_package

load_local_package()
from omh.paths import resolve_paths
from omh.workflows.domain_intelligence import (
    approve_domain_candidate,
    build_domain_review,
    build_domain_status,
    canonical_profile_digest,
    capture_domain_candidate,
    reject_domain_candidate,
    retire_domain_profile,
)


LIFECYCLE = "omh.workflows.domain_intelligence_lifecycle"


def _snapshot(root: Path) -> dict[str, bytes]:
    store = root / ".omh" / "memory" / "domain-intelligence"
    return {
        str(path.relative_to(store)): path.read_bytes()
        for path in sorted(store.rglob("*.json"))
    }


def _operation_digest(operation: dict[str, object]) -> str:
    payload = {
        key: value for key, value in operation.items() if key != "operation_digest"
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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

    def _active_profile(self, root: Path):
        paths = resolve_paths(root / ".omh", root / ".hermes")
        candidate = capture_domain_candidate(
            paths,
            scope_kind="organization",
            scope_ref="retirement-org",
            domain_id="payments",
            mappings=[("capture", "capture")],
        )["candidate"]
        approved = approve_domain_candidate(paths, str(candidate["candidate_id"]))
        return paths, approved["profile"]

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
                with patch(
                    f"{LIFECYCLE}.{boundary}", side_effect=OSError(f"fault:{boundary}")
                ):
                    with self.assertRaisesRegex(OSError, f"fault:{boundary}"):
                        approve_domain_candidate(
                            paths,
                            str(candidate["candidate_id"]),
                            approved_by="operator",
                        )

                recovered = approve_domain_candidate(
                    paths, str(candidate["candidate_id"]), approved_by="operator"
                )
                self.assertEqual(recovered["candidate"]["status"], "approved")
                self.assertEqual(recovered["profile"]["revision"], 2)
                operations = (
                    root / ".omh" / "memory" / "domain-intelligence" / "operations"
                )
                self.assertEqual(list(operations.glob("*.json")), [])
                self.assertEqual(
                    len(list((operations.parent / "history").glob("*.json"))), 1
                )

    def test_legacy_profile_and_review_partial_state_finalizes_pending_candidate(
        self,
    ) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, candidate = self._replacement(root)
            with patch(
                f"{LIFECYCLE}.write_candidate_resumable",
                side_effect=OSError("candidate fault"),
            ):
                with self.assertRaisesRegex(OSError, "candidate fault"):
                    approve_domain_candidate(paths, str(candidate["candidate_id"]))

            operation = next(
                (root / ".omh" / "memory" / "domain-intelligence" / "operations").glob(
                    "*.json"
                )
            )
            operation.unlink()
            recovered = approve_domain_candidate(paths, str(candidate["candidate_id"]))
            self.assertEqual(recovered["candidate"]["status"], "approved")
            self.assertEqual(
                recovered["profile"]["candidate_id"], candidate["candidate_id"]
            )

    def test_legacy_reconciliation_rejects_coordinated_profile_review_tamper(
        self,
    ) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, candidate = self._replacement(root)
            with patch(
                f"{LIFECYCLE}.write_candidate_resumable",
                side_effect=OSError("candidate fault"),
            ):
                with self.assertRaisesRegex(OSError, "candidate fault"):
                    approve_domain_candidate(paths, str(candidate["candidate_id"]))
            store = root / ".omh" / "memory" / "domain-intelligence"
            next((store / "operations").glob("*.json")).unlink()
            profile_path = next((store / "profiles").glob("*.json"))
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["workflow_hints"] = ["deep-interview"]
            profile["payload_digest"] = canonical_profile_digest(profile)
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            review_path = (
                store
                / "reviews"
                / f"direview_{profile['profile_id']}_r{profile['revision']}.json"
            )
            review = json.loads(review_path.read_text(encoding="utf-8"))
            review["payload_digest"] = profile["payload_digest"]
            review_path.write_text(json.dumps(review), encoding="utf-8")
            before = _snapshot(root)

            with self.assertRaisesRegex(
                ValueError,
                "approval_operation_lineage_mismatch|candidate_already_approved_conflict",
            ):
                approve_domain_candidate(paths, str(candidate["candidate_id"]))
            self.assertEqual(_snapshot(root), before)

    def test_rejection_refuses_candidate_with_approval_commit_or_operation(
        self,
    ) -> None:
        for boundary in ("write_archive_idempotent", "write_candidate_resumable"):
            with self.subTest(boundary=boundary), TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths, candidate = self._replacement(root)
                with patch(
                    f"{LIFECYCLE}.{boundary}",
                    side_effect=OSError("approval interrupted"),
                ):
                    with self.assertRaisesRegex(OSError, "approval interrupted"):
                        approve_domain_candidate(paths, str(candidate["candidate_id"]))
                with self.assertRaisesRegex(
                    ValueError, "approval_in_progress|candidate_already_approved"
                ):
                    reject_domain_candidate(paths, str(candidate["candidate_id"]))

    def test_recovery_conflict_preserves_store_byte_for_byte(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, candidate = self._replacement(root)
            with patch(
                f"{LIFECYCLE}.write_review_idempotent",
                side_effect=OSError("review fault"),
            ):
                with self.assertRaisesRegex(OSError, "review fault"):
                    approve_domain_candidate(paths, str(candidate["candidate_id"]))

            profile_path = next(
                (root / ".omh" / "memory" / "domain-intelligence" / "profiles").glob(
                    "*.json"
                )
            )
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
                with patch(
                    f"{LIFECYCLE}.write_archive_idempotent",
                    side_effect=OSError("archive fault"),
                ):
                    with self.assertRaisesRegex(OSError, "archive fault"):
                        approve_domain_candidate(paths, str(candidate["candidate_id"]))
                store = root / ".omh" / "memory" / "domain-intelligence"
                operation = json.loads(
                    next((store / "operations").glob("*.json")).read_text(
                        encoding="utf-8"
                    )
                )
                if artifact == "history":
                    target = (
                        store
                        / "history"
                        / f"{operation['profile_id']}_r{operation['base_profile_revision']}.json"
                    )
                else:
                    target = (
                        store
                        / "reviews"
                        / f"{operation['target_review']['review_id']}.json"
                    )
                target.write_text('{"conflict": true}\n', encoding="utf-8")
                before = _snapshot(root)
                with self.assertRaisesRegex(
                    ValueError, f"approval_{artifact}_state_conflict"
                ):
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
                with patch(
                    f"{LIFECYCLE}.write_archive_idempotent",
                    side_effect=OSError("archive fault"),
                ):
                    with self.assertRaisesRegex(OSError, "archive fault"):
                        approve_domain_candidate(paths, str(candidate["candidate_id"]))
                operation_path = next(
                    (
                        root / ".omh" / "memory" / "domain-intelligence" / "operations"
                    ).glob("*.json")
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

    def test_approval_operation_validates_full_targets_before_resume(self) -> None:
        for violation, expected in (
            ("timestamp", "invalid_profile_approved_at"),
            ("transition", "approval_operation_transition_mismatch"),
        ):
            with self.subTest(violation=violation), TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths, candidate = self._replacement(root)
                with patch(
                    f"{LIFECYCLE}.write_archive_idempotent",
                    side_effect=OSError("archive fault"),
                ):
                    with self.assertRaisesRegex(OSError, "archive fault"):
                        approve_domain_candidate(paths, str(candidate["candidate_id"]))
                operation_path = next(
                    (
                        root / ".omh" / "memory" / "domain-intelligence" / "operations"
                    ).glob("*.json")
                )
                operation = json.loads(operation_path.read_text(encoding="utf-8"))
                if violation == "timestamp":
                    operation["target_profile"]["approved_at"] = "not-a-time"
                else:
                    operation["target_candidate"]["reviewed_at"] = (
                        "2099-01-01T00:00:00Z"
                    )
                    operation["target_candidate"]["updated_at"] = "2099-01-01T00:00:00Z"
                operation["operation_digest"] = _operation_digest(operation)
                operation_path.write_text(json.dumps(operation), encoding="utf-8")
                before = _snapshot(root)
                with self.assertRaisesRegex(ValueError, expected):
                    approve_domain_candidate(paths, str(candidate["candidate_id"]))
                self.assertEqual(_snapshot(root), before)

    def test_rejection_recovers_after_every_write_boundary(self) -> None:
        boundaries = (
            "write_rejection_operation",
            "write_rejection_review_idempotent",
            "write_rejection_candidate_resumable",
            "delete_rejection_operation",
        )
        for boundary in boundaries:
            with self.subTest(boundary=boundary), TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths = resolve_paths(root / ".omh", root / ".hermes")
                candidate = capture_domain_candidate(
                    paths,
                    scope_kind="user",
                    scope_ref="reject-user",
                    domain_id="sales",
                    mappings=[("qbr", "qbr")],
                )["candidate"]
                with patch(
                    f"{LIFECYCLE}.{boundary}", side_effect=OSError(f"fault:{boundary}")
                ):
                    with self.assertRaisesRegex(OSError, f"fault:{boundary}"):
                        reject_domain_candidate(
                            paths,
                            str(candidate["candidate_id"]),
                            reason="insufficient_evidence",
                        )
                operations = (
                    root / ".omh" / "memory" / "domain-intelligence" / "operations"
                )
                records = list(operations.glob("reject_*.json"))
                operation_was_not_written = boundary == "write_rejection_operation"
                self.assertEqual(len(records), 0 if operation_was_not_written else 1)
                targets = (
                    None
                    if operation_was_not_written
                    else json.loads(records[0].read_text(encoding="utf-8"))
                )
                recovered = reject_domain_candidate(
                    paths,
                    str(candidate["candidate_id"]),
                    reason="insufficient_evidence",
                )
                self.assertEqual(recovered["decision"], "rejected")
                if targets is not None:
                    self.assertEqual(
                        recovered["candidate"], targets["target_candidate"]
                    )
                    self.assertEqual(recovered["review"], targets["target_review"])
                self.assertEqual(list(operations.glob("reject_*.json")), [])

    def test_retirement_recovers_after_every_write_boundary(self) -> None:
        boundaries = (
            "write_retirement_operation",
            "write_retirement_archive_idempotent",
            "write_retirement_review_idempotent",
            "write_retirement_profile_resumable",
            "delete_retirement_operation",
        )
        for boundary in boundaries:
            with self.subTest(boundary=boundary), TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths, _ = self._active_profile(root)
                kwargs = {
                    "scope_kind": "organization",
                    "scope_ref": "retirement-org",
                    "domain_id": "payments",
                    "reason": "superseded",
                }
                with patch(
                    f"{LIFECYCLE}.{boundary}", side_effect=OSError(f"fault:{boundary}")
                ):
                    with self.assertRaisesRegex(OSError, f"fault:{boundary}"):
                        retire_domain_profile(paths, **kwargs)
                operations = (
                    root / ".omh" / "memory" / "domain-intelligence" / "operations"
                )
                records = list(operations.glob("retire_*.json"))
                operation_was_not_written = boundary == "write_retirement_operation"
                self.assertEqual(len(records), 0 if operation_was_not_written else 1)
                targets = (
                    None
                    if operation_was_not_written
                    else json.loads(records[0].read_text(encoding="utf-8"))
                )
                recovered = retire_domain_profile(paths, **kwargs)
                self.assertEqual(recovered["decision"], "retired")
                if targets is not None:
                    self.assertEqual(recovered["profile"], targets["target_profile"])
                    self.assertEqual(recovered["review"], targets["target_review"])
                self.assertEqual(list(operations.glob("retire_*.json")), [])

    def test_rejection_and_retirement_conflicts_preserve_store(self) -> None:
        cases = (
            (
                "rejection",
                "write_rejection_review_idempotent",
                "reviews",
                "target_review",
                reject_domain_candidate,
            ),
            (
                "retirement-review",
                "write_retirement_review_idempotent",
                "reviews",
                "target_review",
                retire_domain_profile,
            ),
            (
                "retirement-history",
                "write_retirement_archive_idempotent",
                "history",
                "prior_profile",
                retire_domain_profile,
            ),
        )
        for name, boundary, dirname, target_key, action in cases:
            with self.subTest(name=name), TemporaryDirectory() as tmp:
                root = Path(tmp)
                if name == "rejection":
                    paths = resolve_paths(root / ".omh", root / ".hermes")
                    candidate = capture_domain_candidate(
                        paths,
                        scope_kind="user",
                        scope_ref="conflict-user",
                        domain_id="sales",
                        mappings=[("qbr", "qbr")],
                    )["candidate"]
                    args = (paths, str(candidate["candidate_id"]))
                    kwargs = {}
                else:
                    paths, _ = self._active_profile(root)
                    args = (paths,)
                    kwargs = {
                        "scope_kind": "organization",
                        "scope_ref": "retirement-org",
                        "domain_id": "payments",
                    }
                with patch(
                    f"{LIFECYCLE}.{boundary}", side_effect=OSError("decision fault")
                ):
                    with self.assertRaisesRegex(OSError, "decision fault"):
                        action(*args, **kwargs)
                store = root / ".omh" / "memory" / "domain-intelligence"
                operation = json.loads(
                    next((store / "operations").glob("*.json")).read_text(
                        encoding="utf-8"
                    )
                )
                target = operation[target_key]
                if dirname == "reviews":
                    path = store / dirname / f"{target['review_id']}.json"
                else:
                    path = (
                        store
                        / dirname
                        / f"{target['profile_id']}_r{target['revision']}.json"
                    )
                path.write_text('{"conflict": true}\n', encoding="utf-8")
                before = _snapshot(root)
                with self.assertRaisesRegex(ValueError, "state_conflict"):
                    action(*args, **kwargs)
                self.assertEqual(_snapshot(root), before)

    def test_preexisting_decision_conflicts_do_not_create_operation_records(
        self,
    ) -> None:
        for name in ("rejection", "retirement-review", "retirement-history"):
            with self.subTest(name=name), TemporaryDirectory() as tmp:
                root = Path(tmp)
                store = root / ".omh" / "memory" / "domain-intelligence"
                if name == "rejection":
                    paths = resolve_paths(root / ".omh", root / ".hermes")
                    candidate = capture_domain_candidate(
                        paths,
                        scope_kind="user",
                        scope_ref="existing-conflict",
                        domain_id="sales",
                        mappings=[("qbr", "qbr")],
                    )["candidate"]
                    conflict = (
                        store / "reviews" / f"direview_{candidate['candidate_id']}.json"
                    )
                    action = partial(
                        reject_domain_candidate, paths, str(candidate["candidate_id"])
                    )
                else:
                    paths, profile = self._active_profile(root)
                    if name == "retirement-review":
                        conflict = (
                            store
                            / "reviews"
                            / f"direview_{profile['profile_id']}_r{profile['revision'] + 1}.json"
                        )
                    else:
                        conflict = (
                            store
                            / "history"
                            / f"{profile['profile_id']}_r{profile['revision']}.json"
                        )
                    action = partial(
                        retire_domain_profile,
                        paths,
                        scope_kind="organization",
                        scope_ref="retirement-org",
                        domain_id="payments",
                    )
                conflict.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                conflict.write_text('{"conflict": true}\n', encoding="utf-8")
                before = _snapshot(root)
                with self.assertRaisesRegex(ValueError, "state_conflict"):
                    action()
                self.assertEqual(_snapshot(root), before)
                self.assertEqual(list((store / "operations").glob("*.json")), [])

    def test_candidate_capacity_rejects_257th_without_hiding_first_256(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = resolve_paths(root / ".omh", root / ".hermes")
            for index in range(256):
                capture_domain_candidate(
                    paths,
                    scope_kind="user",
                    scope_ref=f"capacity-{index}",
                    domain_id="sales",
                    mappings=[("qbr", "qbr")],
                )
            with self.assertRaisesRegex(ValueError, "candidate_capacity_exceeded"):
                capture_domain_candidate(
                    paths,
                    scope_kind="user",
                    scope_ref="capacity-overflow",
                    domain_id="sales",
                    mappings=[("qbr", "qbr")],
                )
            self.assertEqual(len(build_domain_review(paths, limit=256)["cards"]), 256)
            self.assertEqual(
                build_domain_status(paths)["counts"]["pending_review"], 256
            )

    def test_operation_symlink_is_rejected_without_mutating_domain_artifacts(
        self,
    ) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, candidate = self._replacement(root)
            operations = root / ".omh" / "memory" / "domain-intelligence" / "operations"
            operations.mkdir(mode=0o700, exist_ok=True)
            outside = root / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            (operations / f"approve_{candidate['candidate_id']}.json").symlink_to(
                outside
            )
            before = _snapshot(root)
            with self.assertRaisesRegex(ValueError, "symlink"):
                approve_domain_candidate(paths, str(candidate["candidate_id"]))
            self.assertEqual(_snapshot(root), before)


if __name__ == "__main__":
    unittest.main()
