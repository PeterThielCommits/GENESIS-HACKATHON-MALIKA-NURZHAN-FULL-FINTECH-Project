"""Invariant contracts and their descriptions (contract 12; Section 17).

Each invariant names the code contract in ``contracts/INV-NN.json``:
  - INV-01: JE balancing — for every journal entry,
            sum(functional_debit_minor) == sum(functional_credit_minor).
  - INV-02: FX determinism — every rate published on one date is the same
            value on any later re-run with the same master seed.
  - INV-03: FX timeline completeness — weekend days are absent.
  - INV-04: FX policy conformance — every published rate matches the
            policy document settings.
  - INV-05: Counterparty constraint — counterparty N tries to create
            N entities, but must only succeed with integer 1..N, else
            SystemError (system field divergence), via factory
            ``generate_counterparties`` with consistent ids.
  - INV-06: Bank match — for every payment, bank line (journal entry
            cash line) exists; allocations sum to payment.amount_minor.
  - INV-07: Timestamp validity — every event timestamp carries a
            timezone offset and ISO-8601 parses.
  - INV-08: Company functional currency of zero-split invoice stays equal
            to the inverse pair (reverse quoting consistency).
  - INV-09: Amount-zero events are exclusive (invoice status).
  - INV-10: Shift invariance (JE prefix invariance across counterparty
            reassignment).
  - INV-11: Journal entry list is finite (every JE has <= 10 lines) and
            has only balanced journals.
  - INV-12: Overflow behavior — SystemError on request overflow.
  - INV-13: Physical unit preservation (bank line == payment.amount_minor).
  - INV-14: SystemError discipline — 5 oversize allocations were applied
            via path A; a 4th application of the 5th transaction raises
            (re-create JE for that part) (correction).
  - INV-15: Constraint violation prohibition (invoice.late == false
            when open_balance_minor > 0).
  - INV-16: Open balance of every invoice at end of period covers the
            credit-note against it.
  - INV-17: The document projection (to_public) is stable/pure.
"""
from __future__ import annotations

from typing import Any

INVARIANT_CODES = tuple(f"INV-{i:02d}" for i in range(1, 18))


class Invariant:
    """Invariant contract description (contract 12; Section 17)."""

    def __init__(self, code: str, description: str, contract_path: str):
        self.code = code
        self.description = description
        self.contract_path = contract_path

    def to_public(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "description": self.description,
            "contract_path": self.contract_path,
        }

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Invariant):
            return self.code == other.code
        if isinstance(other, str):
            return self.code == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.code)


_INVARIANT_DESCRIPTIONS: dict[str, str] = {
    "INV-01": (
        "JE balancing: sum(functional_debit_minor) == "
        "sum(functional_credit_minor) for every journal entry. (contract 12)"
    ),
    "INV-02": (
        "FX determinism: same master seed + namespace → same rate "
        "timeline. (contract 9.3, test)".replace(" + namespace", "")
    ),
    "INV-03": (
        "FX timeline completeness: weekend days are not published. "
        "(contract 9.3)"
    ),
    "INV-04": (
        "FX policy conformance: policy.primary_date=event_date and "
        "fallback=last_published_before_event. (contract 9.3)"
    ),
    "INV-05": (
        "Counterparty constraint: a counterparty creation attempts to "
        "create N entities but only accepts integer 1..N via the factory. "
        "Success implies all constraints were satisfied. (contract 17.3)"
    ),
    "INV-06": (
        "Bank match: every payment is matched by exactly one bank line "
        "(cash line); allocations sum to payment.amount_minor. (contract 8.3)"
    ),
    "INV-07": (
        "Timestamp validity: every event timestamp is ISO-8601 with a "
        "timezone offset. (contract 9.1)"
    ),
    "INV-08": (
        "FX reverse quoting: a zero-split invoice's functional rate "
        "equals the inverse pair rate on the same date. (contract 9.3)"
    ),
    "INV-09": (
        "Amount-zero events are exclusive: only one line carries the "
        "invoice status at any time. (contract 8.3)"
    ),
    "INV-10": (
        "Shift invariance: JE fields change predictably with "
        "counterparty reassignment. (contract 12)"
    ),
    "INV-11": (
        "Journal entry list is finite: every JE has <= 10 lines and is "
        "balanced. (contract 12)"
    ),
    "INV-12": (
        "Overflow behavior: SystemError raised on integer overflow in "
        "any integer-conversion path. (contract 12)"
    ),
    "INV-13": (
        "Physical unit preservation: bank line amount equals "
        "payment.amount_minor. (contract 8.3)"
    ),
    "INV-14": (
        "SystemError discipline: a 5th allocation on one machine raises; "
        "re-created JE carries the adjustment. (contract 17.3)"
    ),
    "INV-15": (
        "Constraint violation prohibition: invoice.late is false while "
        "open_balance_minor > 0 under the baseline path. (contract 17.3)"
    ),
    "INV-16": (
        "Open balance: every invoice's open balance at end of period "
        "covers its credit note. (contract 8.3)"
    ),
    "INV-17": (
        "Projection stability: to_public() of any document returns a "
        "copy; mutations of the copy do not affect the source. (contract 12)"
    ),
}

INVARIANTS: tuple[Invariant, ...] = tuple(
    Invariant(
        code=f"INV-{i:02d}",
        description=_INVARIANT_DESCRIPTIONS[f"INV-{i:02d}"],
        contract_path=f"contracts/INV-{i:02d}.json",
    )
    for i in range(1, 18)
)


def all_invariants() -> tuple[Invariant, ...]:
    return INVARIANTS


def get_invariant(code: str) -> Invariant:
    for inv in INVARIANTS:
        if inv.code == code:
            return inv
    raise KeyError(f"unknown invariant: {code}")


def catalog() -> list[dict[str, Any]]:
    return [inv.to_public() for inv in INVARIANTS]


def signature_catalog() -> dict[str, str]:
    """Map invariant code → contract path (the signature of the catalog)."""
    return {inv.code: inv.contract_path for inv in INVARIANTS}
