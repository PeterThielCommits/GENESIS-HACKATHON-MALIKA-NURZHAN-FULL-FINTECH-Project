"""Immutable public book model (Phase 4.1, 10.3).

A ``Book`` is an immutable, canonically serialisable snapshot of one twin. Mutation
operators never touch the clean book: they receive one and return a *new* ``Book``.

This module is deliberately **public-layer only**: it depends on ``contracts`` and
``core`` and never on ``gen`` or ``invariants``. That is what lets an independent
verifier read the same documents without importing generator internals
(see ``tests/security/test_sealed_boundary.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from typing import Any, Final, Iterable, Mapping, Sequence

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
from core.time_rules import PeriodCalendar

# Roles are mapped to account ids per book, so book-level helpers need the map.
RowMap = dict[str, BookRow]

JSON_TABLES: Final[tuple[str, ...]] = ("company", "policy", "opening_balances", "period_calendar")
JSONL_TABLES: Final[tuple[str, ...]] = TABLES
PUBLIC_FILE_ORDER: Final[tuple[str, ...]] = (
    "company.json",
    "policy.json",
    "accounts.jsonl",
    "counterparties.jsonl",
    "journal_entries.jsonl",
    "invoices.jsonl",
    "credit_notes.jsonl",
    "payments.jsonl",
    "bank_lines.jsonl",
    "fx_rates.jsonl",
    "opening_balances.json",
    "period_calendar.json",
)

@dataclass(frozen=True)
class Book:
    """Immutable public book snapshot for one deterministic episode."""

    company: dict[str, Any]
    policy: dict[str, Any]
    accounts: tuple[Account, ...]
    counterparties: tuple[Counterparty, ...]
    journal_entries: tuple[JournalEntry, ...]
    invoices: tuple[Invoice, ...]
    credit_notes: tuple[CreditNote, ...]
    payments: tuple[Payment, ...]
    bank_lines: tuple[BankLine, ...]
    fx_rates: tuple[FxRate, ...]
    opening_balances: dict[str, Any]
    period_calendar: dict[str, Any]
    _index_cache: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    # ------------------------------------------------------------------ tables
    def rows(self, table: str) -> tuple[BookRow, ...]:
        if table not in TABLES:
            raise ContractError("unknown table", table=table)
        return getattr(self, table)  # type: ignore[no-any-return]

    def table_names(self) -> tuple[str, ...]:
        return TABLES

    def with_rows(self, table: str, rows: Sequence[BookRow]) -> "Book":
        if table not in TABLES:
            raise ContractError("unknown table", table=table)
        ordered = tuple(sort_rows(table, rows))
        # ``replace`` would copy the parent's index cache, which would then describe
        # the *old* rows. Caches are derived state, so they are always dropped.
        return replace(self, **{table: ordered}, _index_cache={})  # type: ignore[arg-type]

    # ------------------------------------------------------------------ lookups
    def by_id(self, table: str) -> dict[str, BookRow]:
        cache_key = f"byid:{table}"
        cached = self._index_cache.get(cache_key)
        if cached is None:
            key_field = {
                "accounts": "account_id",
                "counterparties": "counterparty_id",
                "journal_entries": "je_id",
                "invoices": "doc_id",
                "credit_notes": "credit_note_id",
                "payments": "pay_id",
                "bank_lines": "bank_line_id",
                "fx_rates": "pair",
            }[table]
            mapping = {getattr(row, key_field): row for row in self.rows(table)}
            self._index_cache[cache_key] = mapping
            cached = mapping
        return cached  # type: ignore[return-value]

    def invoice(self, doc_id: str) -> Invoice:
        row = self.by_id("invoices").get(doc_id)
        if row is None:
            raise ContractError("unknown invoice", doc_id=doc_id)
        return row  # type: ignore[return-value]

    def payment(self, pay_id: str) -> Payment:
        row = self.by_id("payments").get(pay_id)
        if row is None:
            raise ContractError("unknown payment", pay_id=pay_id)
        return row  # type: ignore[return-value]

    def account_by_role(self, role: str) -> Account:
        cache_key = f"role:{role}"
        cached = self._index_cache.get(cache_key)
        if cached is None:
            mapping = self.account_roles()
            if role not in mapping:
                raise ContractError("role not present in chart", role=role)
            cached = mapping[role]
            self._index_cache[cache_key] = cached
        return cached  # type: ignore[return-value]

    def account_roles(self) -> dict[str, Account]:
        cached = self._index_cache.get("roles")
        if cached is None:
            mapping: dict[str, Account] = {}
            by_code = {account.code: account for account in self.accounts}
            for key in (
                "bank_account_id",
                "receivable_account_id",
                "advance_account_id",
                "revenue_account_id",
                "fx_gain_loss_account_id",
            ):
                account_id = self.policy.get(key)
                for account in self.accounts:
                    if account.account_id == account_id:
                        mapping[_POLICY_ROLE[key]] = account
                        break
            payable = by_code.get("2000")
            if payable is not None:
                mapping["payable"] = payable
            expense = by_code.get("5000")
            if expense is not None:
                mapping["expense"] = expense
            self._index_cache["roles"] = mapping
            cached = mapping
        return cached  # type: ignore[return-value]

    def calendar(self) -> PeriodCalendar:
        return PeriodCalendar(
            timezone_name=self.company["timezone"],
            period_rule=self.period_calendar["period_rule"],
            fiscal_year_start_month=self.period_calendar["fiscal_year_start_month"],
            fiscal_year_start_day=self.period_calendar["fiscal_year_start_day"],
            cutoff_day_offset=self.period_calendar["cutoff_day_offset"],
            ambiguity_policy=self.period_calendar["ambiguity_policy"],
        )

    def fx_pairs(self) -> tuple[str, ...]:
        return tuple(sorted({row.pair for row in self.fx_rates}))

    def fx_rate_on(self, pair: str, day: date) -> FxRate:
        """Policy fallback: last rate published on or before ``day``."""
        fallback = self.policy.get("fx_fallback_rule", "last_available_on_or_before")
        candidates = [row for row in self.fx_rates if row.pair == pair]
        if not candidates:
            raise ContractError("unknown FX pair", pair=pair)
        if fallback == "exact_date_only":
            for row in candidates:
                if row.effective_date == day.isoformat():
                    return row
            raise ContractError("no exact-date FX rate", pair=pair, day=day.isoformat())
        eligible = [row for row in candidates if row.effective_date <= day.isoformat()]
        if not eligible:
            raise ContractError("no FX rate before date", pair=pair, day=day.isoformat())
        return max(eligible, key=lambda row: row.effective_date)

    def rate_for(self, currency: str, day: date) -> Decimal:
        functional = self.company["functional_currency"]
        if currency == functional:
            return Decimal(1)
        pair = f"{currency}/{functional}"
        return self.fx_rate_on(pair, day).rate_decimal

    def account_currency_scope(self, account_id: str) -> str:
        for account in self.accounts:
            if account.account_id == account_id:
                return account.currency_scope
        raise ContractError("unknown account", account_id=account_id)

    # -------------------------------------------------------------- integrity
    def contract_errors(self) -> list[str]:
        """Cheap structural self-check used before publishing a twin."""
        problems: list[str] = []
        for table in TABLES:
            seen: set[str] = set()
            key_field = {
                "accounts": "account_id",
                "counterparties": "counterparty_id",
                "journal_entries": "je_id",
                "invoices": "doc_id",
                "credit_notes": "credit_note_id",
                "payments": "pay_id",
                "bank_lines": "bank_line_id",
                "fx_rates": "pair",
            }[table]
            for row in self.rows(table):
                key = tuple(getattr(row, key_field) if table != "fx_rates" else (row.pair, row.effective_date))
                if key in seen:
                    problems.append(f"{table}: duplicate key {key}")
                seen.add(key)  # type: ignore[arg-type]
        return problems

    # ------------------------------------------------------------ serialisation
    def public_files(self) -> dict[str, str]:
        """Canonical text of every public file, in the frozen order."""
        files: dict[str, str] = {}
        files["company.json"] = _json_text(self.company)
        files["policy.json"] = _json_text(self.policy)
        for table in TABLES:
            files[f"{table}.jsonl"] = canonical_jsonl(_sorted_rows_json(table, self.rows(table)))
        files["opening_balances.json"] = _json_text(self.opening_balances)
        files["period_calendar.json"] = _json_text(self.period_calendar)
        missing = set(PUBLIC_FILE_ORDER) - set(files)
        if missing:  # pragma: no cover - defensive
            raise ContractError("public file set incomplete", missing=sorted(missing))
        return files

    def public_digest(self) -> str:
        files = self.public_files()
        return digest_of({name: _sha_of_text(files[name]) for name in PUBLIC_FILE_ORDER})

    def file_hashes(self) -> dict[str, str]:
        files = self.public_files()
        return {name: _sha_of_text(files[name]) for name in PUBLIC_FILE_ORDER}

    def row_counts(self) -> dict[str, int]:
        return {table: len(self.rows(table)) for table in TABLES}

    def describe(self) -> dict[str, Any]:
        return {
            "episode_timezone": self.company["timezone"],
            "functional_currency": self.company["functional_currency"],
            "row_counts": self.row_counts(),
            "public_digest": self.public_digest(),
            "fx_pairs": list(self.fx_pairs()),
        }


_POLICY_ROLE: Final[dict[str, str]] = {
    "bank_account_id": "bank",
    "receivable_account_id": "receivable",
    "advance_account_id": "advance",
    "revenue_account_id": "revenue",
    "fx_gain_loss_account_id": "fx_gain_loss",
}


def _json_text(payload: Mapping[str, Any]) -> str:
    from contracts.canonical import canonical_json

    return canonical_json(payload) + "\n"


def _sha_of_text(text: str) -> str:
    from contracts.canonical import sha256_hex

    return sha256_hex(text.encode("utf-8"))


def _sorted_rows_json(table: str, rows: Iterable[BookRow]) -> list[dict[str, Any]]:
    from contracts.models import monotonic_key

    ordered = sorted(rows, key=lambda row: monotonic_key(table, row))  # type: ignore[arg-type]
    return encode_rows(ordered)
