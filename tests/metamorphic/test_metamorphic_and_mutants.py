"""Integration tests for Phase 13 (Metamorphic M-01..M-07 & 26-Mutant Mutation Suite)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from judge.mutation_suite import run_mutation_suite
from metamorphic.suite import run_metamorphic_suite


class TestMetamorphicAndMutationSuites(unittest.TestCase):
    def test_all_seven_metamorphic_relations_pass(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rep = run_metamorphic_suite(output_path=Path(td) / "meta.json")
            self.assertEqual(rep["status"], "PASS")
            self.assertEqual(rep["summary"]["transforms_passed"], 7)
            self.assertEqual(rep["summary"]["transforms_total"], 7)

    def test_all_twenty_six_mutants_killed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rep = run_mutation_suite(output_path=Path(td) / "mut.json")
            self.assertEqual(rep["status"], "PASS")
            self.assertGreaterEqual(rep["summary"]["total_mutants"], 25)
            self.assertEqual(rep["summary"]["surviving_mutants"], 0)
            self.assertEqual(rep["summary"]["mutation_score_pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
