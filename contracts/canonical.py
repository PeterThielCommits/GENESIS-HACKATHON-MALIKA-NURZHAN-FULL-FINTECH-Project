"""TwinLedger canonical JSON and hashing primitives.

Implements REQ-CONTRACT-010 .. REQ-CONTRACT-012 and section 7.2 of the
Master TZ (TwinLedger v3.0.0):

  - UTF-8, ensure_ascii=False, sort_keys=True, separators=(",", ":")
  - NaN / Infinity forbidden
  - LF line endings (single trailing LF for byte streams)
  - Money stays integer minor units; Decimal only as pre-formatted string
  - Arrays are significant and deterministic; set-like arrays must be
    sorted by the caller before serialisation (see ``canonicalize``).

This module is stdlib-only and has no dependency on gen/verifier/scoring.
"""

from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal
from typing import Any

CANONICAL_SEPARATORS = (",", ":")


def _reject_non_finite(value: Any) -> None:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON forbids NaN/Infinity")
    elif isinstance(value, dict):
        for v in value.values():
            _reject_non_finite(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _reject_non_finite(v)


def _normalize(value: Any) -> Any:
    """Recursively normalise a value for canonical serialisation.

    - dict keys must be strings (JSON object keys)
    - Decimal is rejected unless the caller already converted it to a
      pre-formatted string (REQ-MONEY-002: never serialise Decimal from float)
    - tuples become lists (JSON arrays)
    """
    if value is None or isinstance(value, (bool, int, str)):
        # bool is subclass of int; keep as-is (JSON true/false)
        if isinstance(value, bool):
            return value
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON forbids NaN/Infinity")
        # Floats are allowed only as a transport type; callers dealing with
        # money must use int minor units. We keep the value but the
        # serialiser will emit it deterministically via json.
        return value
    if isinstance(value, Decimal):
        raise TypeError(
            "Decimal must be converted to a pre-formatted string before "
            "canonical serialisation (REQ-MONEY-002)"
        )
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise TypeError(f"canonical JSON keys must be str, got {type(k).__name__}")
            out[k] = _normalize(v)
        return out
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    raise TypeError(f"unsupported type for canonical JSON: {type(value).__name__}")


def canonicalize(value: Any) -> Any:
    """Return a normalised copy of ``value`` (dicts sorted by key on dump)."""
    _reject_non_finite(value)
    return _normalize(value)


def canonical_json(value: Any) -> str:
    """Serialise ``value`` to a canonical JSON string (no trailing newline)."""
    norm = canonicalize(value)
    return json.dumps(
        norm,
        ensure_ascii=False,
        sort_keys=True,
        separators=CANONICAL_SEPARATORS,
        allow_nan=False,
    )


def canonical_bytes(value: Any) -> bytes:
    """Canonical JSON as UTF-8 bytes with a single trailing LF."""
    return (canonical_json(value) + "\n").encode("utf-8")


def sha256_hex(value: Any) -> str:
    """SHA-256 hex digest of the canonical byte sequence of ``value``."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_bytes(data: bytes) -> str:
    """SHA-256 hex digest of raw bytes (for file / commitment hashing)."""
    return hashlib.sha256(data).hexdigest()


def config_hash(config: dict[str, Any]) -> str:
    """Return the stable config digest, excluding its stored digest field.

    ``config_hash`` is an envelope field, so hashing it would be recursive.
    The digest is SHA-256 over the canonical JSON bytes of all other config
    fields; callers can store the result back as ``config["config_hash"]``.
    """
    if not isinstance(config, dict):
        raise TypeError("config_hash expects a dict")
    payload = {key: value for key, value in config.items() if key != "config_hash"}
    return sha256_hex(payload)


def parse_canonical(text: str | bytes) -> Any:
    """Parse JSON text (tolerant reader; writer is always canonical)."""
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    return json.loads(text)
