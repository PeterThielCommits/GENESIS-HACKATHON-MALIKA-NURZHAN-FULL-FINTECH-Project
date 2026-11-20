"""Reward configuration (A-005, A-007, Q-005): exact arithmetic, no literals in code."""

from __future__ import annotations

import unittest
from decimal import Decimal

from tests.support import CONFIGS, load_json


class RewardConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.reward = load_json(CONFIGS / "scoring" / "reward.json")
        cls.limits = load_json(CONFIGS / "environment" / "limits.json")["values"]

    def test_reward_is_explicitly_provisional(self) -> None:
        self.assertTrue(self.reward["provisional"])
        self.assertEqual(self.reward["status"], "provisional")
        self.assertIn("Never describe this file as the official reward", self.reward["status_note"])

    def test_eta_and_max_steps_are_exact(self) -> None:
        eta = Decimal(self.reward["parameters"]["ETA"])
        self.assertEqual(eta, Decimal("0.05"))
        self.assertLessEqual(eta, Decimal("0.05"), "the step penalty must never exceed ETA overall")
        self.assertEqual(self.reward["parameters"]["max_steps"], self.limits["MAX_STEPS"])

    def test_formula_is_documented_as_data(self) -> None:
        self.assertEqual(self.reward["formula"], "max(0, F1 - ETA * steps_used / max_steps)")
        self.assertEqual(self.reward["formula_id"], "F1_MINUS_STEP_PENALTY_V1")

    def test_arithmetic_forbids_floats(self) -> None:
        self.assertEqual(self.reward["arithmetic"]["float"], "forbidden")
        self.assertTrue(self.reward["arithmetic"]["raw_reward_preserved"])

    def test_edge_cases_are_defined(self) -> None:
        edges = self.reward["edge_cases"]
        self.assertEqual(edges["empty_truth_and_empty_submission_F1"], "1")
        self.assertEqual(edges["empty_truth_and_false_finding_F1"], "0")
        self.assertEqual(edges["empty_submission_with_truth_F1"], "0")

    def test_step_accounting_agrees_with_limits(self) -> None:
        accounting = self.reward["step_accounting"]
        self.assertIn("failed_tool_calls", accounting["counts"])
        self.assertFalse(self.limits["SUBMIT_COUNTS_AS_INSPECTION_STEP"])
        self.assertIn("submit", accounting["excludes"])

    def test_sanity_examples_are_reproducible_arithmetically(self) -> None:
        eta = Decimal(self.reward["parameters"]["ETA"])
        max_steps = Decimal(self.reward["parameters"]["max_steps"])

        def reward(f1: Decimal, steps: int) -> Decimal:
            return max(Decimal(0), f1 - eta * Decimal(steps) / max_steps)

        # Examples A, B, C, D, E, F from the master specification 15.6.
        self.assertEqual(reward(Decimal(1), 40), Decimal("0.98"))
        self.assertAlmostEqual(float(reward(Decimal(2) / Decimal(3), 30)), 0.6516666667, places=9)
        self.assertEqual(reward(Decimal("0.8"), 40), Decimal("0.78"))
        self.assertEqual(reward(Decimal(1), 20), Decimal("0.99"))
        self.assertEqual(reward(Decimal(0), 40), Decimal(0))
        self.assertEqual(reward(Decimal(0), 100), Decimal(0))
        # Example H: truncated clean episode scores 0.95 but must be flagged separately.
        self.assertEqual(reward(Decimal(1), 100), Decimal("0.95"))

    def test_penalty_cap_is_exactly_eta(self) -> None:
        eta = Decimal(self.reward["parameters"]["ETA"])
        max_steps = int(self.reward["parameters"]["max_steps"])
        self.assertEqual(eta * Decimal(max_steps) / Decimal(max_steps), eta)

    def test_provisional_status_note_forbids_official_claim(self) -> None:
        self.assertIn("Never describe this file as the official reward", self.reward["status_note"])


if __name__ == "__main__":
    unittest.main()
