"""Deterministic SHA-256 scoped RNG derivation for TwinLedger generation.

No global RNG state, no wall-clock time, no PID, no Python hash randomization.
Every sub-stream is derived strictly from ``(master_seed, scope...)``.
"""

from __future__ import annotations

import hashlib
import random
from typing import Any


def derive_bytes(master_seed: int, *scope: Any, length: int = 32) -> bytes:
    """Derive deterministic bytes from ``(master_seed, *scope)`` via SHA-256."""
    if type(master_seed) is not int or isinstance(master_seed, bool):
        raise ValueError("master_seed must be an int")
    if length < 1 or length > 64:
        raise ValueError("length must be in 1..64")
    h = hashlib.sha256()
    h.update(f"twinledger-v3|seed={master_seed}".encode("utf-8"))
    for part in scope:
        h.update(b"|")
        h.update(str(part).encode("utf-8"))
    digest = h.digest()
    if length <= 32:
        return digest[:length]
    h2 = hashlib.sha256(digest + b"|ext").digest()
    return (digest + h2)[:length]


def derive_seed(master_seed: int, *scope: Any) -> int:
    """Derive a deterministic 64-bit integer seed for a named scope."""
    return int.from_bytes(derive_bytes(master_seed, *scope, length=8), "big")


def scoped_rng(master_seed: int, *scope: Any) -> random.Random:
    """Return an isolated ``random.Random`` seeded deterministically for scope."""
    return random.Random(derive_seed(master_seed, *scope))


__all__ = ["derive_bytes", "derive_seed", "scoped_rng"]
