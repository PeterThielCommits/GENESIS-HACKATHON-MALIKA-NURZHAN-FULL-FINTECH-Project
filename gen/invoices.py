"""Invoice generation (contract 8.3, invoices and line_items)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gen.calendar import add_days, ts_in_period
from gen.company import CompanyProfile
from gen.counterparties import Counterparty
from gen.ids import IDFactory
from gen.rng import NamespacedRNG
from gen.text import pick_language, invoice_line_description


@dataclass
class InvoiceLine:
    line_id: str
    description: str
    amount_minor: int
    currency: str

    def to_public(self) -> dict[str, Any]:
        return {
            "line_id": self.line_id,
            "description": self.description,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
        }


@dataclass
class Invoice:
    doc_id: str
    counterparty_id: str
    issue_timestamp: str
    service_start: str
    service_end: str | None
    due_timestamp: str
    currency: str
    total_minor: int
    tax_minor: int
    line_items: list[InvoiceLine]
    status: str

    def to_public(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "counterparty_id": self.counterparty_id,
            "issue_timestamp": self.issue_timestamp,
            "service_start": self.service_start,
            "service_end": self.service_end,
            "due_timestamp": self.due_timestamp,
            "currency": self.currency,
            "total_minor": self.total_minor,
            "tax_minor": self.tax_minor,
            "line_items": [l.to_public() for l in self.line_items],
            "status": self.status,
        }


def invoice_sort_key(inv: Invoice) -> tuple[str, str]:
    return (inv.doc_id, inv.issue_timestamp)


def _split_amount(rng: NamespacedRNG, total: int, n_items: int) -> list[int]:
    """Split ``total`` into ``n_items`` non-negative parts summing to total."""
    if n_items <= 0:
        return []
    if n_items == 1:
        return [total]
    weights = [rng.randint(1, 10) for _ in range(n_items)]
    tw = sum(weights)
    amounts: list[int] = []
    remaining = total
    for w in weights[:-1]:
        amt = remaining * w // tw
        amounts.append(amt)
        remaining -= amt
    amounts.append(remaining)
    # Fix rounding drift so the sum is exact and values stay non-negative.
    while sum(amounts) != total:
        diff = total - sum(amounts)
        moved = False
        for i in range(len(amounts)):
            if amounts[i] + diff >= 0:
                amounts[i] += diff
                moved = True
                break
        if not moved:  # pragma: no cover - safety
            return [total]
    if any(a < 0 for a in amounts):  # pragma: no cover - safety
        return [total]
    return amounts


def generate_invoices(
    rng: NamespacedRNG,
    id_factory: IDFactory,
    company: CompanyProfile,
    counterparties: list[Counterparty],
    periods: list[str],
    n_invoices: int,
    min_amount: int = 500,
    max_amount: int = 50000,
) -> list[Invoice]:
    """Generate clean invoices with realistic multilingual line items."""
    if n_invoices <= 0:
        return []
    invoices: list[Invoice] = []
    for _ in range(n_invoices):
        period = rng.choice(periods)
        issue_ts = ts_in_period(rng, company.timezone, period)
        cp = rng.choice(counterparties)
        lang = pick_language(rng, company)
        ccy = rng.choice(company.supported_currencies)
        total = rng.randint(min_amount, max_amount)
        tax_minor = 0  # clean episodes: tax is captured in tax_minor=0 lines
        due_ts = add_days(issue_ts, rng.randint(20, 45))
        service_end = add_days(issue_ts, rng.randint(1, 90)) if rng.random() < 0.5 else None
        doc_id = id_factory.next_inv_id()
        amounts = _split_amount(rng, total, rng.randint(1, 3))
        line_items = [
            InvoiceLine(
                line_id=id_factory.next_invoice_line_id(),
                description=invoice_line_description(
                    rng, lang, doc_id, cp.name_variants[lang],
                    _item_descriptor(lang, rng), ccy, issue_ts, service_end,
                ),
                amount_minor=amt,
                currency=ccy,
            )
            for amt in amounts
            if amt > 0 or len(amounts) == 1
        ] or [InvoiceLine(line_id=id_factory.next_invoice_line_id(),
                         description="Invoice item", amount_minor=total, currency=ccy)]
        invoices.append(Invoice(
            doc_id=doc_id,
            counterparty_id=cp.counterparty_id,
            issue_timestamp=issue_ts,
            service_start=issue_ts,
            service_end=service_end,
            due_timestamp=due_ts,
            currency=ccy,
            total_minor=total,
            tax_minor=tax_minor,
            line_items=line_items,
            status="open",
        ))
    return sorted(invoices, key=invoice_sort_key)


def _item_descriptor(lang: str, rng: NamespacedRNG) -> str:
    from gen.text import _template_set  # reuse vocabulary table
    return rng.choice(_template_set(lang)[4])
