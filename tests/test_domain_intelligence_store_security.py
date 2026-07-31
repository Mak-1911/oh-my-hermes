from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from _local_package import load_local_package

load_local_package()
from omh.paths import resolve_paths
from omh.system.local_store import file_lock
from omh.workflows import domain_intelligence_store as store


class DomainIntelligenceStoreSecurityTests(unittest.TestCase):
    def test_authoritative_reads_reject_all_target_identity_conflicts(self) -> None:
        cases = (
            (
                "candidate",
                "candidate_id",
                "dicand_authority",
                store.candidates_dir,
                lambda paths, artifact_id: store.read_candidate_or_raise(
                    paths, artifact_id
                ),
                "candidate_identity_conflict",
            ),
            (
                "profile",
                "profile_id",
                "dprof_authority",
                store.profiles_dir,
                lambda paths, artifact_id: store.read_profile(paths, artifact_id),
                "profile_identity_conflict",
            ),
            (
                "review",
                "review_id",
                "direview_authority",
                store.reviews_dir,
                lambda paths, artifact_id: store.read_review(paths, artifact_id),
                "review_identity_conflict",
            ),
        )
        for (
            name,
            identity_field,
            artifact_id,
            directory_fn,
            reader,
            expected_error,
        ) in cases:
            with self.subTest(name=name), TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths = resolve_paths(root / ".omh", root / ".hermes")
                directory = directory_fn(paths)
                artifact = {identity_field: artifact_id}
                (directory / f"{artifact_id}.json").write_text(
                    json.dumps(artifact), encoding="utf-8"
                )
                (directory / "alias.json").write_text(
                    json.dumps({**artifact, "messages": []}),
                    encoding="utf-8",
                )

                if name == "review":
                    value, error = reader(paths, artifact_id)
                    self.assertIsNone(value)
                    self.assertEqual(error, expected_error)
                else:
                    with self.assertRaisesRegex(ValueError, expected_error):
                        reader(paths, artifact_id)

    def test_authoritative_reads_ignore_unrelated_malformed_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = resolve_paths(root / ".omh", root / ".hermes")
            candidate_id = "dicand_unique"
            profile_id = "dprof_unique"
            review_id = "direview_unique"
            cases = (
                (store.candidates_dir(paths), "candidate_id", candidate_id),
                (store.profiles_dir(paths), "profile_id", profile_id),
                (store.reviews_dir(paths), "review_id", review_id),
            )
            for directory, identity_field, artifact_id in cases:
                (directory / f"{artifact_id}.json").write_text(
                    json.dumps({identity_field: artifact_id}),
                    encoding="utf-8",
                )
                (directory / "unrelated-broken.json").write_text("{", encoding="utf-8")

            self.assertEqual(
                store.read_candidate_or_raise(paths, candidate_id)["candidate_id"],
                candidate_id,
            )
            self.assertEqual(
                store.read_profile(paths, profile_id)["profile_id"], profile_id
            )
            review, error = store.read_review(paths, review_id)
            self.assertIsNone(error)
            self.assertEqual(review["review_id"], review_id)

    def test_pairing_readers_close_candidate_and_review_alias_bypass(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = resolve_paths(root / ".omh", root / ".hermes")
            candidate_id = "dicand_pairing"
            review_id = "direview_pairing"
            profile_id = "dprof_pairing"
            for directory, identity_field, artifact_id in (
                (store.candidates_dir(paths), "candidate_id", candidate_id),
                (store.reviews_dir(paths), "review_id", review_id),
            ):
                artifact = {identity_field: artifact_id}
                (directory / f"{artifact_id}.json").write_text(
                    json.dumps(artifact), encoding="utf-8"
                )
                (directory / "alias.json").write_text(
                    json.dumps(artifact), encoding="utf-8"
                )
            store.write_profile(paths, profile_id, {"profile_id": profile_id})
            candidate_diagnostics: list[dict[str, str]] = []
            review_diagnostics: list[dict[str, str]] = []

            self.assertEqual(store.read_candidates(paths, candidate_diagnostics), [])
            self.assertEqual(store.read_reviews(paths, review_diagnostics), [])
            with self.assertRaisesRegex(ValueError, "candidate_identity_conflict"):
                store.read_candidate_or_raise(paths, candidate_id)
            review, error = store.read_review(paths, review_id)
            self.assertIsNone(review)
            self.assertEqual(error, "review_identity_conflict")
            self.assertEqual(
                store.read_profile(paths, profile_id), {"profile_id": profile_id}
            )

    def test_candidates_directory_symlink_escape_is_rejected_without_external_mutation(
        self,
    ) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = resolve_paths(root / ".omh", root / ".hermes")
            outside = root / "outside-candidates"
            outside.mkdir(mode=0o755)
            domain_root = paths.memory_dir / "domain-intelligence"
            domain_root.mkdir(parents=True)
            (domain_root / "candidates").symlink_to(outside, target_is_directory=True)
            before_mode = outside.stat().st_mode & 0o777

            with self.assertRaisesRegex(ValueError, "symlink"):
                store.candidates_dir(paths)

            self.assertEqual(outside.stat().st_mode & 0o777, before_mode)
            self.assertEqual(list(outside.iterdir()), [])

    def test_domain_root_and_artifact_symlinks_are_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = resolve_paths(root / ".omh", root / ".hermes")
            outside = root / "outside-root"
            outside.mkdir()
            paths.memory_dir.mkdir(parents=True)
            (paths.memory_dir / "domain-intelligence").symlink_to(
                outside, target_is_directory=True
            )
            with self.assertRaisesRegex(ValueError, "symlink"):
                store.domain_root(paths)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = resolve_paths(root / ".omh", root / ".hermes")
            candidate_id = "dicand_linked"
            candidate_dir = store.candidates_dir(paths)
            victim = root / "victim.json"
            victim.write_text(
                json.dumps({"candidate_id": candidate_id}), encoding="utf-8"
            )
            (candidate_dir / f"{candidate_id}.json").symlink_to(victim)
            before = victim.read_bytes()

            with self.assertRaisesRegex(ValueError, "symlink"):
                store.read_candidate_or_raise(paths, candidate_id)

            self.assertEqual(victim.read_bytes(), before)

    def test_lock_symlink_does_not_chmod_or_mutate_victim(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = resolve_paths(root / ".omh", root / ".hermes")
            domain_root = paths.memory_dir / "domain-intelligence"
            domain_root.mkdir(parents=True)
            victim = root / "lock-victim"
            victim.write_text("unchanged", encoding="utf-8")
            victim.chmod(0o644)
            (domain_root / ".store.lock").symlink_to(victim)
            before = (victim.read_bytes(), victim.stat().st_mode & 0o777)

            with self.assertRaisesRegex(ValueError, "symlink"):
                with file_lock(store.store_lock_target(paths), private=True):
                    pass

            self.assertEqual(
                (victim.read_bytes(), victim.stat().st_mode & 0o777), before
            )

    def test_safe_domain_lock_api_creates_private_regular_lock(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = resolve_paths(root / ".omh", root / ".hermes")
            with store.domain_store_lock(paths) as state:
                self.assertTrue(state["locked"])
            lock_path = paths.memory_dir / "domain-intelligence" / ".store.lock"
            self.assertTrue(lock_path.is_file())
            self.assertFalse(lock_path.is_symlink())
            self.assertEqual(lock_path.stat().st_mode & 0o777, 0o600)

    def test_bulk_readers_reject_filename_mismatch_and_duplicate_embedded_ids(
        self,
    ) -> None:
        cases = (
            ("candidates", "candidate_id", store.candidates_dir, store.read_candidates),
            ("profiles", "profile_id", store.profiles_dir, store.read_profiles),
            ("reviews", "review_id", store.reviews_dir, store.read_reviews),
        )
        for name, identity_field, directory_fn, reader in cases:
            with self.subTest(name=name), TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths = resolve_paths(root / ".omh", root / ".hermes")
                directory = directory_fn(paths)
                (directory / "expected.json").write_text(
                    json.dumps({identity_field: "other"}), encoding="utf-8"
                )
                diagnostics: list[dict[str, str]] = []
                self.assertEqual(reader(paths, diagnostics), [])
                self.assertEqual(diagnostics[0]["reason"], "artifact_identity_mismatch")

            with self.subTest(name=f"{name}-duplicate"), TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths = resolve_paths(root / ".omh", root / ".hermes")
                directory = directory_fn(paths)
                (directory / "duplicate.json").write_text(
                    json.dumps({identity_field: "duplicate"}), encoding="utf-8"
                )
                (directory / "alias.json").write_text(
                    json.dumps({identity_field: "duplicate"}), encoding="utf-8"
                )
                diagnostics = []
                self.assertEqual(reader(paths, diagnostics), [])
                self.assertEqual(
                    {item["reason"] for item in diagnostics}, {"duplicate_embedded_id"}
                )

    def test_reader_bounds_size_depth_nodes_and_file_count(self) -> None:
        required_constants = (
            "MAX_DOMAIN_ARTIFACT_BYTES",
            "MAX_DOMAIN_ARTIFACT_FILES",
            "MAX_DOMAIN_CANDIDATE_FILES",
            "MAX_DOMAIN_JSON_DEPTH",
            "MAX_DOMAIN_JSON_NODES",
        )
        for name in required_constants:
            self.assertIsInstance(getattr(store, name, None), int)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = resolve_paths(root / ".omh", root / ".hermes")
            directory = store.candidates_dir(paths)
            oversized = {
                "candidate_id": "oversized",
                "padding": "x" * store.MAX_DOMAIN_ARTIFACT_BYTES,
            }
            (directory / "oversized.json").write_text(
                json.dumps(oversized), encoding="utf-8"
            )
            diagnostics: list[dict[str, str]] = []
            self.assertEqual(store.read_candidates(paths, diagnostics), [])
            self.assertEqual(diagnostics[0]["reason"], "artifact_too_large")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = resolve_paths(root / ".omh", root / ".hermes")
            directory = store.candidates_dir(paths)
            deep = (
                '{"candidate_id":"deep","nested":' + "[" * 1200 + "0" + "]" * 1200 + "}"
            )
            (directory / "deep.json").write_text(deep, encoding="utf-8")
            diagnostics = []
            self.assertEqual(store.read_candidates(paths, diagnostics), [])
            self.assertEqual(diagnostics[0]["reason"], "artifact_json_depth_exceeded")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = resolve_paths(root / ".omh", root / ".hermes")
            directory = store.candidates_dir(paths)
            nodes = {
                "candidate_id": "nodes",
                "nodes": [0] * store.MAX_DOMAIN_JSON_NODES,
            }
            (directory / "nodes.json").write_text(json.dumps(nodes), encoding="utf-8")
            diagnostics = []
            self.assertEqual(store.read_candidates(paths, diagnostics), [])
            self.assertEqual(diagnostics[0]["reason"], "artifact_json_nodes_exceeded")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = resolve_paths(root / ".omh", root / ".hermes")
            directory = store.candidates_dir(paths)
            for index in range(store.MAX_DOMAIN_CANDIDATE_FILES + 1):
                artifact_id = f"candidate-{index}"
                (directory / f"{artifact_id}.json").write_text(
                    json.dumps({"candidate_id": artifact_id}), encoding="utf-8"
                )
            diagnostics = []
            self.assertEqual(store.read_candidates(paths, diagnostics), [])
            self.assertEqual(
                diagnostics,
                [{"path_name": "candidates", "reason": "artifact_file_count_exceeded"}],
            )

    def test_candidate_capacity_preserves_readable_maximum_and_rejects_new_write(
        self,
    ) -> None:
        self.assertEqual(store.MAX_DOMAIN_CANDIDATE_FILES, 256)
        self.assertGreaterEqual(store.MAX_DOMAIN_ARTIFACT_FILES, 1024)
        self.assertGreaterEqual(
            store.MAX_DOMAIN_ARTIFACT_FILES, store.MAX_DOMAIN_CANDIDATE_FILES * 4
        )
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = resolve_paths(root / ".omh", root / ".hermes")
            directory = store.candidates_dir(paths)
            for index in range(store.MAX_DOMAIN_CANDIDATE_FILES):
                artifact_id = f"candidate-{index}"
                (directory / f"{artifact_id}.json").write_text(
                    json.dumps({"candidate_id": artifact_id}),
                    encoding="utf-8",
                )
            diagnostics: list[dict[str, str]] = []
            self.assertEqual(
                len(store.read_candidates(paths, diagnostics)),
                store.MAX_DOMAIN_CANDIDATE_FILES,
            )
            self.assertEqual(diagnostics, [])

            with self.assertRaisesRegex(ValueError, "candidate_capacity_exceeded"):
                store.ensure_candidate_capacity(paths)
            with self.assertRaisesRegex(ValueError, "candidate_capacity_exceeded"):
                store.write_candidate(
                    paths, "candidate-overflow", {"candidate_id": "candidate-overflow"}
                )
            self.assertFalse((directory / "candidate-overflow.json").exists())
            store.write_candidate(
                paths, "candidate-0", {"candidate_id": "candidate-0", "updated": True}
            )

    def test_general_artifact_writes_stop_at_reader_capacity(self) -> None:
        cases = (
            (
                "profile",
                store.profiles_dir,
                lambda paths: store.write_profile(
                    paths, "profile-new", {"profile_id": "profile-new"}
                ),
            ),
            (
                "review",
                store.reviews_dir,
                lambda paths: store.write_review(
                    paths, "review-new", {"review_id": "review-new"}
                ),
            ),
            (
                "history",
                store.history_dir,
                lambda paths: store.archive_profile(
                    paths, {"profile_id": "profile-new", "revision": 1}
                ),
            ),
        )
        for name, directory_fn, writer in cases:
            with self.subTest(name=name), TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths = resolve_paths(root / ".omh", root / ".hermes")
                directory = directory_fn(paths)
                for index in range(2):
                    (directory / f"occupied-{index}.json").write_text(
                        "{}", encoding="utf-8"
                    )
                with patch.object(store, "MAX_DOMAIN_ARTIFACT_FILES", 2):
                    with self.assertRaisesRegex(
                        ValueError, "artifact_capacity_exceeded"
                    ):
                        writer(paths)

    def test_history_reader_uses_bounded_identity_checked_storage(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = resolve_paths(root / ".omh", root / ".hermes")
            directory = store.history_dir(paths)
            profile_id = "dprof_history"
            for revision in (1, 2):
                artifact = {"profile_id": profile_id, "revision": revision}
                (directory / f"{profile_id}_r{revision}.json").write_text(
                    json.dumps(artifact), encoding="utf-8"
                )
            (directory / "alias_r3.json").write_text(
                json.dumps({"profile_id": profile_id, "revision": 3}),
                encoding="utf-8",
            )
            victim = root / "history-victim.json"
            victim.write_text(
                json.dumps({"profile_id": "dprof_victim", "revision": 4}),
                encoding="utf-8",
            )
            (directory / "dprof_victim_r4.json").symlink_to(victim)
            before = victim.read_bytes()
            diagnostics: list[dict[str, str]] = []

            records = store.read_history_profiles(paths, diagnostics)

            self.assertEqual(
                [(item[0]["profile_id"], item[0]["revision"]) for item in records],
                [(profile_id, 1), (profile_id, 2)],
            )
            self.assertEqual(
                {item["reason"] for item in diagnostics},
                {
                    "artifact_identity_mismatch",
                    "domain-intelligence artifact path must not be a symlink",
                },
            )
            self.assertEqual(victim.read_bytes(), before)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = resolve_paths(root / ".omh", root / ".hermes")
            directory = store.history_dir(paths)
            profile_id = "dprof_duplicate_history"
            duplicate = {"profile_id": profile_id, "revision": 1}
            (directory / f"{profile_id}_r1.json").write_text(
                json.dumps(duplicate), encoding="utf-8"
            )
            (directory / "alias_r1.json").write_text(
                json.dumps(duplicate), encoding="utf-8"
            )
            revision_two = {"profile_id": profile_id, "revision": 2}
            (directory / f"{profile_id}_r2.json").write_text(
                json.dumps(revision_two), encoding="utf-8"
            )
            diagnostics = []

            records = store.read_history_profiles(paths, diagnostics)

            self.assertEqual(
                [(item[0]["profile_id"], item[0]["revision"]) for item in records],
                [(profile_id, 2)],
            )
            self.assertEqual(
                diagnostics,
                [
                    {"path_name": "alias_r1.json", "reason": "duplicate_embedded_id"},
                    {
                        "path_name": f"{profile_id}_r1.json",
                        "reason": "duplicate_embedded_id",
                    },
                ],
            )


if __name__ == "__main__":
    unittest.main()
