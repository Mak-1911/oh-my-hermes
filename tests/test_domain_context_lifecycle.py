from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from _local_package import load_local_package

load_local_package()

from omh.paths import resolve_paths
from omh.wrapper_sessions import create_or_resume_wrapper_session
from omh.workflows.domain_project_context import bind_plugin_project

from test_plugin_distribution import FakeHermesContext, load_installed_plugin


PUBLIC_CONTEXT_KEYS = {
    "schema_version",
    "workflow_hint",
    "required_input",
    "question",
    "digest",
    "claim_boundary",
}
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EN_SALES_QUESTION = (
    "Which account or customer segment should this sales work focus on?"
)
KO_SALES_QUESTION = (
    "이 영업 작업은 어떤 계정 또는 고객 세그먼트에 집중해야 하나요?"
)
EN_FINANCE_QUESTION = "Which reporting period should this finance analysis cover?"


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _repository(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / ".git").mkdir()
    return path.resolve()


def _command_environment(root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["HOME"] = str(root.parent / "isolated-home")
    environment["OMH_HOME"] = str(root.parent / "hostile-env" / ".omh")
    environment["HERMES_HOME"] = str(root.parent / "hostile-env" / ".hermes")
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(REPOSITORY_ROOT / "src"), str(REPOSITORY_ROOT / "tests"))
    )
    environment["NO_PROXY"] = "*"
    environment["no_proxy"] = "*"
    return environment


def _run_omh(root: Path, *arguments: str) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "-m", "omh.cli", *arguments],
        cwd=root,
        env=_command_environment(root),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"omh command failed ({result.returncode}): {arguments!r}\n{result.stderr}"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"omh command did not return JSON: {arguments!r}\n{result.stdout}"
        ) from exc
    if not isinstance(payload, dict):
        raise AssertionError(f"omh command returned a non-object: {arguments!r}")
    return payload


def _capture_candidate(
    root: Path,
    *,
    scope_kind: str,
    scope_ref: str,
    domain: str,
    phrase: str,
    canonical: str,
    workflow_hints: tuple[str, ...],
) -> str:
    arguments = [
        "--scope",
        "project",
        "memory",
        "domain-capture",
        "--scope-kind",
        scope_kind,
        "--scope-ref",
        scope_ref,
        "--domain",
        domain,
        "--mapping",
        f"{phrase}={canonical}",
        "--source-ref",
        "lifecycle-test",
    ]
    for hint in workflow_hints:
        arguments.extend(("--workflow-hint", hint))
    payload = _run_omh(root, *arguments)
    candidate_id = str(payload["candidate"]["candidate_id"])
    if not candidate_id:
        raise AssertionError("public capture returned an empty candidate id")
    return candidate_id


def _approve_candidate(root: Path, candidate_id: str) -> dict[str, object]:
    review = _run_omh(
        root,
        "--scope",
        "project",
        "memory",
        "domain-review",
        "--candidate",
        candidate_id,
    )
    if review["cards"][0]["candidate_id"] != candidate_id:
        raise AssertionError("public review did not return the captured candidate")
    return _run_omh(
        root,
        "--scope",
        "project",
        "memory",
        "domain-approve",
        candidate_id,
        "--approved-by",
        "lifecycle-test",
    )


def _capture_and_approve(
    root: Path,
    *,
    scope_kind: str = "project",
    scope_ref: str | None = None,
    domain: str,
    phrase: str,
    canonical: str = "review_marker",
    workflow_hints: tuple[str, ...] = ("sales-development",),
) -> dict[str, object]:
    candidate_id = _capture_candidate(
        root,
        scope_kind=scope_kind,
        scope_ref=scope_ref or root.name,
        domain=domain,
        phrase=phrase,
        canonical=canonical,
        workflow_hints=workflow_hints,
    )
    return _approve_candidate(root, candidate_id)


def _chat(root: Path, message: str) -> dict[str, object]:
    return _run_omh(
        root,
        "--scope",
        "project",
        "chat",
        "interact",
        "--source",
        "discord",
        "--json",
        message,
    )


def _unresolved_message(phrase: str) -> str:
    return f"something {phrase} feels unresolved"


