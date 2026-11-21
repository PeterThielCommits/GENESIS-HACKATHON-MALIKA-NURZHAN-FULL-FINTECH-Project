"""Block 3 mirror tests: All 20 reward vectors + M01..M12 (Genesis FinTech 2026-11-20)."""

from __future__ import annotations

import unittest

from scoring.official_scorer import (
    OfficialTruth,
    score_official_findings,
)

TOL = 1e-9


def _truth_a(*, tolerance: int = 0) -> OfficialTruth:
    return OfficialTruth(
        issue_id="A",
        type="DUPLICATE_PAYMENT",
        affected_ids=frozenset({"R1"}),
        expected_amount_minor=10000,
        currency="KZT",
        evidence_sets=(frozenset({"D1", "D2"}),),
        tolerance_minor=tolerance,
    )


def _truth_b() -> OfficialTruth:
    return OfficialTruth(
        issue_id="B",
        type="FX_RATE_MISMATCH",
        affected_ids=frozenset({"R2"}),
        expected_amount_minor=20000,
        currency="KZT",
        evidence_sets=(frozenset({"D3", "D4"}),),
        tolerance_minor=0,
    )


def _finding_a(**overrides) -> dict:
    base = {
        "type": "DUPLICATE_PAYMENT",
        "affected_ids": ["R1"],
        "claimed_amount_minor": 10000,
        "currency": "KZT",
        "evidence_ids": ["D1", "D2"],
        "explanation": "valid finding",
    }
    base.update(overrides)
    return base


ACCESSIBLE = {"R1", "R2", "R3", "R4", "R5", "D1", "D2", "D3", "D4"}


