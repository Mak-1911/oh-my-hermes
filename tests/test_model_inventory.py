from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from _local_package import load_local_package

load_local_package()

from _cli_harness import run_cli  # noqa: E402
from omh.coding.model_inventory import (  # noqa: E402
    CLI_PRESENCE_COMMANDS,
    MODEL_DOMAIN_AFFINITIES,
    MODEL_DOMAIN_AFFINITY_CLAIM_BOUNDARY,
    MODEL_INVENTORY_SCHEMA_VERSION,
    local_model_inventory,
)

_SECRET = "sk-SECRET-VALUE-12345"


def _write_home(
    tmp: str,
    *,
    omo_config: object | None = None,
    omo_raw: str | None = None,
    opencode_config: object | None = None,
    auth: object | None = None,
) -> Path:
    home = Path(tmp)
    config_dir = home / ".config" / "opencode"
    config_dir.mkdir(parents=True, exist_ok=True)
    if omo_raw is not None:
        (config_dir / "oh-my-openagent.json").write_text(omo_raw, encoding="utf-8")
    elif omo_config is not None:
        (config_dir / "oh-my-openagent.json").write_text(json.dumps(omo_config), encoding="utf-8")
    if opencode_config is not None:
        (config_dir / "opencode.json").write_text(json.dumps(opencode_config), encoding="utf-8")
    if auth is not None:
        auth_dir = home / ".local" / "share" / "opencode"
        auth_dir.mkdir(parents=True, exist_ok=True)
        (auth_dir / "auth.json").write_text(json.dumps(auth), encoding="utf-8")
    return home


_OMO_FIXTURE = {
    "$schema": "https://example.invalid/schema.json",
    "agents": {
        "planner": {
            "model": "openai/gpt-5.6-sol",
            "variant": "xhigh",
            "fallback_models": [
                {"model": "opencode/kimi-k3", "variant": "high"},
                {"model": "opencode/glm-5"},
            ],
        },
    },
    "categories": {
        "visual-engineering": {
            "model": "opencode/gemini-3.1-pro",
            "variant": "high",
            "fallback_models": [{"model": "anthropic/claude-opus-5", "variant": "max"}],
        },
    },
}


