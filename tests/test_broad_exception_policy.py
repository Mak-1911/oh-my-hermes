"""Gate for the broad-exception (`BLE001`) policy recorded in `pyproject.toml`.

Ruff's `BLE001` (flake8-blind-except) is deliberately not in `select`. That
omission is a decision, not an oversight, and this module is where the decision
is kept honest.

The policy, as established by issue #637 / PR #641:

    A broad `except` is not itself the defect. Around a delegated call it is
    acceptable when the failure is classified and surfaced -- the handler
    produces a result the caller can tell apart from success and from the
    "optional dependency absent" path, or reports it on an error channel. It
    is a defect when the failure is relabeled as a normal result, so a runtime
    error inside a delegated call becomes indistinguishable from a healthy
    fallback.

`CLASSIFIED_SITES` below records that verdict for every broad `except` site in
`src/`, anchored by file plus enclosing function -- never by line number, which
drifts on unrelated edits. The tests re-derive the live site list from source
and fail when it stops matching, so a new broad `except` cannot land
unclassified and enabling `BLE001` later stays bounded work rather than an
open-ended audit.

Re-derive the same list with Ruff:

    uv run --group lint ruff check --select BLE001 src

`_broad_except_sites()` is intentionally at least as broad as `BLE001`: it
flags every handler catching `Exception` or `BaseException`, including one
carrying a `# noqa: BLE001`, because silencing the rule is exactly the case
that most needs a recorded verdict.

Policy owner: issue #652.
"""

from __future__ import annotations

import ast
import tomllib
import unittest
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "src"
POLICY_TEST_PATH = "tests/test_broad_exception_policy.py"
REDERIVE_COMMAND = "uv run --group lint ruff check --select BLE001 src"
POLICY_OWNER_ISSUE = "#652"

BLIND_EXCEPTION_NAMES = frozenset({"Exception", "BaseException"})

# The failure is classified and surfaced: the caller can tell it apart from
# both success and the "optional dependency absent" path.
INTENTIONAL = "intentional_classified_failure"
# The failure is relabeled as a normal result. Same shape as the defect #637
# fixed; needs that treatment before `BLE001` can be enforced.
NEEDS_637_TREATMENT = "needs_637_treatment"

VERDICTS = frozenset({INTENTIONAL, NEEDS_637_TREATMENT})


class ClassifiedSite(NamedTuple):
    path: str
    function: str
    verdict: str
    rationale: str


CLASSIFIED_SITES: tuple[ClassifiedSite, ...] = (
    ClassifiedSite(
        "src/install/plugin_pack.py",
        "_register_smoke",
        INTENTIONAL,
        "Returns import_smoke=False, register_smoke=False and an `error` string carrying the "
        "exception text, so a failed smoke run is never readable as a passing one.",
    ),
    ClassifiedSite(
        "src/mcp/bridge.py",
        "run_stdio_mcp_server",
        INTENTIONAL,
        "Defensive stdio transport boundary: prints the exception to stderr and answers the "
        "JSON-RPC peer with -32603 Internal error instead of a result.",
    ),
    ClassifiedSite(
        "src/plugin_bundle/omh/awareness.py",
        "_localized_routing_text",
        NEEDS_637_TREATMENT,
        "Returns the raw message, the exact value of the `_prepare_routing_text is None` branch "
        "above it, so a failure inside the delegated call is indistinguishable from the helper "
        "being absent.",
    ),
    ClassifiedSite(
        "src/plugin_bundle/omh/awareness.py",
        "_loop_route_hint_next_action",
        NEEDS_637_TREATMENT,
        "Returns `default_action`, the exact value of the `_assess_loopability is None` branch, "
        "so a failed loopability assessment reads as no assessment being available.",
    ),
    ClassifiedSite(
        "src/plugin_bundle/omh/context_brief.py",
        "_is_catalog_question",
        NEEDS_637_TREATMENT,
        "Two handlers in one function. The import guard is accurate -- an import that raises "
        "means the package path really is unusable, so the standalone answer is the right label. "
        "The second wraps the delegated `is_skill_catalog_question()` call and returns the same "
        "standalone answer, which is the mislabeling #637 fixed elsewhere.",
    ),
    ClassifiedSite(
        "src/plugin_bundle/omh/hooks/llm_hooks.py",
        "pre_llm_call",
        NEEDS_637_TREATMENT,
        "Sets status={} and hud={} on failure; the next branch reads empty status as "
        "`runtime_state_present` being false and injects no context, so a failed status read "
        "looks like a host with nothing to report.",
    ),
    ClassifiedSite(
        "src/plugin_bundle/omh/host_observation.py",
        "_record_observation",
        INTENTIONAL,
        "Already carries the #637 split: ImportError/ModuleNotFoundError takes the standalone "
        "path, any other exception returns `_observation_error(...)` with the error text.",
    ),
    ClassifiedSite(
        "src/plugin_bundle/omh/tools/chat_tool.py",
        "omh_interact_handler",
        INTENTIONAL,
        "Already carries the #637 split: ImportError/ModuleNotFoundError takes "
        "`_fallback_interaction`, any other exception takes `_backend_error_interaction` with the "
        "error type.",
    ),
    ClassifiedSite(
        "src/plugin_bundle/omh/tools/context_tool.py",
        "_context_brief",
        INTENTIONAL,
        "Fixed by #637: returns `_package_context_error(...)` under the distinct "
        "`package_context_error` source instead of `standalone_plugin_bundle_fallback`.",
    ),
    ClassifiedSite(
        "src/plugin_bundle/omh/tools/recommend_tool.py",
        "_recommendations",
        INTENTIONAL,
        "Fixed by #637: returns the distinct `package_recommend_error` source plus a sanitized "
        "error type instead of `standalone_plugin_bundle_fallback`.",
    ),
)

