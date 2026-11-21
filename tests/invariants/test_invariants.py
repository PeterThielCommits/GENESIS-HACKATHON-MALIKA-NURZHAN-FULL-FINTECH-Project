"""Invariant catalogue tests: INV-01..INV-17 (12.1, 12.2, REQ-INV-001..004).

Two kinds of vector per invariant:

* **positive** — the clean twin produces zero violations, and each invariant has a
  dedicated check function registered in ``check_all``;
* **negative** — a deliberately corrupted book produces that invariant, so a check
  can never pass because it silently checks nothing (a green check over an empty
  loop would make every downstream gate meaningless).

Negative vectors are built by editing *public* rows only, so the same vectors are
reproducible by a future verifier that never sees the generator.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import timedelta

from core.time_rules import parse_timestamp
from gen.clean import build_clean_book
from gen.config import load_generator_config
from invariants.checks_clean import (
    check_aging,
    check_all,
    check_allocation_conservation,
    check_ar_subledger,
    check_bank_match,
    check_credit_note_limit,
    check_currency_exponent,
    check_cutoff,
    check_document_status,
    check_fx_policy,
    check_fx_recalc,
    check_id_uniqueness,
    check_je_balance,
    check_open_balance,
    check_period_totals,
    check_referential,
    check_timezone,
    check_trial_balance,
    invoice_open_balances,
    violations_by_invariant,
)
from invariants.model import Violation

CATALOGUE = {
    "INV-01": ("JE_BALANCE", check_je_balance),
    "INV-02": ("TRIAL_BALANCE", check_trial_balance),
    "INV-03": ("AP_SUBLEDGER_VS_DOCS", check_ar_subledger),
    "INV-04": ("OPEN_BALANCE", check_open_balance),
    "INV-05": ("AGING", check_aging),
    "INV-06": ("BANK_MATCH", check_bank_match),
    "INV-07": ("FX_POLICY", check_fx_policy),
    "INV-08": ("FX_RECALC", check_fx_recalc),
    "INV-09": ("CUTOFF", check_cutoff),
    "INV-10": ("PERIOD_TOTALS", check_period_totals),
    "INV-11": ("ID_UNIQUENESS", check_id_uniqueness),
    "INV-12": ("REFERENTIAL", check_referential),
    "INV-13": ("CURRENCY_EXPONENT", check_currency_exponent),
    "INV-14": ("TIMEZONE_VALID", check_timezone),
    "INV-15": ("ALLOCATION_CONSERVATION", check_allocation_conservation),
    "INV-16": ("CREDIT_NOTE_LIMIT", check_credit_note_limit),
    "INV-17": ("DOCUMENT_STATUS", check_document_status),
}


class CatalogueTests(unittest.TestCase):
    def test_all_seventeen_invariants_are_checked(self) -> None:
        self.assertEqual(len(CATALOGUE), 17)
        self.assertEqual(sorted(CATALOGUE), [f"INV-{index:02d}" for index in range(1, 18)])

    def test_every_check_is_registered(self) -> None:
        config = load_generator_config()
        book = build_clean_book(master_seed="catalogue", config=config, difficulty="L1").book
        # A book where *everything* is broken must trip every registered check.
        broken = _corrupt_everything(book)
        found = set(violations_by_invariant(check_all(broken)))
        missing = sorted(set(CATALOGUE) - found)
        self.assertEqual(missing, [], f"checks that never fire: {missing}")

    def test_violation_signature_is_complete(self) -> None:
        signature = Violation(
            invariant_id="INV-04",
            entity_key="invoices:X",
            expected_delta_minor=100,
            currency="USD",
            direction="over",
            tolerance_minor=0,
        ).signature()
        self.assertEqual(
            set(signature),
            {
                "invariant_id",
                "entity_key",
                "expected_delta_minor",
                "currency",
                "direction",
                "tolerance_minor",
                "side_effect_class",
            },
        )
        self.assertIn(signature["direction"], {"over", "under", "mismatch", "invalid"})


class CleanBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_generator_config()
        cls.build = build_clean_book(master_seed="baseline", config=cls.config, difficulty="L2")
        cls.book = cls.build.book

    def test_clean_twin_has_zero_violations(self) -> None:
        self.assertEqual(check_all(self.book), [])

    def test_each_check_individually_passes_on_clean_twin(self) -> None:
        for invariant_id, (name, check) in CATALOGUE.items():
            with self.subTest(invariant=invariant_id, name=name):
                self.assertEqual(check(invariant_id and self.book), [])

    def test_check_all_is_deterministically_ordered(self) -> None:
        broken = _corrupt_everything(self.book)
        first = [violation.sort_key() for violation in check_all(broken)]
        second = [violation.sort_key() for violation in check_all(broken)]
        self.assertEqual(first, second)

    def test_open_balance_matches_documents(self) -> None:
        balances = invoice_open_balances(self.book)
        self.assertEqual(len(balances), len(self.book.invoices))
        for balance in balances.values():
            self.assertEqual(
                balance.remaining_minor,
                balance.total_minor - balance.credited_minor - balance.allocated_minor,
            )


class NegativeVectorTests(unittest.TestCase):
    """One targeted corruption per invariant: the check must catch its own bug."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_generator_config()
        cls.book = build_clean_book(
            master_seed="negative-vectors", config=cls.config, difficulty="L2"
        ).book

    # ---------------------------------------------------------------- helpers
    def _assert_finds(self, broken, invariant_id: str) -> list[Violation]:
        violations = check_all(broken)
        found = [v for v in violations if v.invariant_id == invariant_id]
        self.assertTrue(found, f"{invariant_id} not raised; got {sorted({v.invariant_id for v in violations})}")
        return found

    def _first_entry_with(self, predicate) -> int:
        for index, entry in enumerate(self.book.journal_entries):
            if predicate(entry):
                return index
        self.fail("no matching journal entry in the fixture")

    def _replace_entry(self, index: int, **changes):
        entries = list(self.book.journal_entries)
        entries[index] = replace(entries[index], **changes)
        return self.book.with_rows("journal_entries", entries)

    # ------------------------------------------------------------ INV-01..05
    def test_inv01_unbalanced_entry(self) -> None:
        index = self._first_entry_with(lambda entry: len(entry.lines) >= 2)
        entry = self.book.journal_entries[index]
        line = replace(entry.lines[0], debit_minor=entry.lines[0].debit_minor + 1000)
        broken = self._replace_entry(index, lines=(line, *entry.lines[1:]))
        self._assert_finds(broken, "INV-01")

    def test_inv02_trial_balance_drift(self) -> None:
        index = self._first_entry_with(lambda entry: len(entry.lines) >= 2)
        entry = self.book.journal_entries[index]
        lines = []
        for position, line in enumerate(entry.lines):
            if position == 0:
                lines.append(replace(line, functional_debit_minor=line.functional_debit_minor + 777))
            else:
                lines.append(line)
        # Keep the entry internally balanced in transaction currency so only the
        # functional trial balance is affected.
        broken = self._replace_entry(index, lines=tuple(lines))
        self._assert_finds(broken, "INV-02")

    def test_inv03_receivable_ledger_drift(self) -> None:
        receivable = self.book.account_by_role("receivable").account_id
        index = self._first_entry_with(
            lambda entry: any(line.account_id == receivable for line in entry.lines)
        )
        entry = self.book.journal_entries[index]
        lines = tuple(
            replace(line, credit_minor=line.credit_minor + 500) if line.account_id == receivable
            else line
            for line in entry.lines
        )
        broken = self._replace_entry(index, lines=lines)
        self._assert_finds(broken, "INV-03")

    def test_inv04_overpayment(self) -> None:
        payment = next(
            (p for p in self.book.payments if p.allocations and p.amount_minor > 100),
            None,
        )
        assert payment is not None
        allocation = replace(
            payment.allocations[0],
            amount_minor=payment.allocations[0].amount_minor + 10_000_000,
        )
        payments = [
            replace(p, allocations=(allocation,)) if p.pay_id == payment.pay_id else p
            for p in self.book.payments
        ]
        broken = self.book.with_rows("payments", payments)
        self._assert_finds(broken, "INV-04")

    def test_inv05_aging_inconsistency(self) -> None:
        """A PAID invoice whose payment was removed is an aging contradiction."""
        balance = invoice_open_balances(self.book)
        paid = next(i for i in self.book.invoices if i.status == "PAID")
        # Remove the payments behind it: the invoice still claims PAID while its
        # balance reopens, which is exactly an aging/status contradiction.
        payments = [
            replace(p, allocations=tuple(
                a for a in p.allocations if a.document_id != paid.doc_id
            ))
            for p in self.book.payments
        ]
        broken = self.book.with_rows("payments", payments)
        self.assertGreater(invoice_open_balances(broken)[paid.doc_id].remaining_minor, 0)
        found = self._assert_finds(broken, "INV-05")
        self.assertTrue(any("overdue open amount" in v.detail for v in found))

    # ------------------------------------------------------------ INV-06..10
    def test_inv06_bank_match_amount(self) -> None:
        line = next(b for b in self.book.bank_lines if b.matched_payment_id is not None)
        lines = [
            replace(b, amount_minor=b.amount_minor + 5) if b.bank_line_id == line.bank_line_id else b
            for b in self.book.bank_lines
        ]
        broken = self.book.with_rows("bank_lines", lines)
        self._assert_finds(broken, "INV-06")

    def test_inv07_fx_policy_violation(self) -> None:
        index = self._first_entry_with(
            lambda entry: any(line.currency != "KZT" for line in entry.lines)
        )
        entry = self.book.journal_entries[index]
        lines = tuple(
            replace(line, fx_rate_decimal=line.fx_rate_decimal * 2)
            if line.currency != "KZT" else line
            for line in entry.lines
        )
        broken = self._replace_entry(index, lines=lines)
        self._assert_finds(broken, "INV-07")

    def test_inv08_functional_recalculation(self) -> None:
        index = self._first_entry_with(lambda entry: any(line.debit_minor for line in entry.lines))
        entry = self.book.journal_entries[index]
        lines = tuple(
            replace(line, functional_debit_minor=line.functional_debit_minor + 123)
            if line.debit_minor else line
            for line in entry.lines
        )
        broken = self._replace_entry(index, lines=lines)
        self._assert_finds(broken, "INV-08")

    def test_inv09_cutoff_shift(self) -> None:
        index = self._first_entry_with(
            lambda entry: any(
                line.account_id == self.book.policy["revenue_account_id"] for line in entry.lines
            )
        )
        entry = self.book.journal_entries[index]
        broken = self._replace_entry(index, posting_period="1999-M01")
        self._assert_finds(broken, "INV-09")
        self.assertTrue(entry.posting_period != "1999-M01")

    def test_inv10_period_totals(self) -> None:
        index = self._first_entry_with(lambda entry: True)
        broken = self._replace_entry(index, posting_period="1999-M12")
        self._assert_finds(broken, "INV-10")

    # ----------------------------------------------------------- INV-11..17
    def test_inv11_duplicate_id(self) -> None:
        invoices = list(self.book.invoices)
        invoices[1] = replace(invoices[1], doc_id=invoices[0].doc_id)
        broken = self.book.with_rows("invoices", invoices)
        self._assert_finds(broken, "INV-11")

    def test_inv11_cross_table_id_collision(self) -> None:
        payment = self.book.payments[0]
        invoice_id = self.book.invoices[0].doc_id
        payments = [replace(payment, pay_id=invoice_id), *self.book.payments[1:]]
        broken = self.book.with_rows("payments", payments)
        found = self._assert_finds(broken, "INV-11")
        self.assertTrue(any("reused across tables" in v.detail for v in found))

    def test_inv12_unresolved_reference(self) -> None:
        index = self._first_entry_with(lambda entry: entry.source_document_id is not None)
        broken = self._replace_entry(index, source_document_id="DOC-DOES-NOT-EXIST")
        self._assert_finds(broken, "INV-12")

    def test_inv13_unregistered_currency(self) -> None:
        index = self._first_entry_with(lambda entry: True)
        entry = self.book.journal_entries[index]
        lines = tuple(replace(line, currency="XYZ") for line in entry.lines)
        broken = self._replace_entry(index, lines=lines)
        found = self._assert_finds(broken, "INV-13")
        self.assertTrue(any("unregistered currency XYZ" in v.detail for v in found))

    def test_inv14_timestamp_without_offset(self) -> None:
        index = self._first_entry_with(lambda entry: True)
        broken = self._replace_entry(index, timestamp="2025-01-01T00:00:00")
        self._assert_finds(broken, "INV-14")

    def test_inv15_allocation_exceeds_payment(self) -> None:
        payment = self.book.payments[0]
        allocation = replace(payment.allocations[0], amount_minor=payment.amount_minor + 1000)
        payments = [
            replace(p, allocations=(allocation,)) if p.pay_id == payment.pay_id else p
            for p in self.book.payments
        ]
        broken = self.book.with_rows("payments", payments)
        self._assert_finds(broken, "INV-15")

    def test_inv16_credit_note_over_cap(self) -> None:
        note = self.book.credit_notes[0]
        invoice = self.book.invoice(note.invoice_id)
        notes = [
            replace(note, amount_minor=invoice.total_minor)
            if n.credit_note_id == note.credit_note_id else n
            for n in self.book.credit_notes
        ]
        broken = self.book.with_rows("credit_notes", notes)
        found = self._assert_finds(broken, "INV-16")
        self.assertTrue(any(v.direction == "over" for v in found))

    def test_inv17_status_mismatch(self) -> None:
        invoice = self.book.invoices[0]
        wrong = "PAID" if invoice.status != "PAID" else "OPEN"
        invoices = [
            replace(i, status=wrong) if i.doc_id == invoice.doc_id else i
            for i in self.book.invoices
        ]
        broken = self.book.with_rows("invoices", invoices)
        self._assert_finds(broken, "INV-17")


