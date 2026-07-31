from __future__ import annotations

import importlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from _local_package import load_local_package

load_local_package()

from omh.workflows.domain_intelligence_store_security import (
    MAX_DOMAIN_ARTIFACT_BYTES,
    MAX_DOMAIN_JSON_DEPTH,
    MAX_DOMAIN_JSON_NODES,
)
from omh.workflows.domain_intelligence_store_writer import read_managed_json_at
from domain_project_context_lock_mixin import DomainProjectContextLockMixin


def _repo(root: Path, *, linked_worktree: bool = False) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    marker = root / ".git"
    if linked_worktree:
        marker.write_text("gitdir: /elsewhere/.git/worktrees/test\n", encoding="utf-8")
    else:
        marker.mkdir()
    return root


def _domain_store(root: Path, *, marker: str = "bound") -> Path:
    store = root / ".omh" / "memory" / "domain-intelligence"
    for name in ("profiles", "reviews", "history"):
        (store / name).mkdir(parents=True, mode=0o700)
    (store / ".store.lock").write_text("", encoding="utf-8")
    (store / "profiles" / "marker.json").write_text(
        f'{{"marker":"{marker}"}}', encoding="utf-8"
    )
    return store


def _read_marker(directory_fd: int) -> dict[str, object] | None:
    return read_managed_json_at(
        directory_fd,
        "marker.json",
        max_bytes=MAX_DOMAIN_ARTIFACT_BYTES,
        max_depth=MAX_DOMAIN_JSON_DEPTH,
        max_nodes=MAX_DOMAIN_JSON_NODES,
    )


