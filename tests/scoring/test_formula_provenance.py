"""Formula-provenance tests (Phase 17 audit; BUG-TL-0005 / BUG-TL-0006).

After ``D-18-01`` there is exactly **one** reward implementation
(``scoring.official_scorer``). The audit found that two *published* surfaces
still described the retired provisional contract:

* ``reward_property_matrix.json`` published
  ``"formula": "R = max(0, F1 - eta * steps_used / max_steps)"`` and
  ``"provisional": true`` although every number in the matrix was already
  computed by the official implementation (BUG-TL-0005);
* ``robustness_report.json`` published
  ``"score_contract": "scoring.reward (internal provisional; not
  official_scorer)"`` although ``scoring.reward`` is a thin view over
  ``scoring.official_scorer`` (BUG-TL-0006).

These tests fail on the old code and pin the published contract to the live
constants, so the two cannot drift apart again.
"""

from __future__ import annotations

import json
import unittest
from fractions import Fraction
from pathlib import Path

from scoring.diagnostics import build_reward_property_matrix
from scoring.official_scorer import OFFICIAL_STEP_PENALTY_WEIGHT, official_formula_text
from scoring.reward import FORMULA

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The superseded provisional formula. It must never be published again.
SUPERSEDED_FORMULA = "R = max(0, F1 - eta * steps_used / max_steps)"


class TestFormulaSingleSource(unittest.TestCase):
    def test_formula_text_is_derived_from_live_constants(self) -> None:
        self.assertEqual(FORMULA, official_formula_text())
        self.assertIn("2*F1", FORMULA)
        self.assertIn("/ 100)", FORMULA)
        self.assertNotIn(SUPERSEDED_FORMULA, FORMULA)

    def test_published_weight_matches_the_live_constant(self) -> None:
        """The published string must carry the weight the code applies."""
        self.assertEqual(OFFICIAL_STEP_PENALTY_WEIGHT, Fraction(1, 5))
        self.assertIn("0.2", official_formula_text())


class TestRewardPropertyMatrixProvenance(unittest.TestCase):
    """The matrix must publish the formula the code computes."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.matrix = build_reward_property_matrix(
            [
                {
                    "scenario": "clean-1",
                    "strategy": "honest",
                    "kind": "clean",
                    "anomaly_type": None,
                    "tp": 0,
                    "fp": 0,
                    "fn": 0,
                    "steps_used": 20,
                    "reward_exact": "24/25",
                    "reward_decimal": "0.9600000",
                    "eta_exact": "1/5",
                }
            ]
        )

    def test_matrix_publishes_the_live_formula(self) -> None:
        self.assertEqual(self.matrix["formula"], official_formula_text())
        self.assertNotEqual(self.matrix["formula"], SUPERSEDED_FORMULA)

    def test_matrix_is_not_provisional(self) -> None:
        # The rows are produced by the official implementation, so the matrix
        # must not label itself provisional (BUG-TL-0005).
        self.assertIs(self.matrix["provisional"], False)


class TestRobustnessReportContract(unittest.TestCase):
    def test_score_contract_names_the_single_implementation(self) -> None:
        from judge.robustness_audit import SCORE_CONTRACT

        self.assertIn("scoring.official_scorer", SCORE_CONTRACT)
        self.assertNotIn("provisional", SCORE_CONTRACT.lower())
        self.assertIn(official_formula_text(), SCORE_CONTRACT)

    def test_no_published_artifact_carries_the_superseded_formula(self) -> None:
        """Generated reports must not quote the retired provisional formula."""
        report_dir = REPO_ROOT / "artifacts" / "reports" / "latest"
        if not report_dir.is_dir():
            self.skipTest("generated reports not present (run `make verify` first)")
        offenders = []
        for path in sorted(report_dir.glob("*.json")):
            text = path.read_text(encoding="utf-8", errors="replace")
            if SUPERSEDED_FORMULA in text:
                offenders.append(path.name)
        self.assertEqual(offenders, [], f"published artifacts quote the superseded formula: {offenders}")


if __name__ == "__main__":
    unittest.main()
