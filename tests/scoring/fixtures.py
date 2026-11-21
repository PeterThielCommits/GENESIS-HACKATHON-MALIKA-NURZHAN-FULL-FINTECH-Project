"""Shared builders for Phase 6 scorer tests.

All fixtures are hand-authored synthetic data (no generator output):
typed IDs of the frozen schemas, exact minor units, explicit evidence
sets. Nothing here reads seeded generator state, so the manual checks
stay independent of later generator phases (D-02-01 tradition).
"""

from __future__ import annotations

from contracts.models import Finding, TruthFinding

CURRENCY = "KZT"


def truth(
    truth_id: str = "T1",
    anomaly_type: str = "DUPLICATE_PAYMENT",
    affected_ids: tuple[str, ...] = ("PAY:001", "PAY:002"),
    amount_minor: int = 50000,
    currency: str = CURRENCY,
    tolerance_minor: int = 0,
    evidence_sets: tuple[tuple[str, ...], ...] | None = None,
    minimal_evidence_size: int | None = None,
    **kwargs,
) -> TruthFinding:
    if evidence_sets is None:
        evidence_sets = (tuple(f"JE:{truth_id.lower()}-{i}" for i in range(2)),)
    if minimal_evidence_size is None:
        minimal_evidence_size = len(evidence_sets[0])
    return TruthFinding(
        truth_id=truth_id,
        type=anomaly_type,
        affected_ids=tuple(affected_ids),
        amount_minor=amount_minor,
        currency=currency,
        tolerance_minor=tolerance_minor,
        evidence_sets=tuple(tuple(s) for s in evidence_sets),
        minimal_evidence_size=minimal_evidence_size,
        invariant_signature=kwargs.pop("invariant_signature", {"INV-BAL": 0}),
        operator_version=kwargs.pop("operator_version", "test-operator@1"),
        **kwargs,
    )


def finding(
    anomaly_type: str = "DUPLICATE_PAYMENT",
    affected_ids: tuple[str, ...] = ("PAY:001", "PAY:002"),
    claimed_amount: int = 50000,
    currency: str = CURRENCY,
    evidence_ids: tuple[str, ...] = ("JE:t1-0", "JE:t1-1"),
    explanation: str = "",
    confidence: float | None = None,
) -> Finding:
    return Finding(
        type=anomaly_type,
        affected_ids=tuple(affected_ids),
        claimed_amount=claimed_amount,
        currency=currency,
        evidence_ids=tuple(evidence_ids),
        explanation=explanation,
        confidence=confidence,
    )


def honest_finding(t: TruthFinding) -> Finding:
    """A perfect submission for one truth: exact type/IDs/amount, full evidence."""
    evidence = tuple(sorted({e for s in t.evidence_sets for e in s}))
    return finding(
        anomaly_type=t.type,
        affected_ids=t.affected_ids,
        claimed_amount=t.amount_minor,
        currency=t.currency,
        evidence_ids=evidence,
    )


def duplicate_payment_truth(truth_id: str = "T-DUP") -> TruthFinding:
    return truth(
        truth_id=truth_id,
        anomaly_type="DUPLICATE_PAYMENT",
        affected_ids=("PAY:001", "PAY:002"),
        amount_minor=50000,
        tolerance_minor=0,
        evidence_sets=(("INV:010", "PAY:001", "PAY:002"),),
    )


def partial_alloc_truth(truth_id: str = "T-PART") -> TruthFinding:
    return truth(
        truth_id=truth_id,
        anomaly_type="PARTIAL_PAYMENT_ALLOCATION",
        affected_ids=("INV:020",),
        amount_minor=30000,
        tolerance_minor=10,
        evidence_sets=(("INV:020", "PAY:030"), ("INV:020", "JE:055")),
    )


def fx_truth(truth_id: str = "T-FX") -> TruthFinding:
    return truth(
        truth_id=truth_id,
        anomaly_type="FX_RATE_MISMATCH",
        affected_ids=("FX:007", "PAY:040"),
        amount_minor=12345,
        currency="USD",
        tolerance_minor=1,
        evidence_sets=(("FX:007", "PAY:040", "JE:060"),),
    )


def cutoff_truth(truth_id: str = "T-CUT") -> TruthFinding:
    return truth(
        truth_id=truth_id,
        anomaly_type="PERIOD_CUTOFF",
        affected_ids=("INV:030",),
        amount_minor=8000,
        tolerance_minor=0,
        evidence_sets=(("INV:030", "JE:070"),),
    )


def two_truth_scenario() -> tuple[TruthFinding, TruthFinding]:
    """The 2-truth scenario used by the TZ 15.6 sanity examples."""
    return duplicate_payment_truth("T1"), partial_alloc_truth("T2")


def flag_all_findings() -> list[Finding]:
    """AT-01 style flag-all: one finding per type with candidate amounts."""
    out: list[Finding] = []
    for anomaly_type in (
        "DUPLICATE_PAYMENT",
        "PARTIAL_PAYMENT_ALLOCATION",
        "FX_RATE_MISMATCH",
        "PERIOD_CUTOFF",
    ):
        for amount in (100, 50000, 30000):
            out.append(
                finding(
                    anomaly_type=anomaly_type,
                    affected_ids=("JE:guess",),
                    claimed_amount=amount,
                    evidence_ids=("JE:guess",),
                )
            )
    return out


def split_findings(t: TruthFinding) -> list[Finding]:
    """Split a true finding into two smaller ones that fail exact checks."""
    half = t.amount_minor // 2
    rest = t.amount_minor - half
    ids = list(t.affected_ids)
    first = finding(
        anomaly_type=t.type,
        affected_ids=(ids[0],),
        claimed_amount=half,
        currency=t.currency,
        evidence_ids=tuple(sorted({e for s in t.evidence_sets for e in s})),
    )
    second = finding(
        anomaly_type=t.type,
        affected_ids=tuple(ids[1:]) or ("JE:rest",),
        claimed_amount=rest,
        currency=t.currency,
        evidence_ids=tuple(sorted({e for s in t.evidence_sets for e in s})),
    )
    return [first, second]
