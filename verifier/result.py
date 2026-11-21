"""Result dataclasses and schema serialization for the independent verifier.

Outputs conform strictly to ``contracts/verifier_report.schema.json`` (v1.0.0).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from contracts.canonical import canonicalize, sha256_hex

VERIFIER_VERSION = "1.0.0"
MAX_SCHEMA_EVIDENCE_SETS = 32
MAX_SCHEMA_EVIDENCE_IDS = 20


@dataclass(frozen=True)
class VerifierConfig:
    """Deterministic configuration for verifier discovery."""

    run_ablation: bool = True
    max_evidence_sets: int = MAX_SCHEMA_EVIDENCE_SETS
    include_diagnostics: bool = True


@dataclass(frozen=True)
class VerifierFinding:
    """One independently discovered anomaly finding (TZ 13.3)."""

    type: str
    affected_ids: tuple[str, ...]
    claimed_amount_minor: int
    currency: str
    evidence_sets: tuple[tuple[str, ...], ...]
    explanation_code: str
    proof_graph_ref: str = ""
    evidence_enumeration_complete: bool = True

    @property
    def signature(self) -> tuple[str, tuple[str, ...], int, str]:
        return (
            self.type,
            self.affected_ids,
            self.claimed_amount_minor,
            self.currency,
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.type,
            "affected_ids": list(self.affected_ids),
            "claimed_amount_minor": self.claimed_amount_minor,
            "currency": self.currency,
            "evidence_sets": [list(s) for s in self.evidence_sets],
            "explanation_code": self.explanation_code,
        }
        if self.proof_graph_ref:
            d["proof_graph_ref"] = self.proof_graph_ref
        return d


@dataclass(frozen=True)
class AblationFindingSummary:
    """Ablation minimality & sufficiency outcome for one finding."""

    finding_signature: tuple[str, tuple[str, ...], int, str]
    evidence_sets_checked: int
    all_sufficient: bool
    all_minimal: bool
    full_deletion_breaks_proof: bool
    evidence_enumeration_complete: bool
    failures: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        ftype, affected, amount, currency = self.finding_signature
        return {
            "type": ftype,
            "affected_ids": list(affected),
            "claimed_amount_minor": amount,
            "currency": currency,
            "evidence_sets_checked": self.evidence_sets_checked,
            "all_sufficient": self.all_sufficient,
            "all_minimal": self.all_minimal,
            "full_deletion_breaks_proof": self.full_deletion_breaks_proof,
            "evidence_enumeration_complete": self.evidence_enumeration_complete,
            "failures": list(self.failures),
        }


@dataclass(frozen=True)
class VerifierReport:
    """Discovery report conforming to ``contracts/verifier_report.schema.json``."""

    episode_public_hash: str
    findings: tuple[VerifierFinding, ...]
    examined_public_sources: tuple[str, ...]
    unresolved_ambiguities: tuple[str, ...]
    verifier_version: str = VERIFIER_VERSION
    schema_version: str = "1.0.0"
    deterministic_diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "episode_public_hash": self.episode_public_hash,
            "findings": [f.to_dict() for f in self.findings],
            "examined_public_sources": list(self.examined_public_sources),
            "unresolved_ambiguities": list(self.unresolved_ambiguities),
            "verifier_version": self.verifier_version,
        }
        if self.deterministic_diagnostics:
            d["deterministic_diagnostics"] = canonicalize(self.deterministic_diagnostics)
        return d

    def digest(self) -> str:
        """Canonical SHA-256 of the serialized report (REQ-ORG-003)."""
        return sha256_hex(self.to_dict())


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating a verifier report against public contracts."""

    valid: bool
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "errors": list(self.errors)}


@dataclass(frozen=True)
class DiscoveryOutput:
    """Complete output of Stage 1 public-only discovery."""

    report: VerifierReport
    proof_graph: Any  # verifier.proof_graph.ProofGraph
    report_digest: str
    ablation_results: tuple[AblationFindingSummary, ...] = ()


__all__ = [
    "AblationFindingSummary",
    "DiscoveryOutput",
    "MAX_SCHEMA_EVIDENCE_IDS",
    "MAX_SCHEMA_EVIDENCE_SETS",
    "VERIFIER_VERSION",
    "ValidationResult",
    "VerifierConfig",
    "VerifierFinding",
    "VerifierReport",
]
