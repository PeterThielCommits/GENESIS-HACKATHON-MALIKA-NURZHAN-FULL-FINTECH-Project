"""Order invariance and tie-break tests (Phase 6 task 6.4).

REQ-SCORE-002: the matcher is deterministic and invariant under
permutation of findings, except that the original index serves only as
the final tie-break. REQ-SCORE-003/004/005 are exercised alongside.
"""

from __future__ import annotations

import itertools
import unittest

from scoring.matcher import MatchResult, optimal_matching, optimal_pairs
from scoring.reward import compute_reward, load_scoring_config
from tests.scoring import fixtures as fx


class TestOrderInvariance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_scoring_config()

    def _assert_counts_invariant(self, findings, truths):
        baseline: MatchResult | None = None
        for perm in itertools.permutations(range(len(findings))):
            ordered = [findings[i] for i in perm]
            result = optimal_matching(ordered, truths)
            if baseline is None:
                baseline = result
            self.assertEqual(
                (result.tp, result.fp, result.fn),
                (baseline.tp, baseline.fp, baseline.fn),
                f"permutation {perm} changed counts",
            )
            reward = compute_reward(ordered, truths, 25, config=self.config)
            self.assertEqual(reward.reward, self.baseline_reward)
        return baseline

    def test_counts_invariant_under_permutations(self):
        t1, t2 = fx.two_truth_scenario()
        findings = [
            fx.honest_finding(t1),
            fx.honest_finding(t2),
            fx.finding(
                anomaly_type="DUPLICATE_PAYMENT",
                affected_ids=("PAY:999",),
                claimed_amount=7,
                evidence_ids=("JE:999",),
            ),
        ]
        self.baseline_reward = compute_reward(findings, [t1, t2], 25, config=self.config).reward
        self._assert_counts_invariant(findings, [t1, t2])

    def test_duplicate_pairing_invariant(self):
        t = fx.duplicate_payment_truth()
        honest = fx.honest_finding(t)
        findings = [honest, honest, honest]
        self.baseline_reward = compute_reward(findings, [t], 25, config=self.config).reward
        self._assert_counts_invariant(findings, [t])

    def test_unique_optimum_pairs_are_permutation_invariant(self):
        # One truth, one matching finding plus noise: the matched pair is
        # the same regardless of input order.
        t = fx.partial_alloc_truth()
        honest = fx.honest_finding(t)
        noise = fx.finding(
            anomaly_type="FX_RATE_MISMATCH",
            affected_ids=("FX:1",),
            claimed_amount=1,
            currency="USD",
            evidence_ids=("FX:1",),
        )
        for perm in itertools.permutations([honest, noise, noise]):
            result = optimal_matching(list(perm), [t])
            matched = result.pairs_by_finding()
            self.assertEqual(result.tp, 1)
            pair = list(matched.values())[0]
            self.assertEqual(pair.truth_id, t.truth_id)
            self.assertEqual(pair.amount_error_minor, 0)


class TestTieBreak(unittest.TestCase):
    def test_lexicographic_pair_tuple(self):
        # Fully symmetric 2x2 with zero errors: the unique lexicographic
        # choice is {(0,0), (1,1)}.
        cost = [[0, 0], [0, 0]]
        self.assertEqual(optimal_pairs(cost), [(0, 0), (1, 1)])

    def test_lexicographic_prefers_smaller_first_pair(self):
        # K=1 with two equally good candidate pairs for finding 0.
        cost = [[5, 5]]
        self.assertEqual(optimal_pairs(cost), [(0, 0)])

    def test_lexicographic_skips_infeasible_small_pair(self):
        # Pair (0,0) exists but using it blocks maximum cardinality;
        # the optimum is {(0,1),(1,0)}.
        cost = [[0, 0], [0, None]]
        self.assertEqual(optimal_pairs(cost), [(0, 1), (1, 0)])

    def test_min_error_dominates_lexicographic(self):
        # (0,0) is lexicographically smaller but has a larger error; the
        # secondary objective wins: {(0,1)} with error 0.
        cost = [[5, 0]]
        self.assertEqual(optimal_pairs(cost), [(0, 1)])

    def test_cardinality_dominates_error(self):
        # Matching both pairs (total error 3) beats one perfect pair.
        cost = [[2, 1], [1, None]]
        pairs = optimal_pairs(cost)
        self.assertEqual(len(pairs), 2)
        self.assertEqual(sum(cost[i][j] for i, j in pairs), 2)  # (0,1)+(1,0)

    def test_deterministic_across_repeats(self):
        cost = [[0, 1, 2], [2, 0, 1], [1, 2, 0]]
        runs = {tuple(optimal_pairs(cost)) for _ in range(10)}
        self.assertEqual(len(runs), 1)

    def test_duplicate_findings_do_not_inflate_tp(self):
        t = fx.duplicate_payment_truth()
        honest = fx.honest_finding(t)
        result = optimal_matching([honest, honest, honest], [t])
        self.assertEqual((result.tp, result.fp, result.fn), (1, 2, 0))

    def test_truth_never_matched_twice(self):
        # Two identical truth records (distinct truth_id) and three
        # identical findings: each truth is used at most once
        # (REQ-SCORE-003).
        t1 = fx.duplicate_payment_truth("T1")
        t2 = fx.duplicate_payment_truth("T2b")
        f = fx.honest_finding(t1)
        result = optimal_matching([f, f, f], [t1, t2])
        self.assertEqual(result.tp, 2)
        matched_truths = [pair.truth_index for pair in result.pairs]
        self.assertEqual(len(matched_truths), len(set(matched_truths)))

    def test_same_pair_same_match_decision(self):
        t = fx.fx_truth()
        f = fx.honest_finding(t)
        result_a = optimal_matching([f], [t])
        result_b = optimal_matching([f], [t])
        self.assertEqual(result_a.pairs, result_b.pairs)

    def test_empty_inputs(self):
        result = optimal_matching([], [])
        self.assertEqual((result.tp, result.fp, result.fn), (0, 0, 0))
        self.assertEqual(optimal_pairs([[None]]), [])


if __name__ == "__main__":
    unittest.main()
