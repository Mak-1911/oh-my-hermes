"""The message gate: what a messenger must be told about delegated coding work.

Two things are under test here, and they fail for different reasons.

The RENDERER is tested against shapes that have already gone wrong once. Two
adjacent fences, a roster whose observed times all read `unknown` after a
payload round-trip, an empty `()` the disclosure rule names as forbidden, a
bullet list over the density ceiling OMH itself publishes -- each of these was
a real defect in this module before it had a test.

The WIRING is tested with a negative case per positive one, because the
interesting failure is not "the gate did not attach" but "the gate attached to
something that is not delegated coding work". The `oh-my-hermes` router skill
carries the `coding-handling` harness, so a harness-only condition put a header
reading `model — unknown` on the answer to "what can OMH do?" and raised a
missing-model warning about a capability question. That case is
`test_a_capability_question_carries_no_gate` and it is the point of this file.
"""

from __future__ import annotations

import json
import unittest

from _local_package import load_local_package

load_local_package()

from omh.wrapper.contract import build_chat_interaction_payload  # noqa: E402
from omh.wrapper.message_gate import (  # noqa: E402
    MESSAGE_GATE_SCHEMA_VERSION,
    PROMPT_PREVIEW_CHARS,
    RENDER_PROFILE_LIMITED_MARKDOWN,
    RENDER_PROFILE_RICH_MARKDOWN,
    UNKNOWN,
    WARNING_EMPTY_PARENTHESES,
    WARNING_MISSING_MODEL_LABEL,
    WARNING_MISSING_PROMPT_REFERENCE,
    WARNING_MISSING_STATUS,
    build_message_gate,
    fence_marker_for,
    message_gate_body,
    message_gate_messages,
    message_gate_warnings,
    render_message_gate_lines,
)

# `messenger_rendering.density_policy` publishes this ceiling for every limited
# profile. The gate is a limited-profile surface, so it owes the same number.
DECLARED_MAX_BULLETS = 12
# `_DIGEST_PREFIX` in the module; restated here so a widened prefix has to be a
# deliberate edit in two places rather than a silently longer row.
DECLARED_DIGEST_PREFIX = 12

CODING_MESSAGE = "auth 모듈 리팩터링을 코덱스한테 맡겨줘"


def _routed_gate(**overrides: object) -> dict:
    fields: dict = {
        "skill": "ulw-work",
        "executor": "codex",
        "model": "gpt-5-codex",
        "reasoning_effort": "xhigh",
        "status": "prepared_not_observed",
        "prompt_sha256": "533d406a486317830d49c302e798c242",
        "prompt_chars": 412,
    }
    fields.update(overrides)
    return build_message_gate(**fields)  # type: ignore[arg-type]


def _units(count: int) -> list[dict[str, str]]:
    return [
        {
            "label": f"unit-{index}",
            "owner": "codex",
            "model": "gpt-5-codex",
            "reasoning_effort": "xhigh",
            "status": "running",
            "elapsed_text": f"{index}m",
        }
        for index in range(1, count + 1)
    ]


