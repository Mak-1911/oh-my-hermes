from __future__ import annotations

import re
import unicodedata

from ..plugin_bundle.omh._governance_safety import classify_memory_admission


MAX_MAPPINGS = 40
MAX_PHRASE_CHARS = 80
MAX_CANONICAL_CHARS = 80
MAX_HINTS = 20
MAPPING_KEYS = {"phrase", "canonical"}
_PROMPTISH_WORDS = {"message", "prompt", "raw", "text", "body", "content", "transcript", "hidden_reasoning"}
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,79}$")
_WORKFLOW_HINT = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,79}$")


def normalize_mappings(mappings: list[tuple[str, str]]) -> list[dict[str, str]]:
    if not isinstance(mappings, list) or not mappings or len(mappings) > MAX_MAPPINGS:
        raise ValueError("invalid_mapping_count")
    seen: set[str] = set()
    normalized: list[dict[str, str]] = []
    for item in mappings:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ValueError("invalid_mapping")
        phrase_value = normalize_phrase(item[0])
        phrase_key = phrase_value.casefold()
        if phrase_key in seen:
            raise ValueError("duplicate_phrase")
        seen.add(phrase_key)
        canonical_value = normalize_vocabulary_identifier(item[1])
        normalized.append({"phrase": phrase_value, "canonical": canonical_value})
    return sorted(normalized, key=lambda item: (item["phrase"].casefold(), item["canonical"]))


def normalize_mappings_from_value(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError("vocabulary_mappings must be a list")
    pairs: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != MAPPING_KEYS:
            raise ValueError("mapping_schema_mismatch")
        phrase = item.get("phrase")
        canonical = item.get("canonical")
        if not isinstance(phrase, str) or not isinstance(canonical, str):
            raise ValueError("invalid_mapping_value")
        pairs.append((phrase, canonical))
    return normalize_mappings(pairs)


def normalize_phrase(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid_phrase")
    _ensure_vocabulary_safe(value)
    phrase = " ".join(unicodedata.normalize("NFKC", value).strip().split())
    if not phrase or len(phrase) > MAX_PHRASE_CHARS:
        raise ValueError("invalid_phrase")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in phrase):
        raise ValueError("phrase_contains_control_character")
    if phrase.lower() in _PROMPTISH_WORDS:
        raise ValueError("promptish_phrase")
    if phrase.lstrip().startswith(("{", "[", "<")):
        raise ValueError("promptish_structured_phrase")
    return phrase


def normalize_vocabulary_identifier(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid_canonical_term")
    normalized = unicodedata.normalize("NFKC", value.strip().lower())
    if not _IDENTIFIER.fullmatch(normalized) or len(normalized) > MAX_CANONICAL_CHARS:
        raise ValueError("invalid_canonical_term")
    _ensure_vocabulary_safe(normalized.replace("-", " "))
    return normalized


def normalize_workflow_hints(values: object) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("workflow_hints must be a list")
    normalized = sorted({_normalize_workflow_hint(value) for value in values})
    if len(normalized) > MAX_HINTS:
        raise ValueError("too_many_workflow_hints")
    return normalized


def _normalize_workflow_hint(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid_workflow_hint")
    normalized = unicodedata.normalize("NFKC", value.strip().lower()).replace(" ", "-")
    if not _WORKFLOW_HINT.fullmatch(normalized):
        raise ValueError("invalid_workflow_hint")
    return normalized


def _ensure_vocabulary_safe(value: str) -> None:
    lowered = value.lower()
    raw_log = any(
        marker in lowered
        for marker in ("traceback (most recent call last)", "\nstderr", "\nstdout", "[error]", "exception:", "raw log", "full log")
    )
    timestamps = len(re.findall(r"^\d{4}-\d{2}-\d{2}[ t]\d{2}:\d{2}:\d{2}", value, flags=re.MULTILINE))
    speakers = len(re.findall(r"^(user|assistant|system|developer|human|agent):", value, flags=re.IGNORECASE | re.MULTILINE))
    transcript = "full transcript" in lowered or "chat transcript" in lowered or speakers >= 4
    if raw_log or timestamps >= 3 or transcript or classify_memory_admission(value).get("status") != "safe":
        raise ValueError("unsafe_domain_vocabulary")
