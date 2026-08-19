"""Contracts for prepared per-dispatch delegation routing.

Hermes resolves `delegation.model` / `delegation.reasoning_effort` /
`delegation.provider` from config.yaml at every `delegate_task` dispatch and
invalidates its config cache on the file's mtime+size, so writing the route
between dispatches gives each child its own model. These tests pin the write
itself (surgical, atomic, refuses YAML injection and symlinks) and the tool
projection over the shipped mixture chains.
"""

import json
import tempfile
import unittest
from pathlib import Path

from omh.plugin_bundle.omh.delegation_routing import (
    read_delegation_route,
    write_delegation_route,
)
from omh.plugin_bundle.omh.tools.delegate_route_tool import omh_delegate_route_handler


class DelegationRouteWriterTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.config = self.home / "config.yaml"

    def test_routing_into_a_missing_config_creates_only_the_delegation_section(self):
        result = write_delegation_route(self.home, model="gpt-5.6-sol", reasoning_effort="xhigh")
        self.assertEqual(result["status"], "routed")
        self.assertEqual(
            self.config.read_text(encoding="utf-8"),
            "delegation:\n  model: gpt-5.6-sol\n  reasoning_effort: xhigh\n",
        )

    def test_routing_preserves_every_unmanaged_byte_of_an_existing_config(self):
        self.config.write_text(
            "model: kimi-k3\n"
            "delegation:\n"
            "  max_concurrent_children: 4\n"
            "  model: old-model\n"
            "display:\n"
            "  skin: omh\n",
            encoding="utf-8",
        )
        result = write_delegation_route(self.home, model="glm-5.2-ultrafast")
        self.assertEqual(result["status"], "routed")
        self.assertEqual(result["previous"], {"model": "old-model"})
        self.assertEqual(
            self.config.read_text(encoding="utf-8"),
            "model: kimi-k3\n"
            "delegation:\n"
            "  model: glm-5.2-ultrafast\n"
            "  max_concurrent_children: 4\n"
            "display:\n"
            "  skin: omh\n",
        )

    def test_clear_removes_only_the_routable_keys(self):
        self.config.write_text(
            "delegation:\n"
            "  model: gpt-5.6-sol\n"
            "  reasoning_effort: xhigh\n"
            "  provider: openai-codex\n"
            "  max_concurrent_children: 4\n",
            encoding="utf-8",
        )
        result = write_delegation_route(self.home, clear=True)
        self.assertEqual(result["status"], "cleared")
        self.assertEqual(
            self.config.read_text(encoding="utf-8"),
            "delegation:\n  max_concurrent_children: 4\n",
        )
        self.assertEqual(read_delegation_route(self.home), {})

    def test_a_value_that_is_not_a_plain_token_is_refused(self):
        # Anything beyond an identifier token could smuggle YAML structure
        # into the config; the writer refuses instead of quoting.
        result = write_delegation_route(self.home, model="evil: {a: b}")
        self.assertEqual(result["status"], "error")
        self.assertFalse(self.config.exists())

    def test_a_symlinked_config_is_refused_not_replaced(self):
        real = self.home / "real-config.yaml"
        real.write_text("model: kimi-k3\n", encoding="utf-8")
        self.config.symlink_to(real)
        result = write_delegation_route(self.home, model="gpt-5.6-sol")
        self.assertEqual(result["status"], "error")
        self.assertEqual(real.read_text(encoding="utf-8"), "model: kimi-k3\n")

    def test_read_reports_the_last_occurrence_like_yaml_does(self):
        self.config.write_text(
            "delegation:\n  model: first\n  model: second\n", encoding="utf-8"
        )
        self.assertEqual(read_delegation_route(self.home), {"model": "second"})


class DelegateRouteToolTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        # Hermetic OMH home: without it the handler would read the developer
        # machine's real ~/.omh/routing/model-chains.json overrides.
        self.omh_home = self.home / ".omh"

    def _call(self, **args) -> dict:
        return json.loads(
            omh_delegate_route_handler(
                {"hermes_home": str(self.home), "omh_home": str(self.omh_home), **args}
            )
        )

    def _write_overrides(self, categories: dict) -> None:
        path = self.omh_home / "routing" / "model-chains.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"schema_version": "mixture_chain_overrides/v1", "categories": categories}
            ),
            encoding="utf-8",
        )

    def test_an_overridden_chain_routes_and_falls_back_on_the_users_order(self):
        self._write_overrides({
            "quick": [
                {"model": "kimi-k3-ultrafast", "reasoning_effort": "low"},
                {"model": "glm-5.2-ultrafast", "reasoning_effort": "low"},
            ]
        })
        result = self._call(action="set", category="quick")
        self.assertEqual(
            result["applied"], {"model": "kimi-k3-ultrafast", "reasoning_effort": "low"}
        )
        fallback = self._call(action="fallback")
        self.assertEqual(fallback["status"], "fell_back")
        self.assertEqual(
            fallback["applied"], {"model": "glm-5.2-ultrafast", "reasoning_effort": "low"}
        )

    def test_status_reports_the_override_state_and_path(self):
        result = self._call(action="status")
        self.assertEqual(result["chain_overrides"], "absent")
        self.assertTrue(result["chain_overrides_path"].endswith("routing/model-chains.json"))
        self._write_overrides({"deep": [{"model": "gpt-5.6-terra", "reasoning_effort": "xhigh"}]})
        applied = self._call(action="status")
        self.assertEqual(applied["chain_overrides"], "applied")
        self.assertEqual(
            applied["categories"]["deep"],
            [{"model": "gpt-5.6-terra", "reasoning_effort": "xhigh"}],
        )

    def test_setting_a_category_routes_to_the_chain_head(self):
        result = self._call(action="set", category="ultrabrain")
        self.assertEqual(result["status"], "routed")
        self.assertEqual(result["applied"], {"model": "gpt-5.6-sol", "reasoning_effort": "xhigh"})
        self.assertEqual(result["category"], "ultrabrain")
        self.assertIn("Prepared route only", result["evidence_boundary"])
        self.assertEqual(
            read_delegation_route(self.home),
            {"model": "gpt-5.6-sol", "reasoning_effort": "xhigh"},
        )

    def test_every_category_now_routes_an_explicit_effort(self):
        # Owner decision: the category IS the model+effort pair. Before this,
        # quick and friends declared no effort and every routed lane silently
        # inherited the parent's level ("everything runs medium").
        result = self._call(action="set", category="quick")
        self.assertEqual(
            result["applied"], {"model": "glm-5.2-ultrafast", "reasoning_effort": "low"}
        )
        self.assertEqual(
            read_delegation_route(self.home),
            {"model": "glm-5.2-ultrafast", "reasoning_effort": "low"},
        )

    def test_an_explicit_model_override_wins_over_the_chain_head(self):
        result = self._call(action="set", category="unspecified-high", model="claude-opus-5")
        self.assertEqual(result["applied"], {"model": "claude-opus-5"})
        self.assertEqual(
            result["fallback_candidates"],
            [{"model": "claude-opus-5", "reasoning_effort": "medium"}],
        )

    def test_an_unknown_category_fails_with_the_valid_vocabulary(self):
        result = self._call(action="set", category="galaxybrain")
        self.assertEqual(result["status"], "error")
        self.assertIn("ultrabrain", result["error"])

    def test_fallback_advances_to_the_next_chain_candidate(self):
        self._call(action="set", category="quick")
        result = self._call(action="fallback")
        self.assertEqual(result["status"], "fell_back")
        self.assertEqual(result["category"], "quick")
        self.assertEqual(result["from"], "glm-5.2-ultrafast")
        # quick runs the owner-ordered Ultrafast -> Kimi -> Luna -> Fable
        # sequence, so a rejected ecosystem cannot exhaust the chain.
        self.assertEqual(
            result["fallback_candidates"],
            [
                {"model": "gpt-5.6-luna", "reasoning_effort": "low"},
                {"model": "claude-fable-5", "reasoning_effort": "low"},
            ],
        )
        self.assertEqual(
            read_delegation_route(self.home),
            {"model": "kimi-k3", "reasoning_effort": "low"},
        )

    def test_an_exhausted_chain_clears_the_route_to_parent_inheritance(self):
        # The whole chain was rejected (e.g. a single-provider billing account
        # serves none of it); the only known-working model is the parent's, so
        # fallback past the end restores inheritance instead of routing one
        # more rejection.
        self._call(action="set", category="quick")
        self._call(action="fallback")
        self._call(action="fallback")
        self._call(action="fallback")
        result = self._call(action="fallback")
        self.assertEqual(result["status"], "exhausted_to_inherit")
        self.assertEqual(result["category"], "quick")
        self.assertEqual(result["from"], "claude-fable-5")
        self.assertEqual(read_delegation_route(self.home), {})

    def test_fallback_without_a_route_is_an_error(self):
        result = self._call(action="fallback")
        self.assertEqual(result["status"], "error")
        self.assertIn("no active route", result["error"])

    def test_an_explicit_category_disambiguates_a_shared_model(self):
        # kimi-k3:medium sits in more than one chain; the caller who routed
        # writing passes the category so fallback advances inside writing.
        self._call(action="set", category="writing")
        result = self._call(action="fallback", category="writing")
        self.assertEqual(result["status"], "fell_back")
        self.assertEqual(
            read_delegation_route(self.home),
            {"model": "qwen3-coder", "reasoning_effort": "medium"},
        )

    def test_clear_then_status_shows_an_inherited_route(self):
        self._call(action="set", category="deep")
        cleared = self._call(action="clear")
        self.assertEqual(cleared["status"], "cleared")
        status = self._call(action="status")
        self.assertEqual(status["route"], {})
        self.assertIn("ultrabrain", status["categories"])


if __name__ == "__main__":
    unittest.main()
