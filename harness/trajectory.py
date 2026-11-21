"""Append-only deterministic trajectory recorder for Harness (Phase 9, Task 9.5).

Records replay-critical ``TrajectoryEvent`` chains (validated against frozen
``contracts/trajectory_event.schema.json``) together with exact canonical
action/response JSON payloads for fresh-process replay (TZ §16.4, §16.6).

Uses the exact normative hash-chain specification as ``seal/hashchain.py``:
  - ``h_0 = SHA256("twinledger:h0:v1|" + truth_commitment + "|" + episode_id)``
  - ``h_{i+1} = SHA256(b"twinledger:event:v1|" + h_i.encode("ascii") + b"|" + canonical_bytes(event_i))``

Wall-clock timings are NEVER stored inside ``TrajectoryEvent`` or hashed into
``trajectory_head``; optional wall-clock measurements are written to a separate
diagnostic structure.

Imports ONLY ``contracts/`` and Python 3.11 stdlib (never imports ``seal/``).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from contracts.canonical import canonical_bytes, canonical_json, sha256_hex
from contracts.loader import validate_instance
from contracts.models import TrajectoryEvent
from contracts.version import PROTOCOL_VERSION

GENESIS_DOMAIN = "twinledger:h0:v1"
EVENT_DOMAIN = "twinledger:event:v1"

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def compute_initial_chain_hash(truth_commitment: str, episode_id: str) -> str:
    """Compute genesis trajectory hash ``h_0``."""
    if not isinstance(truth_commitment, str) or not _HEX64_RE.match(truth_commitment):
        raise ValueError("truth_commitment must be a 64-char lowercase hex SHA-256")
    if not isinstance(episode_id, str) or not (1 <= len(episode_id) <= 128):
        raise ValueError("episode_id must be 1..128 chars")
    return hashlib.sha256(
        f"{GENESIS_DOMAIN}|{truth_commitment}|{episode_id}".encode("utf-8")
    ).hexdigest()


def compute_next_chain_hash(previous_hash: str, event_dict: dict[str, Any]) -> str:
    """Advance trajectory hash chain by one schema-validated ``TrajectoryEvent``."""
    errs = validate_instance("trajectory_event", event_dict)
    if errs:
        raise ValueError(f"invalid trajectory_event: {errs[0]}")
    if event_dict["previous_hash"] != previous_hash:
        raise ValueError("previous_hash mismatch in trajectory event")
    prefix = f"{EVENT_DOMAIN}|{previous_hash}|".encode("ascii")
    return hashlib.sha256(prefix + canonical_bytes(event_dict)).hexdigest()


@dataclass(frozen=True)
class RecordedTrajectoryEntry:
    """One deterministic entry in the append-only replay log (zero wall-clock fields)."""

    trajectory_event: TrajectoryEvent
    chain_head_after: str
    canonical_action_json: str
    canonical_response_json: str
    raw_request_line: str | None = None

    def to_jsonl_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema_version": "1.0.0",
            "trajectory_event": self.trajectory_event.to_dict(),
            "chain_head_after": self.chain_head_after,
            "canonical_action_json": self.canonical_action_json,
            "canonical_response_json": self.canonical_response_json,
        }
        if self.raw_request_line is not None:
            d["raw_request_line"] = self.raw_request_line
        return d

    @classmethod
    def from_jsonl_dict(cls, data: dict[str, Any]) -> "RecordedTrajectoryEntry":
        return cls(
            trajectory_event=TrajectoryEvent.from_dict(data["trajectory_event"]),
            chain_head_after=str(data["chain_head_after"]),
            canonical_action_json=str(data["canonical_action_json"]),
            canonical_response_json=str(data["canonical_response_json"]),
            raw_request_line=data.get("raw_request_line"),
        )


class TrajectoryRecorder:
    """Append-only deterministic trajectory builder for one episode run."""

    def __init__(
        self,
        *,
        episode_id: str,
        truth_commitment: str,
        cursor_seed: str = "episode",
        protocol_version: str = PROTOCOL_VERSION,
    ) -> None:
        self._episode_id = episode_id
        self._truth_commitment = truth_commitment
        self._cursor_seed = cursor_seed
        self._protocol_version = protocol_version
        self._initial_hash = compute_initial_chain_hash(truth_commitment, episode_id)
        self._head = self._initial_hash
        self._entries: list[RecordedTrajectoryEntry] = []
        self._diagnostic_timings_ns: list[dict[str, int]] = []

    @property
    def episode_id(self) -> str:
        return self._episode_id

    @property
    def truth_commitment(self) -> str:
        return self._truth_commitment

    @property
    def cursor_seed(self) -> str:
        return self._cursor_seed

    @property
    def initial_hash(self) -> str:
        return self._initial_hash

    @property
    def head(self) -> str:
        return self._head

    @property
    def entries(self) -> tuple[RecordedTrajectoryEntry, ...]:
        return tuple(self._entries)

    @property
    def events(self) -> tuple[TrajectoryEvent, ...]:
        return tuple(e.trajectory_event for e in self._entries)

    def record_event(
        self,
        *,
        event_type: str,
        action_payload: Any,
        response_payload: Any,
        logical_step: int,
        raw_request_line: str | None = None,
        elapsed_ns: int | None = None,
    ) -> RecordedTrajectoryEntry:
        """Append one replay-critical event and advance ``head``."""
        act_json = canonical_json(action_payload)
        resp_json = canonical_json(response_payload)
        ev = TrajectoryEvent(
            event_index=len(self._entries),
            event_type=event_type,
            action_digest=sha256_hex(action_payload),
            response_digest=sha256_hex(response_payload),
            logical_step=logical_step,
            previous_hash=self._head,
            protocol_version=self._protocol_version,
        )
        ev_dict = ev.to_dict()
        new_head = compute_next_chain_hash(self._head, ev_dict)
        entry = RecordedTrajectoryEntry(
            trajectory_event=ev,
            chain_head_after=new_head,
            canonical_action_json=act_json,
            canonical_response_json=resp_json,
            raw_request_line=raw_request_line,
        )
        self._head = new_head
        self._entries.append(entry)
        if elapsed_ns is not None:
            self._diagnostic_timings_ns.append(
                {"event_index": ev.event_index, "elapsed_ns": int(elapsed_ns)}
            )
        return entry

    def write_jsonl(self, path: Path | str) -> None:
        """Write deterministic append-only replay JSONL (zero wall-clock fields)."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        lines = [canonical_json(e.to_jsonl_dict()) for e in self._entries]
        out.write_bytes(("\n".join(lines) + "\n").encode("utf-8") if lines else b"")

    def to_bundle_dict(self) -> dict[str, Any]:
        """Serialize deterministic trajectory bundle (zero wall-clock fields)."""
        return {
            "schema_version": "1.0.0",
            "episode_id": self._episode_id,
            "truth_commitment": self._truth_commitment,
            "cursor_seed": self._cursor_seed,
            "initial_hash": self._initial_hash,
            "trajectory_head": self._head,
            "events": [e.trajectory_event.to_dict() for e in self._entries],
            "entries": [e.to_jsonl_dict() for e in self._entries],
        }

    def diagnostic_timing_log(self) -> dict[str, Any]:
        """Return separate non-replay-critical timing diagnostics (TZ §16.4)."""
        return {
            "episode_id": self._episode_id,
            "note": "Non-deterministic wall-clock diagnostics excluded from trajectory hash chain.",
            "timings": list(self._diagnostic_timings_ns),
        }


def load_recorded_trajectory_jsonl(path: Path | str) -> list[RecordedTrajectoryEntry]:
    """Load recorded trajectory entries from a JSONL file."""
    p = Path(path)
    entries: list[RecordedTrajectoryEntry] = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        entries.append(RecordedTrajectoryEntry.from_jsonl_dict(json.loads(line)))
    return entries


__all__ = [
    "EVENT_DOMAIN",
    "GENESIS_DOMAIN",
    "RecordedTrajectoryEntry",
    "TrajectoryRecorder",
    "compute_initial_chain_hash",
    "compute_next_chain_hash",
    "load_recorded_trajectory_jsonl",
]
