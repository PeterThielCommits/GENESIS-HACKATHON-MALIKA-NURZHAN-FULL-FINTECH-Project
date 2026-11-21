"""Bank lines generation (contract 8.3, bank_lines; INV-06)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gen.company import CompanyProfile
from gen.ids import IDFactory
from gen.payments import Payment
from gen.rng import NamespacedRNG
from gen.text import bank_line_reference_text


@dataclass
class BankLine:
    bank_line_id: str
    timestamp: str
    amount_minor: int
    currency: str
    direction: str
    reference_text: str
    matched_payment_id: str | None
    bank_account_id: str

    def to_public(self) -> dict[str, Any]:
        return {
            "bank_line_id": self.bank_line_id,
            "timestamp": self.timestamp,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "direction": self.direction,
            "reference_text": self.reference_text,
            "matched_payment_id": self.matched_payment_id,
            "bank_account_id": self.bank_account_id,
        }


def bank_line_sort_key(bl: BankLine) -> tuple[str, str]:
    return (bl.bank_line_id, bl.timestamp)


def generate_bank_lines(
    rng: NamespacedRNG,
    id_factory: IDFactory,
    company: CompanyProfile,
    payments: list[Payment],
) -> list[BankLine]:
    """Generate one bank line per payment (matched; INV-06 consistency)."""
    bank_account_id = id_factory.next_ba_id()
    lines = []
    for pay in payments:
        cp_name = _cp_name(rng, company, pay.counterparty_id)
        bl_id = id_factory.next_bank_line_id()
        lines.append(BankLine(
            bank_line_id=bl_id,
            timestamp=pay.timestamp,
            amount_minor=pay.amount_minor,
            currency=pay.currency,
            direction="credit",
            reference_text=bank_line_reference_text(rng, "ru", bl_id, pay.pay_id, cp_name),
            matched_payment_id=pay.pay_id,
            bank_account_id=bank_account_id,
        ))
    return sorted(lines, key=bank_line_sort_key)


def _cp_name(rng: NamespacedRNG, company: CompanyProfile, counterparty_id: str) -> str:
    # Counterparty names are only used for synthetic reference text.
    from gen.counterparties import _CP_NAMES
    return rng.choice(_CP_NAMES)