class ModelInventoryTests(unittest.TestCase):
    def test_models_are_aggregated_with_families_and_variants(self) -> None:
        with TemporaryDirectory() as tmp:
            home = _write_home(tmp, omo_config=_OMO_FIXTURE)
            inventory = local_model_inventory(home)
        self.assertEqual(inventory["schema_version"], MODEL_INVENTORY_SCHEMA_VERSION)
        models = {f"{entry['provider']}/{entry['model_id']}": entry for entry in inventory["available_models"]}
        self.assertEqual(models["opencode/kimi-k3"]["family"], "kimi")
        self.assertEqual(models["opencode/kimi-k3"]["variants"], ["high"])
        self.assertEqual(models["opencode/glm-5"]["family"], "glm")
        self.assertEqual(models["opencode/gemini-3.1-pro"]["family"], "gemini")
        self.assertEqual(models["anthropic/claude-opus-5"]["variants"], ["max"])
        self.assertEqual(
            inventory["families_present"], ["claude", "gemini", "glm", "gpt", "kimi"]
        )
        self.assertEqual(inventory["sources"]["omo_agent_config"]["status"], "present")
        self.assertEqual(inventory["sources"]["omo_agent_config"]["model_count"], 5)
        self.assertEqual(inventory["sources"]["omo_agent_config"]["rejected"], 0)

    def test_no_secret_value_ever_reaches_the_payload(self) -> None:
        # Precedent: tests/test_executor_auth_signals.py — plant a secret in
        # every source file and assert the serialized payload never echoes it.
        omo = json.loads(json.dumps(_OMO_FIXTURE))
        omo["agents"]["planner"]["api_key"] = _SECRET
        with TemporaryDirectory() as tmp:
            home = _write_home(
                tmp,
                omo_config=omo,
                opencode_config={"provider": {"openai": {"apiKey": _SECRET}}},
                auth={"anthropic": {"type": "oauth", "access": _SECRET}},
            )
            inventory = local_model_inventory(home)
        serialized = json.dumps(inventory)
        self.assertNotIn(_SECRET, serialized)
        # Provider key NAMES are the only thing read from auth/config tables.
        self.assertEqual(inventory["sources"]["opencode_config_providers"]["providers"], ["openai"])
        self.assertEqual(inventory["sources"]["opencode_auth_providers"]["providers"], ["anthropic"])

    def test_absent_and_malformed_sources_report_status_without_paths(self) -> None:
        with TemporaryDirectory() as tmp:
            inventory = local_model_inventory(Path(tmp))
            self.assertEqual(inventory["sources"]["omo_agent_config"]["status"], "absent")
            self.assertEqual(inventory["sources"]["opencode_auth_providers"]["status"], "absent")
            self.assertEqual(inventory["available_models"], [])
            self.assertNotIn(tmp, json.dumps(inventory))
        with TemporaryDirectory() as tmp:
            home = _write_home(tmp, omo_raw="{not json", opencode_config={"provider": []})
            inventory = local_model_inventory(home)
            self.assertEqual(inventory["sources"]["omo_agent_config"]["status"], "unreadable")
            # A present file whose section has the wrong shape is not a crash.
            self.assertEqual(inventory["sources"]["opencode_config_providers"]["providers"], [])
            self.assertNotIn(tmp, json.dumps(inventory))

    def test_shape_gate_rejects_hostile_identifiers_without_echoing(self) -> None:
        hostile = {
            "agents": {
                "bad": {
                    "model": "--rm -rf /",
                    "fallback_models": [
                        {"model": "openai/gpt-5.6-sol", "variant": "high"},
                        {"model": "x" * 200},
                        {"model": "openai/api_key=leak"},
                    ],
                },
            },
        }
        with TemporaryDirectory() as tmp:
            inventory = local_model_inventory(_write_home(tmp, omo_config=hostile))
        source = inventory["sources"]["omo_agent_config"]
        self.assertEqual(source["rejected"], 3)
        self.assertEqual(source["model_count"], 1)
        serialized = json.dumps(inventory)
        self.assertNotIn("--rm", serialized)
        self.assertNotIn("x" * 200, serialized)
        self.assertNotIn("api_key", serialized)
        models = [f"{entry['provider']}/{entry['model_id']}" for entry in inventory["available_models"]]
        self.assertEqual(models, ["openai/gpt-5.6-sol"])

    def test_inventory_is_deterministic_modulo_observed_at(self) -> None:
        with TemporaryDirectory() as tmp:
            home = _write_home(tmp, omo_config=_OMO_FIXTURE)
            first = local_model_inventory(home)
            second = local_model_inventory(home)
        for payload in (first, second):
            payload.pop("observed_at")
            payload["sources"]["executor_auth_signals"].pop("observed_at", None)
        self.assertEqual(first, second)

    def test_domain_affinity_notes_are_report_only_static_vocabulary(self) -> None:
        self.assertEqual(MODEL_DOMAIN_AFFINITIES["x_platform_data"], ("grok",))
        with TemporaryDirectory() as tmp:
            inventory = local_model_inventory(_write_home(tmp, omo_config=_OMO_FIXTURE))
        notes = {note["domain"]: note for note in inventory["domain_affinity_notes"]}
        self.assertEqual(notes["x_platform_data"]["locally_present"], [])
        self.assertEqual(notes["multimodal_vision"]["locally_present"], ["claude", "gemini", "gpt"])
        # The affinity table is an editorial default, not a capability claim:
        # its own boundary rides the payload (critic-mandated condition).
        self.assertEqual(inventory["domain_affinity_claim_boundary"], MODEL_DOMAIN_AFFINITY_CLAIM_BOUNDARY)
        self.assertIn("no routing effect", MODEL_DOMAIN_AFFINITY_CLAIM_BOUNDARY)

    def test_affinity_vocabulary_stays_out_of_routing_and_dispatch(self) -> None:
        """No downstream payload builder consumes the affinity table: the
        domain vocabulary must not appear in routing, dispatch, or contract
        modules, so the notes stay report-only by construction."""
        src = Path(__file__).resolve().parent.parent / "src" / "coding"
        for module in ("model_routing.py", "fanout_dispatch.py", "fanout.py", "fanout_contracts.py"):
            source = (src / module).read_text(encoding="utf-8")
            self.assertNotIn("MODEL_DOMAIN_AFFINITIES", source, module)
            self.assertNotIn("x_platform_data", source, module)

    def test_routing_never_imports_the_inventory(self) -> None:
        """Reporting-only is a structural property: the route resolver must not
        read the inventory (or any file), so the import direction is pinned."""
        routing_source = (
            Path(__file__).resolve().parent.parent / "src" / "coding" / "model_routing.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("model_inventory", routing_source)

    def test_cli_presence_table_is_fixed_vocabulary(self) -> None:
        self.assertEqual(
            CLI_PRESENCE_COMMANDS, ("codex", "claude", "opencode", "gemini", "grok", "qwen")
        )


class ModelInventoryCliTests(unittest.TestCase):
    def test_cli_plain_text_default_and_json_optin(self) -> None:
        with TemporaryDirectory() as tmp:
            home = _write_home(tmp, omo_config=_OMO_FIXTURE)
            with mock.patch.dict("os.environ", {"HOME": str(home)}):
                status, stdout, _stderr = run_cli(
                    ["coding", "model-inventory"], output_json=False
                )
                self.assertEqual(status, 0)
                self.assertIn("Local model inventory", stdout)
                self.assertIn("opencode/kimi-k3 [kimi]", stdout)
                self.assertIn("x_platform_data work favors grok", stdout)
                status, stdout, _stderr = run_cli(["coding", "model-inventory", "--json"])
                self.assertEqual(status, 0)
                payload = json.loads(stdout)
        self.assertEqual(payload["schema_version"], MODEL_INVENTORY_SCHEMA_VERSION)
        self.assertTrue(payload["available_models"])


if __name__ == "__main__":
    unittest.main()
