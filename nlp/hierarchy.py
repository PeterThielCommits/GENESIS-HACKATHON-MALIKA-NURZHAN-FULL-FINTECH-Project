"""4-Tier Evidence Hierarchy enforcement (Phase 10, Task 10.5 — Master TZ §17.3).

Hard Benchmark Rule:
  Text similarity or free-text narratives ALONE (Tier 4) are NEVER sufficient
  proof of an accounting anomaly. Any finding claim must be backed by Tier 1
  (exact typed structural link + exact arithmetic/policy check) or Tier 2
  (unique composite structural corroboration across counterparty_id, currency,
  exact minor units, and policy date window).

Two deterministic assessors share one tier vocabulary (no duplicated rules):
  - :func:`assess_evidence_support` — verdict from agent-side investigation
    booleans (public helper for policies / arena consumers);
  - :func:`assess_evidence_reachability` — verdict from structural reachability
    facts only (typed evidence IDs vs. publicly accessible records), used by
    the post-termination scorer diagnostics to enforce "no text-only findings".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence


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


def assess_evidence_reachability(
    *,
    evidence_ids: Iterable[str],
    affected_ids: Iterable[str] = (),
    accessible_public_ids: Iterable[str] | None = None,
) -> EvidenceSupportAssessment:
    """Tier verdict derived from structural reachability facts only (TZ §17.3).

    Deterministic mapping used by the scorer diagnostics (Task 10.5):

    - every evidence ID reachable in public records AND at least one of them is
      an exact typed link to an ``affected_ids`` record  → Tier 1;
    - every evidence ID reachable but no direct affected anchor (composite
      structural corroboration, e.g. bank lines / FX keys)   → Tier 2;
    - some evidence IDs reachable, others not resolvable     → Tier 3
      (alias-style hypothesis: canonical typed IDs must be resolved first);
    - no evidence IDs, or none publicly reachable            → Tier 4
      (text-only / hallucinated support — inadmissible).

    ``accessible_public_ids=None`` disables the reachability check (only the
    affected-anchor test is then applied). This function never inspects free
    text and never performs fuzzy matching.
    """
    ev_list = [str(e) for e in evidence_ids]
    affected = {str(a) for a in affected_ids}
    if not ev_list:
        return EvidenceSupportAssessment(
            strongest_tier=4,
            tier_name=EVIDENCE_TIERS[4],
            admissible_for_submission=False,
            reason="Finding declares no structural evidence IDs: text-only support is forbidden (TZ §17.3).",
        )

    reachable: set[str] = set()
    if accessible_public_ids is not None:
        reachable = {str(a) for a in accessible_public_ids}
        unreachable = sorted(e for e in ev_list if e not in reachable)
    else:
        unreachable = []

    anchored = any(e in affected for e in ev_list)

    if unreachable and len(unreachable) == len(ev_list):
        return EvidenceSupportAssessment(
            strongest_tier=4,
            tier_name=EVIDENCE_TIERS[4],
            admissible_for_submission=False,
            reason=(
                "No declared evidence ID is reachable in public records; free-text similarity "
                f"cannot substitute for structural proof (unreachable: {unreachable[:4]})."
            ),
        )
    if unreachable:
        return EvidenceSupportAssessment(
            strongest_tier=3,
            tier_name=EVIDENCE_TIERS[3],
            admissible_for_submission=False,
            reason=(
                "Mixed structural/alias evidence: unreachable typed IDs must be resolved to "
                f"canonical public records before submission (unresolved: {unreachable[:4]})."
            ),
        )
    if anchored:
        return EvidenceSupportAssessment(
            strongest_tier=1,
            tier_name=EVIDENCE_TIERS[1],
            admissible_for_submission=True,
            reason="Every evidence ID is publicly reachable and at least one is an exact typed link to an affected record.",
        )
    return EvidenceSupportAssessment(
        strongest_tier=2,
        tier_name=EVIDENCE_TIERS[2],
        admissible_for_submission=True,
        reason="Every evidence ID is publicly reachable (composite structural corroboration).",
    )


def build_evidence_hierarchy_report(
    findings: Sequence[Any],
    accessible_public_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Build the diagnostic ``evidence_hierarchy`` block over submitted findings.

    ``findings`` are objects exposing ``affected_ids`` and ``evidence_ids``
    (e.g. ``contracts.models.Finding``) or plain dicts. The result is purely
    diagnostic and NEVER alters matching, F1, or official reward (TZ §15.9).
    """

    def _field(f: Any, name: str) -> tuple[str, ...]:
        if isinstance(f, dict):
            raw = f.get(name) or ()
        else:
            raw = getattr(f, name, ()) or ()
        return tuple(str(x) for x in raw)

    per_finding: list[dict[str, Any]] = []
    for idx, f in enumerate(findings):
        verdict = assess_evidence_reachability(
            evidence_ids=_field(f, "evidence_ids"),
            affected_ids=_field(f, "affected_ids"),
            accessible_public_ids=accessible_public_ids,
        )
        per_finding.append({"finding_index": idx, **verdict.to_dict()})

    admissible_count = sum(1 for item in per_finding if item["admissible_for_submission"])
    total = len(per_finding)
    return {
        "status": "EVALUATED",
        "diagnostic_only": True,
        "affects_official_reward": False,
        "rule": "TZ §17.3: text similarity alone is never sufficient proof; Tier-4 support is inadmissible.",
        "findings_checked": total,
        "admissible_count": admissible_count,
        "inadmissible_count": total - admissible_count,
        "all_admissible": admissible_count == total,
        "per_finding": per_finding,
    }


__all__ = [
    "EVIDENCE_TIERS",
    "EvidenceSupportAssessment",
    "TextOnlyProofRejectedError",
    "assess_evidence_reachability",
    "assess_evidence_support",
    "build_evidence_hierarchy_report",
    "require_structural_proof",
]
