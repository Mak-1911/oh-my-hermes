"""Contract tests for the declared task-scale dial.

Role says WHAT a unit does; scale says HOW MUCH of it there is. Before this
existed, routing keyed on role alone, so a one-line fix and a forty-file
migration both resolved `implementation` to the same model.

Scale is DECLARED, never inferred from request text -- the same contract the
research-depth dial carries, and for the same reason: inferring "large" from
phrasing would make model cost depend on wording.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from omh.coding.model_inventory import (
    OMO_CATEGORY_SCALE_SOURCES,
    inventory_model_catalog,
    local_model_inventory,
)
from omh.coding.model_routing import (
    MODEL_ROLES,
    ROLE_MODEL_CHAINS,
    TASK_SCALE_CHAINS,
    TASK_SCALES,
    resolve_model_route,
)

_OMO_CONFIG = {
    "categories": {
        "ultrabrain": {"model": "openai/gpt-5.6-terra"},
        "deep": {"model": "openai/gpt-5.6-terra"},
        "unspecified-high": {"model": "openai/gpt-5.6-sol"},
        "unspecified-low": {"model": "openai/gpt-5.6-luna"},
        "quick": {"model": "openai/gpt-5.6-luna"},
        "writing": {"model": "openai/gpt-5.6-luna"},
        "visual-engineering": {"model": "openai/gpt-5.6-sol"},
        "artistry": {"model": "openai/gpt-5.6-sol"},
    }
}


def _scale_stage(route: dict) -> dict:
    for entry in route["attempted"]:
        if entry["stage"] == "task_scale":
            return entry
    return {}


class TaskScaleVocabularyTests(unittest.TestCase):
    def test_standard_is_not_a_declared_chain_because_it_is_the_role_chain(self) -> None:
        self.assertIn("standard", TASK_SCALES)
        for profile, chains in TASK_SCALE_CHAINS.items():
            with self.subTest(profile=profile):
                self.assertNotIn("standard", chains)

    def test_every_profile_with_role_chains_declares_both_scale_chains(self) -> None:
        for profile in ROLE_MODEL_CHAINS:
            with self.subTest(profile=profile):
                self.assertEqual(set(TASK_SCALE_CHAINS.get(profile, {})), {"small", "large"})

    def test_every_scale_chain_model_exists_in_that_profiles_role_chains(self) -> None:
        for profile, scales in TASK_SCALE_CHAINS.items():
            known = {
                entry["model_id"]
                for chain in ROLE_MODEL_CHAINS[profile].values()
                for entry in chain
            }
            for scale, chain in scales.items():
                for entry in chain:
                    with self.subTest(profile=profile, scale=scale, model=entry["model_id"]):
                        self.assertIn(entry["model_id"], known)


class TaskScaleResolutionTests(unittest.TestCase):
    def test_scale_moves_the_selected_model_on_codex(self) -> None:
        small = resolve_model_route("codex", role="implementation", requested_scale="small")
        standard = resolve_model_route("codex", role="implementation", requested_scale="standard")
        large = resolve_model_route("codex", role="implementation", requested_scale="large")
        self.assertEqual(small["selected_reasoning_effort"], "low")
        self.assertEqual(standard["selected_model"], "gpt-5")
        self.assertEqual(large["selected_model"], "gpt-5-codex")
        self.assertEqual(large["selected_reasoning_effort"], "high")

    def test_scale_moves_the_selected_model_on_claude_code(self) -> None:
        self.assertEqual(
            resolve_model_route("claude-code", role="implementation", requested_scale="small")["selected_model"],
            "haiku",
        )
        self.assertEqual(
            resolve_model_route("claude-code", role="implementation", requested_scale="large")["selected_model"],
            "opus",
        )

    def test_no_declared_scale_leaves_the_role_chain_untouched(self) -> None:
        without = resolve_model_route("codex", role="implementation")
        standard = resolve_model_route("codex", role="implementation", requested_scale="standard")
        self.assertEqual(without["selected_model"], standard["selected_model"])
        self.assertEqual(_scale_stage(without), {})
        self.assertEqual(_scale_stage(standard)["outcome"], "standard")

    def test_an_unknown_scale_is_named_not_rejected(self) -> None:
        route = resolve_model_route("codex", role="implementation", requested_scale="enormous")
        self.assertEqual(route["status"], "routed")
        self.assertEqual(route["selected_model"], "gpt-5")
        self.assertEqual(_scale_stage(route)["outcome"], "unknown_scale")

    def test_research_keeps_its_depth_dial_and_says_so(self) -> None:
        route = resolve_model_route(
            "codex", role="research", requested_scale="large", requested_depth="deep"
        )
        self.assertEqual(route["selected_model"], "gpt-5-codex")
        stage = _scale_stage(route)
        self.assertEqual(stage["outcome"], "skipped")
        self.assertIn("depth dial", stage["reason"])

    def test_a_requested_model_still_outranks_a_declared_scale(self) -> None:
        route = resolve_model_route(
            "codex", role="implementation", requested_scale="large", requested_model="gpt-5.6-sol"
        )
        self.assertEqual(route["selected_model"], "gpt-5.6-sol")
        self.assertEqual(route["provenance"], "request_named_model")

    def test_scale_is_never_inferred_from_request_text(self) -> None:
        # The resolver takes no text at all; this pins that the only way to
        # reach a scale chain is to declare one.
        for role in MODEL_ROLES:
            with self.subTest(role=role):
                self.assertEqual(_scale_stage(resolve_model_route("codex", role=role)), {})


class TaskScaleLocalInventoryTests(unittest.TestCase):
    def _catalog(self, root: Path):
        config = root / ".config" / "opencode" / "oh-my-openagent.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps(_OMO_CONFIG), encoding="utf-8")
        return inventory_model_catalog(local_model_inventory(root))

    def test_scale_chains_derive_from_the_users_own_omo_categories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog = self._catalog(Path(tmp))
            chains = catalog["chains"]
            self.assertEqual(
                [entry["model_id"] for entry in chains["implementation:small"]],
                ["openai/gpt-5.6-luna"],
            )
            self.assertEqual(
                [entry["model_id"] for entry in chains["implementation:large"]][0],
                "openai/gpt-5.6-terra",
            )

    def test_scale_routes_through_the_local_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog = self._catalog(Path(tmp))
            profile = str(catalog["executor_profile"])
            selected = {
                scale: resolve_model_route(
                    profile, role="implementation", requested_scale=scale, local_catalog=catalog
                )["selected_model"]
                for scale in TASK_SCALES
            }
            self.assertEqual(selected["small"], "openai/gpt-5.6-luna")
            self.assertEqual(selected["standard"], "openai/gpt-5.6-sol")
            self.assertEqual(selected["large"], "openai/gpt-5.6-terra")

    def test_no_dead_research_scale_chain_is_derived(self) -> None:
        # The resolver skips scale for research, so a `research:small` chain
        # would be data nothing can look up.
        with tempfile.TemporaryDirectory() as tmp:
            chains = self._catalog(Path(tmp))["chains"]
            for scale in OMO_CATEGORY_SCALE_SOURCES:
                with self.subTest(scale=scale):
                    self.assertNotIn(f"research:{scale}", chains)

    def test_a_local_catalog_without_the_scale_categories_keeps_the_role_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / ".config" / "opencode" / "oh-my-openagent.json"
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(
                json.dumps({"categories": {"unspecified-high": {"model": "openai/only-one"}}}),
                encoding="utf-8",
            )
            catalog = inventory_model_catalog(local_model_inventory(root))
            route = resolve_model_route(
                str(catalog["executor_profile"]),
                role="implementation",
                requested_scale="small",
                local_catalog=catalog,
            )
            self.assertEqual(route["selected_model"], "openai/only-one")
            self.assertEqual(_scale_stage(route)["outcome"], "no_scale_chain")


if __name__ == "__main__":
    unittest.main()
