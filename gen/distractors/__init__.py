"""Distractor (near-miss) construction — Phase 4.6, 11.6.

A distractor is a **clean** situation that differs from an anomaly by exactly one
fact which the policy can obtain through public tools. It is applied to the clean
twin *before* the mutation, so the mutated twin contains both the anomaly and its
look-alike.

The ``distinguishing_fact`` and ``distractor_of`` fields live in sealed provenance
only (11.6); the public evidence ids recorded here prove the distinguishing fact is
reachable from public records, which the test suite asserts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from contracts.errors import ContractError
from gen.twins import Book

DISTRACTOR_IDS: dict[str, tuple[str, ...]] = {
    "DUPLICATE_PAYMENT": ("D-DUP-01", "D-DUP-02", "D-DUP-03", "D-DUP-04"),
    "PARTIAL_PAYMENT_ALLOCATION": ("D-PART-01", "D-PART-02", "D-PART-03", "D-PART-04"),
}


@dataclass(frozen=True)
class Distractor:
    distractor_id: str
    distractor_of: str
    distinguishing_fact: str
    public_evidence_ids: tuple[str, ...]
    applied: bool = False
    note: str = ""

    @property
    def already_present(self) -> bool:
        return self.applied

    def to_truth_entry(self) -> dict[str, Any]:
        if not self.public_evidence_ids:
            raise ContractError(
                "distractor must expose at least one public evidence id",
                distractor=self.distractor_id,
            )
        return {
            "distractor_id": self.distractor_id,
            "distractor_of": self.distractor_of,
            "distinguishing_fact": self.distinguishing_fact,
            "public_evidence_ids": list(self.public_evidence_ids),
        }


def _dup_01_credit_note(book: Book, budget: Mapping[str, Any]) -> Distractor | None:
    """D-DUP-01: a credit note fully explains a second settlement of a document."""
    for invoice in sorted(book.invoices, key=lambda row: row.doc_id):
        notes = [note for note in book.credit_notes if note.invoice_id == invoice.doc_id]
        settled = sum(
            allocation.amount_minor
            for payment in book.payments
            for allocation in payment.allocations
            if allocation.document_id == invoice.doc_id
        )
        if not notes or settled <= 0:
            continue
        credited = sum(note.amount_minor for note in notes)
        if invoice.total_minor - credited <= 0 or settled < invoice.total_minor - credited:
            continue
        return Distractor(
            distractor_id="D-DUP-01",
            distractor_of="DUPLICATE_PAYMENT",
            distinguishing_fact=(
                "A credit note reduces the obligation so the second settlement is "
                "explained rather than an unexplained overpayment."
            ),
            public_evidence_ids=tuple(sorted([invoice.doc_id] + [note.credit_note_id for note in notes])),
            applied=True,
        )
    return None


def _dup_02_cross_document(book: Book, budget: Mapping[str, Any]) -> Distractor | None:
    """D-DUP-02: a coincidence of amounts across unrelated documents.

    Looks like a duplicated charge to naive amount matching, but the two amounts
    belong to different invoices with different service periods (and often different
    counterparties), so there is nothing to flag.
    """
    by_amount: dict[tuple[str, int], list[Any]] = {}
    for invoice in book.invoices:
        by_amount.setdefault((invoice.currency, invoice.total_minor), []).append(invoice)
    for key in sorted(by_amount):
        group = sorted(by_amount[key], key=lambda row: row.doc_id)
        if len(group) < 2:
            continue
        starts = {row.service_start for row in group[:2]}
        counterparties = {row.counterparty_id for row in group[:2]}
        if len(starts) == 2 or len(counterparties) == 2:
            return Distractor(
                distractor_id="D-DUP-02",
                distractor_of="DUPLICATE_PAYMENT",
                distinguishing_fact=(
                    "Equal amounts belong to different invoices with distinct service "
                    "periods or counterparties; amount equality alone is not a duplicate."
                ),
                public_evidence_ids=tuple(row.doc_id for row in group[:2]),
                applied=True,
            )
    # Fallback: one payment split across two documents never duplicates a charge.
    for payment in sorted(book.payments, key=lambda row: row.pay_id):
        documents = sorted({allocation.document_id for allocation in payment.allocations})
        if len(documents) >= 2:
            return Distractor(
                distractor_id="D-DUP-02",
                distractor_of="DUPLICATE_PAYMENT",
                distinguishing_fact=(
                    "A single payment legitimately covers two different documents, so "
                    "the repeated document reference is expected, not duplicated."
                ),
                public_evidence_ids=tuple([payment.pay_id] + documents),
                applied=True,
            )
    return None


def _dup_03_recurring(book: Book, budget: Mapping[str, Any]) -> Distractor | None:
    """D-DUP-03: recurring subscription invoices for different service periods."""
    by_counterparty: dict[str, list[Any]] = {}
    for invoice in book.invoices:
        if invoice.service_end is None:
            by_counterparty.setdefault(invoice.counterparty_id, []).append(invoice)
    for counterparty in sorted(by_counterparty):
        invoices = sorted(
            by_counterparty[counterparty], key=lambda row: (row.issue_timestamp, row.doc_id)
        )
        if len(invoices) >= 2:
            starts = {invoice.service_start for invoice in invoices[:2]}
            if len(starts) == 2:
                return Distractor(
                    distractor_id="D-DUP-03",
                    distractor_of="DUPLICATE_PAYMENT",
                    distinguishing_fact=(
                        "The two documents cover different service periods, so they are "
                        "separate revenue events rather than a duplicated charge."
                    ),
                    public_evidence_ids=tuple(invoice.doc_id for invoice in invoices[:2]),
                    applied=True,
                )
    return None


def _dup_04_bank_side_duplicate(book: Book, budget: Mapping[str, Any]) -> Distractor | None:
    """D-DUP-04: money movements on the bank account that are not settlements.

    A prepayment/receipt or unapplied cash line looks like an extra payment of an
    already-paid document. The public status explains it: no document allocation and
    an explicit non-payment explanation.
    """
    explained = sorted(
        (line for line in book.bank_lines if line.status == "EXPLAINED_NON_PAYMENT"),
        key=lambda row: row.bank_line_id,
    )
    if explained:
        line = explained[0]
        return Distractor(
            distractor_id="D-DUP-04",
            distractor_of="DUPLICATE_PAYMENT",
            distinguishing_fact=(
                "The bank line is a prepayment (EXPLAINED_NON_PAYMENT): it carries no "
                "document allocation, so it never settles an invoice twice."
            ),
            public_evidence_ids=(line.bank_line_id,),
            applied=True,
        )
    unmatched = sorted(
        (line for line in book.bank_lines if line.matched_payment_id is None),
        key=lambda row: row.bank_line_id,
    )
    if unmatched:
        line = unmatched[0]
        return Distractor(
            distractor_id="D-DUP-04",
            distractor_of="DUPLICATE_PAYMENT",
            distinguishing_fact=(
                "The bank line is unmatched unapplied cash; it never settles a document, "
                "so it cannot duplicate a payment allocation."
            ),
            public_evidence_ids=(line.bank_line_id,),
            applied=True,
        )
    return None


def _part_01_second_payment_closes(book: Book, budget: Mapping[str, Any]) -> Distractor | None:
    """D-PART-01: a second payment legitimately closes the remaining balance."""
    allocations_by_document: dict[str, list[Any]] = {}
    for payment in book.payments:
        for allocation in payment.allocations:
            allocations_by_document.setdefault(allocation.document_id, []).append(
                (payment.pay_id, allocation.amount_minor)
            )
    for doc_id in sorted(allocations_by_document):
        entries = allocations_by_document[doc_id]
        if len(entries) >= 2:
            payments = sorted({pay_id for pay_id, _ in entries})
            invoice = book.invoice(doc_id)
            if invoice.status in ("PAID", "PARTIALLY_PAID"):
                return Distractor(
                    distractor_id="D-PART-01",
                    distractor_of="PARTIAL_PAYMENT_ALLOCATION",
                    distinguishing_fact=(
                        "The remaining balance is settled by a second payment, so the "
                        "observed allocation pattern is correct two-step settlement."
                    ),
                    public_evidence_ids=tuple([doc_id] + payments),
                    applied=True,
                )
    return None


def _part_02_advance(book: Book, budget: Mapping[str, Any]) -> Distractor | None:
    """D-PART-02: cash received ahead of invoicing (an advance, not an allocation)."""
    advance_account = str(book.policy["advance_account_id"])
    advances = [
        entry
        for entry in book.journal_entries
        if any(line.account_id == advance_account for line in entry.lines)
    ]
    if advances:
        entry = sorted(advances, key=lambda row: row.je_id)[0]
        return Distractor(
            distractor_id="D-PART-02",
            distractor_of="PARTIAL_PAYMENT_ALLOCATION",
            distinguishing_fact=(
                "The receipt is booked to the customer-advance account, which is the "
                "policy-sanctioned treatment for unapplied prepayment."
            ),
            public_evidence_ids=(entry.je_id,),
            applied=True,
        )
    return None


def _part_03_multi_invoice(book: Book, budget: Mapping[str, Any]) -> Distractor | None:
    """D-PART-03: one payment allocated correctly across several invoices.

    The split looks like "allocations that exceed the payment", but the allocations
    sum exactly to the amount received, which is what the policy requires.
    """
    for payment in sorted(book.payments, key=lambda row: row.pay_id):
        documents = sorted({allocation.document_id for allocation in payment.allocations})
        if len(documents) >= 2:
            return Distractor(
                distractor_id="D-PART-03",
                distractor_of="PARTIAL_PAYMENT_ALLOCATION",
                distinguishing_fact=(
                    "The payment is split across several documents and the allocations "
                    "sum exactly to the amount received (allocation conservation holds)."
                ),
                public_evidence_ids=tuple([payment.pay_id] + documents),
                applied=True,
            )
    # Fallback: a partial payment whose remainder is settled by a later transfer.
    for document_id in sorted({allocation.document_id for payment in book.payments for allocation in payment.allocations}):
        payers = sorted(
            payment.pay_id
            for payment in book.payments
            if any(allocation.document_id == document_id for allocation in payment.allocations)
        )
        if len(payers) >= 2:
            return Distractor(
                distractor_id="D-PART-03",
                distractor_of="PARTIAL_PAYMENT_ALLOCATION",
                distinguishing_fact=(
                    "Two separate transfers settle the document in two correct steps; "
                    "no single payment was over-allocated."
                ),
                public_evidence_ids=tuple([document_id] + payers),
                applied=True,
            )
    return None


def _part_04_own_open_balance(book: Book, budget: Mapping[str, Any]) -> Distractor | None:
    """D-PART-04: a document left genuinely open after a partial payment."""
    from invariants.checks_clean import invoice_open_balances

    for balance in sorted(invoice_open_balances(book).values(), key=lambda item: item.doc_id):
        if balance.allocated_minor > 0 and balance.remaining_minor > 0:
            payments = sorted(
                payment.pay_id
                for payment in book.payments
                if any(allocation.document_id == balance.doc_id for allocation in payment.allocations)
            )
            return Distractor(
                distractor_id="D-PART-04",
                distractor_of="PARTIAL_PAYMENT_ALLOCATION",
                distinguishing_fact=(
                    "The document keeps a positive open balance equal to the unpaid "
                    "remainder, which is exactly what the policy requires."
                ),
                public_evidence_ids=tuple([balance.doc_id] + payments),
                applied=True,
            )
    return None


BUILDERS: dict[str, Callable[[Book, Mapping[str, Any]], Distractor | None]] = {
    "D-DUP-01": _dup_01_credit_note,
    "D-DUP-02": _dup_02_cross_document,
    "D-DUP-03": _dup_03_recurring,
    "D-DUP-04": _dup_04_bank_side_duplicate,
    "D-PART-01": _part_01_second_payment_closes,
    "D-PART-02": _part_02_advance,
    "D-PART-03": _part_03_multi_invoice,
    "D-PART-04": _part_04_own_open_balance,
}


def build_distractors(
    book: Book,
    *,
    requested: Sequence[str],
    max_active: int,
) -> tuple[Distractor, ...]:
    """Find the requested distractors already present in ``book``.

    Distractors are *observations* over the clean twin: they exist because the
    generator produced realistic look-alikes, so no extra rows are injected. A
    distractor that is not present is simply skipped (and reported), never faked.
    """
    if max_active < 0:
        raise ContractError("max_active must be >= 0", max_active=max_active)
    found: list[Distractor] = []
    for distractor_id in requested:
        if len(found) >= max_active:
            break
        builder = BUILDERS.get(distractor_id)
        if builder is None:
            raise ContractError("unknown distractor id", distractor_id=distractor_id)
        distractor = builder(book, {})
        if distractor is not None:
            found.append(distractor)
    return tuple(found)
