"""Deterministic trajectory hash chain builder and verifier (Phase 9, Task 9.5).

Implements Master TZ v3.0.0 §16.4 and REQ-PROD-009 / REQ-SEAL-021:
  - Genesis anchor:
      ``h_0 = SHA256("twinledger:h0:v1|" + truth_commitment + "|" + episode_id)``
  - Event transition for ``i = 0 .. N-1``:
      ``h_{i+1} = SHA256(b"twinledger:event:v1|" + h_i.encode("ascii") + b"|" + canonical_bytes(event_i))``
    where ``event_i`` validates against frozen ``contracts/trajectory_event.schema.json``
    and satisfies ``event_i["previous_hash"] == h_i`` and ``event_i["event_index"] == i``.
  - Zero wall-clock timestamps are permitted inside replay-critical
    ``TrajectoryEvent`` records (TZ §16.4).

Imports ONLY ``contracts/`` and Python 3.11 stdlib (obeys ``seal/`` boundary).
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import Any, Sequence

from contracts.canonical import canonical_bytes, sha256_hex
from contracts.loader import validate_instance
from contracts.models import TrajectoryEvent
from contracts.version import PROTOCOL_VERSION

GENESIS_DOMAIN = "twinledger:h0:v1"
EVENT_DOMAIN = "twinledger:event:v1"

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_WALLCLOCK_KEYS = frozenset(
    {
        "timestamp",
        "wall_clock",
        "wall_time",
        "duration_s",
        "elapsed_s",
        "created_at",
        "monotonic_ns",
    }
)


def compute_payload_digest(payload: Any) -> str:
    """Compute canonical SHA-256 hex digest of an action or response payload."""
    return sha256_hex(payload)


def compute_initial_hash(truth_commitment: str, episode_id: str) -> str:
    """Compute initial trajectory chain anchor ``h_0 = SHA256(domain | commitment | episode_id)``."""
    if not isinstance(truth_commitment, str) or not _HEX64_RE.match(truth_commitment):
        raise ValueError("truth_commitment must be a 64-char lowercase hex SHA-256")
    if not isinstance(episode_id, str) or not (1 <= len(episode_id) <= 128):
        raise ValueError("episode_id must be a non-empty string of length <= 128")
    preimage = f"{GENESIS_DOMAIN}|{truth_commitment}|{episode_id}".encode("utf-8")
    return hashlib.sha256(preimage).hexdigest()


def compute_event_hash(previous_hash: str, event: TrajectoryEvent | dict[str, Any]) -> str:
    """Compute next hash ``h_{i+1}`` from ``previous_hash`` and canonical ``event_i``."""
    if not isinstance(previous_hash, str) or not _HEX64_RE.match(previous_hash):
        raise ValueError("previous_hash must be a 64-char lowercase hex SHA-256")
    ev_dict = event.to_dict() if isinstance(event, TrajectoryEvent) else event
    if not isinstance(ev_dict, dict):
        raise ValueError("trajectory event must be a dict or TrajectoryEvent")
    bad_keys = sorted(k for k in ev_dict if k in _FORBIDDEN_WALLCLOCK_KEYS or any(tok in k.lower() for tok in ("wall_clock", "timestamp")))
    if bad_keys:
        raise ValueError(f"wall-clock fields forbidden in TrajectoryEvent: {bad_keys}")
    schema_errs = validate_instance("trajectory_event", ev_dict)
    if schema_errs:
        raise ValueError(f"invalid trajectory_event: {schema_errs[0]}")
    if ev_dict["previous_hash"] != previous_hash:
        raise ValueError(
            f"event[{ev_dict['event_index']}] previous_hash mismatch: "
            f"expected {previous_hash}, got {ev_dict['previous_hash']}"
        )
    prefix = f"{EVENT_DOMAIN}|{previous_hash}|".encode("ascii")
    return hashlib.sha256(prefix + canonical_bytes(ev_dict)).hexdigest()


class HashChainBuilder:
    """Stateful append-only builder producing schema-valid ``TrajectoryEvent`` records."""

    def __init__(
        self,
        *,
        truth_commitment: str,
        episode_id: str,
        protocol_version: str = PROTOCOL_VERSION,
    ) -> None:
        self._truth_commitment = truth_commitment
        self._episode_id = episode_id
        self._protocol_version = protocol_version
        self._initial_hash = compute_initial_hash(truth_commitment, episode_id)
        self._head = self._initial_hash
        self._events: list[TrajectoryEvent] = []

    @property
    def initial_hash(self) -> str:
        return self._initial_hash

    @property
    def head(self) -> str:
        return self._head

    @property
    def events(self) -> tuple[TrajectoryEvent, ...]:
        return tuple(self._events)

    def append(
        self,
        *,
        event_type: str,
        action_payload: Any,
        response_payload: Any,
        logical_step: int,
    ) -> TrajectoryEvent:
        """Append one event and advance ``head``."""
        if self._events and logical_step < self._events[-1].logical_step:
            raise ValueError(
                f"logical_step must be non-decreasing ({logical_step} < {self._events[-1].logical_step})"
            )
        ev = TrajectoryEvent(
            event_index=len(self._events),
            event_type=event_type,
            action_digest=compute_payload_digest(action_payload),
            response_digest=compute_payload_digest(response_payload),
            logical_step=logical_step,
            previous_hash=self._head,
            protocol_version=self._protocol_version,
        )
        ev_dict = ev.to_dict()
        errs = validate_instance("trajectory_event", ev_dict)
        if errs:
            raise ValueError(f"invalid TrajectoryEvent: {errs[0]}")
        self._head = compute_event_hash(self._head, ev_dict)
        self._events.append(ev)
        return ev


@dataclass(frozen=True)
class ChainVerificationResult:
    """Deterministic verification summary for an episode trajectory hash chain."""

    valid: bool
    initial_hash: str
    computed_head: str
    event_count: int
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "initial_hash": self.initial_hash,
            "computed_head": self.computed_head,
            "event_count": self.event_count,
            "errors": list(self.errors),
        }


def verify_hash_chain(
    truth_commitment: str,
    episode_id: str,
    events: Sequence[TrajectoryEvent | dict[str, Any]],
    *,
    expected_head: str | None = None,
) -> ChainVerificationResult:
    """Recompute and validate every link of a trajectory hash chain (REQ-SEAL-021)."""
    try:
        h0 = compute_initial_hash(truth_commitment, episode_id)
    except ValueError as exc:
        return ChainVerificationResult(
            valid=False,
            initial_hash="",
            computed_head="",
            event_count=0,
            errors=(str(exc),),
        )

    errors: list[str] = []
    curr = h0
    last_logical_step = 0

    for idx, raw_ev in enumerate(events):
        ev_dict = raw_ev.to_dict() if isinstance(raw_ev, TrajectoryEvent) else raw_ev
        if not isinstance(ev_dict, dict):
            errors.append(f"events[{idx}]: expected object, got {type(ev_dict).__name__}")
            break

        bad_keys = sorted(
            k for k in ev_dict
            if k in _FORBIDDEN_WALLCLOCK_KEYS or any(tok in k.lower() for tok in ("wall_clock", "timestamp"))
        )
        if bad_keys:
            errors.append(f"events[{idx}]: forbidden wall-clock fields {bad_keys}")
            break

        schema_errs = validate_instance("trajectory_event", ev_dict)
        if schema_errs:
            errors.append(f"events[{idx}]: {schema_errs[0]}")
            break

        if ev_dict["event_index"] != idx:
            errors.append(
                f"events[{idx}]: expected event_index={idx}, got {ev_dict['event_index']}"
            )
            break

        if idx > 0 and ev_dict["logical_step"] < last_logical_step:
            errors.append(
                f"events[{idx}]: logical_step regressed from {last_logical_step} to {ev_dict['logical_step']}"
            )
            break
        last_logical_step = ev_dict["logical_step"]

        if not hmac.compare_digest(ev_dict["previous_hash"], curr):
            errors.append(
                f"events[{idx}]: previous_hash mismatch (expected {curr}, got {ev_dict['previous_hash']})"
            )
            break

        curr = compute_event_hash(curr, ev_dict)

    if not errors and expected_head is not None:
        if not isinstance(expected_head, str) or not _HEX64_RE.match(expected_head):
            errors.append("expected_head is not a valid 64-char lowercase hex SHA-256")
        elif not hmac.compare_digest(curr, expected_head):
            errors.append(
                f"trajectory_head mismatch: expected {expected_head}, recomputed {curr}"
            )

    return ChainVerificationResult(
        valid=len(errors) == 0,
        initial_hash=h0,
        computed_head=curr,
        event_count=len(events),
        errors=tuple(errors),
    )


__all__ = [
    "EVENT_DOMAIN",
    "GENESIS_DOMAIN",
    "ChainVerificationResult",
    "HashChainBuilder",
    "compute_event_hash",
    "compute_initial_hash",
    "compute_payload_digest",
    "verify_hash_chain",
]
