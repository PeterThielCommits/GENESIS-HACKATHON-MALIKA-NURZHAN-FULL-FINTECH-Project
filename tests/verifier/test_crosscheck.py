"""Stage-2 independent crosscheck tests (Phase 8, Task 8.6 — REQ-ORG-003,
REQ-VER-020..022, TZ 13.2, 13.3, 13.7).
"""

from __future__ import annotations

import copy
import unittest
from fractions import Fraction

from contracts.models import TruthFinding
from scoring.crosscheck import CrosscheckError, crosscheck
from tests.verifier import fixtures as fx
from verifier import VerifierConfig, discover


class TestIndependentCrosscheck(unittest.TestCase):
    def test_clean_episode_crosscheck_passes(self):
        ep = fx.clean_episode()
        out = discover(ep)
        cc = crosscheck(
            out.report.to_dict(),
            [],
            expected_report_digest=out.report_digest,
            distractor_count=4,
        )
        self.assertFalse(cc.release_blocked)
        self.assertEqual(cc.tp, 0)
        self.assertEqual(cc.fp, 0)
        self.assertEqual(cc.fn, 0)
        self.assertEqual(cc.f1, Fraction(1))
        self.assertEqual(cc.distractor_false_positive_rate, Fraction(0))
        self.assertEqual(cc.evidence_minimality_rate, Fraction(1))
        self.assertEqual(cc.blocking_reasons, ())

    def test_compound_four_type_crosscheck_exact_match(self):
        ep, truths = fx.compound_four_type_episode()
        out = discover(ep, VerifierConfig(run_ablation=True))
        cc = crosscheck(
            out.report.to_dict(),
            truths,
            expected_report_digest=out.report_digest,
        )
        self.assertFalse(cc.release_blocked, msg=cc.blocking_reasons)
        self.assertEqual(cc.tp, 4)
        self.assertEqual(cc.fp, 0)
        self.assertEqual(cc.fn, 0)
        self.assertEqual(cc.precision, Fraction(1))
        self.assertEqual(cc.recall, Fraction(1))
        self.assertEqual(cc.f1, Fraction(1))
        self.assertEqual(cc.exact_affected_id_accuracy, Fraction(1))
        self.assertEqual(cc.amount_exact_accuracy, Fraction(1))
        self.assertEqual(cc.amount_tolerance_accuracy, Fraction(1))
        self.assertEqual(cc.evidence_sufficiency_rate, Fraction(1))
        self.assertEqual(cc.evidence_minimality_rate, Fraction(1))
        self.assertEqual(cc.unresolved_ambiguity_count, 0)
        self.assertEqual(len(cc.crosscheck_hash), 64)
        self.assertEqual(cc.to_dict()["release_blocked"], False)

    def test_missed_truth_blocks_release(self):
        ep, truths = fx.duplicate_payment_episode()
        out = discover(ep)
        extra_truth = TruthFinding(
            truth_id="TRUTH-MISSED",
            type="PERIOD_CUTOFF",
            affected_ids=("JE:JE-9999",),
            amount_minor=1000,
            currency="KZT",
            tolerance_minor=0,
            evidence_sets=(("INV:INV-9999", "JE:JE-9999"),),
            minimal_evidence_size=2,
            invariant_signature={"invariant_id": "INV-09"},
            operator_version="test@1",
        )
        cc = crosscheck(
            out.report.to_dict(),
            truths + [extra_truth],
            expected_report_digest=out.report_digest,
        )
        self.assertTrue(cc.release_blocked)
        self.assertEqual(cc.tp, 1)
        self.assertEqual(cc.fn, 1)
        self.assertEqual(cc.unmatched_truth_ids, ("TRUTH-MISSED",))

    def test_false_positive_blocks_release(self):
        ep, _ = fx.duplicate_payment_episode()
        out = discover(ep)
        cc = crosscheck(
            out.report.to_dict(),
            [],
            expected_report_digest=out.report_digest,
            distractor_count=2,
        )
        self.assertTrue(cc.release_blocked)
        self.assertEqual(cc.fp, 1)
        self.assertEqual(cc.distractor_false_positive_rate, Fraction(1, 2))

    def test_tampered_report_digest_rejected(self):
        ep, truths = fx.period_cutoff_episode()
        out = discover(ep)
        tampered = copy.deepcopy(out.report.to_dict())
        tampered["findings"][0]["claimed_amount_minor"] += 1
        with self.assertRaises(CrosscheckError):
            crosscheck(tampered, truths, expected_report_digest=out.report_digest)

    def test_unresolved_ambiguity_blocks_release(self):
        ep = fx.clean_episode()
        out = discover(ep)
        rep = copy.deepcopy(out.report.to_dict())
        rep["unresolved_ambiguities"] = ["FX_RATE_UNAVAILABLE:JE-1"]
        cc = crosscheck(rep, [])
        self.assertTrue(cc.release_blocked)
        self.assertEqual(cc.unresolved_ambiguity_count, 1)

    def test_non_union_evidence_sufficiency_enforced(self):
        # Truth accepts {A, B} or {C, D}. Verifier emits [{A, C}, {B, D}].
        # Neither individual set is sufficient -> MUST NOT match!
        truth = TruthFinding(
            truth_id="T-NONUNION",
            type="FX_RATE_MISMATCH",
            affected_ids=("JE:JE-1",),
            amount_minor=100,
            currency="KZT",
            tolerance_minor=0,
            evidence_sets=(("FX:A", "JE:JE-1"), ("FX:C", "JE:JE-1")),
            minimal_evidence_size=2,
            invariant_signature={"invariant_id": "INV-07"},
            operator_version="test@1",
        )
        report = {
            "schema_version": "1.0.0",
            "episode_public_hash": "a" * 64,
            "findings": [
                {
                    "type": "FX_RATE_MISMATCH",
                    "affected_ids": ["JE:JE-1"],
                    "claimed_amount_minor": 100,
                    "currency": "KZT",
                    "evidence_sets": [["FX:A", "INV:X"], ["FX:C", "INV:Y"]],
                    "explanation_code": "FX_RATE_POLICY_MISMATCH",
                }
            ],
            "examined_public_sources": ["company.json", "policy.json"],
            "unresolved_ambiguities": [],
            "verifier_version": "1.0.0",
        }
        cc = crosscheck(report, [truth])
        self.assertTrue(cc.release_blocked)
        self.assertEqual(cc.tp, 0)
        self.assertEqual(cc.fp, 1)
        self.assertEqual(cc.fn, 1)

    def test_one_bad_alternative_evidence_set_blocks_release(self):
        # First evidence set is valid, second is insufficient -> sufficiency < 1 -> blocked
        ep, truths = fx.fx_mismatch_episode()
        out = discover(ep)
        rep = copy.deepcopy(out.report.to_dict())
        rep["findings"][0]["evidence_sets"].append(["JE:JE-0301"])  # incomplete set
        cc = crosscheck(rep, truths)
        self.assertTrue(cc.release_blocked)
        self.assertEqual(cc.evidence_sufficiency_rate, Fraction(0))

    def test_ablation_failure_in_diagnostics_blocks_release(self):
        ep, truths = fx.period_cutoff_episode()
        out = discover(ep)
        rep = copy.deepcopy(out.report.to_dict())
        rep["deterministic_diagnostics"]["ablation_summary"]["details"][0]["all_minimal"] = False
        rep["deterministic_diagnostics"]["ablation_summary"]["details"][0]["failures"] = [
            "minimality failed"
        ]
        cc = crosscheck(rep, truths)
        self.assertTrue(cc.release_blocked)
        self.assertEqual(cc.evidence_minimality_rate, Fraction(0))
        self.assertTrue(any("ablation failed" in r for r in cc.blocking_reasons))


if __name__ == "__main__":
    unittest.main()