class RenderShapeTests(unittest.TestCase):
    def test_the_rich_profile_opens_and_closes_exactly_one_fence(self) -> None:
        # Header and roster used to be two adjacent fenced blocks, which renders
        # as a fault rather than as two sections.
        gate = _routed_gate(units=_units(3))
        lines = render_message_gate_lines(gate, render_profile=RENDER_PROFILE_RICH_MARKDOWN)
        self.assertEqual(lines.count("```"), 2)
        self.assertEqual(lines[0], "```")
        self.assertEqual(lines[-1], "```")

    def test_the_limited_profile_never_fences_the_header(self) -> None:
        gate = _routed_gate(units=_units(3))
        lines = render_message_gate_lines(gate, render_profile=RENDER_PROFILE_LIMITED_MARKDOWN)
        self.assertNotIn("```", lines)
        self.assertTrue(all(line.startswith("- ") for line in lines), lines)

    def test_a_full_limited_header_stays_inside_the_declared_bullet_ceiling(self) -> None:
        gate = _routed_gate(task="auth 모듈 리팩터링", units=_units(20))
        lines = render_message_gate_lines(gate, render_profile=RENDER_PROFILE_LIMITED_MARKDOWN)
        bullets = [line for line in lines if line.startswith("- ")]
        self.assertLessEqual(len(bullets), DECLARED_MAX_BULLETS, "\n".join(lines))

    def test_a_capped_roster_says_so_on_its_own_line(self) -> None:
        gate = _routed_gate(units=_units(20))
        self.assertEqual(gate["roster_total"], 20)
        self.assertLess(gate["roster_count"], 20)
        for profile in (RENDER_PROFILE_LIMITED_MARKDOWN, RENDER_PROFILE_RICH_MARKDOWN):
            with self.subTest(profile=profile):
                rendered = "\n".join(render_message_gate_lines(gate, render_profile=profile))
                self.assertIn("more units", rendered)

    def test_a_complete_roster_states_no_omission(self) -> None:
        gate = _routed_gate(units=_units(3))
        rendered = "\n".join(render_message_gate_lines(gate, render_profile=RENDER_PROFILE_LIMITED_MARKDOWN))
        self.assertNotIn("more units", rendered)

    def test_observed_roster_times_survive_the_payload_round_trip(self) -> None:
        # Rows leave the builder keyed `elapsed`; re-running the raw-unit
        # normalizer over them looked for `elapsed_text`, found nothing, and
        # rewrote every observed time to `unknown`.
        gate = _routed_gate(units=_units(3))
        rendered = "\n".join(render_message_gate_lines(gate, render_profile=RENDER_PROFILE_LIMITED_MARKDOWN))
        self.assertIn("1m", rendered)
        self.assertIn("3m", rendered)
        self.assertNotIn(f"— {UNKNOWN}", rendered)

    def test_a_newline_in_a_value_cannot_break_the_rows_below_it(self) -> None:
        gate = _routed_gate(skill="ulw\nwork\nbroken")
        lines = render_message_gate_lines(gate, render_profile=RENDER_PROFILE_LIMITED_MARKDOWN)
        self.assertEqual(len(lines), len([line for line in lines if line.startswith("- ")]))


