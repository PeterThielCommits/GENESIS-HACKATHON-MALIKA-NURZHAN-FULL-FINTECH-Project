"""Payment generation (contract 8.3, payments and allocations)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gen.calendar import period_for_timestamp, ts_in_period
from gen.company import CompanyProfile
from gen.invoices import Invoice
from gen.ids import IDFactory
from gen.rng import NamespacedRNG


@dataclass
class Allocation:
    allocation_id: str
    document_id: str
    amount_minor: int
    allocation_timestamp: str

    def to_public(self) -> dict[str, Any]:
        return {
            "allocation_id": self.allocation_id,
            "document_id": self.document_id,
            "amount_minor": self.amount_minor,
            "allocation_timestamp": self.allocation_timestamp,
        }


@dataclass
class Payment:
    pay_id: str
    timestamp: str
    counterparty_id: str
    currency: str
    amount_minor: int
    allocations: list[Allocation]
    bank_reference: str | None
    payment_channel: str

    def to_public(self) -> dict[str, Any]:
        return {
            "pay_id": self.pay_id,
            "timestamp": self.timestamp,
            "counterparty_id": self.counterparty_id,
            "currency": self.currency,
            "amount_minor": self.amount_minor,
            "allocations": [a.to_public() for a in self.allocations],
            "bank_reference": self.bank_reference,
            "payment_channel": self.payment_channel,
        }


def payment_sort_key(pay: Payment) -> tuple[str, str]:
    return (pay.pay_id, pay.timestamp)


def _choose_invoice_timestamp(rng: NamespacedRNG, invoice: Invoice) -> str:
    return ts_in_period(rng, "Asia/Almaty", period_for_timestamp(invoice.issue_timestamp, "Asia/Almaty"))


def generate_payments(
    rng: NamespacedRNG,
    id_factory: IDFactory,
    company: CompanyProfile,
    invoices: list[Invoice],
    credit_notes: list,
    min_pay: int = 100,
) -> list[Payment]:
    """Generate clean payments: allocations sum to payment.amount_minor (INV-15)."""
    remaining = {inv.doc_id: inv.total_minor for inv in invoices}
    for cn in credit_notes:
        remaining[cn.invoice_id] = max(0, remaining.get(cn.invoice_id, 0) - cn.amount_minor)

    open_invs = [inv for inv in invoices if remaining[inv.doc_id] > 0]
    if not open_invs:
        return []
    n_payments = rng.randint(max(1, len(open_invs) // 4), max(1, len(open_invs) // 2))
    payments: list[Payment] = []
    for _ in range(n_payments):
        eligible = [inv for inv in invoices if remaining[inv.doc_id] > 0]
        if not eligible:
            break
        pay_amount = rng.randint(min_pay, remaining[eligible[0].doc_id])
        chosen = [rng.choice(eligible)]
        if rng.random() < 0.3:
            others = [i for i in eligible if i.doc_id != chosen[0].doc_id]
            if others:
                chosen.append(rng.choice(others))
        # Distribute pay_amount among chosen invoices: positive amounts, sum exact.
        splits = rng.sample(range(1, pay_amount + 1), len(chosen) - 1) if len(chosen) > 1 else []
        prev = 0
        amounts: list[int] = []
        for s in splits:
            amounts.append(s - prev)
            prev = s
        amounts.append(pay_amount - prev)
        if min(amounts) <= 0 or sum(amounts) != pay_amount:
            amounts = [pay_amount]
            chosen = chosen[:1]
        allocations = []
        for inv, amt in zip(chosen, amounts):
            alloc_ts = _choose_invoice_timestamp(rng, inv)
            allocations.append(Allocation(
                allocation_id=id_factory.next_allocation_id(),
                document_id=inv.doc_id,
                amount_minor=amt,
                allocation_timestamp=alloc_ts,
            ))
            remaining[inv.doc_id] -= amt
        payments.append(Payment(
            pay_id=id_factory.next_pay_id(),
            timestamp=allocations[0].allocation_timestamp,
            counterparty_id=chosen[0].counterparty_id,
            currency=chosen[0].currency,
            amount_minor=pay_amount,
            allocations=allocations,
            bank_reference=f"REF-{rng.getrandbits(32):08X}",
            payment_channel=rng.choice(["BANK_EFT", "SEPA", "ACH", "WIRE"]),
        ))
    return sorted(payments, key=payment_sort_key)
