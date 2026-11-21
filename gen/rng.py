"""Namespaced RNG service (contract 10.1; REQ-GEN-001..006).

One master seed spawns isolated per-namespace streams. A stream seed is
SHA-256(canonical([namespace, master_seed])) fed into ``random.Random``.

Rules implemented:
  - REQ-GEN-001: no global random anywhere; every draw uses an explicit
    NamespacedRNG instance injected via dependency injection;
  - REQ-GEN-002: streams are isolated by namespace and master seed;
  - interleaving streams cannot change any stream's output sequence.
"""
from __future__ import annotations

import random
from typing import Any, Sequence

from gen.canonical import sha256_canonical


class NamespacedRNG:
    """An isolated random stream addressable by namespace and master seed."""

    __slots__ = ("namespace", "master_seed", "_rng")

    def __init__(self, namespace: str, master_seed: int):
        if not isinstance(namespace, str) or not namespace:
            raise ValueError("namespace must be a non-empty string")
        if isinstance(master_seed, bool) or not isinstance(master_seed, int):
            raise ValueError("master_seed must be an int")
        digest = sha256_canonical(["random-stream", namespace, master_seed])
        self._rng = random.Random(digest)
        self.namespace = namespace
        self.master_seed = master_seed

    # --- core draws -----------------------------------------------------
    def randint(self, a: int, b: int) -> int:
        if a > b:
            raise ValueError(f"empty range: {a} > {b}")
        return self._rng.randrange(a, b + 1)

    def random(self) -> float:
        return self._rng.random()

    def uniform(self, a: float, b: float) -> float:
        return self._rng.uniform(a, b)

    def getrandbits(self, k: int) -> int:
        return self._rng.getrandbits(k)

    def choice(self, seq: Sequence[Any]) -> Any:
        items = list(seq)
        if not items:
            raise ValueError("cannot choose from an empty sequence")
        return self._rng.choice(items)

    def sample(self, population: Sequence[Any], k: int) -> list[Any]:
        items = list(population)
        if k > len(items):
            raise ValueError("sample larger than population")
        return self._rng.sample(items, k)

    def shuffle(self, seq: list[Any]) -> list[Any]:
        self._rng.shuffle(seq)
        return seq


def make_stream(namespace: str, master_seed: int) -> NamespacedRNG:
    """Create a new namespaced stream for ``namespace`` + ``master_seed``."""
    return NamespacedRNG(namespace, master_seed)
