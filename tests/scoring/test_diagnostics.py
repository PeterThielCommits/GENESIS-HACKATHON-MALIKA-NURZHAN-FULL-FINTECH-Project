"""Diagnostics tests (Phase 6, TZ 15.8-15.9).

Covers the diagnostics payload: counts and breakdowns, evidence
coverage, truncated/no-submit flags with honest audit status, per-type
results, explicit NOT_AVAILABLE markers for later phases, and the
experimental grounded score as a separate column that never feeds the
reward.
"""

from __future__ import annotations

import unittest
from fractions import Fraction

from scoring.diagnostics import (
    DIAGNOSTICS_SCHEMA,
    build_diagnostics,
)
from scoring.matcher import optimal_matching
from scoring.reward import compute_reward, load_scoring_config
from tests.scoring import fixtures as fx


class TestDiagnostics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_scoring_config()
        cls.t = fx.duplicate_payment_truth("T-DUP")
        cls.honest = fx.honest_finding(cls.t)
        cls.result = optimal_matching([cls.honest], [cls.t])
        cls.reward = compute_reward(
            [cls.honest], [cls.t], 30, config=cls.config, match_result=cls.result
        )

    def test_core_fields(self):
        diagnostics = build_diagnostics([self.honest], [self.t], self.result, self.reward)
        self.assertEqual(diagnostics["schema"], DIAGNOSTICS_SCHEMA)
        self.assertEqual(diagnostics["audit_status"], "OK")
        self.assertEqual(diagnostics["counts"]["tp"], 1)
        self.assertEqual(diagnostics["f1"]["exact"], "1")
        self.assertEqual(diagnostics["reward"]["reward_exact"], "47/50")
        self.assertEqual(diagnostics["steps_used"], 30)

    def test_matches_and_evidence_coverage(self):
        diagnostics = build_diagnostics([self.honest], [self.t], self.result, self.reward)
        self.assertEqual(len(diagnostics["matches"]), 1)
        match = diagnostics["matches"][0]
        self.assertTrue(match["exact_amount"])
        self.assertEqual(match["amount_error_minor"], 0)
        self.assertEqual(match["evidence_set"], list(self.t.evidence_sets[0]))
        coverage = diagnostics["evidence_coverage"]
        self.assertEqual(coverage["matched_with_minimal_set"], 1)

    def test_truncated_no_submit_flagged(self):
        empty_result = optimal_matching([], [self.t])
        empty_reward = compute_reward(
            [], [self.t], 100, config=self.config, match_result=empty_result
        )
        diagnostics = build_diagnostics(
            [], [self.t], empty_result, empty_reward,
            run_info={"truncated": True, "no_submit": True},
        )
        self.assertEqual(diagnostics["audit_status"], "TRUNCATED_NO_SUBMIT")
        self.assertTrue(diagnostics["flags"]["truncated"])
        self.assertNotEqual(diagnostics["audit_status"], "OK")

    def test_clean_book_truncated_never_called_success(self):
        empty_result = optimal_matching([], [])
        empty_reward = compute_reward(
            [], [], 100, config=self.config, match_result=empty_result
        )
        diagnostics = build_diagnostics(
            [], [], empty_result, empty_reward,
            run_info={"truncated": True, "no_submit": True},
        )
        # Example H re-based on the official formula (BUG-TL-0001):
        # F1=1, inspection_steps=100 -> 2*1-1-0.2 = 0.80, and the status
        # must still mark truncation, never a successful audit.
        self.assertEqual(diagnostics["f1"]["exact"], "1")
        self.assertEqual(diagnostics["reward"]["reward_exact"], "4/5")
        self.assertEqual(diagnostics["audit_status"], "TRUNCATED_NO_SUBMIT")

    def test_not_available_markers_are_explicit(self):
        diagnostics = build_diagnostics([self.honest], [self.t], self.result, self.reward)
        self.assertEqual(diagnostics["explanation_consistency"]["status"], "NOT_AVAILABLE")
        self.assertEqual(diagnostics["verifier_quality"]["status"], "NOT_AVAILABLE")

    def test_per_type_breakdown(self):
        t2 = fx.fx_truth("T-FX")
        findings = [self.honest, fx.honest_finding(t2)]
        result = optimal_matching(findings, [self.t, t2])
        reward = compute_reward(
            findings, [self.t, t2], 10, config=self.config, match_result=result
        )
        diagnostics = build_diagnostics(findings, [self.t, t2], result, reward)
        self.assertIn("DUPLICATE_PAYMENT", diagnostics["per_type"])
        self.assertIn("FX_RATE_MISMATCH", diagnostics["per_type"])
        self.assertEqual(diagnostics["per_type"]["DUPLICATE_PAYMENT"]["tp"], 1)

    def test_experimental_requires_requested_evidence(self):
        diagnostics = build_diagnostics([self.honest], [self.t], self.result, self.reward)
        experimental = diagnostics["experimental"]
        self.assertEqual(experimental["status"], "NOT_RUN")
        self.assertIsNone(experimental["experimental_grounded_score"])

    def test_experimental_grounded_score_is_separate_column(self):
        requested = list(self.t.evidence_sets[0])  # policy queried the evidence
        diagnostics = build_diagnostics(
            [self.honest], [self.t], self.result, self.reward,
            run_info={"requested_evidence_ids": requested},
        )
        experimental = diagnostics["experimental"]
        self.assertEqual(experimental["status"], "EXPERIMENTAL")
        self.assertEqual(experimental["experimental_grounded_score"]["exact"], "1")
        self.assertIn("never part of the official reward", experimental["note"])
        # The official reward field is untouched by the experiment.
        self.assertEqual(diagnostics["reward"]["reward_exact"], "47/50")

    def test_experimental_downgrades_unrequested_evidence(self):
        diagnostics = build_diagnostics(
            [self.honest], [self.t], self.result, self.reward,
            run_info={"requested_evidence_ids": ["JE:unrelated"]},
        )
        experimental = diagnostics["experimental"]
        self.assertEqual(experimental["grounded_tp"], 0)
        self.assertEqual(Fraction(experimental["experimental_grounded_score"]["exact"]), Fraction(0))
        # Official reward still counts the match.
        self.assertEqual(diagnostics["counts"]["tp"], 1)

    def test_optimal_steps_reported_when_declared(self):
        t = fx.truth(
            truth_id="T-OPT",
            optimal_steps_model_id="model-x",
            optimal_steps=12,
        )
        f = fx.honest_finding(t)
        result = optimal_matching([f], [t])
        reward = compute_reward([f], [t], 30, config=self.config, match_result=result)
        diagnostics = build_diagnostics([f], [t], result, reward)
        self.assertEqual(diagnostics["optimal_steps"]["declared_optimal_steps_sum"], 12)
        self.assertEqual(diagnostics["optimal_steps"]["steps_used"], 30)

    def test_diagnostics_is_json_friendly(self):
        import json

        diagnostics = build_diagnostics([self.honest], [self.t], self.result, self.reward)
        json.dumps(diagnostics)


if __name__ == "__main__":
    unittest.main()