class DisclosureHonestyTests(unittest.TestCase):
    def test_a_known_executor_without_a_route_reads_executor_default(self) -> None:
        gate = _routed_gate(model="", reasoning_effort="")
        self.assertEqual(gate["fields"]["model"], "codex (executor default)")
        self.assertNotIn(WARNING_MISSING_MODEL_LABEL, gate["warnings"])

    def test_knowing_neither_executor_nor_model_reads_unknown_and_warns(self) -> None:
        # `executor default` is a claim about a resolved executor. With no
        # executor at all there is nothing to default, so the honest word is
        # `unknown` and the gate says the disclosure is incomplete.
        gate = _routed_gate(executor="", model="", reasoning_effort="")
        self.assertEqual(gate["fields"]["model"], UNKNOWN)
        self.assertIn(WARNING_MISSING_MODEL_LABEL, gate["warnings"])

    def test_the_parenthetical_is_never_emitted_empty(self) -> None:
        # DELEGATE_MODEL_LABEL_RULE names `()` as the one forbidden shape.
        for overrides in (
            {"model": "", "reasoning_effort": ""},
            {"model": "   ", "reasoning_effort": "   "},
            {"executor": "codex", "model_label": ""},
        ):
            with self.subTest(overrides=overrides):
                gate = _routed_gate(**overrides)
                self.assertNotIn("()", gate["fields"]["model"])
                self.assertNotIn(WARNING_EMPTY_PARENTHESES, gate["warnings"])

    def test_a_missing_status_or_prompt_reference_is_named(self) -> None:
        gate = _routed_gate(status="", prompt_sha256="")
        self.assertEqual(gate["fields"]["status"], UNKNOWN)
        self.assertEqual(gate["fields"]["prompt"], UNKNOWN)
        self.assertIn(WARNING_MISSING_STATUS, gate["warnings"])
        self.assertIn(WARNING_MISSING_PROMPT_REFERENCE, gate["warnings"])

    def test_a_roster_lane_with_no_model_warns_even_when_the_header_has_one(self) -> None:
        gate = _routed_gate(units=[{"label": "unit-1", "status": "running", "elapsed_text": "2m"}])
        self.assertNotEqual(gate["fields"]["model"], UNKNOWN)
        self.assertIn(WARNING_MISSING_MODEL_LABEL, gate["warnings"])

    def test_an_unadmitted_task_is_absent_rather_than_unknown(self) -> None:
        # The chat envelope declares `metadata_only` unless the wrapper opted
        # into `include_message`. Printing `unknown` would describe a redaction
        # as a gap in what OMH knows.
        gate = _routed_gate(task="")
        self.assertNotIn("task", gate["fields"])
        self.assertNotIn("task", gate["field_order"])
        rendered = "\n".join(render_message_gate_lines(gate, render_profile=RENDER_PROFILE_LIMITED_MARKDOWN))
        self.assertNotIn("task", rendered)

    def test_an_admitted_task_is_rendered(self) -> None:
        gate = _routed_gate(task="auth 모듈 리팩터링")
        self.assertEqual(gate["fields"]["task"], "auth 모듈 리팩터링")

    def test_the_prompt_row_carries_a_digest_and_never_the_prompt(self) -> None:
        gate = _routed_gate()
        prompt = gate["fields"]["prompt"]
        self.assertTrue(prompt.startswith("sha256:"), prompt)
        self.assertIn("412 chars", prompt)
        self.assertNotIn(CODING_MESSAGE, prompt)

    def test_the_digest_is_cut_to_the_declared_prefix(self) -> None:
        # A full 64-character digest is still a reference rather than a leak,
        # but it costs 52 characters of a row that has a messenger ceiling to
        # respect, and `omh coding fanout` already prints twelve.
        digest = "533d406a486317830d49c302e798c242bbb9105fa8525e6aac89217fa397e48c"
        gate = _routed_gate(prompt_sha256=digest)
        self.assertEqual(gate["fields"]["prompt"].split(" ")[0], f"sha256:{digest[:DECLARED_DIGEST_PREFIX]}")

    def test_a_non_hex_prompt_reference_is_stripped_to_its_alphanumerics(self) -> None:
        gate = _routed_gate(prompt_sha256="  ab-cd ef/gh  ")
        self.assertEqual(gate["fields"]["prompt"].split(" ")[0], "sha256:abcdefgh")

    def test_an_unmeasured_prompt_length_is_omitted_not_zeroed(self) -> None:
        for value in (None, "", -1, True):
            with self.subTest(value=value):
                gate = _routed_gate(prompt_chars=value)
                self.assertNotIn("chars", gate["fields"]["prompt"])

    def test_the_warning_vocabulary_is_closed(self) -> None:
        # A warning code nothing declares cannot be acted on by an adapter.
        declared = {
            WARNING_MISSING_MODEL_LABEL,
            WARNING_EMPTY_PARENTHESES,
            WARNING_MISSING_STATUS,
            WARNING_MISSING_PROMPT_REFERENCE,
        }
        worst = build_message_gate()
        self.assertTrue(set(worst["warnings"]).issubset(declared), worst["warnings"])
        self.assertEqual(message_gate_warnings(worst), worst["warnings"])

    def test_a_fully_resolved_gate_raises_no_warning(self) -> None:
        self.assertEqual(_routed_gate()["warnings"], [])