class TestBlock3RewardVectors1To20(unittest.TestCase):
    """Exact verification of all 20 Block 3 matcher/reward test vectors."""

    def test_01_single_truth_exact_match(self) -> None:
        r = score_official_findings({"findings": [_finding_a()]}, [_truth_a()], 10, accessible_ids=ACCESSIBLE).to_score_dict()
        self.assertEqual((r["tp"], r["fp"], r["fn"]), (1, 0, 0))
        self.assertAlmostEqual(r["precision"], 1.0, delta=TOL)
        self.assertAlmostEqual(r["recall"], 1.0, delta=TOL)
        self.assertAlmostEqual(r["f1"], 1.0, delta=TOL)
        self.assertAlmostEqual(r["return"], 0.98, delta=TOL)

    def test_02_single_truth_empty_findings(self) -> None:
        r = score_official_findings({"findings": []}, [_truth_a()], 10, accessible_ids=ACCESSIBLE).to_score_dict()
        self.assertEqual((r["tp"], r["fp"], r["fn"]), (0, 0, 1))
        self.assertAlmostEqual(r["f1"], 0.0, delta=TOL)
        self.assertAlmostEqual(r["return"], -1.0, delta=TOL)

    def test_03_empty_truth_empty_findings_special_rule(self) -> None:
        r = score_official_findings({"findings": []}, [], 10, accessible_ids=ACCESSIBLE).to_score_dict()
        self.assertEqual((r["tp"], r["fp"], r["fn"]), (0, 0, 0))
        self.assertAlmostEqual(r["precision"], 0.0, delta=TOL)
        self.assertAlmostEqual(r["recall"], 0.0, delta=TOL)
        self.assertAlmostEqual(r["f1"], 1.0, delta=TOL)
        self.assertAlmostEqual(r["return"], 0.98, delta=TOL)

    def test_04_empty_truth_one_false_positive(self) -> None:
        r = score_official_findings({"findings": [_finding_a()]}, [], 10, accessible_ids=ACCESSIBLE).to_score_dict()
        self.assertEqual((r["tp"], r["fp"], r["fn"]), (0, 1, 0))
        self.assertAlmostEqual(r["f1"], 0.0, delta=TOL)
        self.assertAlmostEqual(r["return"], -1.0, delta=TOL)

    def test_05_duplicate_identical_finding_penalized(self) -> None:
        r = score_official_findings({"findings": [_finding_a(), _finding_a()]}, [_truth_a()], 10, accessible_ids=ACCESSIBLE).to_score_dict()
        self.assertEqual((r["tp"], r["fp"], r["fn"]), (1, 1, 0))
        self.assertAlmostEqual(r["precision"], 0.5, delta=TOL)
        self.assertAlmostEqual(r["recall"], 1.0, delta=TOL)
        self.assertAlmostEqual(r["f1"], 2 / 3, delta=TOL)
        self.assertAlmostEqual(r["return"], 47 / 150, delta=TOL)

    def test_06_wrong_type(self) -> None:
        r = score_official_findings({"findings": [_finding_a(type="PERIOD_CUTOFF")]}, [_truth_a()], 10, accessible_ids=ACCESSIBLE).to_score_dict()
        self.assertEqual((r["tp"], r["fp"], r["fn"]), (0, 1, 1))
        self.assertAlmostEqual(r["return"], -1.0, delta=TOL)

    def test_07_wrong_affected_id(self) -> None:
        r = score_official_findings({"findings": [_finding_a(affected_ids=["R2"])]}, [_truth_a()], 10, accessible_ids=ACCESSIBLE).to_score_dict()
        self.assertEqual((r["tp"], r["fp"], r["fn"]), (0, 1, 1))
        self.assertAlmostEqual(r["return"], -1.0, delta=TOL)

    def test_08_amount_off_by_1_with_zero_tolerance(self) -> None:
        r = score_official_findings({"findings": [_finding_a(claimed_amount_minor=10001)]}, [_truth_a()], 10, accessible_ids=ACCESSIBLE).to_score_dict()
        self.assertEqual((r["tp"], r["fp"], r["fn"]), (0, 1, 1))
        self.assertAlmostEqual(r["return"], -1.0, delta=TOL)

    def test_09_wrong_currency(self) -> None:
        r = score_official_findings({"findings": [_finding_a(currency="USD")]}, [_truth_a()], 10, accessible_ids=ACCESSIBLE).to_score_dict()
        self.assertEqual((r["tp"], r["fp"], r["fn"]), (0, 1, 1))
        self.assertAlmostEqual(r["return"], -1.0, delta=TOL)

    def test_10_incomplete_evidence_set(self) -> None:
        r = score_official_findings({"findings": [_finding_a(evidence_ids=["D1"])]}, [_truth_a()], 10, accessible_ids=ACCESSIBLE).to_score_dict()
        self.assertEqual((r["tp"], r["fp"], r["fn"]), (0, 1, 1))
        self.assertAlmostEqual(r["return"], -1.0, delta=TOL)

    def test_11_nonexistent_evidence_id_instead_of_D2(self) -> None:
        r = score_official_findings({"findings": [_finding_a(evidence_ids=["D1", "U"])]}, [_truth_a()], 10, accessible_ids=ACCESSIBLE).to_score_dict()
        self.assertEqual((r["tp"], r["fp"], r["fn"]), (0, 1, 1))
        self.assertAlmostEqual(r["return"], -1.0, delta=TOL)

    def test_12_mass_flagging_attack_5_records_x_4_types(self) -> None:
        types = ("DUPLICATE_PAYMENT", "PARTIAL_PAYMENT_ALLOCATION", "FX_RATE_MISMATCH", "PERIOD_CUTOFF")
        spam = [
            _finding_a(type=t, affected_ids=[f"R{i}"])
            for i in range(1, 6)
            for t in types
        ]
        self.assertEqual(len(spam), 20)
        r = score_official_findings({"findings": spam}, [_truth_a()], 10, accessible_ids=ACCESSIBLE).to_score_dict()
        self.assertEqual((r["tp"], r["fp"], r["fn"]), (1, 19, 0))
        self.assertAlmostEqual(r["precision"], 1 / 20, delta=TOL)
        self.assertAlmostEqual(r["recall"], 1.0, delta=TOL)
        self.assertAlmostEqual(r["f1"], 2 / 21, delta=TOL)
        self.assertAlmostEqual(r["return"], -871 / 1050, delta=TOL)

    def test_13_two_truths_one_matched(self) -> None:
        r = score_official_findings({"findings": [_finding_a()]}, [_truth_a(), _truth_b()], 10, accessible_ids=ACCESSIBLE).to_score_dict()
        self.assertEqual((r["tp"], r["fp"], r["fn"]), (1, 0, 1))
        self.assertAlmostEqual(r["precision"], 1.0, delta=TOL)
        self.assertAlmostEqual(r["recall"], 0.5, delta=TOL)
        self.assertAlmostEqual(r["f1"], 2 / 3, delta=TOL)
        self.assertAlmostEqual(r["return"], 47 / 150, delta=TOL)

    def test_14_two_truths_one_tp_one_fp(self) -> None:
        fp_finding = _finding_a(affected_ids=["R5"])
        r = score_official_findings({"findings": [_finding_a(), fp_finding]}, [_truth_a(), _truth_b()], 10, accessible_ids=ACCESSIBLE).to_score_dict()
        self.assertEqual((r["tp"], r["fp"], r["fn"]), (1, 1, 1))
        self.assertAlmostEqual(r["precision"], 0.5, delta=TOL)
        self.assertAlmostEqual(r["recall"], 0.5, delta=TOL)
        self.assertAlmostEqual(r["f1"], 0.5, delta=TOL)
        self.assertAlmostEqual(r["return"], -0.02, delta=TOL)

    def test_15_zero_inspection_steps(self) -> None:
        r = score_official_findings({"findings": [_finding_a()]}, [_truth_a()], 0, accessible_ids=ACCESSIBLE).to_score_dict()
        self.assertAlmostEqual(r["f1"], 1.0, delta=TOL)
        self.assertAlmostEqual(r["return"], 1.0, delta=TOL)

    def test_16_fifty_inspection_steps(self) -> None:
        r = score_official_findings({"findings": [_finding_a()]}, [_truth_a()], 50, accessible_ids=ACCESSIBLE).to_score_dict()
        self.assertAlmostEqual(r["f1"], 1.0, delta=TOL)
        self.assertAlmostEqual(r["return"], 0.90, delta=TOL)

    def test_17_hundred_inspection_steps(self) -> None:
        r = score_official_findings({"findings": [_finding_a()]}, [_truth_a()], 100, accessible_ids=ACCESSIBLE).to_score_dict()
        self.assertAlmostEqual(r["f1"], 1.0, delta=TOL)
        self.assertAlmostEqual(r["return"], 0.80, delta=TOL)

    def test_18_31_findings_invalid_structure(self) -> None:
        r = score_official_findings({"findings": [_finding_a()] * 31}, [_truth_a()], 10, accessible_ids=ACCESSIBLE).to_score_dict()
        self.assertEqual(r, {"tp": None, "fp": None, "fn": None, "precision": None, "recall": None, "f1": None, "return": -1.0})

    def test_19_11_evidence_ids_invalid_structure(self) -> None:
        ev11 = [f"D{i}" for i in range(11)]
        r = score_official_findings({"findings": [_finding_a(evidence_ids=ev11)]}, [_truth_a()], 10, accessible_ids=ACCESSIBLE).to_score_dict()
        self.assertEqual(r, {"tp": None, "fp": None, "fn": None, "precision": None, "recall": None, "f1": None, "return": -1.0})

    def test_20_1001_ascii_explanation_invalid_structure(self) -> None:
        r = score_official_findings({"findings": [_finding_a(explanation="x" * 1001)]}, [_truth_a()], 10, accessible_ids=ACCESSIBLE).to_score_dict()
        self.assertEqual(r, {"tp": None, "fp": None, "fn": None, "precision": None, "recall": None, "f1": None, "return": -1.0})


