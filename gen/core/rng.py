"""Addressable, isolated RNG streams (REQ-GEN-001..006, 10.1).

A stream is derived from ``SHA-256(master_seed || namespace)`` and materialised
as a dedicated ``random.Random`` instance. No component ever touches the global
``random`` module, and adding a new namespace cannot perturb existing streams —
which is what makes "adding an operator never changes the clean twin" testable.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Final, Iterable

from contracts.errors import ConfigError

STREAM_SEPARATOR: Final[str] = "\x1f"
RESERVED_NAMESPACES: Final[tuple[str, ...]] = (
    "company",
    "chart",
    "counterparties",
    "policy",
    "text",
    "ids",
)


def _derive_seed(master_seed: str, namespace: str) -> int:
    if not master_seed or not isinstance(master_seed, str):
        raise ConfigError("master_seed must be a non-empty string")
    payload = f"{namespace}{STREAM_SEPARATOR}{master_seed}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


@dataclass
class RngService:
    """Factory of independent RNG streams for one master seed."""

    master_seed: str
    _streams: dict[str, RngStream] = field(default_factory=dict, init=False)
    _created_order: list[str] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.master_seed, str) or not self.master_seed:
            raise ConfigError("master_seed must be a non-empty string")
        self.seed_digest = hashlib.sha256(
            self.master_seed.encode("utf-8")
        ).hexdigest()

    def stream(self, namespace: str) -> "RngStream":
        """Return (creating on first use) the isolated stream for ``namespace``."""
        if not isinstance(namespace, str) or not namespace:
            raise ConfigError("namespace must be a non-empty string")
        if namespace.startswith("/") or namespace.endswith("/") or "//" in namespace:
            raise ConfigError("namespace must not start or end with '/'", namespace=namespace)
        stream = self._streams.get(namespace)
        if stream is None:
            stream = RngStream(
                namespace=namespace,
                seed=_derive_seed(self.master_seed, namespace),
            )
            self._streams[namespace] = stream
            self._created_order.append(namespace)
        return stream

    def namespaces(self) -> tuple[str, ...]:
        return tuple(self._created_order)

    def reset(self, namespace: str) -> "RngStream":
        """Re-create a stream from scratch (used by tests and reject sampling)."""
        self._streams.pop(namespace, None)
        if namespace in self._created_order:
            self._created_order.remove(namespace)
        return self.stream(namespace)

    def fork(self, namespace: str, discriminator: str) -> "RngStream":
        """Derive a child stream so retries never advance a parent stream."""
        return self.stream(f"{namespace}#{discriminator}")


@dataclass
class RngStream:
    """A single isolated deterministic random stream."""

    namespace: str
    seed: int
    _random: random.Random | None = field(default=None, init=False, repr=False)

    @property
    def random(self) -> random.Random:
        if self._random is None:
            self._random = random.Random(self.seed)
        return self._random

    # -- typed helpers that keep call sites explicit and testable -------------
    def randint(self, low: int, high: int) -> int:
        if low > high:
            raise ConfigError("randint bounds inverted", low=low, high=high)
        return self.random.randint(low, high)

    def choice(self, items: Iterable[object]) -> object:
        pool = list(items)
        if not pool:
            raise ConfigError("cannot choose from an empty pool", namespace=self.namespace)
        return pool[self.random.randrange(len(pool))]

    def choices_weighted(self, options: dict[str, int]) -> str:
        if not options:
            raise ConfigError("cannot choose from empty weighted options")
        total = sum(options.values())
        if total <= 0:
            raise ConfigError("weighted options must sum to a positive value")
        ticket = self.random.randrange(total)
        cumulative = 0
        for key, weight in options.items():
            cumulative += weight
            if ticket < cumulative:
                return key
        return next(reversed(options))  # pragma: no cover - defensive

    def ratio_hit(self, bps: int) -> bool:
        """True with probability ``bps/10000`` (integer arithmetic, no floats)."""
        if not 0 <= bps <= 10000:
            raise ConfigError("ratio must be 0..10000", bps=bps)
        return self.random.randrange(10000) < bps

    def shuffled(self, items: Iterable[object]) -> list[object]:
        pool = list(items)
        self.random.shuffle(pool)
        return pool

    def state(self) -> tuple:
        return self.random.getstate()

    def restore(self, state: tuple) -> None:
        self.random.setstate(state)
