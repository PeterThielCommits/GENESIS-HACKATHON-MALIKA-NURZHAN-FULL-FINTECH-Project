"""Journal entry generation (contract 8.3, journal_entries; INV-01..02)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gen.calendar import period_for_timestamp
from gen.chart import (
    AP_ACCOUNT_ID,
    CASH_ACCOUNT_ID,
    PURCHASES_ACCOUNT_ID,
)
from gen.company import CompanyProfile
from gen.fx import rate_for_event
from gen.ids import IDFactory
from gen.invoices import Invoice
from gen.credit_notes import CreditNote
from gen.payments import Payment
from gen.rng import NamespacedRNG


@dataclass
class JELine:
    line_id: str
    account_id: str
    debit_minor: int
    credit_minor: int
    currency: str
    fx_rate_decimal: str
    functional_debit_minor: int
    functional_credit_minor: int
    counterparty_id: str | None
    analytic_tag: str | None

    def to_public(self) -> dict[str, Any]:
        return {
            "line_id": self.line_id,
            "account_id": self.account_id,
            "debit_minor": self.debit_minor,
            "credit_minor": self.credit_minor,
            "currency": self.currency,
            "fx_rate_decimal": self.fx_rate_decimal,
            "functional_debit_minor": self.functional_debit_minor,
            "functional_credit_minor": self.functional_credit_minor,
            "counterparty_id": self.counterparty_id,
            "analytic_tag": self.analytic_tag,
        }


@dataclass
class JournalEntry:
    je_id: str
    timestamp: str
    posting_period: str
    source_document_id: str | None
    description: str
    lines: list[JELine]

    def to_public(self) -> dict[str, Any]:
        return {
            "je_id": self.je_id,
            "timestamp": self.timestamp,
            "posting_period": self.posting_period,
            "source_document_id": self.source_document_id,
            "description": self.description,
            "lines": [l.to_public() for l in self.lines],
        }


def journal_sort_key(je: JournalEntry) -> str:
    return je.je_id


def build_journal_entries(
    rng: NamespacedRNG,
    id_factory: IDFactory,
    company: CompanyProfile,
    invoices: list[Invoice],
    credit_notes: list[CreditNote],
    payments: list[Payment],
    fx_rates: list,
) -> list[JournalEntry]:
    """Build balanced JEs from clean invoices/payments/credit notes."""
    entries: list[JournalEntry] = []
    for inv in invoices:
        entries.append(_invoice_je(id_factory, company, inv, fx_rates))
    for cn in credit_notes:
        entries.append(_credit_note_je(id_factory, company, cn, fx_rates))
    for pay in payments:
        entries.append(_payment_je(id_factory, company, pay, fx_rates))
    return sorted(entries, key=journal_sort_key)


def _invoice_je(
    id_factory: IDFactory,
    company: CompanyProfile,
    inv: Invoice,
    fx_rates: list,
) -> JournalEntry:
    tz = company.timezone
    rate = rate_for_event(fx_rates, company.functional_currency, inv.currency, inv.issue_timestamp)
    from gen.money import convert_minor

    f_total, _ = convert_minor(inv.total_minor, inv.currency, company.functional_currency, rate)
    return JournalEntry(
        je_id=id_factory.next_je_id(),
        timestamp=inv.issue_timestamp,
        posting_period=period_for_timestamp(inv.issue_timestamp, tz),
        source_document_id=inv.doc_id,
        description=f"Invoice {inv.doc_id} from {inv.counterparty_id}",
        lines=[
            JELine(
                line_id=id_factory.next_journal_line_id(),
                account_id=PURCHASES_ACCOUNT_ID,
                debit_minor=inv.total_minor,
                credit_minor=0,
                currency=inv.currency,
                fx_rate_decimal=f"{rate:f}",
                functional_debit_minor=f_total,
                functional_credit_minor=0,
                counterparty_id=inv.counterparty_id,
                analytic_tag="purchase",
            ),
            JELine(
                line_id=id_factory.next_journal_line_id(),
                account_id=AP_ACCOUNT_ID,
                debit_minor=0,
                credit_minor=inv.total_minor,
                currency=inv.currency,
                fx_rate_decimal=f"{rate:f}",
                functional_debit_minor=0,
                functional_credit_minor=f_total,
                counterparty_id=inv.counterparty_id,
                analytic_tag="payables",
            ),
        ],
    )


def _payment_je(
    id_factory: IDFactory,
    company: CompanyProfile,
    pay: Payment,
    fx_rates: list,
) -> JournalEntry:
    tz = company.timezone
    from gen.money import convert_minor

    lines: list[JELine] = []
    total_functional = 0
    for alloc in pay.allocations:
        rate = rate_for_event(fx_rates, company.functional_currency, pay.currency, alloc.allocation_timestamp)
        f_alloc, _ = convert_minor(alloc.amount_minor, pay.currency, company.functional_currency, rate)
        total_functional += f_alloc
        lines.append(JELine(
            line_id=id_factory.next_journal_line_id(),
            account_id=AP_ACCOUNT_ID,
            debit_minor=alloc.amount_minor,
            credit_minor=0,
            currency=pay.currency,
            fx_rate_decimal=f"{rate:f}",
            functional_debit_minor=f_alloc,
            functional_credit_minor=0,
            counterparty_id=pay.counterparty_id,
            analytic_tag="payable",
        ))
    # Cash line: CR Cash = total payment, functional = sum of allocation functionals.
    lines.append(JELine(
        line_id=id_factory.next_journal_line_id(),
        account_id=CASH_ACCOUNT_ID,
        debit_minor=0,
        credit_minor=pay.amount_minor,
        currency=pay.currency,
        fx_rate_decimal="",
        functional_debit_minor=0,
        functional_credit_minor=total_functional,
        counterparty_id=pay.counterparty_id,
        analytic_tag="cash",
    ))
    return JournalEntry(
        je_id=id_factory.next_je_id(),
        timestamp=pay.timestamp,
        posting_period=period_for_timestamp(pay.timestamp, tz),
        source_document_id=None,
        description=f"Payment {pay.pay_id} to {pay.counterparty_id}",
        lines=lines,
    )


def _credit_note_je(
    id_factory: IDFactory,
    company: CompanyProfile,
    cn: CreditNote,
    fx_rates: list,
) -> JournalEntry:
    tz = company.timezone
    rate = rate_for_event(fx_rates, company.functional_currency, cn.currency, cn.timestamp)
    from gen.money import convert_minor

    f_cn, _ = convert_minor(cn.amount_minor, cn.currency, company.functional_currency, rate)
    return JournalEntry(
        je_id=id_factory.next_je_id(),
        timestamp=cn.timestamp,
        posting_period=period_for_timestamp(cn.timestamp, tz),
        source_document_id=cn.credit_note_id,
        description=f"Credit note {cn.credit_note_id} against {cn.invoice_id}",
        lines=[
            JELine(
                line_id=id_factory.next_journal_line_id(),
                account_id=AP_ACCOUNT_ID,
                debit_minor=cn.amount_minor,
                credit_minor=0,
                currency=cn.currency,
                fx_rate_decimal=f"{rate:f}",
                functional_debit_minor=f_cn,
                functional_credit_minor=0,
                counterparty_id=cn.counterparty_id,
                analytic_tag="payables",
            ),
            JELine(
                line_id=id_factory.next_journal_line_id(),
                account_id=PURCHASES_ACCOUNT_ID,
                debit_minor=0,
                credit_minor=cn.amount_minor,
                currency=cn.currency,
                fx_rate_decimal=f"{rate:f}",
                functional_debit_minor=0,
                functional_credit_minor=f_cn,
                counterparty_id=cn.counterparty_id,
                analytic_tag="purchase_adjustment",
            ),
        ],
    )
