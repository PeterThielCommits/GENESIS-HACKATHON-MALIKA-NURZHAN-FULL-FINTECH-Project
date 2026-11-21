"""Stage-2 independent crosscheck of a VerifierReport against sealed truth.

Implements Master TZ sections 13.2, 13.3, and 13.7 (REQ-ORG-003,
REQ-VER-020..022):

  - Strictly separated from Stage-1 public discovery: accepts only a
    serialized ``verifier_report`` dict conforming to
    ``contracts/verifier_report.schema.json`` and canonical
    :class:`TruthFinding` records;
  - Verifies the pre-committed ``report_digest`` (SHA-256 of canonical
    report JSON) BEFORE comparing against truth (REQ-ORG-003);
  - Delegates TP/FP/FN to :func:`scoring.matcher.optimal_matching`
    (REQ-SCORE-001) without importing ``verifier/`` or ``gen/``;
  - Computes every TZ 13.7 verifier quality metric in exact rational
    arithmetic and blocks release on any mismatch, insufficient evidence,
    ablation failure, or unresolved ambiguity (REQ-VER-020).

Dependencies: ``contracts`` + ``scoring`` + Python 3.11 stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Sequence

from contracts.canonical import canonicalize, sha256_hex
from contracts.loader import validate_instance
from contracts.models import Finding, TruthFinding
from scoring.canon import (
    ScoringInputError,
    canonical_id_set,
    validate_truths,
)
from scoring.matcher import MatchResult, optimal_matching
from scoring.reward import f1_score, precision_score, recall_score, render_decimal


class CrosscheckError(ScoringInputError):
    """Raised when Stage-2 crosscheck inputs violate contract or digest rules."""


@dataclass(frozen=True)
class CrosscheckReport:
    """Audit artifact for Stage-2 verifier-vs-truth comparison (REQ-VER-022)."""

    episode_public_hash: str
    verifier_report_hash: str
    truth_set_hash: str
    verifier_version: str
    tp: int
    fp: int
    fn: int
    precision: Fraction
    recall: Fraction
    f1: Fraction
    exact_affected_id_accuracy: Fraction
    amount_exact_accuracy: Fraction
    amount_tolerance_accuracy: Fraction
    evidence_sufficiency_rate: Fraction
    evidence_minimality_rate: Fraction | None
    distractor_false_positive_rate: Fraction
    unresolved_ambiguity_count: int
    release_blocked: bool
    blocking_reasons: tuple[str, ...]
    unmatched_verifier_indices: tuple[int, ...]
    unmatched_truth_ids: tuple[str, ...]
    crosscheck_hash: str

    def to_dict(self) -> dict[str, Any]:
        def _metric(val: Fraction) -> dict[str, str]:
            return {"exact": str(val), "decimal": render_decimal(val)}

        minimality_field: dict[str, Any]
        if self.evidence_minimality_rate is None:
            minimality_field = {"status": "NOT_RUN", "exact": None, "decimal": None}
        else:
            minimality_field = {
                "status": "EVALUATED",
                **_metric(self.evidence_minimality_rate),
            }

        return {
            "schema_version": "1.0.0",
            "episode_public_hash": self.episode_public_hash,
            "verifier_report_hash": self.verifier_report_hash,
            "truth_set_hash": self.truth_set_hash,
            "verifier_version": self.verifier_version,
            "counts": {"tp": self.tp, "fp": self.fp, "fn": self.fn},
            "metrics": {
                "precision": _metric(self.precision),
                "recall": _metric(self.recall),
                "f1": _metric(self.f1),
                "exact_affected_id_accuracy": _metric(self.exact_affected_id_accuracy),
                "amount_exact_accuracy": _metric(self.amount_exact_accuracy),
                "amount_tolerance_accuracy": _metric(self.amount_tolerance_accuracy),
                "evidence_sufficiency_rate": _metric(self.evidence_sufficiency_rate),
                "evidence_minimality_rate": minimality_field,
                "distractor_false_positive_rate": _metric(self.distractor_false_positive_rate),
                "unresolved_ambiguity_count": self.unresolved_ambiguity_count,
            },
            "release_blocked": self.release_blocked,
            "blocking_reasons": list(self.blocking_reasons),
            "unmatched_verifier_indices": list(self.unmatched_verifier_indices),
            "unmatched_truth_ids": list(self.unmatched_truth_ids),
            "crosscheck_hash": self.crosscheck_hash,
        }


def _select_representative_evidence_set(
    vf: dict[str, Any],
    canon_truths: Sequence[TruthFinding],
) -> tuple[str, ...]:
    """Select one concrete verifier evidence set without taking a cross-set union."""
    raw_sets = [canonical_id_set(s) for s in vf["evidence_sets"]]
    vf_type = str(vf["type"])
    vf_affected = canonical_id_set(vf["affected_ids"])
    vf_currency = str(vf["currency"])

    for truth in canon_truths:
        if (
            truth.type == vf_type
            and truth.affected_ids == vf_affected
            and truth.currency == vf_currency
        ):
            for cand_set in raw_sets:
                cand_fs = set(cand_set)
                if any(set(ts).issubset(cand_fs) for ts in truth.evidence_sets):
                    return cand_set
    return raw_sets[0]


def _all_sets_sufficient_for_truth(
    vf: dict[str, Any],
    truth: TruthFinding,
) -> bool:
    """Return True iff EVERY evidence set emitted by verifier satisfies truth."""
    for raw_set in vf["evidence_sets"]:
        cand_fs = set(canonical_id_set(raw_set))
        if not any(set(ts).issubset(cand_fs) for ts in truth.evidence_sets):
            return False
    return True


def _extract_minimality_rate(
    verifier_report: dict[str, Any],
    findings_count: int,
) -> tuple[Fraction | None, list[str]]:
    """Read ablation minimality metrics from deterministic diagnostics if run."""
    diag = verifier_report.get("deterministic_diagnostics")
    if not isinstance(diag, dict) or not diag.get("ablation_run"):
        return None, []

    ablation = diag.get("ablation_summary")
    if not isinstance(ablation, dict):
        return None, []

    details = ablation.get("details", [])
    if findings_count == 0 and not details:
        return Fraction(1), []
    if not details:
        return Fraction(0), ["ablation_run=True but no ablation details recorded"]

    passed = 0
    reasons: list[str] = []
    for idx, item in enumerate(details):
        ok = (
            bool(item.get("all_sufficient"))
            and bool(item.get("all_minimal"))
            and bool(item.get("full_deletion_breaks_proof"))
        )
        if ok:
            passed += 1
        else:
            reasons.append(
                f"ablation failed for finding[{idx}]: {item.get('failures', [])}"
            )
    return Fraction(passed, len(details)), reasons


def crosscheck(
    verifier_report: dict[str, Any],
    truth_findings: Sequence[TruthFinding],
    *,
    expected_report_digest: str | None = None,
    distractor_count: int = 0,
) -> CrosscheckReport:
    """Compare a frozen Stage-1 ``verifier_report`` against sealed truths.

    Enforces REQ-ORG-003 (digest lock before comparison) and REQ-VER-020
    (any mismatch, insufficient evidence, ablation failure, or unresolved
    ambiguity blocks episode release).
    """
    if not isinstance(verifier_report, dict):
        raise CrosscheckError("verifier_report must be a dict")
    if type(distractor_count) is not int or distractor_count < 0:
        raise CrosscheckError("distractor_count must be a non-negative int")

    schema_errors = validate_instance("verifier_report", verifier_report)
    if schema_errors:
        raise CrosscheckError(
            f"verifier_report violates frozen schema: {'; '.join(schema_errors)}"
        )

    report_hash = sha256_hex(verifier_report)
    if expected_report_digest is not None and report_hash != expected_report_digest:
        raise CrosscheckError(
            f"verifier_report digest mismatch: expected {expected_report_digest}, "
            f"got {report_hash} (REQ-ORG-003)"
        )

    canon_truths = validate_truths(truth_findings)
    truth_hash = sha256_hex([canonicalize(t.to_dict()) for t in canon_truths])

    raw_findings = list(verifier_report.get("findings", ()))
    converted: list[Finding] = []
    for vf in raw_findings:
        rep_ev = _select_representative_evidence_set(vf, canon_truths)
        converted.append(
            Finding(
                type=str(vf["type"]),
                affected_ids=canonical_id_set(vf["affected_ids"]),
                claimed_amount=int(vf["claimed_amount_minor"]),
                currency=str(vf["currency"]),
                evidence_ids=rep_ev,
                explanation=str(vf["explanation_code"]),
            )
        )

    match_res: MatchResult = optimal_matching(converted, canon_truths)
    precision = precision_score(match_res.tp, match_res.fp)
    recall = recall_score(match_res.tp, match_res.fn)
    f1 = f1_score(match_res.tp, match_res.fp, match_res.fn)

    n_truths = len(canon_truths)
    exact_amount_matches = sum(1 for p in match_res.pairs if p.amount_error_minor == 0)
    sufficient_matches = sum(
        1
        for p in match_res.pairs
        if _all_sets_sufficient_for_truth(raw_findings[p.finding_index], canon_truths[p.truth_index])
    )

    if n_truths > 0:
        exact_affected_acc = Fraction(match_res.tp, n_truths)
        amount_exact_acc = Fraction(exact_amount_matches, n_truths)
        amount_tol_acc = Fraction(match_res.tp, n_truths)
    else:
        clean_ok = Fraction(1) if match_res.fp == 0 else Fraction(0)
        exact_affected_acc = clean_ok
        amount_exact_acc = clean_ok
        amount_tol_acc = clean_ok

    if match_res.tp > 0:
        ev_sufficiency_rate = Fraction(sufficient_matches, match_res.tp)
    else:
        ev_sufficiency_rate = Fraction(1) if (match_res.fp == 0 and match_res.fn == 0) else Fraction(0)

    ev_minimality_rate, ablation_reasons = _extract_minimality_rate(
        verifier_report, len(raw_findings)
    )

    if distractor_count > 0:
        distractor_fp_rate = Fraction(match_res.fp, distractor_count)
    else:
        distractor_fp_rate = Fraction(0) if match_res.fp == 0 else Fraction(1)

    ambiguities = list(verifier_report.get("unresolved_ambiguities", ()))
    amb_count = len(ambiguities)

    blocking_reasons: list[str] = []
    if match_res.fp > 0:
        blocking_reasons.append(f"false positives detected: fp={match_res.fp}")
    if match_res.fn > 0:
        blocking_reasons.append(f"missed truth findings: fn={match_res.fn}")
    if amb_count > 0:
        blocking_reasons.append(f"unresolved ambiguities present: count={amb_count}")
    if ev_sufficiency_rate < 1:
        blocking_reasons.append(
            f"evidence sufficiency below 1.0: {ev_sufficiency_rate}"
        )
    if ev_minimality_rate is not None and ev_minimality_rate < 1:
        blocking_reasons.extend(ablation_reasons or [f"evidence minimality below 1.0: {ev_minimality_rate}"])

    unmatched_truth_ids = tuple(
        canon_truths[j].truth_id for j in match_res.unmatched_truths
    )

    hash_payload = {
        "episode_public_hash": verifier_report["episode_public_hash"],
        "verifier_report_hash": report_hash,
        "truth_set_hash": truth_hash,
        "tp": match_res.tp,
        "fp": match_res.fp,
        "fn": match_res.fn,
        "release_blocked": bool(blocking_reasons),
        "blocking_reasons": blocking_reasons,
    }
    crosscheck_digest = sha256_hex(hash_payload)

    return CrosscheckReport(
        episode_public_hash=str(verifier_report["episode_public_hash"]),
        verifier_report_hash=report_hash,
        truth_set_hash=truth_hash,
        verifier_version=str(verifier_report["verifier_version"]),
        tp=match_res.tp,
        fp=match_res.fp,
        fn=match_res.fn,
        precision=precision,
        recall=recall,
        f1=f1,
        exact_affected_id_accuracy=exact_affected_acc,
        amount_exact_accuracy=amount_exact_acc,
        amount_tolerance_accuracy=amount_tol_acc,
        evidence_sufficiency_rate=ev_sufficiency_rate,
        evidence_minimality_rate=ev_minimality_rate,
        distractor_false_positive_rate=distractor_fp_rate,
        unresolved_ambiguity_count=amb_count,
        release_blocked=bool(blocking_reasons),
        blocking_reasons=tuple(blocking_reasons),
        unmatched_verifier_indices=match_res.unmatched_findings,
        unmatched_truth_ids=unmatched_truth_ids,
        crosscheck_hash=crosscheck_digest,
    )


__all__ = [
    "CrosscheckError",
    "CrosscheckReport",
    "crosscheck",
]
