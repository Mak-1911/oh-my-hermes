from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from _local_package import load_local_package

load_local_package()

from omh.coding_lifecycle import start_codex_delegation_lifecycle
from omh.paths import project_identity, resolve_paths
from omh.runtime_records import (
    WRAPPER_SESSION_RECORD_KEYS,
    validate_coding_delegation_record,
    validate_wrapper_session_record,
)
from omh.workflows.domain_intelligence import retire_domain_profile
from omh.workflows.domain_project_context import bind_cli_project
from omh.wrapper_contract import build_chat_interaction_payload, build_status_card_from_status
from omh.wrapper_sessions import create_or_resume_wrapper_session

from test_domain_routing_context import _approve_profile, _repository


AUTHORITATIVE_DIRECTORIES = ("candidates", "reviews", "profiles", "history")
PUBLIC_CONTEXT_KEYS = {
    "schema_version",
    "workflow_hint",
    "required_input",
    "question",
    "digest",
    "claim_boundary",
}
PROFILE_PRIVATE_KEYS = {
    "profile_id",
    "revision",
    "payload_digest",
    "mapping_digest",
    "mapping_ref",
    "mapping_index",
    "vocabulary_mappings",
    "phrase",
    "canonical",
    "project_scope_ref",
    "store_path",
    "root_path",
    "candidate_id",
    "review_id",
}


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _authoritative_snapshot(store: Path) -> dict[str, tuple[int, str]]:
    snapshot: dict[str, tuple[int, str]] = {}
    for dirname in AUTHORITATIVE_DIRECTORIES:
        directory = store / dirname
        directory.mkdir(parents=True, exist_ok=True)
        for path in sorted(directory.glob("*.json")):
            data = path.read_bytes()
            snapshot[str(path.relative_to(store))] = (
                len(data),
                hashlib.sha256(data).hexdigest(),
            )
    return snapshot


def _private_source_values(root: Path, profile: dict[str, object]) -> set[str]:
    store = root / ".omh" / "memory" / "domain-intelligence"
    mapping = profile["vocabulary_mappings"][0]
    values = {
        str(profile["profile_id"]),
        str(profile["candidate_id"]),
        str(profile["payload_digest"]),
        str(profile["scope"]["ref"]),
        str(profile["domain_id"]),
        str(mapping["phrase"]),
        str(mapping["canonical"]),
        str(root.resolve()),
        str(store.resolve()),
        _canonical_bytes(mapping).decode("utf-8"),
    }
    for path in sorted(store.rglob("*.json")):
        values.add(path.stem)
        value = json.loads(path.read_text(encoding="utf-8"))
        for key in ("candidate_id", "profile_id", "review_id", "payload_digest"):
            if value.get(key):
                values.add(str(value[key]))

    derivatives: set[str] = set()
    for value in values:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        derivatives.update({digest, digest[:16], digest[:24], digest[:32]})
    return {value for value in values | derivatives if len(value) >= 8}


