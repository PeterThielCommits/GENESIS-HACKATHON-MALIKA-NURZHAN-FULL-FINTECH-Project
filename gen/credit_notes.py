"""Credit note generation (contract 8.3, credit_notes)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gen.calendar import period_for_timestamp, ts_in_period
from gen.ids import IDFactory
from gen.invoices import Invoice
from gen.rng import NamespacedRNG


@dataclass
class CreditNote:
    credit_note_id: str
    invoice_id: str
    counterparty_id: str
    timestamp: str
    amount_minor: int
    currency: str
    reason_code: str

    def to_public(self) -> dict[str, Any]:
        return {
            "credit_note_id": self.credit_note_id,
            "invoice_id": self.invoice_id,
            "counterparty_id": self.counterparty_id,
            "timestamp": self.timestamp,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "reason_code": self.reason_code,
        }


def credit_note_sort_key(cn: CreditNote) -> tuple[str, str]:
    return (cn.credit_note_id, cn.timestamp)


def generate_credit_notes(
    rng: NamespacedRNG,
    id_factory: IDFactory,
    invoices: list[Invoice],
    prob: float = 0.15,
) -> list[CreditNote]:
    """Generate clean credit notes against invoices (INV-16: CN <= total)."""
    if prob <= 0 or not invoices:
        return []
    cns: list[CreditNote] = []
    for inv in invoices:
        if rng.random() >= prob or inv.total_minor <= 0:
            continue
        amount = rng.randint(100, inv.total_minor)
        if amount <= 0:
            continue
        ts = ts_in_period(rng, "Asia/Almaty", period_for_timestamp(inv.issue_timestamp, "Asia/Almaty"))
        cns.append(CreditNote(
            credit_note_id=id_factory.next_credit_note_id(),
            invoice_id=inv.doc_id,
            counterparty_id=inv.counterparty_id,
            timestamp=ts,
            amount_minor=amount,
            currency=inv.currency,
            reason_code=rng.choice(["ADJUSTMENT", "ERROR_CORRECTION", "OVERPAID_CORRECTION", "CANCELED_GOODS"]),
        ))
    return sorted(cns, key=credit_note_sort_key)
