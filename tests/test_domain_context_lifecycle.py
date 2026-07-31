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

from test_domain_context_lifecycle_journey import DomainContextLifecycleJourneyMixin

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


class DomainContextLifecycleTests(DomainContextLifecycleJourneyMixin, unittest.TestCase):
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
