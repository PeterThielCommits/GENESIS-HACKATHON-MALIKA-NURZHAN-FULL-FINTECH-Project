"""Frozen row models for the TwinLedger public book (contract 1.0.0).

Rows are plain frozen dataclasses whose ``to_row``/``from_row`` round-trip through
the JSON-Lines contract. Validation happens at the system boundary: decoded rows
are checked against ``contracts/book.schema.json`` before any business logic sees
them (REQ-CONTRACT-002).

Money fields are ``int`` minor units and rates are exact ``Decimal`` parsed from
strings (REQ-MONEY-002) — never floats.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final, Iterable, Mapping, Sequence, TypeVar

from contracts.errors import ContractError
from contracts.jsonschema_subset import SchemaValidator
from core.money import parse_decimal, validate_currency
from core.time_rules import parse_timestamp

BOOK_SCHEMA_NAME: Final[str] = "book.schema.json"

TABLES: Final[tuple[str, ...]] = (
    "accounts",
    "counterparties",
    "journal_entries",
    "invoices",
    "credit_notes",
    "payments",
    "bank_lines",
    "fx_rates",
)

RowT = TypeVar("RowT", bound="BookRow")


class BookRow:
    """Base behaviour shared by all row models."""

    table: str = ""

    def to_row(self) -> dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Any:
        raise NotImplementedError


@dataclass(frozen=True)
class Account(BookRow):
    table = "accounts"
    account_id: str
    code: str
    name: str
    type: str
    normal_balance: str
    currency_scope: str

    def to_row(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "code": self.code,
            "name": self.name,
            "type": self.type,
            "normal_balance": self.normal_balance,
            "currency_scope": self.currency_scope,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Account":
        _require_keys(row, cls.__dataclass_fields__.keys())  # type: ignore[arg-type]
        return cls(
            account_id=str(row["account_id"]),
            code=str(row["code"]),
            name=str(row["name"]),
            type=str(row["type"]),
            normal_balance=str(row["normal_balance"]),
            currency_scope=str(row["currency_scope"]),
        )


@dataclass(frozen=True)
class Counterparty(BookRow):
    table = "counterparties"
    counterparty_id: str
    legal_name: str
    country_marker: str
    vat_marker: str
    payment_terms_days: int
    category: str
    name_variants: dict[str, str]

    def to_row(self) -> dict[str, Any]:
        return {
            "counterparty_id": self.counterparty_id,
            "legal_name": self.legal_name,
            "country_marker": self.country_marker,
            "vat_marker": self.vat_marker,
            "payment_terms_days": self.payment_terms_days,
            "category": self.category,
            "name_variants": dict(sorted(self.name_variants.items())),
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Counterparty":
        _require_keys(row, cls.__dataclass_fields__.keys())  # type: ignore[arg-type]
        variants = row["name_variants"]
        if not isinstance(variants, Mapping):
            raise ContractError("name_variants must be an object", table=cls.table)
        return cls(
            counterparty_id=str(row["counterparty_id"]),
            legal_name=str(row["legal_name"]),
            country_marker=str(row["country_marker"]),
            vat_marker=str(row["vat_marker"]),
            payment_terms_days=int(row["payment_terms_days"]),
            category=str(row["category"]),
            name_variants={str(key): str(value) for key, value in variants.items()},
        )


@dataclass(frozen=True)
class JournalLine:
    line_id: str
    account_id: str
    debit_minor: int
    credit_minor: int
    currency: str
    fx_rate_decimal: Decimal
    functional_debit_minor: int
    functional_credit_minor: int
    counterparty_id: str | None
    analytic_tag: str | None

    def to_row(self) -> dict[str, Any]:
        return {
            "line_id": self.line_id,
            "account_id": self.account_id,
            "debit_minor": self.debit_minor,
            "credit_minor": self.credit_minor,
            "currency": self.currency,
            "fx_rate_decimal": format_rate(self.fx_rate_decimal),
            "functional_debit_minor": self.functional_debit_minor,
            "functional_credit_minor": self.functional_credit_minor,
            "counterparty_id": self.counterparty_id,
            "analytic_tag": self.analytic_tag,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "JournalLine":
        _require_keys(row, cls.__dataclass_fields__.keys())  # type: ignore[arg-type]
        if bool(row["debit_minor"]) and bool(row["credit_minor"]):
            raise ContractError(
                "a journal line cannot carry both debit and credit",
                line_id=row.get("line_id"),
            )
        if (row["debit_minor"] or row["credit_minor"]) and (
            row["debit_minor"] < 0 or row["credit_minor"] < 0
        ):
            raise ContractError("journal amounts must be non-negative", line_id=row.get("line_id"))
        return cls(
            line_id=str(row["line_id"]),
            account_id=str(row["account_id"]),
            debit_minor=int(row["debit_minor"]),
            credit_minor=int(row["credit_minor"]),
            currency=str(row["currency"]),
            fx_rate_decimal=parse_decimal(str(row["fx_rate_decimal"]), field="fx_rate_decimal"),
            functional_debit_minor=int(row["functional_debit_minor"]),
            functional_credit_minor=int(row["functional_credit_minor"]),
            counterparty_id=_optional_str(row["counterparty_id"]),
            analytic_tag=_optional_str(row["analytic_tag"]),
        )


@dataclass(frozen=True)
class JournalEntry(BookRow):
    table = "journal_entries"
    je_id: str
    timestamp: str
    posting_period: str
    source_document_id: str | None
    description: str
    lines: tuple[JournalLine, ...]

    @property
    def debit_total(self) -> int:
        return sum(line.debit_minor for line in self.lines)

    @property
    def credit_total(self) -> int:
        return sum(line.credit_minor for line in self.lines)

    @property
    def functional_debit_total(self) -> int:
        return sum(line.functional_debit_minor for line in self.lines)

    @property
    def functional_credit_total(self) -> int:
        return sum(line.functional_credit_minor for line in self.lines)

    def to_row(self) -> dict[str, Any]:
        return {
            "je_id": self.je_id,
            "timestamp": self.timestamp,
            "posting_period": self.posting_period,
            "source_document_id": self.source_document_id,
            "description": self.description,
            "lines": [line.to_row() for line in self.lines],
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "JournalEntry":
        _require_keys(row, cls.__dataclass_fields__.keys())  # type: ignore[arg-type]
        lines = row["lines"]
        if not isinstance(lines, Sequence) or isinstance(lines, (str, bytes)):
            raise ContractError("journal lines must be an array", je_id=row.get("je_id"))
        parse_timestamp(str(row["timestamp"]), field="journal_entries.timestamp")
        return cls(
            je_id=str(row["je_id"]),
            timestamp=str(row["timestamp"]),
            posting_period=str(row["posting_period"]),
            source_document_id=_optional_str(row["source_document_id"]),
            description=str(row["description"]),
            lines=tuple(JournalLine.from_row(line) for line in lines),
        )


@dataclass(frozen=True)
class InvoiceLine:
    line_id: str
    description: str
    quantity_decimal: Decimal | None
    unit_price_minor: int | None
    amount_minor: int
    service_reference: str | None

    def to_row(self) -> dict[str, Any]:
        return {
            "line_id": self.line_id,
            "description": self.description,
            "quantity_decimal": None
            if self.quantity_decimal is None
            else format_quantity(self.quantity_decimal),
            "unit_price_minor": self.unit_price_minor,
            "amount_minor": self.amount_minor,
            "service_reference": self.service_reference,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "InvoiceLine":
        _require_keys(row, cls.__dataclass_fields__.keys())  # type: ignore[arg-type]
        quantity = row["quantity_decimal"]
        return cls(
            line_id=str(row["line_id"]),
            description=str(row["description"]),
            quantity_decimal=None if quantity is None else parse_decimal(str(quantity), field="quantity"),
            unit_price_minor=_optional_int(row["unit_price_minor"]),
            amount_minor=int(row["amount_minor"]),
            service_reference=_optional_str(row["service_reference"]),
        )


@dataclass(frozen=True)
class Invoice(BookRow):
    table = "invoices"
    doc_id: str
    counterparty_id: str
    issue_timestamp: str
    service_start: str
    service_end: str | None
    due_timestamp: str
    currency: str
    total_minor: int
    tax_minor: int | None
    line_items: tuple[InvoiceLine, ...]
    status: str

    def to_row(self) -> dict[str, Any]:
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
            "line_items": [item.to_row() for item in self.line_items],
            "status": self.status,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Invoice":
        _require_keys(row, cls.__dataclass_fields__.keys())  # type: ignore[arg-type]
        items = row["line_items"]
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            raise ContractError("line_items must be an array", doc_id=row.get("doc_id"))
        validate_currency(str(row["currency"]))
        parse_timestamp(str(row["issue_timestamp"]), field="invoices.issue_timestamp")
        parse_timestamp(str(row["due_timestamp"]), field="invoices.due_timestamp")
        if row["service_end"] is not None:
            parse_timestamp(str(row["service_end"]), field="invoices.service_end")
        return cls(
            doc_id=str(row["doc_id"]),
            counterparty_id=str(row["counterparty_id"]),
            issue_timestamp=str(row["issue_timestamp"]),
            service_start=str(row["service_start"]),
            service_end=None if row["service_end"] is None else str(row["service_end"]),
            due_timestamp=str(row["due_timestamp"]),
            currency=str(row["currency"]),
            total_minor=int(row["total_minor"]),
            tax_minor=_optional_int(row["tax_minor"]),
            line_items=tuple(InvoiceLine.from_row(item) for item in items),
            status=str(row["status"]),
        )


@dataclass(frozen=True)
class CreditNote(BookRow):
    table = "credit_notes"
    credit_note_id: str
    invoice_id: str
    counterparty_id: str
    timestamp: str
    amount_minor: int
    currency: str
    reason_code: str

    def to_row(self) -> dict[str, Any]:
        return {
            "credit_note_id": self.credit_note_id,
            "invoice_id": self.invoice_id,
            "counterparty_id": self.counterparty_id,
            "timestamp": self.timestamp,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "reason_code": self.reason_code,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "CreditNote":
        _require_keys(row, cls.__dataclass_fields__.keys())  # type: ignore[arg-type]
        return cls(
            credit_note_id=str(row["credit_note_id"]),
            invoice_id=str(row["invoice_id"]),
            counterparty_id=str(row["counterparty_id"]),
            timestamp=str(row["timestamp"]),
            amount_minor=int(row["amount_minor"]),
            currency=str(row["currency"]),
            reason_code=str(row["reason_code"]),
        )


@dataclass(frozen=True)
class Allocation:
    allocation_id: str
    document_id: str
    amount_minor: int
    allocation_timestamp: str

    def to_row(self) -> dict[str, Any]:
        return {
            "allocation_id": self.allocation_id,
            "document_id": self.document_id,
            "amount_minor": self.amount_minor,
            "allocation_timestamp": self.allocation_timestamp,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Allocation":
        _require_keys(row, cls.__dataclass_fields__.keys())  # type: ignore[arg-type]
        return cls(
            allocation_id=str(row["allocation_id"]),
            document_id=str(row["document_id"]),
            amount_minor=int(row["amount_minor"]),
            allocation_timestamp=str(row["allocation_timestamp"]),
        )


@dataclass(frozen=True)
class Payment(BookRow):
    table = "payments"
    pay_id: str
    timestamp: str
    counterparty_id: str
    currency: str
    amount_minor: int
    functional_amount_minor: int
    fx_rate_decimal: Decimal
    allocations: tuple[Allocation, ...]
    bank_reference: str | None
    payment_channel: str

    @property
    def allocated_minor(self) -> int:
        return sum(allocation.amount_minor for allocation in self.allocations)

    def to_row(self) -> dict[str, Any]:
        return {
            "pay_id": self.pay_id,
            "timestamp": self.timestamp,
            "counterparty_id": self.counterparty_id,
            "currency": self.currency,
            "amount_minor": self.amount_minor,
            "functional_amount_minor": self.functional_amount_minor,
            "fx_rate_decimal": format_rate(self.fx_rate_decimal),
            "allocations": [allocation.to_row() for allocation in self.allocations],
            "bank_reference": self.bank_reference,
            "payment_channel": self.payment_channel,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Payment":
        _require_keys(row, cls.__dataclass_fields__.keys())  # type: ignore[arg-type]
        allocations = row["allocations"]
        if not isinstance(allocations, Sequence) or isinstance(allocations, (str, bytes)):
            raise ContractError("allocations must be an array", pay_id=row.get("pay_id"))
        return cls(
            pay_id=str(row["pay_id"]),
            timestamp=str(row["timestamp"]),
            counterparty_id=str(row["counterparty_id"]),
            currency=str(row["currency"]),
            amount_minor=int(row["amount_minor"]),
            functional_amount_minor=int(row["functional_amount_minor"]),
            fx_rate_decimal=parse_decimal(str(row["fx_rate_decimal"]), field="payments.fx_rate_decimal"),
            allocations=tuple(Allocation.from_row(item) for item in allocations),
            bank_reference=_optional_str(row["bank_reference"]),
            payment_channel=str(row["payment_channel"]),
        )


@dataclass(frozen=True)
class BankLine(BookRow):
    table = "bank_lines"
    bank_line_id: str
    timestamp: str
    amount_minor: int
    currency: str
    direction: str
    reference_text: str
    matched_payment_id: str | None
    bank_account_id: str
    status: str

    def to_row(self) -> dict[str, Any]:
        return {
            "bank_line_id": self.bank_line_id,
            "timestamp": self.timestamp,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "direction": self.direction,
            "reference_text": self.reference_text,
            "matched_payment_id": self.matched_payment_id,
            "bank_account_id": self.bank_account_id,
            "status": self.status,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "BankLine":
        _require_keys(row, cls.__dataclass_fields__.keys())  # type: ignore[arg-type]
        return cls(
            bank_line_id=str(row["bank_line_id"]),
            timestamp=str(row["timestamp"]),
            amount_minor=int(row["amount_minor"]),
            currency=str(row["currency"]),
            direction=str(row["direction"]),
            reference_text=str(row["reference_text"]),
            matched_payment_id=_optional_str(row["matched_payment_id"]),
            bank_account_id=str(row["bank_account_id"]),
            status=str(row["status"]),
        )


@dataclass(frozen=True)
class FxRate(BookRow):
    table = "fx_rates"
    pair: str
    effective_date: str
    rate_decimal: Decimal
    source_code: str
    publication_timestamp: str | None

    def to_row(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "effective_date": self.effective_date,
            "rate_decimal": format_rate(self.rate_decimal),
            "source_code": self.source_code,
            "publication_timestamp": self.publication_timestamp,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "FxRate":
        _require_keys(row, cls.__dataclass_fields__.keys())  # type: ignore[arg-type]
        return cls(
            pair=str(row["pair"]),
            effective_date=str(row["effective_date"]),
            rate_decimal=parse_decimal(str(row["rate_decimal"]), field="fx_rates.rate_decimal"),
            source_code=str(row["source_code"]),
            publication_timestamp=_optional_str(row["publication_timestamp"]),
        )


ROW_MODEL_BY_TABLE: Final[dict[str, type[BookRow]]] = {
    "accounts": Account,
    "counterparties": Counterparty,
    "journal_entries": JournalEntry,
    "invoices": Invoice,
    "credit_notes": CreditNote,
    "payments": Payment,
    "bank_lines": BankLine,
    "fx_rates": FxRate,
}

ROW_SET_KEYS: Final[dict[str, str]] = {
    "accounts": "account_id",
    "counterparties": "counterparty_id",
    "journal_entries": "je_id",
    "invoices": "doc_id",
    "credit_notes": "credit_note_id",
    "payments": "pay_id",
    "bank_lines": "bank_line_id",
    "fx_rates": "pair",
}


def format_rate(rate: Decimal) -> str:
    """Serialise a rate deterministically without exponent notation."""
    text = format(rate.normalize(), "f")
    return text


def format_quantity(quantity: Decimal) -> str:
    return format(quantity.normalize(), "f")


def decode_rows(table: str, rows: Iterable[Mapping[str, Any]], validator: SchemaValidator) -> list[Any]:
    """Validate raw JSON rows against the frozen schema, then build models."""
    if table not in ROW_MODEL_BY_TABLE:
        raise ContractError("unknown table", table=table)
    row_schema = dict(validator.schema["$defs"][table])
    # Row schemas use local $refs ($defs/id, $defs/rate, ...) that resolve against
    # the whole book document, so the document is passed as the resolver root.
    row_validator = SchemaValidator(row_schema, name=f"book.schema.json#{table}", document=validator.schema)
    model = ROW_MODEL_BY_TABLE[table]
    decoded = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ContractError("row must be an object", table=table, index=index)
        try:
            row_validator.validate(dict(row))
        except ContractError as exc:
            raise ContractError(
                "row violates frozen schema",
                table=table,
                index=index,
                reason=exc.message,
                details=exc.context,
            ) from exc
        decoded.append(model.from_row(row))
    return decoded


def encode_rows(rows: Sequence[Any]) -> list[dict[str, Any]]:
    return [row.to_row() for row in rows]


def _require_keys(row: Mapping[str, Any], expected: Iterable[str]) -> None:
    expected_set = set(expected)
    actual = set(row.keys())
    missing = expected_set - actual
    extra = actual - expected_set
    if missing or extra:
        raise ContractError(
            "row keys do not match contract",
            missing=sorted(missing),
            unexpected=sorted(extra),
        )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContractError("expected string or null", got=type(value).__name__)
    return value


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError("expected integer or null", got=type(value).__name__)
    return value


def monotonic_key(table: str, row: Any) -> tuple:
    """Stable sort key per table (G10 deterministic ordering)."""
    if table == "accounts":
        return (row.code, row.account_id)
    if table == "counterparties":
        return (row.counterparty_id,)
    if table == "journal_entries":
        return (row.timestamp, row.je_id)
    if table == "invoices":
        return (row.issue_timestamp, row.doc_id)
    if table == "credit_notes":
        return (row.timestamp, row.credit_note_id)
    if table == "payments":
        return (row.timestamp, row.pay_id)
    if table == "bank_lines":
        return (row.timestamp, row.bank_line_id)
    if table == "fx_rates":
        return (row.pair, row.effective_date)
    raise ContractError("unknown table", table=table)


def sort_rows(table: str, rows: Iterable[Any]) -> list[Any]:
    return sorted(rows, key=lambda row: monotonic_key(table, row))