class TestBlock3OpenExamplesM01ToM12(unittest.TestCase):
    """Exact verification of all 12 normative matcher examples M01..M12."""

    def _truth_m(self, tolerance: int = 0) -> OfficialTruth:
        return OfficialTruth(
            issue_id="A",
            type="DUPLICATE_PAYMENT",
            affected_ids=frozenset({"R1", "R2"}),
            expected_amount_minor=10000,
            currency="KZT",
            evidence_sets=(frozenset({"D1", "D2"}),),
            tolerance_minor=tolerance,
        )

    def test_M01_duplicate_and_reordered_affected_ids_still_tp(self) -> None:
        f = _finding_a(affected_ids=["R2", "R1", "R1"])
        r = score_official_findings({"findings": [f]}, [self._truth_m()], 10, accessible_ids=ACCESSIBLE)
        self.assertEqual((r.tp, r.fp, r.fn), (1, 0, 0))

    def test_M02_extra_unaffected_record_R3_is_fp(self) -> None:
        f = _finding_a(affected_ids=["R1", "R2", "R3"])
        r = score_official_findings({"findings": [f]}, [self._truth_m()], 10, accessible_ids=ACCESSIBLE)
        self.assertEqual((r.tp, r.fp, r.fn), (0, 1, 1))

    def test_M03_superset_accessible_evidence_D3_is_tp(self) -> None:
        f = _finding_a(affected_ids=["R1", "R2"], evidence_ids=["D2", "D1", "D3"])
        r = score_official_findings({"findings": [f]}, [self._truth_m()], 10, accessible_ids=ACCESSIBLE)
        self.assertEqual((r.tp, r.fp, r.fn), (1, 0, 0))

    def test_M04_nonexistent_evidence_U_with_valid_set_is_fp(self) -> None:
        f = _finding_a(affected_ids=["R1", "R2"], evidence_ids=["D1", "D2", "U"])
        r = score_official_findings({"findings": [f]}, [self._truth_m()], 10, accessible_ids=ACCESSIBLE)
        self.assertEqual((r.tp, r.fp, r.fn), (0, 1, 1))

    def test_M05_11_evidence_ids_with_duplicates_rejected_before_dedup(self) -> None:
        f = _finding_a(affected_ids=["R1", "R2"], evidence_ids=["D1"] * 10 + ["D2"])
        r = score_official_findings({"findings": [f]}, [self._truth_m()], 10, accessible_ids=ACCESSIBLE).to_score_dict()
        self.assertEqual(r["return"], -1.0)
        self.assertIsNone(r["tp"])

    def test_M06_currency_case_or_whitespace_mismatch_is_fp(self) -> None:
        for bad_cur in ("kzt", " KZT", "KZT "):
            f = _finding_a(affected_ids=["R1", "R2"], currency=bad_cur)
            r = score_official_findings({"findings": [f]}, [self._truth_m()], 10, accessible_ids=ACCESSIBLE)
            self.assertEqual((r.tp, r.fp, r.fn), (0, 1, 1))

    def test_M07_amount_10001_with_tau_0_is_fp(self) -> None:
        f = _finding_a(affected_ids=["R1", "R2"], claimed_amount_minor=10001)
        r = score_official_findings({"findings": [f]}, [self._truth_m(tolerance=0)], 10, accessible_ids=ACCESSIBLE)
        self.assertEqual((r.tp, r.fp, r.fn), (0, 1, 1))

    def test_M08_amount_boundary_with_tau_1(self) -> None:
        f_ok = _finding_a(affected_ids=["R1", "R2"], claimed_amount_minor=10001)
        f_bad = _finding_a(affected_ids=["R1", "R2"], claimed_amount_minor=10002)
        r_ok = score_official_findings({"findings": [f_ok]}, [self._truth_m(tolerance=1)], 10, accessible_ids=ACCESSIBLE)
        r_bad = score_official_findings({"findings": [f_bad]}, [self._truth_m(tolerance=1)], 10, accessible_ids=ACCESSIBLE)
        self.assertEqual((r_ok.tp, r_ok.fp, r_ok.fn), (1, 0, 0))
        self.assertEqual((r_bad.tp, r_bad.fp, r_bad.fn), (0, 1, 1))

    def test_M09_amount_string_or_bool_is_structural_error(self) -> None:
        for bad_amt in ("10000", True, False, 10000.0):
            f = _finding_a(affected_ids=["R1", "R2"], claimed_amount_minor=bad_amt)
            r = score_official_findings({"findings": [f]}, [self._truth_m()], 10, accessible_ids=ACCESSIBLE).to_score_dict()
            self.assertEqual(r["return"], -1.0)
            self.assertIsNone(r["tp"])

    def test_M10_max_cardinality_matching_beats_greedy(self) -> None:
        # Truth A accepts {D1} or {D1,D2}; Truth B accepts {D1,D2}.
        # F0 has {D1,D2} (matches A and B); F1 has {D1} (matches only A).
        t_a = OfficialTruth("A", "DUPLICATE_PAYMENT", frozenset({"R1"}), 10000, "KZT", (frozenset({"D1"}),))
        t_b = OfficialTruth("B", "DUPLICATE_PAYMENT", frozenset({"R1"}), 10000, "KZT", (frozenset({"D1", "D2"}),))
        f0 = _finding_a(affected_ids=["R1"], evidence_ids=["D1", "D2"])
        f1 = _finding_a(affected_ids=["R1"], evidence_ids=["D1"])
        r = score_official_findings({"findings": [f0, f1]}, [t_a, t_b], 10, accessible_ids=ACCESSIBLE)
        self.assertEqual((r.tp, r.fp, r.fn), (2, 0, 0))
        self.assertEqual(r.pairs, (("A", 1), ("B", 0)))

    def test_M11_deterministic_lexicographic_tie_break_on_issue_id_and_index(self) -> None:
        t_a = OfficialTruth("A", "DUPLICATE_PAYMENT", frozenset({"R1"}), 10000, "KZT", (frozenset({"D1"}),))
        t_b = OfficialTruth("B", "DUPLICATE_PAYMENT", frozenset({"R1"}), 10000, "KZT", (frozenset({"D1"}),))
        f0 = _finding_a(affected_ids=["R1"], evidence_ids=["D1"])
        f1 = _finding_a(affected_ids=["R1"], evidence_ids=["D1"])
        # Even if truths passed in reverse order [B, A], tie-break sorts issue_id -> A<B -> (A,0),(B,1)
        r = score_official_findings({"findings": [f0, f1]}, [t_b, t_a], 10, accessible_ids=ACCESSIBLE)
        self.assertEqual((r.tp, r.fp, r.fn), (2, 0, 0))
        self.assertEqual(r.pairs, (("A", 0), ("B", 1)))

    def test_M12_duplicate_identical_findings_kept_as_separate_vertices(self) -> None:
        f = _finding_a(affected_ids=["R1", "R2"])
        r = score_official_findings({"findings": [f, f]}, [self._truth_m()], 10, accessible_ids=ACCESSIBLE)
        self.assertEqual((r.tp, r.fp, r.fn), (1, 1, 0))
        self.assertEqual(r.pairs, (("A", 0),))


if __name__ == "__main__":
    unittest.main()