class PromptBlockTests(unittest.TestCase):
    LONG_PROMPT = "You are Codex, acting as the coding executor. " * 40

    def test_the_block_is_bounded_with_the_documented_truncation_marker(self) -> None:
        gate = _routed_gate(composed_prompt=self.LONG_PROMPT)
        block = gate["prompt_block"]
        # The reported total is the length of the stripped prompt the block was
        # cut from, not of the caller's trailing whitespace.
        self.assertIn(f"[truncated, {len(self.LONG_PROMPT.strip())} chars total]", block)
        self.assertLess(len(block), len(self.LONG_PROMPT))

    def test_a_short_prompt_is_shown_whole(self) -> None:
        prompt = "You are Codex. Refactor the auth module."
        gate = _routed_gate(composed_prompt=prompt)
        self.assertIn(prompt, gate["prompt_block"])
        self.assertNotIn("truncated", gate["prompt_block"])

    def test_the_preview_bound_is_the_declared_one(self) -> None:
        gate = _routed_gate(composed_prompt=self.LONG_PROMPT)
        body = gate["prompt_block"].split("\n")[2]
        self.assertLessEqual(len(body.split("...")[0]), PROMPT_PREVIEW_CHARS)

    def test_a_prompt_that_contains_a_fence_still_nests(self) -> None:
        gate = _routed_gate(composed_prompt="Run this:\n```sh\nmake test\n```\nThen report.")
        block = gate["prompt_block"]
        opening = block.split("\n")[1]
        self.assertGreater(len(opening), 3, block)
        self.assertEqual(opening, fence_marker_for("```"))

    def test_no_composed_prompt_means_no_block(self) -> None:
        self.assertNotIn("prompt_block", _routed_gate(composed_prompt="").keys())

    def test_the_block_is_its_own_message_never_appended_to_the_body(self) -> None:
        gate = _routed_gate(composed_prompt="You are Codex. Refactor auth.")
        messages = message_gate_messages(
            gate, render_profile=RENDER_PROFILE_LIMITED_MARKDOWN, body="Handoff ready."
        )
        self.assertEqual(len(messages), 2)
        self.assertNotIn("HERMES PROMPTING", messages[0])
        self.assertIn("HERMES PROMPTING", messages[1])

    def test_the_block_names_the_model_it_was_ordered_on(self) -> None:
        gate = _routed_gate(composed_prompt="You are Codex.")
        self.assertIn("codex (gpt-5-codex xhigh)", gate["prompt_block"].split("\n")[0])


class PayloadShapeTests(unittest.TestCase):
    def test_the_payload_is_schema_versioned_and_json_safe(self) -> None:
        gate = _routed_gate(units=_units(3), composed_prompt="You are Codex.", task="refactor auth")
        self.assertEqual(gate["schema_version"], MESSAGE_GATE_SCHEMA_VERSION)
        self.assertEqual(json.loads(json.dumps(gate)), gate)

    def test_field_order_names_only_present_fields(self) -> None:
        gate = _routed_gate(task="")
        self.assertEqual(sorted(gate["field_order"]), sorted(gate["fields"]))

    def test_an_empty_gate_renders_nothing_rather_than_a_header_of_dashes(self) -> None:
        self.assertEqual(message_gate_body({}, body="Body only."), "Body only.")
        self.assertEqual(render_message_gate_lines({}), [])