# Ruff reports one hit per handler; the inventory is keyed per enclosing
# function, and `_is_catalog_question` holds two handlers, so the two totals
# differ by exactly one.
EXPECTED_HANDLER_COUNT = 11
EXPECTED_ANCHOR_COUNT = 10


class DerivedSite(NamedTuple):
    path: str
    function: str


def _catches_blind_exception(handler: ast.ExceptHandler) -> bool:
    caught = handler.type
    if caught is None:
        return False
    parts = caught.elts if isinstance(caught, ast.Tuple) else [caught]
    return any(isinstance(part, ast.Name) and part.id in BLIND_EXCEPTION_NAMES for part in parts)


def _enclosing_function(tree: ast.Module, lineno: int) -> str:
    innermost = ""
    innermost_start = -1
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end = node.end_lineno or node.lineno
        if node.lineno <= lineno <= end and node.lineno > innermost_start:
            innermost = node.name
            innermost_start = node.lineno
    return innermost or "<module>"


def _broad_except_sites() -> list[DerivedSite]:
    sites: list[DerivedSite] = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and _catches_blind_exception(node):
                relative = path.relative_to(REPO_ROOT).as_posix()
                sites.append(DerivedSite(relative, _enclosing_function(tree, node.lineno)))
    return sites


def _pyproject_text() -> str:
    return (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")


class BroadExceptionPolicyTests(unittest.TestCase):
    def test_classified_inventory_covers_every_broad_except_site(self) -> None:
        derived = set(_broad_except_sites())
        classified = {DerivedSite(site.path, site.function) for site in CLASSIFIED_SITES}

        unclassified = sorted(derived - classified)
        stale = sorted(classified - derived)
        self.assertEqual(
            (unclassified, stale),
            ([], []),
            "Broad-exception inventory drifted from source. Re-derive with "
            f"`{REDERIVE_COMMAND}`, then update CLASSIFIED_SITES in {POLICY_TEST_PATH}: "
            f"add a verdict for {unclassified or 'nothing'}; drop the stale entries "
            f"{stale or 'nothing'}.",
        )

    def test_site_totals_match_the_recorded_counts(self) -> None:
        self.assertEqual(len(_broad_except_sites()), EXPECTED_HANDLER_COUNT)
        self.assertEqual(len(CLASSIFIED_SITES), EXPECTED_ANCHOR_COUNT)

    def test_every_site_carries_a_known_verdict_and_a_rationale(self) -> None:
        for site in CLASSIFIED_SITES:
            with self.subTest(path=site.path, function=site.function):
                self.assertIn(site.verdict, VERDICTS)
                self.assertGreater(
                    len(site.rationale.strip()),
                    40,
                    "Each verdict needs a rationale a reviewer can check against the source.",
                )

    def test_ble001_stays_unselected_under_the_pyflakes_baseline(self) -> None:
        config = tomllib.loads(_pyproject_text())
        select = config["tool"]["ruff"]["lint"]["select"]

        self.assertEqual(select, ["F"], "The baseline gate is Pyflakes-only; broadening it is separate work.")
        self.assertNotIn("BLE001", select)

    def test_recorded_policy_names_a_live_owner_and_the_rederive_command(self) -> None:
        # Issue #637 may still be cited as the precedent that established the
        # classified-versus-relabeled distinction, but it is closed and must not
        # be the tracking owner. The durable link is this module's path.
        for relative in ("pyproject.toml", "CLAUDE.md"):
            text = (REPO_ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(path=relative):
                self.assertIn(POLICY_OWNER_ISSUE, text)
                self.assertIn(POLICY_TEST_PATH, text)

        self.assertIn(REDERIVE_COMMAND, _pyproject_text())


if __name__ == "__main__":
    unittest.main()