def _session_turn(
    root: Path,
    message: str,
    *,
    event_id: str = "event-lifecycle",
    channel_ref: str = "channel-lifecycle",
) -> dict[str, object]:
    return _run_omh(
        root,
        "--scope",
        "project",
        "chat",
        "session",
        "start",
        "--source",
        "discord",
        "--source-event-id",
        event_id,
        "--channel-ref",
        channel_ref,
        message,
    )


def _assert_applied_context(
    testcase: unittest.TestCase,
    interaction: dict[str, object],
    *,
    workflow: str,
    locale: str,
    question: str,
) -> None:
    testcase.assertEqual(set(interaction["domain_routing_context"]), PUBLIC_CONTEXT_KEYS)
    context = interaction["domain_routing_context"]
    testcase.assertEqual(context["schema_version"], "domain_routing_context/v1")
    testcase.assertEqual(context["workflow_hint"], workflow)
    testcase.assertEqual(context["question"], {"locale": locale, "text": question})
    testcase.assertRegex(context["digest"], r"^[0-9a-f]{64}$")
    testcase.assertEqual(
        interaction["chat_response"]["body"].splitlines()[-1],
        question,
    )


@contextmanager
def _block_external_connections():
    with mock.patch.object(
        socket.socket,
        "connect",
        side_effect=AssertionError("external connection attempted"),
    ):
        yield