def _private_key_paths(value: object, prefix: tuple[str, ...] = ()) -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            path = (*prefix, key_text)
            if key_text in PROFILE_PRIVATE_KEYS:
                paths.append(".".join(path))
            paths.extend(_private_key_paths(nested, path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            paths.extend(_private_key_paths(nested, (*prefix, f"[{index}]")))
    return paths


def _assert_no_private_material(
    testcase: unittest.TestCase,
    value: object,
    private_values: set[str],
    *,
    label: str,
) -> None:
    serialized = _canonical_bytes(value).decode("utf-8")
    leaked_values = sorted(item for item in private_values if item in serialized)
    testcase.assertEqual(leaked_values, [], f"{label} leaked private values")
    testcase.assertEqual(
        _private_key_paths(value),
        [],
        f"{label} retained profile-private fields",
    )


class DomainContextPrivacyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = _repository(Path(self.temporary.name).resolve() / "privacy-project")
        self.paths = resolve_paths(self.root / ".omh", self.root / ".hermes")
        self.phrase = "private routing marker"
        self.message = f"Something about this {self.phrase} still feels unresolved"
        self.profile = _approve_profile(
            self.root,
            domain_id="privacy-audit",
            phrase=self.phrase,
            canonical="private_routing_marker_canonical",
        )
        self.store = self.root / ".omh" / "memory" / "domain-intelligence"
        self.private_values = _private_source_values(self.root, self.profile)

    def _applied_interaction(self) -> dict[str, object]:
        with bind_cli_project(self.root) as binding:
            if binding is None:
                raise AssertionError("fixture failed to mint a project binding")
            return build_chat_interaction_payload(
                self.message,
                source="discord",
                source_metadata={"source_event_id": "event-001", "channel_ref": "channel-001"},
                paths=self.paths,
                _host_project_binding=binding,
            )

    def _binding_factory(self):
        binding = bind_cli_project(self.root)
        if binding is None:
            raise AssertionError("fixture failed to mint a project binding")
        return binding

    def test_public_context_has_only_contract_fields_and_public_digest_inputs(self) -> None:
        interaction = self._applied_interaction()

        self.assertIn("domain_routing_context", interaction)
        context = interaction["domain_routing_context"]
        self.assertEqual(set(context), PUBLIC_CONTEXT_KEYS)
        self.assertEqual(
            [path for path in _find_key_paths(interaction, "domain_routing_context")],
            ["domain_routing_context"],
        )
        preimage = {key: value for key, value in context.items() if key != "digest"}
        self.assertEqual(
            context["digest"],
            hashlib.sha256(_canonical_bytes(preimage)).hexdigest(),
        )
        _assert_no_private_material(
            self,
            preimage,
            self.private_values,
            label="public digest preimage",
        )

    def test_applied_interaction_leaves_authoritative_sources_unchanged(self) -> None:
        before = _authoritative_snapshot(self.store)
        stdout = StringIO()
        stderr = StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            interaction = self._applied_interaction()

        self.assertIn("domain_routing_context", interaction)
        self.assertEqual(_authoritative_snapshot(self.store), before)
        self.assertEqual(
            {dirname: len(list((self.store / dirname).glob("*.json"))) for dirname in AUTHORITATIVE_DIRECTORIES},
            {"candidates": 1, "reviews": 1, "profiles": 1, "history": 0},
        )
        _assert_no_private_material(
            self,
            {"stdout": stdout.getvalue(), "stderr": stderr.getvalue()},
            self.private_values,
            label="interaction output streams",
        )

    def test_session_second_turn_rederives_state_without_retaining_context(self) -> None:
        calls = 0

        def binding_factory():
            nonlocal calls
            calls += 1
            return self._binding_factory()

        metadata = {"source_event_id": "event-002", "channel_ref": "channel-002"}
        first = create_or_resume_wrapper_session(
            self.paths,
            self.message,
            source="discord",
            source_metadata=metadata,
            _host_project_binding_factory=binding_factory,
        )
        self.assertIn("domain_routing_context", first["interaction"])
        self.assertNotIn("domain_routing_context", first["session"])

        retire_domain_profile(
            self.paths,
            scope_kind="project",
            scope_ref=project_identity(self.root),
            domain_id=str(self.profile["domain_id"]),
            reason="superseded",
        )
        second = create_or_resume_wrapper_session(
            self.paths,
            self.message,
            source="discord",
            source_metadata=metadata,
            _host_project_binding_factory=binding_factory,
        )

        self.assertTrue(second["resumed"])
        self.assertNotIn("domain_routing_context", second["interaction"])
        self.assertEqual(calls, 2)
        self.assertEqual(set(second["session"]), set(WRAPPER_SESSION_RECORD_KEYS))
        self.assertEqual(validate_wrapper_session_record(second["session"]), [])
        _assert_no_private_material(
            self,
            {
                "source_metadata": second["session"]["source_metadata"],
                "thread_key": second["session"]["thread_key"],
                "session": second["session"],
                "status": second["status"],
            },
            self.private_values,
            label="session continuity",
        )

    def test_runtime_coding_and_status_records_keep_existing_schemas_private(self) -> None:
        interaction = self._applied_interaction()
        self.assertIn("domain_routing_context", interaction)
        lifecycle = start_codex_delegation_lifecycle(
            self.paths,
            "Implement the bounded validation and add focused tests",
            source="discord",
            source_metadata={"source_event_id": "event-003", "channel_ref": "channel-003"},
        )
        coding = lifecycle["coding_delegation"]
        status_card = build_status_card_from_status(lifecycle["status"])
        plain_root = _repository(Path(self.temporary.name).resolve() / "plain-project")
        plain_paths = resolve_paths(plain_root / ".omh", plain_root / ".hermes")
        baseline = start_codex_delegation_lifecycle(
            plain_paths,
            "Implement the bounded validation and add focused tests",
            source="discord",
            source_metadata={"source_event_id": "event-003", "channel_ref": "channel-003"},
        )
        baseline_status_card = build_status_card_from_status(baseline["status"])

        self.assertEqual(set(lifecycle["run"]), set(baseline["run"]))
        self.assertEqual(set(coding), set(baseline["coding_delegation"]))
        self.assertEqual(set(status_card), set(baseline_status_card))
        self.assertEqual(validate_coding_delegation_record(coding), [])
        _assert_no_private_material(
            self,
            {
                "run": lifecycle["run"],
                "coding": coding,
                "status_card": status_card,
            },
            self.private_values,
            label="runtime coding and status records",
        )

    def test_non_authoritative_files_and_logs_contain_no_private_material(self) -> None:
        self._applied_interaction()
        create_or_resume_wrapper_session(
            self.paths,
            self.message,
            source="discord",
            source_metadata={"source_event_id": "event-004", "channel_ref": "channel-004"},
            _host_project_binding_factory=self._binding_factory,
        )
        start_codex_delegation_lifecycle(
            self.paths,
            "Implement the bounded validation and add focused tests",
            source="discord",
            source_metadata={"source_event_id": "event-005", "channel_ref": "channel-005"},
        )

        scanned: dict[str, str] = {}
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or self.store in path.parents:
                continue
            scanned[str(path.relative_to(self.root))] = path.read_text(
                encoding="utf-8",
                errors="replace",
            )

        self.assertTrue(scanned)
        _assert_no_private_material(
            self,
            scanned,
            self.private_values,
            label="non-authoritative recursive file and log scan",
        )


def _find_key_paths(
    value: object,
    target: str,
    prefix: tuple[str, ...] = (),
) -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            path = (*prefix, key_text)
            if key_text == target:
                paths.append(".".join(path))
            paths.extend(_find_key_paths(nested, target, path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            paths.extend(_find_key_paths(nested, target, (*prefix, f"[{index}]")))
    return paths


if __name__ == "__main__":
    unittest.main()
