from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re

from ..local_store import read_json_object
from ..paths import OmhPaths
from .memory import _redact


REJECTED_DECISION_RECALL_SCHEMA_VERSION = "rejected_decision_recall/v1"
REJECTED_DECISION_RECALL_CLAIM_BOUNDARY = (
    "Rejected-decision context is reviewed OMH-local context, not approved memory, Hermes memory, or execution evidence."
)
_ALLOWED_SCOPE_KINDS = frozenset({"project", "target", "thread", "run"})
_SAFE_REF = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")
_TOKEN_RE = re.compile(r"[a-z0-9_/-]+")


@dataclass(frozen=True)
class RejectedDecisionRecallRequest:
    query: str
    scope_kind: str
    scope_ref: str
    tags: tuple[str, ...] = ()
    include_stale: bool = False
    limit: int = 6


@dataclass(frozen=True)
class _RejectedCandidate:
    candidate_id: str
    record_type: str
    summary: str
    rejection_reason: str
    scope_kind: str
    scope_ref: str
    tags: tuple[str, ...]
    reviewed_at: str
    stale: bool
    expired: bool


@dataclass(frozen=True)
class _RejectedDecisionMatch:
    candidate_id: str
    record_type: str
    summary: str
    rejection_reason: str
    scope_kind: str
    scope_ref: str
    tags: tuple[str, ...]
    reviewed_at: str
    stale: bool
    match_score: int

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "record_type": self.record_type,
            "summary": self.summary,
            "rejection_reason": self.rejection_reason,
            "scope": {"kind": self.scope_kind, "ref": self.scope_ref},
            "tags": list(self.tags),
            "reviewed_at": self.reviewed_at,
            "stale": self.stale,
            "match_score": self.match_score,
        }


def build_rejected_decision_recall(paths: OmhPaths, request: RejectedDecisionRecallRequest) -> dict[str, object]:
    scope_kind, scope_ref = _validated_scope(request)
    requested_tags = _normalized_tags(request.tags)
    limit = _validated_limit(request.limit)
    query = str(request.query or "").strip()
    query_tokens = _tokens(query)
    matches: list[_RejectedDecisionMatch] = []
    for candidate in _read_rejected_candidates(paths):
        if (candidate.scope_kind, candidate.scope_ref) != (scope_kind, scope_ref):
            continue
        if candidate.expired or (candidate.stale and not request.include_stale):
            continue
        if not set(requested_tags).issubset(candidate.tags):
            continue
        match_score = _match_score(candidate, query_tokens)
        if query_tokens and match_score == 0:
            continue
        matches.append(
            _RejectedDecisionMatch(
                candidate.candidate_id,
                candidate.record_type,
                candidate.summary,
                candidate.rejection_reason,
                candidate.scope_kind,
                candidate.scope_ref,
                candidate.tags,
                candidate.reviewed_at,
                candidate.stale,
                match_score,
            )
        )
    matches.sort(key=lambda match: match.candidate_id)
    matches.sort(key=lambda match: match.reviewed_at, reverse=True)
    matches.sort(key=lambda match: match.match_score, reverse=True)
    return {
        "schema_version": REJECTED_DECISION_RECALL_SCHEMA_VERSION,
        "query": query,
        "scope": {"kind": scope_kind, "ref": scope_ref},
        "requested_tags": list(requested_tags),
        "include_stale": request.include_stale,
        "limit": limit,
        "matches": [match.to_dict() for match in matches[:limit]],
        "claim_boundary": REJECTED_DECISION_RECALL_CLAIM_BOUNDARY,
    }


def _read_rejected_candidates(paths: OmhPaths) -> tuple[_RejectedCandidate, ...]:
    candidates_dir = paths.memory_dir / "candidates"
    if not candidates_dir.exists():
        return ()
    memory_root = paths.memory_dir.resolve()
    candidates: list[_RejectedCandidate] = []
    for path in sorted(candidates_dir.glob("*.json")):
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(memory_root):
            continue
        candidate = _parse_rejected_candidate(read_json_object(path))
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates)


def _parse_rejected_candidate(raw: object) -> _RejectedCandidate | None:
    if not isinstance(raw, dict) or raw.get("status") != "rejected":
        return None
    candidate_id = _safe_string(raw.get("candidate_id"))
    record_type = _safe_string(raw.get("record_type"))
    summary = _safe_string(raw.get("summary"))
    reviewed_at = _safe_string(raw.get("reviewed_at"))
    scope = raw.get("scope")
    if not candidate_id or not record_type or not summary or not reviewed_at or not isinstance(scope, dict):
        return None
    scope_kind = _safe_string(scope.get("kind"))
    scope_ref = _safe_string(scope.get("ref"))
    if scope_kind not in _ALLOWED_SCOPE_KINDS or not _SAFE_REF.fullmatch(scope_ref):
        return None
    stale, expired = _staleness(raw)
    return _RejectedCandidate(
        candidate_id,
        record_type,
        _redact(summary)[:500],
        _redact(_safe_string(raw.get("rejection_reason")))[:300],
        scope_kind,
        scope_ref,
        _normalized_tags(raw.get("tags")),
        reviewed_at,
        stale,
        expired,
    )


def _staleness(raw: dict[object, object]) -> tuple[bool, bool]:
    now = datetime.now(timezone.utc)
    ttl = raw.get("ttl")
    expires_at = _timestamp(ttl.get("expires_at")) if isinstance(ttl, dict) else None
    if expires_at is not None and expires_at <= now:
        return False, True
    staleness = raw.get("staleness")
    stale_after = _timestamp(staleness.get("stale_after")) if isinstance(staleness, dict) else None
    return stale_after is not None and stale_after <= now, False


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _match_score(candidate: _RejectedCandidate, query_tokens: frozenset[str]) -> int:
    searchable_tokens = _tokens(f"{candidate.summary} {candidate.record_type}")
    tag_tokens = frozenset(tag for tag in candidate.tags)
    return len(query_tokens & searchable_tokens) + len(query_tokens & tag_tokens)


def _validated_scope(request: RejectedDecisionRecallRequest) -> tuple[str, str]:
    if request.scope_kind not in _ALLOWED_SCOPE_KINDS:
        raise ValueError(f"unsupported rejected-decision scope kind: {request.scope_kind}")
    if not _SAFE_REF.fullmatch(request.scope_ref):
        raise ValueError(f"unsafe rejected-decision scope ref: {request.scope_ref!r}")
    return request.scope_kind, request.scope_ref


def _validated_limit(limit: int) -> int:
    if not 1 <= limit <= 20:
        raise ValueError("rejected-decision recall limit must be between 1 and 20")
    return limit


def _normalized_tags(values: object) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)):
        return ()
    tags: list[str] = []
    for value in values:
        tag = str(value).strip().lower()
        if tag and _SAFE_REF.fullmatch(tag) and tag not in tags:
            tags.append(tag)
    return tuple(tags[:12])


def _tokens(value: str) -> frozenset[str]:
    return frozenset(_TOKEN_RE.findall(value.lower()))


def _safe_string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
