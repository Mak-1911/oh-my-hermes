from __future__ import annotations

import os
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.quality.cross_harness_adapter_sandbox import ChildContext, sandbox_command
from src.quality.cross_harness_adapters import ExecutionSpec, run_adapter
from tests.test_cross_harness_adapters import ROOT, _RunnerMixin, _output, _spec


class AdapterSandboxSecurityTests(_RunnerMixin, unittest.TestCase):
    def test_ambient_credentials_are_stripped_and_requested_credentials_rejected(self) -> None:
        with patch.dict(os.environ, {"AWS_SECRET_ACCESS_KEY": "ambient-secret"}):
            outcome = self._run("environment-clean")
        self.assertEqual(outcome.status, "observed_success")

        with TemporaryDirectory() as temporary:
            request, spec = _spec(Path(temporary), "passing", environment=(("GITHUB_TOKEN", "secret"),))
            outcome = run_adapter(request, spec, _output(Path(temporary)))
        self.assertEqual(outcome.reason_code, "credential_environment_rejected")

    def test_real_home_credentials_are_unreadable(self) -> None:
        with TemporaryDirectory() as temporary:
            sentinel = Path(temporary) / "credential.txt"
            sentinel.write_text("sentinel-secret", encoding="utf-8")
            outcome = self._run("credential-read-denied", sandbox=True, environment=(("OMH_READ_PROBE", str(sentinel)),))
            self.assertEqual(outcome.status, "observed_success")

    def test_default_network_and_outside_scratch_write_are_denied(self) -> None:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            network = self._run("network-denied", sandbox=True, environment=(("OMH_NETWORK_PORT", str(port)),))
            allowed = self._run("network-allowed", sandbox=True, environment=(("OMH_NETWORK_PORT", str(port)),), allow_network=True)
        outside = self._run("outside-write-denied", sandbox=True)
        self.assertEqual((network.status, allowed.status, outside.status, allowed.network_allowed), ("observed_success", "observed_success", "observed_success", True))

    def test_dirty_worktree_is_not_observed_or_modified(self) -> None:
        dirty = ROOT / "task2-dirty-sentinel.txt"
        dirty.write_text("owned-by-test", encoding="utf-8")
        self.addCleanup(dirty.unlink)
        outcome = self._run("dirty-worktree-denied", sandbox=True, environment=(("OMH_DIRTY_PROBE", str(dirty)),))
        self.assertEqual(outcome.status, "observed_success")
        self.assertEqual(dirty.read_text(encoding="utf-8"), "owned-by-test")

    def test_stdout_and_stderr_are_hash_only_and_bounded(self) -> None:
        outcome = self._run("noisy")
        repetition = outcome.repetitions[0]
        self.assertEqual(outcome.status, "observed_success")
        self.assertEqual(len(repetition.stdout_hash), 64)
        self.assertGreater(repetition.stdout_bytes, 0)
        self.assertLessEqual(repetition.stdout_bytes, 1_048_576)
        self.assertFalse(hasattr(repetition, "stdout"))

        oversized = self._run("oversized-output")
        receipt = oversized.repetitions[0]
        self.assertEqual(oversized.reason_code, "output_limit_exceeded")
        self.assertGreater(receipt.stdout_bytes, 1_048_576)
        self.assertGreater(receipt.stderr_bytes, 1_048_576)
        self.assertNotEqual(receipt.stdout_hash, receipt.stderr_hash)

    def test_scratch_write_fd_closure_and_literal_argv(self) -> None:
        written = self._run("scratch-write", sandbox=True)
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, read_fd)
        self.addCleanup(os.close, write_fd)
        os.set_inheritable(read_fd, True)
        closed = self._run("fd-denied", environment=(("OMH_FD_PROBE", str(read_fd)),))
        injected = self._run("passing;touch outside")
        self.assertEqual((written.status, closed.status, injected.status), ("observed_success",) * 3)
        self.assertEqual(written.repetitions[0].inventory[0].path, "work/product.bin")

    def test_symlink_escape_is_denied_and_symlinked_sensitive_root_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            allowed = root / "allowed"
            allowed.mkdir()
            secret = root / "secret"
            secret.write_text("sentinel-secret", encoding="utf-8")
            linked = allowed / "linked"
            linked.symlink_to(secret)
            outcome = self._run("credential-read-denied", sandbox=True, environment=(("OMH_READ_PROBE", str(linked)),), read_roots=(allowed,))
            self.assertEqual(outcome.status, "observed_success")

            request, spec = _spec(root, "passing")
            sensitive_link = root / "sensitive"
            sensitive_link.symlink_to(Path.home() / ".ssh")
            rejected = run_adapter(request, ExecutionSpec(spec.argv, (sensitive_link,), root, spec.backend), _output(root))
            self.assertEqual(rejected.reason_code, "unsafe_read_root")

    def test_linux_command_is_strict_and_missing_backend_fails_closed(self) -> None:
        child = ChildContext(Path("/tmp/scratch"), Path("/tmp/scratch/home"), Path("/tmp/scratch/work"), Path("/tmp/scratch/tmp"), Path("/tmp/scratch/output"), Path("/tmp/scratch/request.json"), Path("/tmp/scratch/output/result.json"), "f" * 64)
        environment = {"HOME": "/tmp/scratch/home", "PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1"}
        with patch("src.quality.cross_harness_adapter_sandbox.shutil.which", return_value="/usr/bin/bwrap"):
            command = sandbox_command(("/opt/runtime/bin/tool", "run"), "bwrap", (Path("/opt/fixtures"),), child, False, environment)
        expected = ("/usr/bin/bwrap", "--unshare-user", "--unshare-ipc", "--unshare-pid", "--unshare-net", "--unshare-uts", "--disable-userns", "--new-session", "--die-with-parent", "--clearenv", "--tmpfs", "/", "--ro-bind", "/opt/fixtures", "/opt/fixtures", "--ro-bind", "/opt/runtime/bin", "/opt/runtime/bin", "--bind", "/tmp/scratch", "/tmp/scratch", "--chdir", "/tmp/scratch/work", "--setenv", "HOME", "/tmp/scratch/home", "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "PYTHONNOUSERSITE", "1", "--", "/opt/runtime/bin/tool", "run")
        self.assertEqual(command, expected)
        self.assertFalse(any("try" in part or part in {str(Path.home()), "--share-net"} for part in command))

    def test_unsafe_read_roots_fail_before_launch(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            request, spec = _spec(root, "passing")
            for unsafe in (Path("/"), Path.home(), Path.home() / ".ssh"):
                with self.subTest(unsafe=unsafe.name):
                    candidate = ExecutionSpec(spec.argv, (unsafe,), root, spec.backend)
                    outcome = run_adapter(request, candidate, _output(root))
                    self.assertEqual(outcome.reason_code, "unsafe_read_root")


if __name__ == "__main__":
    unittest.main()
