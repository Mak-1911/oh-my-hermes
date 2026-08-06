"""The vendored reader's CI and merge success claims must be receipt-backed.

`src/plugin_bundle/omh/runtime_reader.py` is the Hermes-facing surface. It is
standalone and hand-mirrored -- it cannot import from `src/omh` or `src/coding`
-- so the receipt rule issue #836 added to `omh.runtime.claims` had to be copied
into it by hand, and a hand-copy drifts.

Two things are pinned here:

* Behaviour. With no receipt naming an acting surface, the reader must not
  report `ci_observed` or `merge_observed`. That is the state of every store
  written before #836, so the reader has to withdraw the claim rather than
  trust the local `ci.json` / `merge.json` beside it.
* Parity. The vendored constants must still name the store the source writes,
  and the reader's verdict must match the CLI claim gate's verdict for the same
  run. A differential, not a restatement: it fails when either side moves.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from _local_package import load_local_package

load_local_package()

from omh.coding_delegation import build_coding_delegation_payload, coding_delegation_record_payload
from omh.conformance.checker import check_runtime_run
from omh.external_effect_receipts import (
    CLAIM_BOUNDARY,
    EXTERNAL_EFFECT_RECEIPT_SCHEMA_VERSION,
)
from omh.paths import OmhPaths, resolve_paths
from omh.plugin_bundle.omh import runtime_reader
from omh.plugin_bundle.omh.runtime_reader import read_omh_status
from omh.runtime.artifacts import EXTERNAL_EFFECT_RECORD_SURFACES, external_effect_id
from omh.runtime_artifacts import (
    create_prepared_coding_delegation_run,
    write_ci_record,
    write_coding_delegation,
    write_delegation,
    write_merge_record,
    write_review_record,
    write_wrapper_contract,
)


def _executed_run(paths: OmhPaths) -> str:
    run = create_prepared_coding_delegation_run(paths, {"skill": "coding", "harness": "delegate"})
    run_id = str(run["run_id"])
    run_dir = paths.runtime_runs_dir / run_id
    message = "implement safe conformance adapter without overclaiming"
    payload = build_coding_delegation_payload(message, source="discord", executor_target="codex")
    write_coding_delegation(run_dir, coding_delegation_record_payload(payload, message))
    write_wrapper_contract(
        run_dir,
        {
            "prompt_dispatched": True,
            "hermes_response_observed": True,
            "verification_observed": True,
            "completion_status": "completed",
        },
    )
    write_delegation(run_dir, {"requested": True, "observed": True, "result": "completed"})
    write_review_record(run_dir, {"status": "passed", "reviewer": "code-review", "evidence_refs": ["review-comment"]})
    return run_id


def _pass_ci_and_merge(paths: OmhPaths, run_id: str) -> None:
    run_dir = paths.runtime_runs_dir / run_id
    write_ci_record(run_dir, {"status": "passed", "provider": "github-actions", "checks": ["unit:passed"]})
    write_merge_record(run_dir, {"status": "merged", "target_branch": "main", "merge_commit": "abc123"})


def _run_summary(paths: OmhPaths, run_id: str) -> dict[str, object]:
    status = read_omh_status(paths.omh_home, limit=5)
    for run in status["runs"]:
        if str(run.get("run_id", "")) == run_id:
            return run
    raise AssertionError(f"run {run_id} is absent from the vendored reader status")


class VendoredReaderReceiptRuleTests(unittest.TestCase):
    def test_ci_and_merge_success_is_not_claimed_without_a_receipt(self) -> None:
        """The pre-#836 store shape: local records claim success, nothing observed it."""
        with TemporaryDirectory() as tmp:
            paths = resolve_paths(Path(tmp) / ".omh", Path(tmp) / ".hermes")
            run_id = _executed_run(paths)
            _pass_ci_and_merge(paths, run_id)
            # Every store written before this feature existed looks like this.
            paths.runtime_external_effect_receipts_path.unlink()

            summary = _run_summary(paths, run_id)

            self.assertFalse(summary["ci_observed"])
            self.assertFalse(summary["merge_observed"])
            self.assertNotIn(summary["observation_status"], {"ci_observed", "merge_observed"})
            self.assertFalse(summary["lifecycle"]["ci_observed"])
            self.assertFalse(summary["lifecycle"]["merge_observed"])
            self.assertEqual(summary["external_effect_claims"]["unreceipted"], ["ci", "merge"])
            self.assertEqual(summary["external_effect_claims"]["receipt_backed"], [])

    def test_ci_and_merge_success_is_claimed_when_receipts_name_the_acting_surface(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = resolve_paths(Path(tmp) / ".omh", Path(tmp) / ".hermes")
            run_id = _executed_run(paths)
            _pass_ci_and_merge(paths, run_id)

            summary = _run_summary(paths, run_id)

            self.assertTrue(summary["ci_observed"])
            self.assertTrue(summary["merge_observed"])
            self.assertEqual(summary["external_effect_claims"]["receipt_backed"], ["ci", "merge"])
            self.assertEqual(summary["external_effect_claims"]["unreceipted"], [])

    def test_observation_status_is_demoted_only_to_the_rung_it_can_still_claim(self) -> None:
        demote = runtime_reader._demote_observation_status

        self.assertEqual(demote("merge_observed", {"ci", "merge"}), "merge_observed")
        self.assertEqual(demote("merge_observed", {"ci"}), "merge_gate_observed")
        self.assertEqual(demote("merge_observed", set()), "merge_gate_observed")
        self.assertEqual(demote("ci_observed", set()), "review_observed")
        self.assertEqual(demote("ci_observed", {"ci"}), "ci_observed")
        # Local rungs are never demoted, and a terminal state is never rewritten.
        self.assertEqual(demote("execution_observed", set()), "execution_observed")
        self.assertEqual(demote("blocked", set()), "blocked")
        self.assertEqual(demote("something_else", set()), "something_else")

    def test_an_unnamed_ci_success_is_not_a_ci_claim(self) -> None:
        """A CI record with nothing naming the system that ran it mints `unknown`."""
        with TemporaryDirectory() as tmp:
            paths = resolve_paths(Path(tmp) / ".omh", Path(tmp) / ".hermes")
            run_id = _executed_run(paths)
            write_ci_record(paths.runtime_runs_dir / run_id, {"status": "passed", "checks": ["unit:passed"]})

            summary = _run_summary(paths, run_id)

            self.assertFalse(summary["ci_observed"])
            self.assertEqual(summary["ci_status"], "passed")
            self.assertEqual(summary["external_effect_claims"]["unreceipted"], ["ci", "merge"])

    def test_a_superseding_failure_withdraws_the_earlier_success_claim(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = resolve_paths(Path(tmp) / ".omh", Path(tmp) / ".hermes")
            run_id = _executed_run(paths)
            run_dir = paths.runtime_runs_dir / run_id
            write_ci_record(run_dir, {"status": "passed", "provider": "github-actions", "checks": ["unit:passed"]})
            self.assertTrue(_run_summary(paths, run_id)["ci_observed"])

            write_ci_record(run_dir, {"status": "failed", "provider": "github-actions", "checks": ["unit:failed"]})

            summary = _run_summary(paths, run_id)
            self.assertFalse(summary["ci_observed"])
            self.assertEqual(summary["external_effect_claims"]["receipt_backed"], [])

    def test_another_runs_receipt_does_not_back_this_runs_claim(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = resolve_paths(Path(tmp) / ".omh", Path(tmp) / ".hermes")
            receipted = _executed_run(paths)
            _pass_ci_and_merge(paths, receipted)
            bare = _executed_run(paths)
            bare_dir = paths.runtime_runs_dir / bare
            bare_dir.joinpath("ci.json").write_text(
                (paths.runtime_runs_dir / receipted / "ci.json").read_text(encoding="utf-8").replace(receipted, bare),
                encoding="utf-8",
            )

            summary = _run_summary(paths, bare)

            self.assertEqual(summary["ci_status"], "passed")
            self.assertFalse(summary["ci_observed"])


class VendoredReaderParityTests(unittest.TestCase):
    def test_vendored_constants_name_the_store_the_source_writes(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = resolve_paths(Path(tmp) / ".omh", Path(tmp) / ".hermes")

            self.assertEqual(
                runtime_reader.EXTERNAL_EFFECT_RECEIPT_STORE_NAME,
                paths.runtime_external_effect_receipts_path.name,
            )
            self.assertEqual(
                paths.runtime_external_effect_receipts_path.parent.name,
                "journal",
                "the reader looks for the store under <runtime>/journal/",
            )
        self.assertEqual(
            runtime_reader.EXTERNAL_EFFECT_RECEIPT_SCHEMA_VERSION,
            EXTERNAL_EFFECT_RECEIPT_SCHEMA_VERSION,
        )
        self.assertEqual(runtime_reader.EXTERNAL_EFFECT_CLAIM_BOUNDARY, CLAIM_BOUNDARY)

    def test_vendored_effect_kinds_match_the_source_record_surfaces(self) -> None:
        self.assertEqual(
            sorted(runtime_reader.RECEIPT_BACKED_RUN_CLAIMS.values()),
            ["ci", "merge"],
        )
        for kind in runtime_reader.RECEIPT_BACKED_RUN_CLAIMS.values():
            with self.subTest(kind=kind):
                self.assertIn(kind, EXTERNAL_EFFECT_RECORD_SURFACES)
                # The reader splits an effect id on the first ":" and compares
                # the tail to the run id, so this composition has to hold.
                self.assertEqual(external_effect_id(kind, "run-1"), f"{kind}:run-1")

    def test_vendored_status_order_covers_every_claim_it_demotes(self) -> None:
        for status in runtime_reader.RECEIPT_BACKED_RUN_CLAIMS:
            with self.subTest(status=status):
                self.assertIn(status, runtime_reader.OBSERVATION_STATUS_ORDER)

    def test_reader_verdict_matches_the_cli_claim_gate(self) -> None:
        """The differential: both surfaces read the same run and must agree."""
        for label, drop_store in (("receipted", False), ("unreceipted", True)):
            with self.subTest(store=label), TemporaryDirectory() as tmp:
                paths = resolve_paths(Path(tmp) / ".omh", Path(tmp) / ".hermes")
                run_id = _executed_run(paths)
                _pass_ci_and_merge(paths, run_id)
                if drop_store:
                    paths.runtime_external_effect_receipts_path.unlink()

                summary = _run_summary(paths, run_id)
                allowed = set(check_runtime_run(paths, run_id)["allowed_claims"])

                self.assertEqual(bool(summary["ci_observed"]), "ci_observed" in allowed)
                self.assertEqual(bool(summary["merge_observed"]), "merged" in allowed)


if __name__ == "__main__":
    unittest.main()
