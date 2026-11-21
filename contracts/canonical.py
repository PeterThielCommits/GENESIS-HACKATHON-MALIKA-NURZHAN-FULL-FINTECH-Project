"""Canonical JSON and deterministic hashing (REQ-CONTRACT-010..012).

Rules (frozen, see contracts/version.json):
  * UTF-8, ``ensure_ascii=False``, ``sort_keys=True``, separators ``(",", ":")``;
  * ``NaN``/``Infinity`` are rejected (``allow_nan=False``);
  * ``float`` is rejected outright: money is integer minor units and exact rates
    are strings parsed into ``Decimal`` (REQ-MONEY-002);
  * ``Decimal`` is rejected in canonical payloads: callers must convert to ``str``
    (rates) or ``int`` (minor units) explicitly, so the wire format stays stable;
  * dataclasses/tuples are normalised before serialisation.

A single object therefore has exactly one canonical byte sequence.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from contracts.errors import ContractError

CANONICAL_VERSION = "1.0.0"


def _normalise(value: Any, path: str = "$") -> Any:
    """Convert ``value`` into a canonical-JSON-compatible structure."""
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractError(
                    "canonical JSON requires string keys", path=path, key=repr(key)
                )
            out[key] = _normalise(item, f"{path}.{key}")
        return out
    if isinstance(value, (set, frozenset)):
        # Sets are unordered: sort their canonical rendering to keep determinism.
        rendered = [_normalise(item, path) for item in value]
        return sorted(rendered, key=lambda item: canonical_json(item))
    if isinstance(value, (list, tuple)):
        return [_normalise(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _normalise(dataclasses.asdict(value), path)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise ContractError(
            "float is forbidden in canonical payloads", path=path, value=repr(value)
        )
    if isinstance(value, Decimal):
        raise ContractError(
            "Decimal must be serialised explicitly as str or int", path=path
        )
    if isinstance(value, str):
        if "\r" in value:
            raise ContractError("CR characters are forbidden (LF only)", path=path)
        return value
    raise ContractError(
        "unsupported type in canonical payload", path=path, type=type(value).__name__
    )


def canonical_json(value: Any) -> str:
    """Return the canonical JSON text for ``value`` (single byte sequence)."""
    normalised = _normalise(value)
    try:
        return json.dumps(
            normalised,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise ContractError("value is not canonically serialisable", reason=str(exc))


def canonical_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def digest_of(value: Any) -> str:
    """SHA-256 of the canonical form of ``value``."""
    return sha256_hex(canonical_bytes(value))


def canonical_jsonl(records: Sequence[Any]) -> str:
    """One canonical JSON object per line, LF terminated, records pre-sorted."""
    if not records:
        return ""
    lines = [canonical_json(record) for record in records]
    return "\n".join(lines) + "\n"


def freeze(value: Any) -> Any:
    """Recursively freeze JSON-like data into an immutable structure."""
    if isinstance(value, Mapping):
        from types import MappingProxyType

        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise ContractError(
        "unsupported type for freeze", type=type(value).__name__
    )


def thaw(value: Any) -> Any:
    """Recursively copy a frozen structure back into plain mutable containers."""
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    return value
