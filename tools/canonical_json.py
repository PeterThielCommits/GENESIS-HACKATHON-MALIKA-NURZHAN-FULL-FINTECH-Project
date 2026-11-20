"""Canonical JSON for TwinLedger (REQ-CONTRACT-010..012, master spec §7.2).

This module is deliberately small, pure stdlib and dependency-free: it is the single
definition of "canonical bytes" used by contract digests, episode manifests, truth
commitments, trajectory hash chains and replay comparisons.

Rules (normative, see contracts/CONTRACT.md §Canonical JSON):

* UTF-8 output, ``ensure_ascii=False``;
* object keys sorted by Unicode code point (``sort_keys=True``);
* separators ``("," , ":")`` - no insignificant whitespace;
* ``NaN``, ``Infinity`` and ``-Infinity`` are rejected;
* ``float`` is rejected outright: money is integer minor units and rates are strings,
  so a float in canonical output would silently lose precision (REQ-MONEY-001/002);
* ``Decimal`` is serialized as a plain decimal string (never exponent notation),
  because JSON has no decimal type and the string form is stable and exact;
* line endings are LF and a single trailing newline is *not* implied by this function -
  callers that write files decide, and the digest always covers exactly these bytes.

The pure canonicalization function must be deterministic across processes: it performs
no I/O, has no randomness and no locale/timezone dependency.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

__all__ = [
    "CanonicalJSONError",
    "canonical_json",
    "canonical_bytes",
    "sha256_hex",
    "canonical_digest",
    "load_canonical",
]

_MAX_DEPTH = 64


class CanonicalJSONError(ValueError):
    """Raised when a value cannot be canonicalized without ambiguity."""


def _normalize(value: Any, depth: int = 0) -> Any:
    """Return a JSON-safe structure with floats rejected and Decimals stringified."""
    if depth > _MAX_DEPTH:
        raise CanonicalJSONError(f"nesting deeper than {_MAX_DEPTH} levels is not canonicalizable")
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise CanonicalJSONError(
            "float is forbidden in canonical JSON (use integer minor units or a decimal string)"
        )
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise CanonicalJSONError("non-finite Decimal is forbidden")
        return format(value, "f")
    if isinstance(value, (list, tuple)):
        return [_normalize(item, depth + 1) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalJSONError(f"object keys must be strings, got {type(key).__name__}")
            normalized[key] = _normalize(item, depth + 1)
        return normalized
    raise CanonicalJSONError(f"type {type(value).__name__} has no canonical JSON form")


def canonical_json(value: Any) -> str:
    """Serialize ``value`` to its unique canonical JSON text."""
    normalized = _normalize(value)
    try:
        return json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise CanonicalJSONError(str(exc)) from exc


def canonical_bytes(value: Any) -> bytes:
    """Canonical UTF-8 bytes, LF-normalized (``\\r`` may only appear inside strings)."""
    return canonical_json(value).encode("utf-8")


def sha256_hex(data: bytes | str) -> str:
    """Lower-case hex SHA-256 of bytes or of canonical JSON text."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical_digest(value: Any) -> str:
    """SHA-256 over the canonical bytes of ``value`` (domain-separated by the tag below)."""
    return sha256_hex(canonical_bytes(value))


def load_canonical(raw: str) -> Any:
    """Parse JSON text strictly, rejecting NaN/Infinity and duplicate keys.

    Duplicate keys are rejected because ``{"a":1,"a":2}`` has no single canonical form.
    """
    def _no_constants(token: str) -> Any:
        raise CanonicalJSONError(f"non-finite constant {token!r} is forbidden")

    def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, item in pairs:
            if key in out:
                raise CanonicalJSONError(f"duplicate object key {key!r}")
            out[key] = item
        return out

    return json.loads(raw, parse_constant=_no_constants, object_pairs_hook=_pairs)