class DomainContextLifecycleTests(unittest.TestCase):
    def test_public_capture_approve_replace_retire_journey(self) -> None:
        with TemporaryDirectory() as temporary:
            root = _repository(Path(temporary) / "redwood-project")
            phrase = "expert-marker-100-en"
            message = _unresolved_message(phrase)

            before_approval = _chat(root, message)
            self.assertNotIn("domain_routing_context", before_approval)
            generic_body = before_approval["chat_response"]["body"]
            baseline_route = _canonical(before_approval["route"])
            baseline_candidate = _canonical(
                before_approval["route"].get("candidate_handoff")
            )

            first_candidate_id = _capture_candidate(
                root,
                scope_kind="project",
                scope_ref="redwood-project",
                domain="redwood-operations",
                phrase=phrase,
                canonical="redwood_review_marker",
                workflow_hints=("sales-development",),
            )
            first_approval = _approve_candidate(root, first_candidate_id)
            self.assertEqual(first_approval["decision"], "approved")

            english = _chat(root, message)
            korean = _chat(root, f"뭔가 {phrase} 관련해서 애매해요")
            _assert_applied_context(
                self,
                english,
                workflow="sales-development",
                locale="en",
                question=EN_SALES_QUESTION,
            )
            _assert_applied_context(
                self,
                korean,
                workflow="sales-development",
                locale="ko",
                question=KO_SALES_QUESTION,
            )
            self.assertEqual(_canonical(english["route"]), baseline_route)
            self.assertEqual(
                _canonical(english["route"].get("candidate_handoff")),
                baseline_candidate,
            )

            setup = _run_omh(
                root, "--scope", "project", "setup", "--with-plugin", "--json"
            )
            self.assertIn(setup.get("status"), {"installed", "updated", "ok", None})
            plugin = load_installed_plugin(root / ".hermes" / "plugins" / "omh")
            context = FakeHermesContext()
            plugin.register(context)
            plugin_handler = context.tools["omh_interact"]["args"][2]
            with _block_external_connections():
                plugin_interaction = json.loads(
                    plugin_handler(
                        {
                            "message": message,
                            "source": "discord",
                            "record_session": False,
                        },
                        project_root=str(root),
                    )
                )
            _assert_applied_context(
                self,
                plugin_interaction,
                workflow="sales-development",
                locale="en",
                question=EN_SALES_QUESTION,
            )

            first_turn = _session_turn(root, message)
            self.assertFalse(first_turn["resumed"])
            _assert_applied_context(
                self,
                first_turn["interaction"],
                workflow="sales-development",
                locale="en",
                question=EN_SALES_QUESTION,
            )

            replacement_id = _capture_candidate(
                root,
                scope_kind="project",
                scope_ref="redwood-project",
                domain="redwood-operations",
                phrase=phrase,
                canonical="redwood_review_marker",
                workflow_hints=("finance-analysis",),
            )
            replacement = _approve_candidate(root, replacement_id)
            self.assertEqual(replacement["profile"]["revision"], 2)
            next_turn = _session_turn(root, message)
            self.assertTrue(next_turn["resumed"])
            self.assertEqual(
                next_turn["session"]["session_id"], first_turn["session"]["session_id"]
            )
            _assert_applied_context(
                self,
                next_turn["interaction"],
                workflow="finance-analysis",
                locale="en",
                question=EN_FINANCE_QUESTION,
            )

            retired = _run_omh(
                root,
                "--scope",
                "project",
                "memory",
                "domain-retire",
                "--scope-kind",
                "project",
                "--scope-ref",
                "redwood-project",
                "--domain",
                "redwood-operations",
                "--retired-by",
                "lifecycle-test",
                "--reason",
                "superseded",
            )
            self.assertEqual(retired["decision"], "retired")
            after_retirement = _chat(root, message)
            self.assertNotIn("domain_routing_context", after_retirement)
            self.assertEqual(after_retirement["chat_response"]["body"], generic_body)
            self.assertEqual(_canonical(after_retirement["route"]), baseline_route)

    def test_same_named_repositories_use_only_the_bound_project_store(self) -> None:
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            first = _repository(base / "one" / "same-project")
            second = _repository(base / "two" / "same-project")
            phrase = "expert-marker-200-en"
            _capture_and_approve(first, domain="isolation", phrase=phrase)

            applied = _chat(first, _unresolved_message(phrase))
            isolated = _chat(second, _unresolved_message(phrase))

            self.assertIn("domain_routing_context", applied)
            self.assertNotIn("domain_routing_context", isolated)

    def test_user_and_organization_profiles_are_not_consumed(self) -> None:
        with TemporaryDirectory() as temporary:
            root = _repository(Path(temporary) / "scope-project")
            phrase = "expert-marker-300-en"
            _capture_and_approve(
                root,
                scope_kind="user",
                scope_ref="user-lifecycle",
                domain="user-domain",
                phrase=phrase,
            )
            _capture_and_approve(
                root,
                scope_kind="organization",
                scope_ref="org-lifecycle",
                domain="organization-domain",
                phrase=phrase,
            )

            interaction = _chat(root, _unresolved_message(phrase))

            self.assertNotIn("domain_routing_context", interaction)

    def test_packaged_plugin_rejects_absent_and_hostile_redirects(self) -> None:
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            trusted = _repository(base / "trusted-project")
            hostile = _repository(base / "hostile-project")
            phrase = "expert-marker-400-en"
            _capture_and_approve(trusted, domain="trusted", phrase=phrase)
            _capture_and_approve(hostile, domain="hostile", phrase=phrase)
            _run_omh(
                trusted, "--scope", "project", "setup", "--with-plugin", "--json"
            )
            plugin = load_installed_plugin(trusted / ".hermes" / "plugins" / "omh")
            context = FakeHermesContext()
            plugin.register(context)
            handler = context.tools["omh_interact"]["args"][2]
            args = {
                "message": _unresolved_message(phrase),
                "source": "discord",
                "record_session": False,
                "project_root": str(hostile),
                "omh_home": str(hostile / ".omh"),
                "source_metadata": {"project_ref": str(hostile)},
            }

            with mock.patch.dict(
                os.environ,
                {
                    "PROJECT_ROOT": str(hostile),
                    "OMH_HOME": str(hostile / ".omh"),
                },
            ), _block_external_connections():
                absent = json.loads(handler(args))
                applied = json.loads(handler(args, project_root=str(trusted)))

            self.assertNotIn("domain_routing_context", absent)
            _assert_applied_context(
                self,
                applied,
                workflow="sales-development",
                locale="en",
                question=EN_SALES_QUESTION,
            )

    def test_cross_repository_session_reuse_uses_each_turns_fresh_binding(self) -> None:
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            first = _repository(base / "first" / "same-project")
            second = _repository(base / "second" / "same-project")
            phrase = "expert-marker-500-en"
            _capture_and_approve(first, domain="first", phrase=phrase)
            _capture_and_approve(
                second,
                domain="second",
                phrase=phrase,
                workflow_hints=("finance-analysis",),
            )
            shared_paths = resolve_paths(base / "shared-omh", base / "shared-hermes")
            metadata = {"source_event_id": "same-event", "channel_ref": "same-channel"}

            with _block_external_connections(), bind_plugin_project(
                {"project_root": str(first)}
            ) as first_binding:
                first_turn = create_or_resume_wrapper_session(
                    shared_paths,
                    _unresolved_message(phrase),
                    source="discord",
                    source_metadata=metadata,
                    _host_project_binding=first_binding,
                )
            with _block_external_connections(), bind_plugin_project(
                {"project_root": str(second)}
            ) as second_binding:
                second_turn = create_or_resume_wrapper_session(
                    shared_paths,
                    _unresolved_message(phrase),
                    source="discord",
                    source_metadata=metadata,
                    _host_project_binding=second_binding,
                )

            self.assertTrue(second_turn["resumed"])
            self.assertEqual(
                first_turn["session"]["session_id"], second_turn["session"]["session_id"]
            )
            self.assertEqual(
                first_turn["interaction"]["domain_routing_context"]["workflow_hint"],
                "sales-development",
            )
            self.assertEqual(
                second_turn["interaction"]["domain_routing_context"]["workflow_hint"],
                "finance-analysis",
            )

    def test_unrelated_malformed_health_artifact_suppresses_context(self) -> None:
        with TemporaryDirectory() as temporary:
            root = _repository(Path(temporary) / "unhealthy-project")
            phrase = "expert-marker-600-en"
            _capture_and_approve(root, domain="healthy", phrase=phrase)
            reviews = root / ".omh" / "memory" / "domain-intelligence" / "reviews"
            (reviews / "unrelated-malformed.json").write_text("{", encoding="utf-8")

            interaction = _chat(root, _unresolved_message(phrase))

            self.assertNotIn("domain_routing_context", interaction)

    def test_valid_and_empty_hint_profiles_suppress_context(self) -> None:
        with TemporaryDirectory() as temporary:
            root = _repository(Path(temporary) / "empty-hint-project")
            phrase = "expert-marker-700-en"
            _capture_and_approve(root, domain="valid", phrase=phrase)
            _capture_and_approve(
                root,
                domain="empty",
                phrase=phrase,
                workflow_hints=(),
            )

            interaction = _chat(root, _unresolved_message(phrase))

            self.assertNotIn("domain_routing_context", interaction)

    def test_unknown_hint_suppresses_context(self) -> None:
        with TemporaryDirectory() as temporary:
            root = _repository(Path(temporary) / "unknown-hint-project")
            phrase = "expert-marker-800-en"
            _capture_and_approve(
                root,
                domain="unknown",
                phrase=phrase,
                workflow_hints=("unknown-workflow",),
            )

            interaction = _chat(root, _unresolved_message(phrase))

            self.assertNotIn("domain_routing_context", interaction)

    def test_protected_routes_keep_body_route_and_candidate_exactly_equal(self) -> None:
        with TemporaryDirectory() as temporary:
            root = _repository(Path(temporary) / "protected-project")
            phrase = "protected route marker"
            protected_messages = ("what's 2+2?", "README 파일 찾아줘")
            baselines = {message: _chat(root, message) for message in protected_messages}
            _capture_and_approve(root, domain="protected", phrase=phrase)

            for message in protected_messages:
                with self.subTest(message=message):
                    after = _chat(root, message)
                    before = baselines[message]
                    self.assertNotIn("domain_routing_context", after)
                    self.assertEqual(after["chat_response"]["body"], before["chat_response"]["body"])
                    self.assertEqual(_canonical(after["route"]), _canonical(before["route"]))
                    self.assertEqual(
                        _canonical(after["route"].get("candidate_handoff")),
                        _canonical(before["route"].get("candidate_handoff")),
                    )


if __name__ == "__main__":
    unittest.main()
