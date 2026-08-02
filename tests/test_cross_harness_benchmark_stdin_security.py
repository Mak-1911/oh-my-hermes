from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).parents[1]


def _run_cli_bytes(stdin_bytes: bytes) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "omh.cli",
            "benchmark",
            "score",
            "--stdin",
        ],
        cwd=ROOT,
        input=stdin_bytes,
        capture_output=True,
        check=False,
        env={**os.environ, "OMH_OUTPUT": "json"},
    )


class CrossHarnessBenchmarkStdinSecurityTests(unittest.TestCase):
    def test_oversize_json_integer_is_a_structured_input_error(self) -> None:
        secret = b"7" * 5_000
        completed = _run_cli_bytes(b'{"value":' + secret + b"}")

        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertEqual(
            json.loads(completed.stdout)["reason_codes"], ["invalid_json"]
        )
        self.assertNotIn(secret, completed.stdout)
        self.assertNotIn(secret, completed.stderr)

    def test_invalid_utf8_stdin_is_a_structured_input_error(self) -> None:
        completed = _run_cli_bytes(b'\xff{"secret":"do-not-echo"}')

        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertEqual(
            json.loads(completed.stdout)["reason_codes"], ["invalid_utf8"]
        )
        self.assertNotIn(b"do-not-echo", completed.stdout)
        self.assertNotIn(b"do-not-echo", completed.stderr)

    def test_multibyte_stdin_limit_is_enforced_in_bytes(self) -> None:
        completed = _run_cli_bytes(('"' + "\u00e9" * 500_001 + '"').encode())

        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertEqual(
            json.loads(completed.stdout)["reason_codes"], ["input_too_large"]
        )


if __name__ == "__main__":
    unittest.main()
