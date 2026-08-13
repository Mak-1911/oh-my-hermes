"""Descriptive `executor_capability/v1` metadata for spawnable dispatch profiles.

What this table is: a place to write down what is KNOWN about the dispatch
profiles omh can spawn — which edit formats they accept, whether they keep a
persistent evaluation context, whether a tool call can re-enter, whether they
batch code-mode work. What it is NOT: an opinion about which profile is
better. Nothing here ranks, scores, or recommends, and no routing or
preference code may read these fields. A capability row is display metadata
that travels with a handoff and a dispatch record so a reader can see what the
project has actually established about the executor it is talking to.

Three deliberate shapes:

* Tri-state strings, never booleans. `unsupported` means someone looked and
  the capability is absent; `unknown` means nobody looked. A boolean erases
  that difference, and the erased half is precisely the half that would let a
  guess be read downstream as an observation.
* `unknown` is the default for every cell. Rows are populated only from
  provenance a maintainer can name (`source`, `observed_at`,
  `executor_version`); an empty `source` and a wall of `unknown` is the honest
  state of this table today, not a placeholder to be filled by inference.
* Keys are executor-neutral. `edit_format_support.patch` describes a format,
  not a vendor, so a new profile is a new row rather than a new vocabulary.

Sub-hosts: `omo-runtime` dispatches through a runtime-detected host CLI (pi,
senpi, or opencode). Those are hosts of one profile, not profiles of their
own, so any per-host difference belongs in this row's `host_variants` map and
nowhere else.

This module is unrelated to `executor_capability_snapshots.py`, which records
observed Hermes-native host capabilities (parallel agents, worktree isolation,
visual QA) per executor session. That one is about what a host session did;
this one is about what a dispatch profile's CLI accepts.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Final


EXECUTOR_CAPABILITY_SCHEMA_VERSION: Final = "executor_capability/v1"
# `unsupported` is an observation ("looked, absent"); `unknown` is the absence
# of one. Callers render both; nothing derives a preference from either.
CAPABILITY_STATES: Final = ("supported", "unsupported", "unknown")
EDIT_FORMAT_KEYS: Final = ("hashline", "str_replace", "patch")
EXECUTOR_CAPABILITY_CLAIM_BOUNDARY: Final = (
    "An executor capability row is descriptive metadata about a dispatch profile's declared surface. "
    "It is not a benchmark, not a ranking, and not evidence that any executor did anything."
)
# Runtime-detected hosts of the `omo-runtime` profile. Listed so a host
# variant cannot be invented for a host omh never dispatches through.
CAPABILITY_HOST_VARIANT_KEYS: Final = ("pi", "senpi", "opencode")


def _unresearched_row(profile: str) -> dict[str, Any]:
    """Every cell `unknown`, with provenance saying nobody has looked yet."""
    return {
        "schema_version": EXECUTOR_CAPABILITY_SCHEMA_VERSION,
        "profile": profile,
        "edit_format_support": {name: "unknown" for name in EDIT_FORMAT_KEYS},
        "persistent_eval": "unknown",
        "tool_reentry": "unknown",
        "code_mode_batching": "unknown",
        "host_variants": {},
        "provenance": {"source": "", "observed_at": None, "executor_version": None},
        "claim_boundary": EXECUTOR_CAPABILITY_CLAIM_BOUNDARY,
    }


# Keyed by DISPATCH PROFILE KEY — the same three keys as
# `fanout_dispatch.DISPATCH_COMMAND_TEMPLATES`. A profile with no local spawn
# template has no row here because there is no CLI surface to describe.
#
# Every row is currently unresearched. Filling a cell requires naming the
# source that established it in `provenance`; until then `unknown` is the
# accurate answer and the only permitted one.
_CAPABILITY_TABLE: Final[dict[str, dict[str, Any]]] = {
    "codex": _unresearched_row("codex"),
    "claude-code": _unresearched_row("claude-code"),
    "omo-runtime": _unresearched_row("omo-runtime"),
}

KNOWN_CAPABILITY_PROFILES: Final = tuple(_CAPABILITY_TABLE)


def capability_for_profile(profile_key: str) -> dict[str, Any]:
    """Return the capability row for one dispatch profile.

    Raises `ValueError` naming the profile when it has no row: a caller asking
    about a profile omh cannot spawn is asking a question this table has no
    answer to, and returning an all-`unknown` row would answer it anyway.
    """
    row = _CAPABILITY_TABLE.get(str(profile_key))
    if row is None:
        known = ", ".join(KNOWN_CAPABILITY_PROFILES)
        raise ValueError(f"unknown dispatch profile: {profile_key!r}; known profiles are {known}")
    # Deep copy: the table is module state, and a caller that stamps a row into
    # a summary or a briefing must not be able to edit the shared row.
    return deepcopy(row)


def capability_for_profile_or_none(profile_key: str) -> dict[str, Any] | None:
    """Capability row for a profile, or None when the profile has no row.

    For display surfaces that render whatever profile a session happens to
    carry — including non-spawnable ones like `hermes` or `choose`, where the
    absence of a row is simply nothing to show rather than an error.
    """
    try:
        return capability_for_profile(profile_key)
    except ValueError:
        return None
