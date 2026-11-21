"""Typed domain models for TwinLedger contracts (Phase 1).

Lightweight dataclasses with ``to_dict`` / ``from_dict`` round-trips.
Validation is delegated to :mod:`contracts.validate` via
:mod:`contracts.loader` (single source of truth = JSON schemas).
Money is always ``int`` minor units (REQ-MONEY-001).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from contracts.loader import validate_instance

ANOMALY_TYPES = (
    "DUPLICATE_PAYMENT",
    "PARTIAL_PAYMENT_ALLOCATION",
    "FX_RATE_MISMATCH",
    "PERIOD_CUTOFF",
)

TOOLS = ("list_records", "get_record", "get_document", "calc", "submit")

ERROR_CODES = (
    "UNKNOWN_TOOL", "BAD_ARGS", "BAD_FILTER", "BAD_CURSOR", "NOT_FOUND",
    "BAD_FINDING", "CALC_ERROR", "LIMIT", "TERMINATED",
    "ALREADY_SUBMITTED", "INTERNAL",
)


def _require_valid(contract: str, data: dict[str, Any]) -> None:
    errors = validate_instance(contract, data)
    if errors:
        raise ValueError(f"invalid {contract}: {errors}")


@dataclass(frozen=True)
class Finding:
    type: str
    affected_ids: tuple[str, ...]
    claimed_amount: int
    currency: str
    evidence_ids: tuple[str, ...]
    explanation: str = ""
    confidence: float | None = None
    schema_version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "type": self.type,
            "affected_ids": list(self.affected_ids),
            "claimed_amount": self.claimed_amount,
            "currency": self.currency,
            "evidence_ids": list(self.evidence_ids),
        }
        if self.explanation:
            d["explanation"] = self.explanation
        if self.confidence is not None:
            d["confidence"] = self.confidence
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Finding":
        _require_valid("finding", data)
        return cls(
            type=data["type"],
            affected_ids=tuple(data["affected_ids"]),
            claimed_amount=data["claimed_amount"],
            currency=data["currency"],
            evidence_ids=tuple(data["evidence_ids"]),
            explanation=data.get("explanation", ""),
            confidence=data.get("confidence"),
            schema_version=data.get("schema_version", "1.0.0"),
        )

    def validate(self) -> None:
        _require_valid("finding", self.to_dict())


@dataclass(frozen=True)
class ToolRequest:
    request_id: str
    tool: str
    args: dict[str, Any]
    protocol_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "action": {"tool": self.tool, "args": dict(self.args)},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolRequest":
        _require_valid("tool_request", data)
        action = data["action"]
        return cls(
            request_id=data["request_id"],
            tool=action["tool"],
            args=dict(action["args"]),
            protocol_version=data.get("protocol_version", "1.0"),
        )


@dataclass(frozen=True)
class ToolResponse:
    request_id: str
    ok: bool
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    protocol_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "ok": self.ok,
        }
        if self.ok:
            d["result"] = dict(self.result) if self.result is not None else None
            d["error"] = None
        else:
            d["result"] = None
            d["error"] = {
                "code": self.error_code or "INTERNAL",
                "message": self.error_message or "internal error",
            }
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolResponse":
        _require_valid("tool_response", data)
        err = data.get("error")
        return cls(
            request_id=data["request_id"],
            ok=data["ok"],
            result=data.get("result"),
            error_code=err["code"] if err else None,
            error_message=err["message"] if err else None,
            protocol_version=data.get("protocol_version", "1.0"),
        )


@dataclass(frozen=True)
class TrajectoryEvent:
    event_index: int
    event_type: str
    action_digest: str
    response_digest: str
    logical_step: int
    previous_hash: str
    protocol_version: str = "1.0"
    schema_version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_index": self.event_index,
            "event_type": self.event_type,
            "action_digest": self.action_digest,
            "response_digest": self.response_digest,
            "protocol_version": self.protocol_version,
            "logical_step": self.logical_step,
            "previous_hash": self.previous_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrajectoryEvent":
        _require_valid("trajectory_event", data)
        return cls(
            event_index=data["event_index"],
            event_type=data["event_type"],
            action_digest=data["action_digest"],
            response_digest=data["response_digest"],
            logical_step=data["logical_step"],
            previous_hash=data["previous_hash"],
            protocol_version=data.get("protocol_version", "1.0"),
            schema_version=data.get("schema_version", "1.0.0"),
        )


@dataclass(frozen=True)
class Receipt:
    episode_id: str
    code_version_hash: str
    config_hash: str
    public_manifest_hash: str
    truth_commitment: str
    trajectory_head: str
    merkle_leaf_index: int
    policy_identifier: str
    verification_status: str = "PENDING"
    protocol_version: str = "1.0"
    schema_version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "protocol_version": self.protocol_version,
            "code_version_hash": self.code_version_hash,
            "config_hash": self.config_hash,
            "public_manifest_hash": self.public_manifest_hash,
            "truth_commitment": self.truth_commitment,
            "trajectory_head": self.trajectory_head,
            "merkle_leaf_index": self.merkle_leaf_index,
            "policy_identifier": self.policy_identifier,
            "verification_status": self.verification_status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Receipt":
        _require_valid("receipt", data)
        return cls(
            episode_id=data["episode_id"],
            code_version_hash=data["code_version_hash"],
            config_hash=data["config_hash"],
            public_manifest_hash=data["public_manifest_hash"],
            truth_commitment=data["truth_commitment"],
            trajectory_head=data["trajectory_head"],
            merkle_leaf_index=data["merkle_leaf_index"],
            policy_identifier=data["policy_identifier"],
            verification_status=data.get("verification_status", "PENDING"),
            protocol_version=data.get("protocol_version", "1.0"),
            schema_version=data.get("schema_version", "1.0.0"),
        )


@dataclass(frozen=True)
class TruthFinding:
    truth_id: str
    type: str
    affected_ids: tuple[str, ...]
    amount_minor: int
    currency: str
    tolerance_minor: int
    evidence_sets: tuple[tuple[str, ...], ...]
    minimal_evidence_size: int
    invariant_signature: dict[str, Any]
    operator_version: str
    evidence_enumeration_complete: bool = True
    optimal_steps_model_id: str = ""
    optimal_steps: int | None = None
    depends_on: tuple[str, ...] = ()
    schema_version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "truth_id": self.truth_id,
            "type": self.type,
            "affected_ids": list(self.affected_ids),
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "tolerance_minor": self.tolerance_minor,
            "evidence_sets": [list(s) for s in self.evidence_sets],
            "minimal_evidence_size": self.minimal_evidence_size,
            "invariant_signature": dict(self.invariant_signature),
            "operator_version": self.operator_version,
        }
        d["evidence_enumeration_complete"] = self.evidence_enumeration_complete
        if self.optimal_steps_model_id:
            d["optimal_steps_model_id"] = self.optimal_steps_model_id
        if self.optimal_steps is not None:
            d["optimal_steps"] = self.optimal_steps
        if self.depends_on:
            d["depends_on"] = list(self.depends_on)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TruthFinding":
        _require_valid("truth", data)
        return cls(
            truth_id=data["truth_id"],
            type=data["type"],
            affected_ids=tuple(data["affected_ids"]),
            amount_minor=data["amount_minor"],
            currency=data["currency"],
            tolerance_minor=data["tolerance_minor"],
            evidence_sets=tuple(tuple(s) for s in data["evidence_sets"]),
            minimal_evidence_size=data["minimal_evidence_size"],
            invariant_signature=dict(data["invariant_signature"]),
            operator_version=data["operator_version"],
            evidence_enumeration_complete=data.get("evidence_enumeration_complete", True),
            optimal_steps_model_id=data.get("optimal_steps_model_id", ""),
            optimal_steps=data.get("optimal_steps"),
            depends_on=tuple(data.get("depends_on", ())),
            schema_version=data.get("schema_version", "1.0.0"),
        )


def canonical_ids(ids: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Canonicalise typed IDs: NFC-normalise, sort, dedupe (TZ 15.1)."""
    import unicodedata

    normed = [unicodedata.normalize("NFC", i) for i in ids]
    return tuple(sorted(set(normed)))


__all__ = [
    "ANOMALY_TYPES", "TOOLS", "ERROR_CODES",
    "Finding", "ToolRequest", "ToolResponse", "TrajectoryEvent",
    "Receipt", "TruthFinding", "canonical_ids",
]
