"""Mutation-operator tests (Phase 4.2, 4.3, 11.1-11.5, REQ-ERR-001..022).

Each test targets a *specific failure mode* rather than the happy path:
immutability of the clean twin, determinism, forbidden invariants, ID style,
reachability of evidence and error handling of invalid parameters.
"""

from __future__ import annotations

import unittest

from contracts.errors import OperatorError, TwinLedgerError
from gen.clean import build_clean_book
from gen.config import load_generator_config
from gen.core.journal import allocated_totals, credited_totals
from gen.core.rng import RngService
from gen.errors.duplicate_payment import DuplicatePaymentOperator
from gen.errors.partial_allocation import SUBTYPES, PartialAllocationOperator
from gen.errors.signatures import verify_signature
from invariants.checks_clean import check_all


class OperatorTestCase(unittest.TestCase):
    config = load_generator_config()

    @classmethod
    def setUpClass(cls) -> None:
        cls.build = build_clean_book(master_seed="op-suite", config=cls.config, difficulty="L2")
        cls.book = cls.build.book

    def stream(self, namespace: str = "mutation/test/0") -> RngService:
        return RngService("op-suite").stream(namespace)


class DuplicatePaymentTests(OperatorTestCase):
    def setUp(self) -> None:
        self.operator = DuplicatePaymentOperator()
        self.params = self.operator.candidate_params(
            self.book, self.config.mutation_raw["duplicate_payment"]
        )[0]

    def test_clean_twin_is_not_mutated(self) -> None:
        before = self.book.public_digest()
        files_before = dict(self.book.public_files())
        self.operator.apply(self.book, self.params, self.stream())
        self.assertEqual(self.book.public_digest(), before)
        self.assertEqual(self.book.public_files(), files_before)

    def test_deterministic_on_fixed_inputs(self) -> None:
        first, _ = self.operator.apply(self.book, self.params, self.stream("mutation/a"))
        second, _ = self.operator.apply(self.book, self.params, self.stream("mutation/a"))
        self.assertEqual(first.public_digest(), second.public_digest())

    def test_adds_one_payment_one_bank_line_one_entry(self) -> None:
        mutated, _ = self.operator.apply(self.book, self.params, self.stream())
        self.assertEqual(
            mutated.row_counts()["payments"] - self.book.row_counts()["payments"], 1
        )
        self.assertEqual(
            mutated.row_counts()["bank_lines"] - self.book.row_counts()["bank_lines"], 1
        )
        self.assertEqual(
            mutated.row_counts()["journal_entries"] - self.book.row_counts()["journal_entries"], 1
        )

    def test_only_intended_invariant_changes(self) -> None:
        mutated, _ = self.operator.apply(self.book, self.params, self.stream())
        decision = verify_signature("DUPLICATE_PAYMENT", check_all(mutated))
        self.assertTrue(decision.accepted, decision.reasons)
        self.assertIn("INV-04", decision.observed)

    def test_forbidden_invariants_stay_clean(self) -> None:
        mutated, _ = self.operator.apply(self.book, self.params, self.stream())
        observed = {violation.invariant_id for violation in check_all(mutated)}
        for invariant in ("INV-01", "INV-06", "INV-07", "INV-09", "INV-11", "INV-12",
                          "INV-13", "INV-14", "INV-15", "INV-16"):
            self.assertNotIn(invariant, observed, f"{invariant} must not break")

    def test_new_ids_follow_company_style_and_are_unique(self) -> None:
        mutated, application = self.operator.apply(self.book, self.params, self.stream())
        payments_before = {payment.pay_id for payment in self.book.payments}
        new_payment = [p for p in mutated.payments if p.pay_id not in payments_before][0]
        style = self.book.company["id_style"]
        if style == "A":
            self.assertRegex(new_payment.pay_id, r"^PAY-\d{6}$")
        elif style == "B":
            self.assertRegex(new_payment.pay_id, r"^P[0-9A-F]{7}$")
        elif style == "C":
            self.assertRegex(new_payment.pay_id, r"^pm_[0-9a-f]{6}$")
        else:
            self.assertTrue(new_payment.pay_id.isdigit())
        self.assertIn(new_payment.pay_id, application.affected_ids)

    def test_affected_ids_are_new_payment_and_its_entry(self) -> None:
        mutated, application = self.operator.apply(self.book, self.params, self.stream())
        self.assertEqual(len(application.affected_ids), 2)
        self.assertTrue(any(item.startswith(("PAY-", "P0", "pm_")) or item.isdigit()
                            for item in application.affected_ids))

    def test_journal_entry_balances(self) -> None:
        mutated, _ = self.operator.apply(self.book, self.params, self.stream())
        new_entries = [
            entry for entry in mutated.journal_entries
            if entry.je_id not in {old.je_id for old in self.book.journal_entries}
        ]
        self.assertEqual(len(new_entries), 1)
        entry = new_entries[0]
        self.assertEqual(entry.functional_debit_total, entry.functional_credit_total)

    def test_duplicate_bank_reference_is_fresh(self) -> None:
        mutated, _ = self.operator.apply(self.book, self.params, self.stream())
        references = [line.reference_text for line in mutated.bank_lines]
        self.assertEqual(len(references), len(set(references)))

    def test_invalid_target_rejected(self) -> None:
        with self.assertRaises(OperatorError):
            self.operator.apply(
                self.book,
                {**self.params, "target_invoice_id": "INV-DOES-NOT-EXIST"},
                self.stream(),
            )

    def test_invalid_delay_rejected(self) -> None:
        for bad in (0, -3, 10_000, "7"):
            with self.subTest(delay=bad), self.assertRaises(OperatorError):
                self.operator.apply(
                    self.book, {**self.params, "replay_delay_days": bad}, self.stream()
                )

    def test_invalid_channel_rejected(self) -> None:
        with self.assertRaises(OperatorError):
            self.operator.apply(
                self.book, {**self.params, "payment_channel": "CARRIER_PIGEON"}, self.stream()
            )

    def test_missing_params_rejected(self) -> None:
        with self.assertRaises(OperatorError):
            self.operator.apply(self.book, {"target_invoice_id": "X"}, self.stream())

    def test_bank_reference_strategy_guard(self) -> None:
        with self.assertRaises(OperatorError):
            self.operator.apply(
                self.book,
                {**self.params, "bank_reference_strategy": "reuse_reference"},
                self.stream(),
            )

    def test_unsettled_invoice_rejected(self) -> None:
        """Preconditions decide, not luck: the condition is constructed explicitly."""
        from dataclasses import replace

        # Model "nobody has settled this invoice yet" by stripping its allocations,
        # then prove the operator refuses to invent an unexplained duplicate.
        target = self.book.invoices[0]
        payments = [
            replace(
                payment,
                allocations=tuple(
                    allocation
                    for allocation in payment.allocations
                    if allocation.document_id != target.doc_id
                ),
            )
            if any(allocation.document_id == target.doc_id for allocation in payment.allocations)
            else payment
            for payment in self.book.payments
        ]
        payments = [payment for payment in payments if payment.allocations]
        stripped = self.book.with_rows("payments", payments)
        with self.assertRaises(OperatorError):
            self.operator.apply(
                stripped, {**self.params, "target_invoice_id": target.doc_id}, self.stream()
            )

    def test_candidates_are_precondition_valid(self) -> None:
        candidates = self.operator.candidate_params(
            self.book, self.config.mutation_raw["duplicate_payment"]
        )
        self.assertTrue(candidates)
        for params in candidates:
            self.operator.preconditions(self.book, params)