def _corrupt_everything(book):
    """Break one row per invariant family so every registered check must fire."""
    receivable = book.account_by_role("receivable").account_id

    # INV-01 / INV-08: unbalanced entry with a wrong functional amount.
    entries = list(book.journal_entries)
    first = entries[0]
    entries[0] = replace(
        first,
        lines=tuple(
            replace(line, debit_minor=line.debit_minor + 1000)
            if line.debit_minor else line
            for line in first.lines
        ),
    )
    # INV-02: functional drift on another entry (kept transaction-balanced).
    second_index = next(i for i, entry in enumerate(entries) if i != 0 and len(entry.lines) >= 2)
    second = entries[second_index]
    entries[second_index] = replace(
        second,
        lines=tuple(
            replace(line, functional_debit_minor=line.functional_debit_minor + 999)
            if position == 0 else line
            for position, line in enumerate(second.lines)
        ),
    )
    # INV-03: receivable ledger drift.
    third_index = next(
        i for i, entry in enumerate(entries)
        if any(line.account_id == receivable and line.credit_minor for line in entry.lines)
    )
    third = entries[third_index]
    entries[third_index] = replace(
        third,
        lines=tuple(
            replace(line, credit_minor=line.credit_minor + 500)
            if line.account_id == receivable else line
            for line in third.lines
        ),
    )
    # INV-07: wrong rate on a foreign-currency line.
    fourth_index = next(
        i for i, entry in enumerate(entries)
        if any(line.currency != "KZT" and line.fx_rate_decimal for line in entry.lines)
    )
    fourth = entries[fourth_index]
    entries[fourth_index] = replace(
        fourth,
        lines=tuple(
            replace(line, fx_rate_decimal=line.fx_rate_decimal * 3)
            if line.currency != "KZT" else line
            for line in fourth.lines
        ),
    )
    # INV-09 / INV-10: wrong posting period on a recognition entry. It must be a
    # *different* entry from the one that loses its timestamp below, otherwise
    # INV-14 makes that entry unreadable for the period checks too.
    used = {0, second_index, third_index, fourth_index}
    fifth_index = next(
        i for i, entry in enumerate(entries)
        if i not in used
        and any(line.account_id == book.policy["revenue_account_id"] for line in entry.lines)
    )
    entries[fifth_index] = replace(entries[fifth_index], posting_period="1999-M01")
    # INV-12 / INV-13 / INV-14: bad reference, currency and timestamp.
    broken_book = book.with_rows("journal_entries", entries)
    entries = list(broken_book.journal_entries)
    used.add(fifth_index)
    sixth_index = next(
        i for i, entry in enumerate(entries)
        if i not in used and entry.source_document_id is not None
    )
    entries[sixth_index] = replace(
        entries[sixth_index],
        source_document_id="DOC-MISSING",
        timestamp="2025-01-01T00:00:00",
        lines=tuple(replace(line, currency="XYZ") for line in entries[sixth_index].lines),
    )
    broken_book = broken_book.with_rows("journal_entries", entries)

    # INV-04 / INV-15: an allocation larger than its payment and beyond the invoice.
    payment = broken_book.payments[0]
    allocation = replace(payment.allocations[0], amount_minor=payment.amount_minor + 50_000_000)
    payments = [
        replace(p, allocations=(allocation,)) if p.pay_id == payment.pay_id else p
        for p in broken_book.payments
    ]
    broken_book = broken_book.with_rows("payments", payments)

    # INV-05 / INV-17: PAID status with an open amount and a far-future due date.
    open_invoice = next(
        balance.doc_id for balance in invoice_open_balances(broken_book).values()
        if balance.remaining_minor > 0
    )
    far_future = (parse_timestamp(broken_book.invoice(open_invoice).due_timestamp)
                  + timedelta(days=3650)).isoformat()
    invoices = [
        replace(i, status="PAID", due_timestamp=far_future) if i.doc_id == open_invoice else i
        for i in broken_book.invoices
    ]
    broken_book = broken_book.with_rows("invoices", invoices)

    # INV-06: bank line amount mismatch.
    bank_line = next(b for b in broken_book.bank_lines if b.matched_payment_id is not None)
    lines = [
        replace(b, amount_minor=b.amount_minor + 5) if b.bank_line_id == bank_line.bank_line_id else b
        for b in broken_book.bank_lines
    ]
    broken_book = broken_book.with_rows("bank_lines", lines)

    # INV-16: credit note above the configured cap.
    note = broken_book.credit_notes[0]
    invoice = broken_book.invoice(note.invoice_id)
    notes = [
        replace(note, amount_minor=invoice.total_minor)
        if n.credit_note_id == note.credit_note_id else n
        for n in broken_book.credit_notes
    ]
    broken_book = broken_book.with_rows("credit_notes", notes)

    # INV-11: duplicated invoice id (cross-table reuse). Done last: renaming a
    # document breaks lookups for everything that referred to it.
    invoices = list(broken_book.invoices)
    invoices[0] = replace(invoices[0], doc_id=broken_book.payments[0].pay_id)
    return broken_book.with_rows("invoices", invoices)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
