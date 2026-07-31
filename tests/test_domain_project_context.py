from __future__ import annotations

import fcntl
import importlib
import inspect
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from _local_package import load_local_package

load_local_package()


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


class DomainProjectContextTests(unittest.TestCase):
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
                first_value = domain_context.read_json_at(directory_fd, "marker.json")
            with second_binding.open_directory("profiles") as directory_fd:
                second_value = domain_context.read_json_at(directory_fd, "marker.json")
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
                    value = domain_context.read_json_at(directory_fd, "marker.json")

            self.assertEqual(value, {"marker": "opened-before-swap"})
            opened_store = opened_home / "memory" / "domain-intelligence"
            self.assertEqual(
                (opened_store.stat().st_dev, opened_store.stat().st_ino),
                original_identity,
            )

    def test_symlinked_store_components_fail_closed(self) -> None:
        domain_context = self._module()
        with TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = _repo(base / "symlink-project")
            outside = base / "outside"
            (outside / "memory" / "domain-intelligence").mkdir(parents=True)
            (root / ".omh").symlink_to(outside, target_is_directory=True)

            self.assertIsNone(domain_context.bind_cli_project(root))

    def test_shared_lock_is_descriptor_relative_nonblocking_and_fail_closed(self) -> None:
        domain_context = self._module()
        security = importlib.import_module(
            "omh.workflows.domain_intelligence_store_security"
        )
        with TemporaryDirectory() as tmp:
            root = _repo(Path(tmp).resolve() / "lock-project")
            store = _domain_store(root)
            binding = domain_context.bind_cli_project(root)
            self.addCleanup(self._close, binding)
            self.assertIsNotNone(binding)

            signature = inspect.signature(security.shared_domain_store_lock_at)
            self.assertEqual(signature.parameters["timeout_seconds"].default, 0.25)
            self.assertEqual(signature.parameters["poll_interval"].default, 0.01)

            with binding.shared_store_lock() as state:
                self.assertEqual(state, {"locked": True, "mode": "shared"})
                contender = os.open(store / ".store.lock", os.O_RDWR)
                try:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    os.close(contender)

            with patch.object(security, "fcntl", None):
                with self.assertRaisesRegex(ValueError, "shared_lock_unavailable"):
                    with binding.shared_store_lock():
                        pass

            (store / ".store.lock").unlink()
            with self.assertRaises(FileNotFoundError):
                with binding.shared_store_lock():
                    pass

    def test_shared_lock_times_out_without_creating_or_reopening_lock(self) -> None:
        domain_context = self._module()
        with TemporaryDirectory() as tmp:
            root = _repo(Path(tmp).resolve() / "busy-lock-project")
            store = _domain_store(root)
            binding = domain_context.bind_cli_project(root)
            self.addCleanup(self._close, binding)
            contender = os.open(store / ".store.lock", os.O_RDWR)
            fcntl.flock(contender, fcntl.LOCK_EX)
            try:
                with self.assertRaisesRegex(Exception, "within 0.03s"):
                    with binding.shared_store_lock(
                        timeout_seconds=0.03, poll_interval=0.01
                    ):
                        pass
            finally:
                fcntl.flock(contender, fcntl.LOCK_UN)
                os.close(contender)


if __name__ == "__main__":
    unittest.main()
