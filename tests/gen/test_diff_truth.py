"""Diff and diff-derived-truth tests (Phase 4.4, 4.5, 10.3, REQ-GEN-010..012).

The point of these tests is the *causal chain* required by the Master TЗ:

    operator -> diff facts -> invariant signature -> candidate truth -> evidence

A finding that cannot be walked back along that chain must be rejected, and the
tests below construct exactly those failure modes.
"""

from __future__ import annotations

import unittest

from contracts.errors import ContractError
from gen.clean import build_clean_book
from gen.config import load_generator_config
from gen.core.rng import RngService
from gen.errors.duplicate_payment import DuplicatePaymentOperator
from gen.errors.partial_allocation import PartialAllocationOperator
from gen.truth_build import (
    AMOUNT_INVARIANT_BY_SIGNATURE,
    EVIDENCE_RULE_BY_TYPE,
    build_candidate_truth,
    reachable_evidence,
)
from gen.truthdiff import assert_clean_untouched, structural_diff, touched_entities
from invariants.checks_clean import check_all


class StructuralDiffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_generator_config()
        cls.build = build_clean_book(master_seed="diff-suite", config=cls.config, difficulty="L2")
        cls.book = cls.build.book
        operator = DuplicatePaymentOperator()
        params = operator.candidate_params(cls.book, cls.config.mutation_raw["duplicate_payment"])[0]
        cls.operator = operator
        cls.params = params
        cls.mutated, cls.application = operator.apply(
            cls.book, params, RngService("diff-suite").stream("mutation/diff/0")
        )

    def test_diff_is_deterministic(self) -> None:
        first = structural_diff(self.book, self.mutated)
        second = structural_diff(self.book, self.mutated)
        self.assertEqual(first.digest(), second.digest())

    def test_diff_identical_books_is_empty(self) -> None:
        diff = structural_diff(self.book, self.book)
        self.assertTrue(diff.is_empty())
        self.assertEqual(diff.summary()["added"], 0)

    def test_duplicate_adds_payment_bank_line_and_entry(self) -> None:
        diff = structural_diff(self.book, self.mutated)
        self.assertEqual(len(diff.added("payments")), 1)
        self.assertEqual(len(diff.added("bank_lines")), 1)
        self.assertEqual(len(diff.added("journal_entries")), 1)
        self.assertEqual(len(diff.removed()), 0)

    def test_diff_reports_modified_status(self) -> None:
        diff = structural_diff(self.book, self.mutated)
        modified = diff.modified("invoices")
        self.assertTrue(modified)
        self.assertIn("status", modified[0].changed_fields)

    def test_diff_captures_exact_amounts(self) -> None:
        diff = structural_diff(self.book, self.mutated)
        added_payment = diff.added("payments")[0].after
        self.assertIsNotNone(added_payment)
        new_payment_id = added_payment["pay_id"]  # type: ignore[index]
        self.assertEqual(
            self.mutated.payment(new_payment_id).amount_minor,
            self.mutated.payment(new_payment_id).allocated_minor,
        )

    def test_removal_is_reported(self) -> None:
        subset = self.mutated.with_rows("payments", self.mutated.payments[1:])
        diff = structural_diff(self.mutated, subset)
        self.assertEqual(len(diff.removed("payments")), 1)
        self.assertEqual(len(diff.added()), 0)

    def test_clean_twin_guard(self) -> None:
        assert_clean_untouched(self.book, self.build.book)
        with self.assertRaises(ContractError):
            assert_clean_untouched(self.book, self.mutated)

    def test_touched_entities_include_new_rows(self) -> None:
        diff = structural_diff(self.book, self.mutated)
        touched = touched_entities(diff)
        self.assertIn("payments", touched)
        self.assertIn(self.application.affected_ids[0], sum(touched.values(), ()))

    def test_modified_field_detection_on_link_change(self) -> None:
        operator = PartialAllocationOperator()
        params = operator.candidate_params(
            self.book, self.config.mutation_raw["partial_payment_allocation"]
        )[0]
        mutated, _ = operator.apply(self.book, params, RngService("diff-suite").stream("m/p"))
        diff = structural_diff(self.book, mutated)
        modified = diff.modified("payments")
        self.assertEqual(len(modified), 1)
        self.assertIn("allocations", modified[0].changed_fields)


class TruthConstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_generator_config()
        cls.build = build_clean_book(master_seed="truth-suite", config=cls.config, difficulty="L2")
        cls.book = cls.build.book

    def _duplicate_truth(self):
        operator = DuplicatePaymentOperator()
        params = operator.candidate_params(self.book, self.config.mutation_raw["duplicate_payment"])[0]
        mutated, application = operator.apply(
            self.book, params, RngService("truth-suite").stream("m/d")
        )
        diff = structural_diff(self.book, mutated)
        violations = check_all(mutated)
        truth = build_candidate_truth(
            clean=self.book,
            mutated=mutated,
            diff=diff,
            violations=violations,
            application=application,
            subtype=None,
        )
        return mutated, application, diff, truth

    def test_truth_finding_is_diff_backed(self) -> None:
        _, application, diff, truth = self._duplicate_truth()
        finding = truth.findings[0]
        self.assertTrue(finding.diff_refs)
        self.assertEqual(set(finding.affected_ids), set(application.affected_ids))
        # Truth must be canonically ordered (canonical table order), not in
        # operation-application order, and must be stable across rebuilds.
        self.assertNotEqual(list(finding.affected_ids), list(application.affected_ids))
        _, _, _, rebuilt = self._duplicate_truth()
        self.assertEqual(finding.affected_ids, rebuilt.findings[0].affected_ids)
        refs = " ".join(finding.diff_refs)
        for identifier in finding.affected_ids:
            self.assertTrue(
                any(identifier in ref for ref in finding.diff_refs),
                f"{identifier} has no diff fact in {refs}",
            )

    def test_truth_amount_matches_invariant_signature(self) -> None:
        _, _, _, truth = self._duplicate_truth()
        finding = truth.findings[0]
        self.assertEqual(finding.invariant_signature["invariant_id"], "INV-04")
        self.assertGreater(finding.amount_minor, 0)
        self.assertEqual(finding.tolerance_minor, 0)

    def test_truth_evidence_is_reachable(self) -> None:
        mutated, _, _, truth = self._duplicate_truth()
        index = reachable_evidence(mutated)
        universe = {item for ids in index.values() for item in ids}
        for evidence_set in truth.findings[0].evidence_sets:
            for identifier in evidence_set:
                self.assertIn(identifier, universe)

    def test_truth_document_is_schema_shaped(self) -> None:
        _, _, _, truth = self._duplicate_truth()
        document = truth.to_truth_document(episode_id="EP-L2-TESTTESTTEST", mode="ANOMALOUS")
        self.assertEqual(document["truth_version"], "1.0.0")
        self.assertEqual(document["mode"], "ANOMALOUS")
        self.assertEqual(len(document["findings"]), 1)
        self.assertEqual(document["findings"][0]["optimal_steps"], None)
        self.assertEqual(document["findings"][0]["optimal_steps_model_id"], "query_plan_v1")

    def test_truth_rejected_without_diff_facts(self) -> None:
        operator = DuplicatePaymentOperator()
        params = operator.candidate_params(self.book, self.config.mutation_raw["duplicate_payment"])[0]
        mutated, application = operator.apply(
            self.book, params, RngService("truth-suite").stream("m/d")
        )
        empty_diff = structural_diff(self.book, self.book)
        with self.assertRaises(ContractError):
            build_candidate_truth(
                clean=self.book,
                mutated=mutated,
                diff=empty_diff,
                violations=check_all(mutated),
                application=application,
                subtype=None,
            )

    def test_truth_rejected_without_violation(self) -> None:
        operator = DuplicatePaymentOperator()
        params = operator.candidate_params(self.book, self.config.mutation_raw["duplicate_payment"])[0]
        mutated, application = operator.apply(
            self.book, params, RngService("truth-suite").stream("m/d")
        )
        diff = structural_diff(self.book, mutated)
        with self.assertRaises(ContractError):
            build_candidate_truth(
                clean=self.book,
                mutated=mutated,
                diff=diff,
                violations=[],
                application=application,
                subtype=None,
            )

    def test_clean_book_truth_is_empty(self) -> None:
        diff = structural_diff(self.book, self.book)
        from gen.truth_build import TruthBuild

        truth = TruthBuild(findings=(), diff=diff, evidence_index={})
        self.assertTrue(truth.is_clean)
        document = truth.to_truth_document(episode_id="EP-L1-CLEANCLEANCLE", mode="CLEAN")
        self.assertEqual(document["findings"], [])

    def test_amount_invariant_map_covers_all_signatures(self) -> None:
        from gen.errors.partial_allocation import SUBTYPES

        self.assertIn(("DUPLICATE_PAYMENT", None), AMOUNT_INVARIANT_BY_SIGNATURE)
        for subtype in SUBTYPES:
            self.assertIn(("PARTIAL_PAYMENT_ALLOCATION", subtype), AMOUNT_INVARIANT_BY_SIGNATURE)

    def test_evidence_rules_documented_for_both_types(self) -> None:
        self.assertIn("DUPLICATE_PAYMENT", EVIDENCE_RULE_BY_TYPE)
        self.assertIn("PARTIAL_PAYMENT_ALLOCATION", EVIDENCE_RULE_BY_TYPE)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
