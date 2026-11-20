"""Tolerance model (A-014, §9.2) is provisional, bounded and proof-gated."""

from __future__ import annotations

import unittest

from tests.support import CONFIGS, load_json


class ToleranceConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_json(CONFIGS / "scoring" / "tolerance.json")

    def test_rule_is_identified_and_provisional(self) -> None:
        self.assertEqual(self.config["rule_id"], "ROUNDING_OPERATIONS_V1")
        self.assertTrue(self.config["provisional"])
        policy_enum = load_json("contracts/policy.schema.json")["properties"]["tolerance"]["properties"]["rule_id"]["enum"]
        self.assertIn(self.config["rule_id"], policy_enum)

    def test_formula_uses_real_rounding_operations(self) -> None:
        self.assertEqual(self.config["formula"], "tolerance_minor = rounding_ops * per_op_minor")
        self.assertEqual(self.config["per_op_minor"], 1)
        self.assertIn("rounding_trace", self.config["rounding_ops_source"])

    def test_widening_after_observing_results_is_forbidden(self) -> None:
        self.assertTrue(self.config["forbidden"]["widening_tolerance_after_observing_policy_results"])
        self.assertTrue(self.config["forbidden"]["tolerance_from_approximate_operation_count_guess"])

    def test_proof_obligation_is_stated(self) -> None:
        proof = self.config["proof_obligation"]
        self.assertIn("prove", proof)
        self.assertIn("bounded", proof)

    def test_rubric_mentions_the_tolerance_proof(self) -> None:
        rubric = load_json("judge/rubric_map.json")
        titles = " ".join(check["title"] + " " + check["note"] for check in rubric["internal_checks"])
        self.assertIn("tolerance", titles.lower())


if __name__ == "__main__":
    unittest.main()
