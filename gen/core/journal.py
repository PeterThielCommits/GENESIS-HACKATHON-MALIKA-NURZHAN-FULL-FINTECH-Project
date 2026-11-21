"""Shared journal-line and document-status helpers (used by clean history and operators).

Keeping this in one place means a mutated record is built by *the same code path*
as a clean record — the operator cannot accidentally produce a differently shaped
line, a float amount or a foreign timestamp (REQ-ERR-003).
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any, Mapping, Sequence

from contracts.models import Invoice, JournalLine, Payment, CreditNote
from core.money import convert_minor
from gen.twins import Book


def build_line(
    *,
    line_id: str,
    account_id: str,
    currency: str,
    rate: Decimal,
    functional: str,
    rounding_mode: str,
    counterparty_id: str | None = None,
    analytic_tag: str | None = None,
    debit: int = 0,
    credit: int = 0,
) -> JournalLine:
    """Create a balanced, exponent-aware journal line."""
    if debit and credit:
        raise ValueError("a journal line carries either debit or credit, not both")
    functional_debit = (
        convert_minor(debit, currency, functional, rate, mode=rounding_mode).amount_minor
        if debit
        else 0
    )
    functional_credit = (
        convert_minor(credit, currency, functional, rate, mode=rounding_mode).amount_minor
        if credit
        else 0
    )
    return JournalLine(
        line_id=line_id,
        account_id=account_id,
        debit_minor=debit,
        credit_minor=credit,
        currency=currency,
        fx_rate_decimal=rate,
        functional_debit_minor=functional_debit,
        functional_credit_minor=functional_credit,
        counterparty_id=counterparty_id,
        analytic_tag=analytic_tag,
    )


def credited_totals(credit_notes: Sequence[CreditNote]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for note in credit_notes:
        totals[note.invoice_id] = totals.get(note.invoice_id, 0) + note.amount_minor
    return totals


def allocated_totals(payments: Sequence[Payment]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for payment in payments:
        for allocation in payment.allocations:
            totals[allocation.document_id] = (
                totals.get(allocation.document_id, 0) + allocation.amount_minor
            )
    return totals


def derive_status(invoice: Invoice, credited_minor: int, allocated_minor: int) -> str:
    """Single source of truth for the stored document status (INV-17)."""
    if invoice.status == "VOID":
        return "VOID"
    remaining = invoice.total_minor - credited_minor - allocated_minor
    if remaining < 0:
        return "OVERPAID"
    if remaining == 0:
        if allocated_minor:
            return "PAID"
        return "CREDITED" if credited_minor else "OPEN"
    if allocated_minor or credited_minor:
        return "PARTIALLY_PAID"
    return "OPEN"


def recompute_invoice_statuses(book: Book) -> Book:
    """Return a copy of ``book`` with every invoice status re-derived."""
    credited = credited_totals(book.credit_notes)
    allocated = allocated_totals(book.payments)
    updated: list[Invoice] = []
    for invoice in book.invoices:
        status = derive_status(
            invoice, credited.get(invoice.doc_id, 0), allocated.get(invoice.doc_id, 0)
        )
        updated.append(replace(invoice, status=status))
    return book.with_rows("invoices", updated)


def invoice_payable_minor(invoice: Invoice, credited_minor: int = 0) -> int:
    """Amount a policy-compliant settlement may still settle for this document."""
    return max(0, invoice.total_minor - credited_minor)


def open_invoices_for(book: Book, counterparty_id: str, currency: str) -> list[Invoice]:
    """Open invoices of a counterparty in a currency, deterministically ordered."""
    credited = credited_totals(book.credit_notes)
    allocated = allocated_totals(book.payments)
    result: list[Invoice] = []
    for invoice in book.invoices:
        if invoice.counterparty_id != counterparty_id or invoice.currency != currency:
            continue
        if invoice.status == "VOID":
            continue
        remaining = (
            invoice.total_minor
            - credited.get(invoice.doc_id, 0)
            - allocated.get(invoice.doc_id, 0)
        )
        if remaining > 0:
            result.append(invoice)
    return sorted(result, key=lambda item: (item.issue_timestamp, item.doc_id))


def payment_affecting(book: Book, document_id: str) -> list[Payment]:
    """Payments that allocate to ``document_id`` (deterministic order)."""
    return [
        payment
        for payment in book.payments
        if any(allocation.document_id == document_id for allocation in payment.allocations)
    ]


def document_currency(book: Book, document_id: str) -> str:
    return book.invoice(document_id).currency


def describe_payment(payment: Payment) -> dict[str, Any]:
    return {
        "pay_id": payment.pay_id,
        "amount_minor": payment.amount_minor,
        "currency": payment.currency,
        "allocated_minor": payment.allocated_minor,
        "documents": sorted({allocation.document_id for allocation in payment.allocations}),
    }


def as_mapping(row: Any) -> Mapping[str, Any]:
    return row.to_row()
