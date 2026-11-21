"""Match predicate tests (Phase 6 task 6.3, TZ 15.2).

Covers all six conditions, tolerance boundaries (example J), currency /
ID / evidence mismatches, alternative evidence sets, supersets and the
rule that explanation/confidence never influence matching
(REQ-SCORE-005).
"""

from __future__ import annotations

import unittest

from scoring.matcher import (
    REASON_AMOUNT,
    REASON_AFFECTED,
    REASON_CURRENCY,
    REASON_EVIDENCE,
    REASON_OK,
    REASON_TYPE,
    match_predicate,
)
from tests.scoring import fixtures as fx


class TestMatchPredicate(unittest.TestCase):
    def test_full_match(self):
        t = fx.duplicate_payment_truth()
        f = fx.honest_finding(t)
        decision = match_predicate(f, t)
        self.assertTrue(decision.matched)
        self.assertEqual(decision.reason, REASON_OK)
        self.assertEqual(decision.amount_error_minor, 0)

    def test_type_mismatch(self):
        t = fx.duplicate_payment_truth()
        f = fx.honest_finding(t)
        other = fx.finding(
            anomaly_type="PERIOD_CUTOFF",
            affected_ids=f.affected_ids,
            claimed_amount=f.claimed_amount,
            currency=f.currency,
            evidence_ids=f.evidence_ids,
        )
        decision = match_predicate(other, t)
        self.assertFalse(decision.matched)
        self.assertEqual(decision.reason, REASON_TYPE)

    def test_affected_ids_mismatch(self):
        t = fx.duplicate_payment_truth()
        f = fx.honest_finding(t)
        other = fx.finding(
            anomaly_type=t.type,
            affected_ids=("PAY:001",),
            claimed_amount=f.claimed_amount,
            currency=f.currency,
            evidence_ids=f.evidence_ids,
        )
        decision = match_predicate(other, t)
        self.assertFalse(decision.matched)
        self.assertEqual(decision.reason, REASON_AFFECTED)

    def test_affected_ids_order_and_dupes_do_not_matter(self):
        t = fx.duplicate_payment_truth()
        f = fx.finding(
            anomaly_type=t.type,
            affected_ids=("PAY:002", "PAY:001", "PAY:002"),
            claimed_amount=t.amount_minor,
            currency=t.currency,
            evidence_ids=t.evidence_sets[0],
        )
        self.assertTrue(match_predicate(f, t).matched)

    def test_currency_mismatch(self):
        t = fx.fx_truth()  # USD
        f = fx.finding(
            anomaly_type=t.type,
            affected_ids=t.affected_ids,
            claimed_amount=t.amount_minor,
            currency="KZT",
            evidence_ids=t.evidence_sets[0],
        )
        decision = match_predicate(f, t)
        self.assertFalse(decision.matched)
        self.assertEqual(decision.reason, REASON_CURRENCY)

    def test_amount_within_tolerance_matches(self):
        t = fx.partial_alloc_truth()  # tolerance 10
        f = fx.finding(
            anomaly_type=t.type,
            affected_ids=t.affected_ids,
            claimed_amount=t.amount_minor + 10,
            currency=t.currency,
            evidence_ids=t.evidence_sets[0],
        )
        decision = match_predicate(f, t)
        self.assertTrue(decision.matched)
        self.assertEqual(decision.amount_error_minor, 10)

    def test_amount_at_exact_boundary(self):
        # Example J: at the tolerance boundary matches; one unit beyond
        # does not.
        t = fx.partial_alloc_truth()  # tolerance 10
        at_boundary = fx.finding(
            anomaly_type=t.type,
            affected_ids=t.affected_ids,
            claimed_amount=t.amount_minor - 10,
            currency=t.currency,
            evidence_ids=t.evidence_sets[0],
        )
        beyond = fx.finding(
            anomaly_type=t.type,
            affected_ids=t.affected_ids,
            claimed_amount=t.amount_minor + 11,
            currency=t.currency,
            evidence_ids=t.evidence_sets[0],
        )
        self.assertTrue(match_predicate(at_boundary, t).matched)
        decision = match_predicate(beyond, t)
        self.assertFalse(decision.matched)
        self.assertEqual(decision.reason, REASON_AMOUNT)
        self.assertEqual(decision.amount_error_minor, 11)

    def test_zero_tolerance_exact_only(self):
        t = fx.duplicate_payment_truth()  # tolerance 0
        f = fx.finding(
            anomaly_type=t.type,
            affected_ids=t.affected_ids,
            claimed_amount=t.amount_minor + 1,
            currency=t.currency,
            evidence_ids=t.evidence_sets[0],
        )
        self.assertFalse(match_predicate(f, t).matched)

    def test_evidence_superset_matches(self):
        t = fx.duplicate_payment_truth()
        f = fx.finding(
            anomaly_type=t.type,
            affected_ids=t.affected_ids,
            claimed_amount=t.amount_minor,
            currency=t.currency,
            evidence_ids=t.evidence_sets[0] + ("JE:extra", "JE:more"),
        )
        decision = match_predicate(f, t)
        self.assertTrue(decision.matched)
        self.assertEqual(decision.reason, REASON_OK)

    def test_evidence_partial_set_fails(self):
        t = fx.duplicate_payment_truth()
        partial = tuple(t.evidence_sets[0][:-1])
        f = fx.finding(
            anomaly_type=t.type,
            affected_ids=t.affected_ids,
            claimed_amount=t.amount_minor,
            currency=t.currency,
            evidence_ids=partial + ("JE:unrelated",),
        )
        decision = match_predicate(f, t)
        self.assertFalse(decision.matched)
        self.assertEqual(decision.reason, REASON_EVIDENCE)

    def test_alternative_evidence_sets(self):
        t = fx.partial_alloc_truth()  # two acceptable sets
        second_set = t.evidence_sets[1]
        f = fx.finding(
            anomaly_type=t.type,
            affected_ids=t.affected_ids,
            claimed_amount=t.amount_minor,
            currency=t.currency,
            evidence_ids=second_set + ("JE:extra",),
        )
        self.assertTrue(match_predicate(f, t).matched)

    def test_mix_across_alternative_sets_fails(self):
        t = fx.partial_alloc_truth()
        # One element from each alternative set completes neither.
        mixed = (t.evidence_sets[0][1], t.evidence_sets[1][1])
        f = fx.finding(
            anomaly_type=t.type,
            affected_ids=t.affected_ids,
            claimed_amount=t.amount_minor,
            currency=t.currency,
            evidence_ids=mixed,
        )
        decision = match_predicate(f, t)
        self.assertFalse(decision.matched)
        self.assertEqual(decision.reason, REASON_EVIDENCE)

    def test_explanation_and_confidence_do_not_matter(self):
        t = fx.duplicate_payment_truth()
        base = fx.honest_finding(t)
        verbose = fx.finding(
            anomaly_type=base.type,
            affected_ids=base.affected_ids,
            claimed_amount=base.claimed_amount,
            currency=base.currency,
            evidence_ids=base.evidence_ids,
            explanation="A very long, eloquent explanation with keywords.",
            confidence=0.99,
        )
        silent = fx.finding(
            anomaly_type=base.type,
            affected_ids=base.affected_ids,
            claimed_amount=base.claimed_amount,
            currency=base.currency,
            evidence_ids=base.evidence_ids,
        )
        self.assertEqual(
            match_predicate(verbose, t), match_predicate(silent, t)
        )

    def test_pure_function_same_pair_same_result(self):
        t = fx.fx_truth()
        f = fx.honest_finding(t)
        results = {match_predicate(f, t) for _ in range(5)}
        self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
