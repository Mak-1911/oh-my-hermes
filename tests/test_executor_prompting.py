from __future__ import annotations

import json
import unittest

from _local_package import load_local_package

load_local_package()

from omh.coding.prompting import select_executor_prompting_strategy
from omh.coding_delegation import build_coding_delegation_payload, coding_delegation_record_payload
from omh.runtime.records import (
    validate_coding_executor_handoff,
    validate_coding_prompt_handoff,
    validate_coding_runtime_handoff,
    validate_executor_prompting_contract,
)


class ExecutorPromptingTests(unittest.TestCase):
    def test_handoffs_share_canonical_prompt_sections_across_executor_paths(self) -> None:
        cases = (
            ("codex", "executor_handoff", validate_coding_executor_handoff),
            ("claude-code", "prompt_handoff", validate_coding_prompt_handoff),
            ("hermes", "runtime_handoff", validate_coding_runtime_handoff),
            ("omx-runtime", "runtime_handoff", validate_coding_runtime_handoff),
        )
        expected_sections = (
            "Goal",
            "Do",
            "Don't",
            "Known context",
            "Unknowns and decision rule",
            "Expected result",
            "Test",
            "Progress and blockers",
            "Evidence boundary",
            "Task",
        )

        for executor, key, validator in cases:
            with self.subTest(executor=executor):
                payload = build_coding_delegation_payload(
                    "Safely refactor src/example.py and add focused tests.",
                    executor_target=executor,
                )
                handoff = payload[key]

                self.assertEqual(validator(handoff), [])
                contract = handoff["executor_prompting_contract"]
                self.assertEqual(contract["profile"], executor)
                self.assertEqual(contract["status"], "prepared_not_observed")
                self.assertEqual(contract["strategy"], "risk_aware_change")
                self.assertEqual(contract["required_sections"], list(expected_sections))
                self.assertIn("{changed_constraint}", contract["steering_delta_template"])
                self.assertIn("{verification_target_changed}", contract["steering_delta_template"])
                for section in expected_sections[:-1]:
                    self.assertIn(f"{section}\n", handoff["prompt_template"])
                self.assertIn("Task:\n{message}", handoff["prompt_template"])
                self.assertIn(payload["delegation"]["acceptance_criteria"][0], handoff["prompt_template"])
                self.assertIn(payload["delegation"]["verification"][0], handoff["prompt_template"])

    def test_strategy_selection_distinguishes_plan_risk_and_repair(self) -> None:
        self.assertEqual(
            select_executor_prompting_strategy(
                intent="coding",
                message="Implement src/example.py validation.",
                has_plan_artifact=False,
                isolation_plan={"risk_level": "low"},
            ),
            "direct_change",
        )
        self.assertEqual(
            select_executor_prompting_strategy(
                intent="coding",
                message="Safely refactor src/payments.py.",
                has_plan_artifact=False,
                isolation_plan={"risk_level": "medium"},
            ),
            "risk_aware_change",
        )
        self.assertEqual(
            select_executor_prompting_strategy(
                intent="review",
                message="Review src/example.py.",
                has_plan_artifact=False,
                isolation_plan={},
            ),
            "review_or_repair",
        )
        payload = build_coding_delegation_payload(
            "Implement the accepted plan in src/example.py.",
            executor_target="codex",
            plan_artifact={"path": ".omh/plans/example.json", "status": "accepted"},
        )
        contract = payload["executor_handoff"]["executor_prompting_contract"]
        self.assertEqual(contract["strategy"], "plan_backed_change")
        self.assertEqual(contract["task_source"], "accepted_plan_artifact")

    def test_contract_rejects_missing_steering_field_and_persists_no_raw_task(self) -> None:
        raw_task = "do not persist this exact raw task in a durable artifact"
        payload = build_coding_delegation_payload(raw_task, executor_target="codex", include_message=True)
        contract = dict(payload["executor_handoff"]["executor_prompting_contract"])
        contract["steering_delta_template"] = contract["steering_delta_template"].replace("{new_evidence}", "")
        errors = validate_executor_prompting_contract(contract, "prompting", expected_profile="codex")
        self.assertTrue(any("steering_delta_template must include {new_evidence}" in error for error in errors))

        record = coding_delegation_record_payload(payload, raw_task)
        self.assertNotIn(raw_task, json.dumps(record))
        self.assertEqual(
            record["executor_handoff"]["executor_prompting_contract"]["task_source"],
            "original_message_at_dispatch_time",
        )


if __name__ == "__main__":
    unittest.main()