class WiringTests(unittest.TestCase):
    """Where the gate attaches -- and, more importantly, where it must not."""

    def _payload(self, message: str, **kwargs: object) -> dict:
        return build_chat_interaction_payload(message, source="discord", **kwargs)  # type: ignore[arg-type]

    def test_a_coding_delegation_carries_the_gate(self) -> None:
        response = self._payload(CODING_MESSAGE, executor_target="codex", mode="delegate")["chat_response"]
        gate = response["message_gate"]
        self.assertEqual(gate["schema_version"], MESSAGE_GATE_SCHEMA_VERSION)
        self.assertIn("codex", gate["fields"]["model"])
        self.assertTrue(gate["fields"]["prompt"].startswith("sha256:"))

    def test_the_gate_lines_reach_the_body_the_messenger_actually_posts(self) -> None:
        rendering = self._payload(CODING_MESSAGE, executor_target="codex", mode="delegate")[
            "chat_response"
        ]["messenger_rendering"]
        self.assertIn("- model — ", rendering["body_text"])
        self.assertIn("- status — ", rendering["body_text"])

    def test_a_capability_question_carries_no_gate(self) -> None:
        # The `oh-my-hermes` router skill's own harness is `coding-handling`, so
        # a harness-only condition gave this answer a `model — unknown` header
        # and a missing-model warning about a question with no executor at all.
        response = self._payload("what can OMH do?")["chat_response"]
        self.assertNotIn("message_gate", response)
        self.assertNotIn("- model — ", response["messenger_rendering"]["body_text"])

    def test_a_research_route_carries_no_gate(self) -> None:
        response = self._payload("웹서치해서 최신 자료 정리해줘")["chat_response"]
        self.assertNotIn("message_gate", response)

    def test_a_maintenance_command_carries_no_gate(self) -> None:
        response = self._payload("omh update")["chat_response"]
        self.assertNotIn("message_gate", response)

    def test_the_prompt_block_ships_as_a_follow_up_message_not_as_body(self) -> None:
        rendering = self._payload(CODING_MESSAGE, executor_target="codex", mode="delegate")[
            "chat_response"
        ]["messenger_rendering"]
        follow_ups = rendering["follow_up_texts"]
        self.assertEqual(len(follow_ups), 1)
        self.assertIn("HERMES PROMPTING", follow_ups[0])
        self.assertNotIn("HERMES PROMPTING", rendering["body_text"])

    def test_a_response_with_nothing_to_add_declares_an_empty_follow_up_list(self) -> None:
        rendering = self._payload("웹서치해서 최신 자료 정리해줘")["chat_response"]["messenger_rendering"]
        self.assertEqual(rendering["follow_up_texts"], [])

    def test_every_follow_up_fits_one_message_on_every_platform(self) -> None:
        for source in ("discord", "slack", "telegram", "generic", "hermes"):
            with self.subTest(source=source):
                rendering = build_chat_interaction_payload(
                    CODING_MESSAGE, source=source, executor_target="codex", mode="delegate"
                )["chat_response"]["messenger_rendering"]
                ceiling = int(rendering["chunking"]["max_recommended_chars"])
                for text in rendering["follow_up_texts"]:
                    self.assertLessEqual(len(text), ceiling)

    def test_the_gated_body_still_chunks_under_every_platform_ceiling(self) -> None:
        for source in ("discord", "slack", "telegram"):
            with self.subTest(source=source):
                rendering = build_chat_interaction_payload(
                    CODING_MESSAGE, source=source, executor_target="codex", mode="delegate"
                )["chat_response"]["messenger_rendering"]
                ceiling = int(rendering["chunking"]["hard_limit_chars"])
                for chunk in rendering["chunked_body_texts"]:
                    self.assertLessEqual(len(chunk), ceiling)

    def test_a_cached_copy_does_not_alias_the_gate(self) -> None:
        # `_copy_chat_response_payload` starts from a shallow `dict(response)`,
        # so a nested `fields` dict would be shared by every cached caller.
        first = self._payload(CODING_MESSAGE, executor_target="codex", mode="delegate")
        second = self._payload(CODING_MESSAGE, executor_target="codex", mode="delegate")
        first["chat_response"]["message_gate"]["fields"]["model"] = "poisoned"
        self.assertNotEqual(second["chat_response"]["message_gate"]["fields"]["model"], "poisoned")

    def test_a_cached_copy_does_not_alias_the_density_policy(self) -> None:
        first = self._payload(CODING_MESSAGE, executor_target="codex", mode="delegate")
        second = self._payload(CODING_MESSAGE, executor_target="codex", mode="delegate")
        first["chat_response"]["messenger_rendering"]["density_policy"]["avoid"].append("poisoned")
        self.assertNotIn(
            "poisoned", second["chat_response"]["messenger_rendering"]["density_policy"]["avoid"]
        )


class FenceMarkerOwnershipTests(unittest.TestCase):
    def test_the_contract_and_the_gate_share_one_fence_implementation(self) -> None:
        from omh.wrapper.contract import _fence_marker_for

        for text in ("plain", "a ``` fence", "a ```` deeper fence", "```` mixed ``` runs"):
            with self.subTest(text=text):
                self.assertEqual(_fence_marker_for(text), fence_marker_for(text))


if __name__ == "__main__":
    unittest.main()