class PartialAllocationTests(OperatorTestCase):
    def setUp(self) -> None:
        self.operator = PartialAllocationOperator()
        self.candidates = self.operator.candidate_params(
            self.book, self.config.mutation_raw["partial_payment_allocation"]
        )

    def test_all_documented_subtypes_exist(self) -> None:
        self.assertEqual(len(SUBTYPES), 3)
        self.assertIn("OVER_ALLOCATE_TO_ONE_INVOICE", SUBTYPES)
        self.assertIn("ALLOCATE_TO_ALREADY_SETTLED_INVOICE", SUBTYPES)
        self.assertIn("ALLOCATIONS_EXCEED_PAYMENT", SUBTYPES)

    def test_every_candidate_passes_its_signature(self) -> None:
        self.assertTrue(self.candidates)
        for params in self.candidates:
            with self.subTest(subtype=params["subtype"], payment=params["target_payment_id"]):
                mutated, _ = self.operator.apply(self.book, params, self.stream())
                decision = verify_signature(
                    "PARTIAL_PAYMENT_ALLOCATION", check_all(mutated), subtype=params["subtype"]
                )
                self.assertTrue(decision.accepted, decision.reasons)

    def test_clean_twin_is_not_mutated(self) -> None:
        before = self.book.public_files()
        for params in self.candidates:
            self.operator.apply(self.book, params, self.stream())
        self.assertEqual(self.book.public_files(), before)

    def test_allocation_conservation_signature(self) -> None:
        params = next(
            candidate
            for candidate in self.candidates
            if candidate["subtype"] == "ALLOCATIONS_EXCEED_PAYMENT"
        )
        mutated, _ = self.operator.apply(self.book, params, self.stream("mutation/e"))
        observed = {violation.invariant_id for violation in check_all(mutated)}
        self.assertIn("INV-15", observed)

    def test_forbidden_invariants_stay_clean(self) -> None:
        for params in self.candidates:
            mutated, _ = self.operator.apply(self.book, params, self.stream())
            observed = {violation.invariant_id for violation in check_all(mutated)}
            for invariant in ("INV-01", "INV-06", "INV-07", "INV-09", "INV-11",
                              "INV-12", "INV-13", "INV-14", "INV-16"):
                self.assertNotIn(invariant, observed, f"{invariant} broke for {params['subtype']}")

    def test_unknown_subtype_rejected(self) -> None:
        with self.assertRaises(OperatorError):
            self.operator.apply(
                self.book,
                {"target_payment_id": self.book.payments[0].pay_id, "subtype": "MADE_UP"},
                self.stream(),
            )

    def test_multi_allocation_payment_rejected(self) -> None:
        """A split payment is not a valid target: the condition is constructed, not hoped for."""
        from dataclasses import replace

        from contracts.models import Allocation

        original = self.book.payments[0]
        first = Allocation(
            allocation_id=f"AL-TEST-{original.pay_id}",
            document_id=original.allocations[0].document_id,
            amount_minor=max(1, original.amount_minor // 2),
            allocation_timestamp=original.timestamp,
        )
        second = Allocation(
            allocation_id=f"AL-TEST2-{original.pay_id}",
            document_id=original.allocations[0].document_id,
            amount_minor=max(1, original.amount_minor - first.amount_minor),
            allocation_timestamp=original.timestamp,
        )
        split_payment = replace(original, allocations=(first, second))
        book = self.book.with_rows(
            "payments",
            [split_payment if row.pay_id == original.pay_id else row for row in self.book.payments],
        )
        with self.assertRaises(OperatorError):
            self.operator.apply(
                book,
                {"target_payment_id": original.pay_id, "subtype": "ALLOCATIONS_EXCEED_PAYMENT"},
                self.stream(),
            )

    def test_unknown_payment_rejected(self) -> None:
        with self.assertRaises(TwinLedgerError):
            self.operator.apply(
                self.book,
                {"target_payment_id": "PAY-GHOST", "subtype": "ALLOCATIONS_EXCEED_PAYMENT"},
                self.stream(),
            )

    def test_deterministic(self) -> None:
        params = self.candidates[0]
        first, _ = self.operator.apply(self.book, params, self.stream("mutation/d"))
        second, _ = self.operator.apply(self.book, params, self.stream("mutation/d"))
        self.assertEqual(first.public_digest(), second.public_digest())

    def test_affected_ids_cover_payment_and_documents(self) -> None:
        params = self.candidates[0]
        mutated, application = self.operator.apply(self.book, params, self.stream())
        payment = mutated.payment(params["target_payment_id"])
        for allocation in payment.allocations:
            self.assertIn(allocation.document_id, application.affected_ids)
        self.assertIn(params["target_payment_id"], application.affected_ids)


class ErrorMatrixIntegrityTests(unittest.TestCase):
    def test_intended_and_forbidden_do_not_overlap(self) -> None:
        from gen.errors.signatures import ERROR_MATRIX, SUBTYPE_MATRIX

        for anomaly_type, matrix in ERROR_MATRIX.items():
            with self.subTest(anomaly_type=anomaly_type):
                self.assertFalse(set(matrix["intended"]) & set(matrix["forbidden"]))
                self.assertFalse(set(matrix["intended"]) & set(matrix["allowed"]))
        for key, matrix in SUBTYPE_MATRIX.items():
            with self.subTest(key=key):
                self.assertFalse(set(matrix["intended"]) & set(matrix["forbidden"]))

    def test_catalog_matches_error_matrix(self) -> None:
        import json
        from pathlib import Path

        from gen.errors.signatures import ERROR_MATRIX

        catalog = json.loads(
            (Path(__file__).resolve().parents[2] / "contracts" / "anomaly_catalog.json").read_text(
                encoding="utf-8"
            )
        )
        for entry in catalog["types"]:
            if entry["type"] not in ERROR_MATRIX:
                continue
            with self.subTest(type=entry["type"]):
                self.assertEqual(
                    set(entry["forbidden_invariants"]),
                    set(ERROR_MATRIX[entry["type"]]["forbidden"]),
                    "catalog forbidden set drifted from the frozen error matrix",
                )
                self.assertEqual(
                    set(entry["intended_invariants"]),
                    set(ERROR_MATRIX[entry["type"]]["intended"]),
                )


class SubtypeSpreadTests(unittest.TestCase):
    """All declared subtypes must be reachable from the candidate list.

    A regression here is invisible in per-episode tests: the first configured subtype
    would silently dominate every generated episode and the other signatures would
    never be exercised by any later phase.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_generator_config()
        cls.operator = PartialAllocationOperator()
        cls.cfg = cls.config.mutation_raw["partial_payment_allocation"]

    def test_candidate_list_interleaves_subtypes(self) -> None:
        book = build_clean_book(master_seed="phase4-009", config=self.config, difficulty="L1").book
        candidates = self.operator.candidate_params(book, self.cfg)
        self.assertGreater(len(candidates), 2)
        self.assertEqual(
            {candidate["subtype"] for candidate in candidates}, set(SUBTYPES)
        )
        # The selector picks positionally, so the first two slots must differ.
        self.assertNotEqual(candidates[0]["subtype"], candidates[1]["subtype"])

    def test_every_subtype_appears_across_books(self) -> None:
        seen: set[str] = set()
        for index in range(12):
            book = build_clean_book(
                master_seed=f"spread-{index}", config=self.config, difficulty="L2"
            ).book
            seen.update(
                candidate["subtype"] for candidate in self.operator.candidate_params(book, self.cfg)
            )
        self.assertEqual(seen, set(SUBTYPES))

    def test_candidates_are_deterministic(self) -> None:
        book = build_clean_book(master_seed="spread-det", config=self.config, difficulty="L1").book
        first = self.operator.candidate_params(book, self.cfg)
        second = self.operator.candidate_params(book, self.cfg)
        self.assertEqual(first, second)

    def test_every_candidate_passes_preconditions(self) -> None:
        book = build_clean_book(master_seed="spread-pre", config=self.config, difficulty="L2").book
        for candidate in self.operator.candidate_params(book, self.cfg):
            with self.subTest(candidate=candidate["subtype"]):
                self.operator.preconditions(book, candidate)

    def test_generated_episodes_cover_all_subtypes(self) -> None:
        from gen.build_episodes import build_episode
        from contracts.errors import RejectError

        seen: set[str] = set()
        for index in range(16):
            try:
                episode = build_episode(
                    master_seed=f"subtype-ep-{index}",
                    config=self.config,
                    difficulty="L2",
                    created_at="2026-11-21T00:00:00+00:00",
                )
            except RejectError:
                continue
            seen.update(f.subtype for f in episode.findings if f.subtype)
        self.assertEqual(seen, set(SUBTYPES), f"unreached subtypes: {set(SUBTYPES) - seen}")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
