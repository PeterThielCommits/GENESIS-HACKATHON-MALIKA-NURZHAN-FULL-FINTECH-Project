"""Unit tests for TZ §17.6 diagnostic explanation consistency linter."""

from __future__ import annotations

import unittest

from contracts.models import Finding
from scoring.diagnostics import build_diagnostics
from scoring.explanation_linter import lint_findings_explanations
from scoring.matcher import optimal_matching
from scoring.reward import compute_reward


class TestExplanationLinter(unittest.TestCase):
    def _make_finding(self, explanation: str | None) -> Finding:
        kw = dict(
            type="DUPLICATE_PAYMENT",
            affected_ids=("INV:1001", "JE:2001"),
            claimed_amount=125000,
            currency="KZT",
            evidence_ids=("INV:1001", "JE:2001"),
        )
        if explanation is not None:
            kw["explanation"] = explanation
        return Finding(**kw)

    def test_consistent_explanation_passes_all_checks(self) -> None:
        f = self._make_finding(
            "Duplicate posting detected on INV:1001 and JE:2001 for amount 125000 KZT."
        )
        rep = lint_findings_explanations([f])
        self.assertEqual(rep["status"], "EVALUATED")
        self.assertFalse(rep["affects_official_reward"])
        self.assertEqual(rep["consistent_count"], 1)
        self.assertEqual(rep["inconsistent_count"], 0)
        self.assertTrue(rep["all_consistent"])

    def test_contradictory_amount_and_currency_flagged(self) -> None:
        f = self._make_finding("Mismatch on INV:1001 and PAY:9999 for amount 99999 USD.")
        rep = lint_findings_explanations([f])
        self.assertEqual(rep["inconsistent_count"], 1)
        self.assertEqual(rep["consistent_count"], 0)
        item = rep["per_finding"][0]
        self.assertTrue(item["currency_mismatch"])
        self.assertIn("PAY:9999", item["undeclared_ids"])

    def test_empty_or_missing_explanation_is_deterministic_and_non_contradictory(self) -> None:
        f_none = self._make_finding(None)
        rep = lint_findings_explanations([f_none])
        self.assertEqual(rep["consistent_count"], 1)
        self.assertEqual(rep["inconsistent_count"], 0)

    def test_diagnostics_populates_explanation_and_verifier_quality_when_provided(self) -> None:
        f = self._make_finding("Duplicate posting on INV:1001 for amount 125000 KZT")
        lint_rep = lint_findings_explanations([f])
        mr = optimal_matching([f], [])
        rb = compute_reward([f], [], 2, match_result=mr)
        diag = build_diagnostics(
            [f],
            [],
            mr,
            rb,
            run_info={
                "steps_used": 2,
                "explanation_consistency": lint_rep,
                "verifier_quality": {"status": "EVALUATED", "release_blocked": False},
            },
        )
        self.assertEqual(diag["explanation_consistency"]["status"], "EVALUATED")
        self.assertEqual(diag["verifier_quality"]["status"], "EVALUATED")


if __name__ == "__main__":
    unittest.main()