class GoalSurfaceTests(unittest.TestCase):
    """`omh goal status --text` -- the second gate surface, with no executor."""

    CARD = {
        "goal_status": "active",
        "objective_summary": "포맷 선택 화면에서 진입하는 별도 가이드 페이지.",
        "progress": {
            "criteria_total": 6,
            "criteria_satisfied": 2,
            "required_total": 4,
            "required_satisfied": 1,
            "active_blockers": 0,
            "percent_required_satisfied": 25,
        },
        "next_action": "record_checkpoint",
        "checkpoint_lines": ["- a1b2c3: router wired — done, observed"],
        "missing_criteria": [{"summary": "guide page renders"}, "a bare string criterion"],
        "active_blockers": [],
    }

    def _render(self, card: dict | None = None, **kwargs: str) -> str:
        from omh.workflows.goal_ledger import render_goal_status_text

        return render_goal_status_text(card if card is not None else self.CARD, **kwargs)  # type: ignore[arg-type]

    def test_the_criteria_line_reads_the_keys_the_ledger_actually_writes(self) -> None:
        # `_goal_progress` writes `criteria_satisfied` / `criteria_total`. Reading
        # `satisfied` / `total` rendered a six-criteria goal as `0 of 0` -- a
        # wrong number that reads exactly like a right one.
        self.assertIn("Criteria: 2 of 6 satisfied", self._render())
        self.assertIn("25% of required", self._render())

    def test_a_goal_declares_no_model_rather_than_an_unknown_one(self) -> None:
        rendered = self._render()
        self.assertNotIn("model", rendered)
        self.assertIn("- skill — ulw-goal", rendered)
        self.assertIn("- status — active", rendered)

    def test_a_declared_non_disclosure_raises_no_missing_model_warning(self) -> None:
        gate = build_message_gate(skill="ulw-goal", status="active", prompt_sha256="abc123", discloses_model=False)
        self.assertNotIn("model", gate["fields"])
        self.assertNotIn(WARNING_MISSING_MODEL_LABEL, gate["warnings"])

    def test_a_delegation_surface_still_warns_when_it_resolved_no_model(self) -> None:
        # The escape hatch above must not weaken the guard it sits next to.
        gate = build_message_gate(skill="ulw-work", status="prepared_not_observed", prompt_sha256="abc123")
        self.assertIn(WARNING_MISSING_MODEL_LABEL, gate["warnings"])

    def test_the_rich_profile_fences_the_goal_header_too(self) -> None:
        rendered = self._render(render_profile=RENDER_PROFILE_RICH_MARKDOWN)
        self.assertIn("SKILL   ulw-goal", rendered)
        self.assertEqual(rendered.count("```"), 2)

    def test_no_table_is_ever_rendered(self) -> None:
        # The one-off `render_guidance` this generalizes exists because a live
        # Slack session lost a markdown table.
        for profile in (RENDER_PROFILE_LIMITED_MARKDOWN, RENDER_PROFILE_RICH_MARKDOWN):
            with self.subTest(profile=profile):
                self.assertNotIn(" | ", self._render(render_profile=profile))

    def test_ledger_entries_render_whether_stored_as_dicts_or_strings(self) -> None:
        rendered = self._render()
        self.assertIn("- guide page renders", rendered)
        self.assertIn("- a bare string criterion", rendered)

    def test_an_empty_card_renders_a_sentence_rather_than_a_blank_body(self) -> None:
        rendered = self._render({})
        self.assertIn("(no objective recorded)", rendered)
        self.assertIn("No checkpoints recorded.", rendered)

    def test_the_last_line_is_the_claim_boundary(self) -> None:
        from omh.workflows.goal_ledger import GOAL_STATUS_CLAIM_BOUNDARY

        self.assertTrue(self._render().endswith(GOAL_STATUS_CLAIM_BOUNDARY))


class GoalCliTests(unittest.TestCase):
    def _base(self, root) -> list[str]:
        return ["--omh-home", str(root / ".omh"), "--hermes-home", str(root / ".hermes")]

    def test_text_requires_a_goal_and_says_so(self) -> None:
        import tempfile
        from pathlib import Path

        from _cli_harness import run_cli

        with tempfile.TemporaryDirectory() as tmp:
            status, stdout, stderr = run_cli(
                [*self._base(Path(tmp)), "goal", "status", "--text"], output_json=False
            )
        self.assertNotEqual(status, 0)
        self.assertEqual(stdout, "")
        self.assertIn("--goal", stderr)

    def test_json_stays_the_default_for_this_control_plane_command(self) -> None:
        import tempfile
        from pathlib import Path

        from _cli_harness import run_cli

        with tempfile.TemporaryDirectory() as tmp:
            status, stdout, _ = run_cli([*self._base(Path(tmp)), "goal", "status"], output_json=False)
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(stdout), {"goals": []})
