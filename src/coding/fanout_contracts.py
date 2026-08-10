from __future__ import annotations

from .executors import EXECUTOR_PROFILES, HERMES_CODING_TEAM_STATUS_LADDER


FANOUT_CONTRACT_SCHEMA_VERSION = "fanout_contract/v1"
FANOUT_ID_PATTERN = r"^fanout-[0-9a-f]{12}$"
FANOUT_UNIT_STATUSES = ("prepared", *HERMES_CODING_TEAM_STATUS_LADDER)
FANOUT_UNIT_OWNERS = EXECUTOR_PROFILES
PREPARED_NOT_OBSERVED = "prepared_not_observed"
FANOUT_CLAIM_BOUNDARY = (
    "A fanout contract freezes a proposed parallel work split into prepared per-unit handoffs and a merge plan. "
    "It is not dispatch, execution, implementation, verification, review, CI, merge-readiness, or merge evidence; "
    "unit status advances only on observed per-unit run records."
)
FANOUT_FINAL_INTEGRATION_GATE = (
    "PYTHONPATH=tests uv run python -m unittest discover -s tests",
    "uv run python -m omh.cli docs workflows --check",
    "uv run python -m omh.cli docs roles --check",
    "uv run python -m omh.cli docs capability-families --check",
    "git diff --check",
)

# The key set a `fanout_contract/v1` freeze carries. `safety_profile_revision`
# and `spawn_plan` are optional and additive: an install without the preflight
# evaluator omits the first, and a split that needed no justification omits the
# second. Everything else is always present. Declared here rather than inlined
# in a test so the contract's shape lives beside its schema version.
FANOUT_CONTRACT_KEYS = (
    "board_projection",
    "claim_boundary",
    "fanout_id",
    "goal",
    "merge_plan",
    "observed_evidence_required",
    "schema_version",
    "source",
    "source_metadata",
    "status",
    "units",
)
FANOUT_CONTRACT_OPTIONAL_KEYS = ("safety_profile_revision", "spawn_plan")

FANOUT_SPAWN_PLAN_SCHEMA_VERSION = "fanout_spawn_plan/v1"
# Up to four units a split is small enough to read at a glance. Past that the
# contract stops recording an obvious decomposition and starts recording a
# guess, so the operator has to say why out loud. The threshold is locked
# rather than configurable on purpose: a threshold that can be raised is a
# threshold that gets raised instead of answered.
FANOUT_SPAWN_PLAN_THRESHOLD = 4
FANOUT_SPAWN_PLAN_TEXT_FIELDS = (
    "why_parallel",
    "why_not_single_unit",
    "independence",
    "expected_evidence_shape",
)
FANOUT_SPAWN_PLAN_FIELDS = (*FANOUT_SPAWN_PLAN_TEXT_FIELDS, "max_inline_tokens")
# Bounded for the reason every operator-typed contract string is bounded here:
# a field with no ceiling is a field that eventually carries a pasted
# transcript. One or two sentences is the whole intent.
MAX_SPAWN_PLAN_FIELD_CHARS = 280
FANOUT_SPAWN_PLAN_CLAIM_BOUNDARY = (
    "A spawn plan is the operator's prepared justification for splitting one goal across several units. "
    "It is not evidence that the split is correct, that the units are independent, that the named evidence "
    "shape was produced, or that any unit ran."
)


class FanoutContractError(ValueError):
    """Raised when a proposed fanout unit list cannot be frozen into a contract."""