class DomainProjectContextTests(DomainProjectContextLockMixin, unittest.TestCase):
    def _module(self):
        return importlib.import_module("omh.workflows.domain_project_context")

    def _close(self, binding) -> None:
        if binding is not None:
            binding.close()

    def test_host_binding_is_surface_specific(self) -> None:
        domain_context = self._module()
        with TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            cli_root = _repo(base / "cli-project")
            plugin_root = _repo(base / "plugin-project")
            _domain_store(cli_root)
            _domain_store(plugin_root)
            nested = cli_root / "src" / "nested"
            nested.mkdir(parents=True)

            cli_binding = domain_context.bind_cli_project(nested)
            self.addCleanup(self._close, cli_binding)
            self.assertIsNotNone(cli_binding)
            self.assertEqual(cli_binding.surface, "cli")
            self.assertEqual(cli_binding.project_root, cli_root)

            self.assertIsNone(domain_context.bind_plugin_project({}))
            with patch.dict(
                os.environ,
                {"OMH_HOME": str(cli_root / ".omh"), "PROJECT_ROOT": str(cli_root)},
            ), patch("pathlib.Path.cwd", return_value=cli_root):
                self.assertIsNone(
                    domain_context.bind_plugin_project(
                        {
                            "args": {"project_root": str(cli_root)},
                            "metadata": {"project_ref": cli_root.name},
                            "omh_home": str(cli_root / ".omh"),
                        }
                    )
                )

            plugin_binding = domain_context.bind_plugin_project(
                {"project_root": str(plugin_root)}
            )
            self.addCleanup(self._close, plugin_binding)
            self.assertIsNotNone(plugin_binding)
            self.assertEqual(plugin_binding.surface, "plugin")
            self.assertEqual(plugin_binding.project_root, plugin_root)

            session_binding = domain_context.bind_session_project(plugin_binding)
            self.addCleanup(self._close, session_binding)
            self.assertIsNotNone(session_binding)
            self.assertEqual(session_binding.surface, "session")
            self.assertEqual(session_binding.project_root, plugin_root)
            self.assertNotEqual(
                session_binding.domain_store_fd, plugin_binding.domain_store_fd
            )
            self.assertIsNone(domain_context.bind_session_project(None))
            self.assertIsNone(domain_context.bind_session_project(session_binding))

    def test_cli_binding_canonicalizes_nested_and_symlinked_cwd(self) -> None:
        domain_context = self._module()
        with TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = _repo(base / "canonical-project")
            _domain_store(root)
            nested = root / "src" / "deep"
            nested.mkdir(parents=True)
            cwd_link = base / "cwd-link"
            cwd_link.symlink_to(nested, target_is_directory=True)

            binding = domain_context.bind_cli_project(cwd_link)
            self.addCleanup(self._close, binding)
            self.assertIsNotNone(binding)
            self.assertEqual(binding.project_root, root)
            self.assertEqual(binding.project_paths.omh_home, root / ".omh")
            self.assertFalse(binding.project_paths.omh_home_named)

    def test_linked_worktree_root_is_supported(self) -> None:
        domain_context = self._module()
        with TemporaryDirectory() as tmp:
            root = _repo(Path(tmp).resolve() / "linked", linked_worktree=True)
            _domain_store(root)

            binding = domain_context.bind_cli_project(root)
            self.addCleanup(self._close, binding)
            self.assertIsNotNone(binding)
            self.assertEqual(binding.project_root, root)

    def test_plugin_root_must_be_the_canonical_repository_root(self) -> None:
        domain_context = self._module()
        with TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = _repo(base / "strict-project")
            _domain_store(root)
            nested = root / "nested"
            nested.mkdir()
            root_link = base / "root-link"
            root_link.symlink_to(root, target_is_directory=True)

            self.assertIsNone(
                domain_context.bind_plugin_project({"project_root": str(nested)})
            )
            self.assertIsNone(
                domain_context.bind_plugin_project({"project_root": str(root_link)})
            )
            self.assertIsNone(
                domain_context.bind_plugin_project({"project_root": str(base / "missing")})
            )

    def test_same_named_repositories_keep_distinct_bound_stores(self) -> None:
        domain_context = self._module()
        with TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            first = _repo(base / "one" / "same-name")
            second = _repo(base / "two" / "same-name")
            _domain_store(first, marker="first")
            _domain_store(second, marker="second")

            first_binding = domain_context.bind_cli_project(first)
            second_binding = domain_context.bind_cli_project(second)
            self.addCleanup(self._close, first_binding)
            self.addCleanup(self._close, second_binding)

            with first_binding.open_directory("profiles") as directory_fd:
                first_value = _read_marker(directory_fd)
            with second_binding.open_directory("profiles") as directory_fd:
                second_value = _read_marker(directory_fd)
            self.assertEqual(first_value, {"marker": "first"})
            self.assertEqual(second_value, {"marker": "second"})

    def test_bound_descriptor_survives_path_swap(self) -> None:
        domain_context = self._module()
        with TemporaryDirectory() as tmp:
            root = _repo(Path(tmp).resolve() / "swap-project")
            original_store = _domain_store(root, marker="opened-before-swap")
            original_identity = (original_store.stat().st_dev, original_store.stat().st_ino)
            binding = domain_context.bind_cli_project(root)
            self.addCleanup(self._close, binding)
            self.assertIsNotNone(binding)

            opened_home = root / ".omh-opened"
            (root / ".omh").rename(opened_home)
            _domain_store(root, marker="replacement-path")

            with binding.shared_store_lock():
                with binding.open_directory("profiles") as directory_fd:
                    value = _read_marker(directory_fd)

            self.assertEqual(value, {"marker": "opened-before-swap"})
            opened_store = opened_home / "memory" / "domain-intelligence"
            self.assertEqual(
                (opened_store.stat().st_dev, opened_store.stat().st_ino),
                original_identity,
            )

    def test_session_binding_duplicates_trusted_descriptor_after_path_swap(self) -> None:
        domain_context = self._module()
        with TemporaryDirectory() as tmp:
            root = _repo(Path(tmp).resolve() / "session-swap-project")
            original_store = _domain_store(root, marker="host-bound")
            original_identity = (
                original_store.stat().st_dev,
                original_store.stat().st_ino,
            )
            host_binding = domain_context.bind_cli_project(root)
            self.addCleanup(self._close, host_binding)
            self.assertIsNotNone(host_binding)

            (root / ".omh").rename(root / ".omh-host-bound")
            replacement_store = _domain_store(root, marker="replacement-path")
            replacement_identity = (
                replacement_store.stat().st_dev,
                replacement_store.stat().st_ino,
            )

            with patch.object(
                domain_context,
                "open_domain_directory",
                side_effect=AssertionError("session binding reopened the store path"),
            ):
                session_binding = domain_context.bind_session_project(host_binding)
                next_session_binding = domain_context.bind_session_project(host_binding)
            self.addCleanup(self._close, session_binding)
            self.addCleanup(self._close, next_session_binding)
            self.assertIsNotNone(session_binding)
            self.assertIsNotNone(next_session_binding)
            self.assertEqual(session_binding.project_root, host_binding.project_root)
            self.assertEqual(session_binding.project_paths, host_binding.project_paths)
            self.assertEqual(
                next_session_binding.project_paths,
                host_binding.project_paths,
            )
            self.assertEqual(
                len(
                    {
                        host_binding.domain_store_fd,
                        session_binding.domain_store_fd,
                        next_session_binding.domain_store_fd,
                    }
                ),
                3,
            )
            self.assertFalse(os.get_inheritable(session_binding.domain_store_fd))
            self.assertFalse(os.get_inheritable(next_session_binding.domain_store_fd))
            session_stat = os.fstat(session_binding.domain_store_fd)
            self.assertEqual(
                (session_stat.st_dev, session_stat.st_ino),
                original_identity,
            )
            self.assertNotEqual(original_identity, replacement_identity)
            host_binding.close()
            with session_binding.open_directory("profiles") as directory_fd:
                self.assertEqual(_read_marker(directory_fd), {"marker": "host-bound"})
            session_binding.close()
            with next_session_binding.open_directory("profiles") as directory_fd:
                self.assertEqual(_read_marker(directory_fd), {"marker": "host-bound"})

    def test_session_binding_rejects_closed_or_changed_host_descriptor(self) -> None:
        domain_context = self._module()
        with TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = _repo(base / "trusted-project")
            other_root = _repo(base / "other-project")
            _domain_store(root)
            other_store = _domain_store(other_root)

            closed_binding = domain_context.bind_cli_project(root)
            self.assertIsNotNone(closed_binding)
            closed_binding.close()
            self.assertIsNone(domain_context.bind_session_project(closed_binding))

            changed_binding = domain_context.bind_cli_project(root)
            self.addCleanup(self._close, changed_binding)
            self.assertIsNotNone(changed_binding)
            os.close(changed_binding.domain_store_fd)
            changed_binding.domain_store_fd = os.open(
                other_store,
                os.O_RDONLY | os.O_DIRECTORY,
            )
            self.assertIsNone(domain_context.bind_session_project(changed_binding))

    def test_session_constructor_failure_closes_duplicated_descriptor(self) -> None:
        domain_context = self._module()
        with TemporaryDirectory() as tmp:
            root = _repo(Path(tmp).resolve() / "session-constructor-failure")
            _domain_store(root)
            host_binding = domain_context.bind_cli_project(root)
            self.addCleanup(self._close, host_binding)
            self.assertIsNotNone(host_binding)
            duplicate = os.dup(host_binding.domain_store_fd)

            with (
                patch.object(domain_context.os, "dup", return_value=duplicate),
                patch.object(
                    domain_context.HostProjectBinding,
                    "__init__",
                    side_effect=RuntimeError("construction failed"),
                ),
                self.assertRaisesRegex(RuntimeError, "construction failed"),
            ):
                domain_context.bind_session_project(host_binding)

            with self.assertRaises(OSError):
                os.fstat(duplicate)

    def test_symlinked_store_components_fail_closed(self) -> None:
        domain_context = self._module()
        with TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = _repo(base / "symlink-project")
            outside = base / "outside"
            (outside / "memory" / "domain-intelligence").mkdir(parents=True)
            (root / ".omh").symlink_to(outside, target_is_directory=True)

            self.assertIsNone(domain_context.bind_cli_project(root))

    def test_binding_constructor_failure_closes_owned_descriptor(self) -> None:
        domain_context = self._module()
        with TemporaryDirectory() as tmp:
            root = _repo(Path(tmp).resolve() / "constructor-failure")
            store = _domain_store(root)
            descriptor = os.open(store, os.O_RDONLY | os.O_DIRECTORY)
            with (
                patch.object(
                    domain_context, "open_domain_directory", return_value=descriptor
                ),
                patch.object(
                    domain_context,
                    "HostProjectBinding",
                    side_effect=RuntimeError("construction failed"),
                ),
                self.assertRaisesRegex(RuntimeError, "construction failed"),
            ):
                domain_context.bind_cli_project(root)

            with self.assertRaises(OSError):
                os.fstat(descriptor)


if __name__ == "__main__":
    unittest.main()
