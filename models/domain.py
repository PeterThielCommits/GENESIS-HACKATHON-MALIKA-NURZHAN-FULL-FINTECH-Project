"""One dataclass per contract schema (11 typed structures).

Field order follows the schema, optional fields default to ``None`` and are omitted from
``to_dict`` when absent. Nested objects stay ``dict`` on purpose: the contract defines them with
inline properties, and re-modelling them here would create a second source of truth. The parity
tool checks names and JSON types, and every valid fixture is round-tripped by the tests.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from models.base import Model


@dataclasses.dataclass
class Company(Model):
    SCHEMA = "company.schema.json"
    REQUIRED = frozenset({"schema_version", "company_id", "legal_name", "name_variants",
                          "jurisdiction_code", "timezone", "functional_currency",
                          "supported_currencies", "fiscal_year_start", "fiscal_period_rule",
                          "accounting_basis", "id_style", "text_profile", "company_size"})

    schema_version: str
    company_id: str
    legal_name: str
    name_variants: dict[str, Any]
    jurisdiction_code: str
    timezone: str
    functional_currency: str
    supported_currencies: list[dict[str, Any]]
    fiscal_year_start: str
    fiscal_period_rule: str
    accounting_basis: dict[str, Any]
    id_style: str
    text_profile: dict[str, Any]
    company_size: str


@dataclasses.dataclass
class Policy(Model):
    SCHEMA = "policy.schema.json"
    REQUIRED = frozenset({"schema_version", "policy_version", "functional_currency", "timezone",
                          "rounding_mode", "fx", "recognition", "allocation", "credit_notes",
                          "tolerance"})

    schema_version: str
    policy_version: str
    functional_currency: str
    timezone: str
    rounding_mode: str
    fx: dict[str, Any]
    recognition: dict[str, Any]
    allocation: dict[str, Any]
    credit_notes: dict[str, Any]
    tolerance: dict[str, Any]


@dataclasses.dataclass
class Finding(Model):
    SCHEMA = "finding.schema.json"
    REQUIRED = frozenset({"type", "affected_ids", "claimed_amount", "currency", "evidence_ids"})

    type: str
    affected_ids: list[str]
    claimed_amount: int
    currency: str
    evidence_ids: list[str]
    schema_version: str | None = None
    explanation: str | None = None
    confidence: float | None = None


@dataclasses.dataclass
class Truth(Model):
    SCHEMA = "truth.schema.json"
    REQUIRED = frozenset({"schema_version", "episode_id", "truth_version", "findings"})

    schema_version: str
    episode_id: str
    truth_version: str
    findings: list[dict[str, Any]]
    episode_public_hash: str | None = None


@dataclasses.dataclass
class ToolRequest(Model):
    SCHEMA = "tool_request.schema.json"
    REQUIRED = frozenset({"schema_version", "request_id", "action"})

    schema_version: str
    request_id: str
    action: dict[str, Any]
    protocol_version: str | None = None


@dataclasses.dataclass
class ToolResponse(Model):
    SCHEMA = "tool_response.schema.json"
    REQUIRED = frozenset({"schema_version", "protocol_version", "request_id", "ok"})

    schema_version: str
    protocol_version: str
    request_id: str
    ok: bool
    result: Any = None
    error: dict[str, Any] | None = None
    info: dict[str, Any] | None = None


@dataclasses.dataclass
class TrajectoryEvent(Model):
    SCHEMA = "trajectory_event.schema.json"
    REQUIRED = frozenset({"schema_version", "protocol_version", "episode_id", "event_index",
                          "logical_step", "kind", "action_digest", "response_digest",
                          "previous_hash", "event_hash"})

    schema_version: str
    protocol_version: str
    episode_id: str
    event_index: int
    logical_step: int
    kind: str
    action_digest: str
    response_digest: str
    previous_hash: str
    event_hash: str


@dataclasses.dataclass
class Receipt(Model):
    SCHEMA = "receipt.schema.json"
    REQUIRED = frozenset({"schema_version", "episode_id", "protocol_version", "code_version_hash",
                          "config_hash", "public_manifest_hash", "truth_commitment",
                          "trajectory_head", "merkle_leaf_index", "policy_identifier",
                          "reward_breakdown_ref", "verification_status"})

    schema_version: str
    episode_id: str
    protocol_version: str
    code_version_hash: str
    config_hash: str
    public_manifest_hash: str
    truth_commitment: str
    trajectory_head: str
    merkle_leaf_index: int
    policy_identifier: str
    reward_breakdown_ref: str
    verification_status: str
    salt_reveal_ref: str | None = None


@dataclasses.dataclass
class VerifierReport(Model):
    SCHEMA = "verifier_report.schema.json"
    REQUIRED = frozenset({"schema_version", "verifier_version", "episode_public_hash",
                          "findings", "examined_public_sources"})

    schema_version: str
    verifier_version: str
    episode_public_hash: str
    examined_public_sources: list[str]
    findings: list[dict[str, Any]]
    proof_graph: dict[str, Any] | None = None
    unresolved_ambiguities: list[str] | None = None
    deterministic_diagnostics: dict[str, Any] | None = None


@dataclasses.dataclass
class RubricCheck(Model):
    SCHEMA = "rubric_check.schema.json"
    REQUIRED = frozenset({"schema_version", "check_id", "block", "title", "official", "status"})

    schema_version: str
    check_id: str
    block: str
    title: str
    official: bool
    status: str
    provisional: bool | None = None
    req_ids: list[str] | None = None
    command: str | None = None
    artifact: str | None = None
    reason: str | None = None
    duration_ms: int | None = None


@dataclasses.dataclass
class EpisodeManifest(Model):
    SCHEMA = "episode_manifest.schema.json"
    REQUIRED = frozenset({"schema_version", "episode_id", "episode_level", "generator_version",
                          "contract_version", "config_hash", "config_refs", "public_files",
                          "public_manifest_hash", "truth_commitment"})

    schema_version: str
    episode_id: str
    episode_level: str
    generator_version: str
    contract_version: str
    config_hash: str
    config_refs: list[str]
    public_files: list[dict[str, Any]]
    public_manifest_hash: str
    truth_commitment: str
    split: str | None = None
    salt_ref: str | None = None
    created_utc: str | None = None


MODELS: dict[str, type[Model]] = {
    "company.schema.json": Company,
    "policy.schema.json": Policy,
    "finding.schema.json": Finding,
    "truth.schema.json": Truth,
    "tool_request.schema.json": ToolRequest,
    "tool_response.schema.json": ToolResponse,
    "trajectory_event.schema.json": TrajectoryEvent,
    "receipt.schema.json": Receipt,
    "verifier_report.schema.json": VerifierReport,
    "rubric_check.schema.json": RubricCheck,
    "episode_manifest.schema.json": EpisodeManifest,
}
