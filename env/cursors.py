"""Opaque HMAC-SHA256 signed pagination cursors (REQ-ENV-012)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

from contracts.canonical import canonical_bytes
from env.errors import EnvError


class CursorCodec:
    """Issues and validates tamper-evident opaque cursors bound to query state."""

    def __init__(self, secret_key: bytes) -> None:
        if not isinstance(secret_key, bytes) or len(secret_key) < 16:
            raise ValueError("secret_key must be >= 16 bytes")
        self._key = secret_key

    def _query_hash(self, table: str, filters: dict[str, Any]) -> str:
        return hashlib.sha256(canonical_bytes({"table": table, "filters": filters})).hexdigest()[:16]

    #: Fixed signature width. The token layout is ``sig || raw`` with the
    #: signature occupying the first :data:`_SIG_LEN` bytes, so no byte value
    #: is ever significant as a delimiter. A delimiter-based split is
    #: unsafe here: with 16 random HMAC bytes, ~6% of all tokens contain the
    #: separator byte inside the signature and then fail verification.
    _SIG_LEN = 16

    def encode(self, table: str, filters: dict[str, Any], offset: int) -> str:
        if type(offset) is not int or offset < 0:
            raise EnvError("BAD_CURSOR", "cursor offset must be a non-negative integer")
        payload = {"t": table, "q": self._query_hash(table, filters), "o": offset}
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        sig = hmac.new(self._key, raw, hashlib.sha256).digest()[: self._SIG_LEN]
        return base64.urlsafe_b64encode(sig + raw).decode("ascii")

    def decode(self, token: str, table: str, filters: dict[str, Any]) -> int:
        if not isinstance(token, str) or not token or len(token) > 512:
            raise EnvError("BAD_CURSOR", "cursor must be a non-empty opaque token string")
        try:
            decoded = base64.urlsafe_b64decode(token.encode("ascii"))
        except Exception as exc:
            raise EnvError("BAD_CURSOR", "malformed cursor encoding") from exc
        # Strict canonical encoding: Python's base64 decoder silently ignores
        # trailing garbage, so ``token + "x"`` would otherwise decode to the
        # original bytes and pass every later check. Re-encoding must reproduce
        # the presented token byte for byte, which also rejects alternate
        # alphabets, stray padding and non-canonical trailing bits.
        if base64.urlsafe_b64encode(decoded).decode("ascii") != token:
            raise EnvError("BAD_CURSOR", "cursor is not canonically encoded")
        if len(decoded) <= self._SIG_LEN:
            raise EnvError("BAD_CURSOR", "malformed cursor structure")
        sig, raw = decoded[: self._SIG_LEN], decoded[self._SIG_LEN :]
        expected = hmac.new(self._key, raw, hashlib.sha256).digest()[: self._SIG_LEN]
        if not hmac.compare_digest(sig, expected):
            raise EnvError("BAD_CURSOR", "cursor signature verification failed")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise EnvError("BAD_CURSOR", "corrupted cursor payload") from exc
        if not isinstance(payload, dict):
            raise EnvError("BAD_CURSOR", "invalid cursor payload")
        if payload.get("t") != table or payload.get("q") != self._query_hash(table, filters):
            raise EnvError("BAD_CURSOR", "cursor does not match requested table or filters")
        offset = payload.get("o")
        if type(offset) is not int or offset < 0:
            raise EnvError("BAD_CURSOR", "invalid cursor offset")
        return offset


__all__ = ["CursorCodec"]
