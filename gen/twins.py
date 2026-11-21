"""Clean/mutated twin construction (Phase 4.1).

The immutable ``Book`` model now lives in ``contracts/book_model.py`` so the public
layer can be read without importing the generator. This module keeps only the
*construction* side: assembling a ``Book`` from generated rows and deriving the
public file set.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Iterable, Mapping, Sequence

from contracts.book_model import (
    JSON_TABLES,
    JSONL_TABLES,
    PUBLIC_FILE_ORDER,
    Book,
    RowMap,
)
from contracts.canonical import canonical_jsonl, digest_of
from contracts.errors import ContractError
from contracts.models import (
    TABLES,
    Account,
    BankLine,
    BookRow,
    Counterparty,
    CreditNote,
    FxRate,
    Invoice,
    JournalEntry,
    Payment,
    encode_rows,
    sort_rows,
)

def build_book(
    *,
    company: Mapping[str, Any],
    policy: Mapping[str, Any],
    accounts: Iterable[Account],
    counterparties: Iterable[Counterparty],
    journal_entries: Iterable[JournalEntry],
    invoices: Iterable[Invoice],
    credit_notes: Iterable[CreditNote],
    payments: Iterable[Payment],
    bank_lines: Iterable[BankLine],
    fx_rates: Iterable[FxRate],
    opening_balances: Mapping[str, Any],
    period_calendar: Mapping[str, Any],
) -> Book:
    """Construct a canonically ordered immutable book."""
    ordered = {
        "accounts": tuple(sort_rows("accounts", accounts)),
        "counterparties": tuple(sort_rows("counterparties", counterparties)),
        "journal_entries": tuple(sort_rows("journal_entries", journal_entries)),
        "invoices": tuple(sort_rows("invoices", invoices)),
        "credit_notes": tuple(sort_rows("credit_notes", credit_notes)),
        "payments": tuple(sort_rows("payments", payments)),
        "bank_lines": tuple(sort_rows("bank_lines", bank_lines)),
        "fx_rates": tuple(sort_rows("fx_rates", fx_rates)),
    }
    return Book(
        company=dict(company),
        policy=dict(policy),
        opening_balances=dict(opening_balances),
        period_calendar=dict(period_calendar),
        **ordered,  # type: ignore[arg-type]
    )


@dataclass(frozen=True)
class TwinPair:
    """The counterfactual pair C (clean) and M (mutated) plus their diff linkage."""

    clean: Book
    mutated: Book

    @property
    def clean_digest(self) -> str:
        return self.clean.public_digest()

    @property
    def mutated_digest(self) -> str:
        return self.mutated.public_digest()

    def clean_unchanged(self) -> bool:
        return self.clean_digest == self.clean.public_digest()

    def describe(self) -> dict[str, Any]:
        return {
            "clean_digest": self.clean_digest,
            "mutated_digest": self.mutated_digest,
            "clean_rows": self.clean.row_counts(),
            "mutated_rows": self.mutated.row_counts(),
        }
