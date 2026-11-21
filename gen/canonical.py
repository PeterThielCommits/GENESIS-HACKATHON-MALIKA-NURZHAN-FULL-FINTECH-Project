"""Canonical JSON serialization per TwinLedger contract 7.2.

Rules (contract 7.2):
  - UTF-8; ensure_ascii=False; sort_keys=True; separators=(",", ":");
  - no NaN/Infinity (floats); Decimal is serialized only in the pre-set
    string format ``f"{value:f}"``;
  - LF string endings; array order is significant (deterministic by the
    caller); object keys sorted.
"""
from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal
from typing import Any


class CanonicalError(ValueError):
    """Raised when a value cannot be canonicalized."""


def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalError("non-finite float is not canonical")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise CanonicalError("non-finite Decimal is not canonical")
        return f"{value:f}"
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    if isinstance(value, dict):
        out = {}
        for key, val in value.items():
            if not isinstance(key, str):
                raise CanonicalError(f"non-string dict key: {key!r}")
            out[key] = _normalize(val)
        return out
    raise CanonicalError(f"unsupported type for canonicalization: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Return the single canonical JSON string for ``value``."""
    try:
        return json.dumps(
            _normalize(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except ValueError as exc:
        raise CanonicalError(f"canonical serialization failed: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    """Canonical UTF-8 bytes."""
    return canonical_json(value).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_canonical(value: Any) -> str:
    """SHA-256 of the canonical bytes of ``value``."""
    return sha256_hex(canonical_bytes(value))
