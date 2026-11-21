"""Executable sanity examples of Master TZ v3.0.0 section 15.6.

Every numeric example A-J from the specification becomes a test with
the exact expected values at ETA=0.05, max_steps=100. Example B pins
the exact rational R = 391/600 (displayed as 0.6516667).
"""

from __future__ import annotations

import unittest
from fractions import Fraction

from scoring.matcher import optimal_matching
from scoring.reward import (
    ScoringInputError,
    compute_reward,
    f1_score,
    load_scoring_config,
    render_decimal,
)
from tests.scoring import fixtures as fx


class TestRewardSanity(unittest.TestCase):
    """TZ 15.6 examples A-J (provisional formula, A-005)."""

    @classmethod
    def setUpClass(cls):
        cls.config = load_scoring_config()
        cls.t1, cls.t2 = fx.two_truth_scenario()

    def test_a_two_truths_found_40_steps(self):
        findings = [fx.honest_finding(self.t1), fx.honest_finding(self.t2)]
        reward = compute_reward(findings, [self.t1, self.t2], 40, config=self.config)
        self.assertEqual((reward.tp, reward.fp, reward.fn), (2, 0, 0))
        self.assertEqual(reward.f1, Fraction(1))
        self.assertEqual(reward.reward, Fraction(49, 50))  # 0.98
        self.assertEqual(reward.to_dict()["reward_decimal"], "0.9800000")

    def test_b_one_of_two_found_30_steps(self):
        findings = [fx.honest_finding(self.t1)]
        reward = compute_reward(findings, [self.t1, self.t2], 30, config=self.config)
        self.assertEqual((reward.tp, reward.fp, reward.fn), (1, 0, 1))
        self.assertEqual(reward.f1, Fraction(2, 3))
        self.assertEqual(reward.reward, Fraction(391, 600))
        self.assertEqual(render_decimal(reward.reward), "0.6516667")

    def test_c_duplicate_extra_40_steps(self):
        honest = fx.honest_finding(self.t2)
        findings = [fx.honest_finding(self.t1), honest, honest]
        reward = compute_reward(findings, [self.t1, self.t2], 40, config=self.config)
        self.assertEqual((reward.tp, reward.fp, reward.fn), (2, 1, 0))
        self.assertEqual(reward.f1, Fraction(4, 5))  # 0.8
        self.assertEqual(reward.reward, Fraction(39, 50))  # 0.78

    def test_d_clean_book_empty_answer_20_steps(self):
        reward = compute_reward([], [], 20, config=self.config)
        self.assertEqual((reward.tp, reward.fp, reward.fn), (0, 0, 0))
        self.assertEqual(reward.f1, Fraction(1))
        self.assertEqual(reward.reward, Fraction(99, 100))  # 0.99

    def test_e_clean_book_false_finding(self):
        false_finding = fx.finding(
            anomaly_type="DUPLICATE_PAYMENT",
            affected_ids=("PAY:999",),
            claimed_amount=1,
            evidence_ids=("JE:999",),
        )
        reward = compute_reward([false_finding], [], 20, config=self.config)
        self.assertEqual((reward.tp, reward.fp, reward.fn), (0, 1, 0))
        self.assertEqual(reward.f1, Fraction(0))
        self.assertEqual(reward.reward, Fraction(0))

    def test_f_dirty_book_empty_answer(self):
        reward = compute_reward([], [self.t1, self.t2], 20, config=self.config)
        self.assertEqual(reward.recall, Fraction(0))
        self.assertEqual(reward.f1, Fraction(0))
        self.assertEqual(reward.reward, Fraction(0))

    def test_g_truncated_dirty_book_empty_answer(self):
        # Truncation does not change the formula (A-07); F1 stays 0.
        reward = compute_reward([], [self.t1], 100, config=self.config)
        self.assertEqual(reward.f1, Fraction(0))
        self.assertEqual(reward.reward, Fraction(0))

    def test_h_truncated_clean_book_empty_answer(self):
        # Budget exhausted at truncation: steps_used = max_steps = 100.
        reward = compute_reward([], [], 100, config=self.config)
        self.assertEqual(reward.f1, Fraction(1))
        self.assertEqual(reward.reward, Fraction(19, 20))  # 0.95

    def test_i_split_finding_does_not_inflate_tp(self):
        # One true finding split into two smaller ones: neither passes
        # the exact ID/amount check, TP must not artificially grow.
        t = fx.duplicate_payment_truth()
        splits = fx.split_findings(t)
        reward = compute_reward(splits, [t], 40, config=self.config)
        self.assertEqual((reward.tp, reward.fp, reward.fn), (0, 2, 1))
        self.assertLessEqual(reward.tp, 1)

    def test_i_split_with_lucky_half_is_capped(self):
        # Even when one part lands inside tolerance, TP can grow by at
        # most one for one truth (REQ-SCORE-003).
        t = fx.partial_alloc_truth()  # tolerance 10, amount 30000
        lucky = fx.finding(
            anomaly_type=t.type,
            affected_ids=t.affected_ids[:1],
            claimed_amount=t.amount_minor - 5,  # within tolerance
            currency=t.currency,
            evidence_ids=t.evidence_sets[0],
        )
        other = fx.finding(
            anomaly_type=t.type,
            affected_ids=("JE:rest",),
            claimed_amount=1,
            currency=t.currency,
            evidence_ids=t.evidence_sets[0],
        )
        match = optimal_matching([lucky, other], [t])
        self.assertLessEqual(match.tp, 1)

    def test_j_tolerance_boundary(self):
        t = fx.partial_alloc_truth()  # tolerance 10
        at_boundary = fx.finding(
            anomaly_type=t.type,
            affected_ids=t.affected_ids,
            claimed_amount=t.amount_minor + 10,
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
        matched = compute_reward([at_boundary], [t], 10, config=self.config)
        missed = compute_reward([beyond], [t], 10, config=self.config)
        self.assertEqual(matched.tp, 1)
        self.assertEqual(missed.tp, 0)
        self.assertEqual((missed.fp, missed.fn), (1, 1))

    def test_formula_is_exactly_the_documented_one(self):
        findings = [fx.honest_finding(self.t1)]
        reward = compute_reward(findings, [self.t1, self.t2], 30, config=self.config)
        expected = reward.f1 - reward.eta * Fraction(30, 100)
        self.assertEqual(reward.reward, expected)
        self.assertEqual(reward.formula, "R = max(0, F1 - eta * steps_used / max_steps)")
        self.assertTrue(reward.provisional)

    def test_reward_never_negative(self):
        reward = compute_reward([], [self.t1], 100, config=self.config)
        self.assertEqual(reward.reward, Fraction(0))

    def test_steps_out_of_bounds_rejected(self):
        for steps in (-1, 101, True, 1.5, "10"):
            with self.subTest(steps=steps):
                with self.assertRaises(ScoringInputError):
                    compute_reward([], [], steps, config=self.config)  # type: ignore[arg-type]

    def test_f1_special_rules(self):
        self.assertEqual(f1_score(0, 0, 0), Fraction(1))
        self.assertEqual(f1_score(0, 1, 0), Fraction(0))
        self.assertEqual(f1_score(0, 0, 1), Fraction(0))
        self.assertEqual(f1_score(1, 0, 1), Fraction(2, 3))
        self.assertEqual(f1_score(2, 1, 0), Fraction(4, 5))
        with self.assertRaises(ScoringInputError):
            f1_score(-1, 0, 0)


if __name__ == "__main__":
    unittest.main()
