from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from _cli_harness import run_cli
from omh.workflows.plugin_risk_audit import audit_plugin_risk


class PluginRiskAuditTests(unittest.TestCase):
    def test_audit_reports_static_risk_categories_without_exposing_plugin_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "plugin.json").write_text('{"name": "example"}\n', encoding="utf-8")
            (root / "pyproject.toml").write_text('dependencies = ["requests>=2"]\n', encoding="utf-8")
            source_marker = "PRIVATE_AUDIT_SOURCE_MARKER"
            (root / "plugin.py").write_text(
                "import requests\n"
                "import subprocess\n"
                "def hook() -> None:\n"
                "    subprocess.run(['tool'], check=False)\n"
                "    eval('1 + 1')\n"
                "    requests.get('https://example.invalid')\n"
                "    pre_tool_call = True\n"
                "    api_key = 'sk_abcdefghijk1234567890'\n"
                f"    marker = '{source_marker}'\n",
                encoding="utf-8",
            )

            payload = audit_plugin_risk(root)

        self.assertEqual(payload["schema_version"], "plugin_risk_audit/v1")
        self.assertEqual(payload["source"]["root_path"], str(root.resolve()))
        self.assertEqual(payload["source"]["manifest_status"], "present")
        self.assertEqual(payload["summary"]["scanned_file_count"], 3)
        self.assertEqual(
            payload["summary"]["risk_categories"],
            [
                "declared_dependency",
                "dynamic_code_execution",
                "hermes_hook_capability",
                "network_request",
                "potential_committed_secret",
                "process_execution",
            ],
        )
        self.assertEqual(payload["not_observed"]["plugin_import"]["status"], "not_observed")
        self.assertEqual(payload["not_observed"]["plugin_execution"]["status"], "not_observed")
        self.assertNotIn(source_marker, json.dumps(payload))

    def test_audit_rejects_non_directory_and_symlinked_plugin_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "plugin.py"
            source.write_text("pass\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "directory"):
                audit_plugin_risk(source)

            nested = root / "plugin"
            nested.mkdir()
            (nested / "plugin.py").write_text("pass\n", encoding="utf-8")
            linked = nested / "linked.py"
            linked.symlink_to(source)

            with self.assertRaisesRegex(ValueError, "symlink"):
                audit_plugin_risk(nested)

    def test_audit_rejects_the_filesystem_root_before_scanning(self) -> None:
        filesystem_root = Path(Path.cwd().anchor)

        with self.assertRaisesRegex(ValueError, "filesystem root"):
            audit_plugin_risk(filesystem_root)

    def test_audit_rejects_special_audited_files_without_reading_them(self) -> None:
        if not hasattr(os, "mkfifo"):
            self.skipTest("named pipes are unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            os.mkfifo(root / "untrusted.py")

            with self.assertRaisesRegex(ValueError, "regular files"):
                audit_plugin_risk(root)

    def test_cli_audits_one_explicit_plugin_root_without_registering_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "plugin.json").write_text('{"name": "example"}\n', encoding="utf-8")
            (root / "plugin.py").write_text("def pre_llm_call() -> None:\n    return None\n", encoding="utf-8")

            status, stdout, stderr = run_cli(["ops", "plugin-risk-audit", "--path", str(root)])

        self.assertEqual(status, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["schema_version"], "plugin_risk_audit/v1")
        self.assertEqual(payload["summary"]["scanned_file_count"], 2)
        self.assertEqual(payload["not_observed"]["plugin_registration"]["status"], "not_observed")


if __name__ == "__main__":
    unittest.main()
