from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from _local_package import load_local_package

load_local_package()

from omh.paths import OmhPaths
from omh.plugin_bundle.omh.buzz_diagnostics import probe_buzz


class BuzzDiagnosticsTests(unittest.TestCase):
    def test_missing_cli_is_truthful_read_only_and_secret_safe(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = OmhPaths(root / ".omh", root / ".hermes")
            paths.hermes_home.mkdir()
            paths.hermes_config_path.write_text(
                "gateway:\n  platforms:\n    buzz:\n      enabled: true\n      relay_url: https://relay.example\n",
                encoding="utf-8",
            )
            before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            with patch.dict(
                os.environ,
                {
                    "BUZZ_PRIVATE_KEY": "nsec-secret-do-not-print",
                    "OPENAI_API_KEY": "model-secret-do-not-print",
                    "BUZZ_CLI_PATH": str(root / "missing-buzz"),
                },
                clear=False,
            ):
                payload = probe_buzz(paths)
            after = sorted(str(path.relative_to(root)) for path in root.rglob("*"))

            self.assertEqual(payload["schema_version"], "omh_buzz_probe/v1")
            self.assertEqual(payload["status"], "missing")
            self.assertEqual(payload["reason_code"], "buzz_cli_missing")
            self.assertTrue(payload["configured"])
            self.assertTrue(payload["credential_present"])
            self.assertTrue(payload["read_only"])
            self.assertEqual(before, after)
            rendered = json.dumps(payload, sort_keys=True)
            self.assertNotIn("nsec-secret-do-not-print", rendered)
            self.assertNotIn("model-secret-do-not-print", rendered)
            self.assertNotIn("https://relay.example", rendered)

    def test_version_probe_uses_exact_argv_and_minimal_environment(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = OmhPaths(root / ".omh", root / ".hermes")
            paths.hermes_home.mkdir()
            executable = root / "buzz"
            executable.write_text("", encoding="utf-8")
            executable.chmod(0o755)

            seen: dict[str, object] = {}

            def runner(
                argv: tuple[str, ...],
                *,
                env: dict[str, str],
                timeout: int,
            ) -> tuple[int, str, str]:
                seen.update(argv=argv, env=env, timeout=timeout)
                return 0, "buzz-cli 0.5.10\n", ""

            with patch.dict(
                os.environ,
                {
                    "BUZZ_CLI_PATH": str(executable),
                    "BUZZ_PRIVATE_KEY": "nsec-secret-do-not-print",
                    "OPENAI_API_KEY": "model-secret-do-not-print",
                    "AWS_SECRET_ACCESS_KEY": "cloud-secret-do-not-print",
                    "PYTHONPATH": "/tmp/inject",
                    "DYLD_INSERT_LIBRARIES": "/tmp/inject.dylib",
                },
                clear=False,
            ):
                payload = probe_buzz(paths, runner=runner)

            self.assertEqual(seen["argv"], (str(executable.resolve()), "--version"))
            self.assertEqual(set(seen["env"]), {"HOME", "LANG", "LC_ALL", "PATH", "TMPDIR"})
            self.assertEqual(seen["timeout"], 5)
            self.assertEqual(payload["status"], "available")
            self.assertEqual(payload["version"], "0.5.10")
            self.assertNotIn("nsec-secret-do-not-print", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
