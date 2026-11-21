"""4-Tier Evidence Hierarchy enforcement (Phase 10 — TZ §11.3).

Hard Benchmark Rule:
  Text similarity or free-text narratives ALONE (Tier 4) are NEVER sufficient
  proof of an accounting anomaly. Any finding claim must be backed by Tier 1
  (exact typed structural link + exact arithmetic/policy check) or Tier 2
  (unique composite structural corroboration across counterparty_id, currency,
  exact minor units, and policy date window).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class TextOnlyProofRejectedError(ValueError):
    """Raised when a caller attempts to promote Tier-4 text similarity as sole proof."""


EVIDENCE_TIERS: dict[int, str] = {
    1: "TIER_1_EXACT_TYPED_LINK",
    2: "TIER_2_COMPOSITE_STRUCTURAL",
    3: "TIER_3_ALIAS_PLUS_STRUCTURAL",
    4: "TIER_4_TEXT_SIMILARITY_ONLY",
}


@dataclass(frozen=True)
class EvidenceSupportAssessment:
    """Deterministic assessment of whether candidate evidence satisfies TZ §11.3."""

    strongest_tier: int
    tier_name: str
    admissible_for_submission: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "strongest_tier": self.strongest_tier,
            "tier_name": self.tier_name,
            "admissible_for_submission": self.admissible_for_submission,
            "reason": self.reason,
        }


def assess_evidence_support(
    *,
    has_exact_typed_fk: bool = False,
    has_exact_amount_and_currency: bool = False,
    has_policy_rule_violation: bool = False,
    has_counterparty_id_match: bool = False,
    has_alias_match: bool = False,
    text_similarity_bps: int = 0,
) -> EvidenceSupportAssessment:
    """Evaluate evidence strength under the TZ §11.3 4-tier hierarchy."""
    if has_exact_typed_fk and (has_exact_amount_and_currency or has_policy_rule_violation):
        return EvidenceSupportAssessment(
            strongest_tier=1,
            tier_name=EVIDENCE_TIERS[1],
            admissible_for_submission=True,
            reason="Exact typed foreign-key link corroborated by deterministic arithmetic/policy check.",
        )

    if has_counterparty_id_match and has_exact_amount_and_currency and has_policy_rule_violation:
        return EvidenceSupportAssessment(
            strongest_tier=2,
            tier_name=EVIDENCE_TIERS[2],
            admissible_for_submission=True,
            reason="Composite structural match (counterparty_id + exact minor amount + policy violation).",
        )

    if has_alias_match and has_exact_amount_and_currency and has_policy_rule_violation:
        return EvidenceSupportAssessment(
            strongest_tier=3,
            tier_name=EVIDENCE_TIERS[3],
            admissible_for_submission=False,
            reason="Alias + structural hypothesis requires resolving canonical typed IDs before submission.",
        )

    return EvidenceSupportAssessment(
        strongest_tier=4,
        tier_name=EVIDENCE_TIERS[4],
        admissible_for_submission=False,
        reason=(
            f"Text similarity alone ({text_similarity_bps} bps) is forbidden as proof of an accounting discrepancy."
        ),
    )


def require_structural_proof(assessment: EvidenceSupportAssessment) -> None:
    """Raise ``TextOnlyProofRejectedError`` unless Tier-1 or Tier-2 proof is present."""
    if not assessment.admissible_for_submission:
        raise TextOnlyProofRejectedError(assessment.reason)


__all__ = [
    "EVIDENCE_TIERS",
    "EvidenceSupportAssessment",
    "TextOnlyProofRejectedError",
    "assess_evidence_support",
    "require_structural_proof",
]
