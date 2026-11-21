"""Generator-side invariant checks over a public book (12.2, REQ-INV-001..003).

These checks read only the **public** book model (``contracts/book_model.py``) and
never import ``gen``, so the same code is usable from the sealed side *and* as a
reference for the independent verifier in Phase 8 (docs/INDEPENDENCE.md). Each check
returns a ``Violation`` with a deterministic signature.

Checks implemented here (all of the MVP scope):
  INV-01 JE_BALANCE, INV-04 OPEN_BALANCE, INV-06 BANK_MATCH, INV-08 FX_RECALC,
  INV-09 CUTOFF, INV-11 ID_UNIQUENESS, INV-12 REFERENTIAL, INV-13 CURRENCY_EXPONENT,
  INV-14 TIMEZONE_VALID, INV-15 ALLOCATION_CONSERVATION, INV-16 CREDIT_NOTE_LIMIT,
  INV-17 DOCUMENT_STATUS, INV-02 TRIAL_BALANCE, INV-03 AR_SUBLEDGER_VS_DOCS,
  INV-05 AGING, INV-07 FX_POLICY, INV-10 PERIOD_TOTALS.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

from contracts.errors import ContractError, MoneyError, TimeRuleError
from core.money import MAX_ABS_MINOR, SUPPORTED_CURRENCIES, exponent_of, parse_rate
from core.time_rules import parse_timestamp
from contracts.book_model import Book
from invariants.model import Violation

DELTA_TOLERANCE_MINOR = 0


@dataclass(frozen=True)
class OpenBalance:
    """Derived open balance of one invoice under public evidence."""

    doc_id: str
    counterparty_id: str
    currency: str
    total_minor: int
    credited_minor: int
    allocated_minor: int

    @property
    def remaining_minor(self) -> int:
        return self.total_minor - self.credited_minor - self.allocated_minor


def invoice_open_balances(book: Book) -> dict[str, OpenBalance]:
    """Allocation state per invoice, derived only from public rows."""
    credited: dict[str, int] = {}
    for note in book.credit_notes:
        credited[note.invoice_id] = credited.get(note.invoice_id, 0) + note.amount_minor
    allocated: dict[str, int] = {}
    for payment in book.payments:
        for allocation in payment.allocations:
            allocated[allocation.document_id] = (
                allocated.get(allocation.document_id, 0) + allocation.amount_minor
            )
    balances: dict[str, OpenBalance] = {}
    for invoice in book.invoices:
        balances[invoice.doc_id] = OpenBalance(
            doc_id=invoice.doc_id,
            counterparty_id=invoice.counterparty_id,
            currency=invoice.currency,
            total_minor=invoice.total_minor,
            credited_minor=credited.get(invoice.doc_id, 0),
            allocated_minor=allocated.get(invoice.doc_id, 0),
        )
    return balances


def check_id_uniqueness(book: Book) -> list[Violation]:
    violations: list[Violation] = []
    for table in book.table_names():
        seen: dict[str, int] = {}
        key_field = _KEY_FIELD[table]
        for row in book.rows(table):
            if table == "fx_rates":
                key = f"{row.pair}@{row.effective_date}"
            else:
                key = getattr(row, key_field)
            seen[key] = seen.get(key, 0) + 1
        for key, count in sorted(seen.items()):
            if count > 1:
                violations.append(
                    Violation(
                        invariant_id="INV-11",
                        entity_key=f"{table}:{key}",
                        expected_delta_minor=None,
                        currency=None,
                        direction="invalid",
                        tolerance_minor=0,
                        detail=f"primary key repeated {count} times in {table}",
                        entity_ids=(key,),
                    )
                )
    # Cross-table uniqueness: ``source_document_id`` and allocation targets are
    # pointers into *any* document table, so an id must identify exactly one row.
    global_ids: dict[str, list[str]] = {}
    for table in ("invoices", "payments", "credit_notes", "bank_lines"):
        for row in book.rows(table):
            identifier = getattr(row, {"invoices":"doc_id","payments":"pay_id",
                                       "credit_notes":"credit_note_id",
                                       "bank_lines":"bank_line_id"}[table])
            global_ids.setdefault(identifier, []).append(table)
    for identifier, tables in sorted(global_ids.items()):
        if len(tables) > 1:
            violations.append(
                Violation(
                    invariant_id="INV-11",
                    entity_key=f"global:{identifier}",
                    expected_delta_minor=None,
                    currency=None,
                    direction="invalid",
                    tolerance_minor=0,
                    detail=f"id reused across tables: {sorted(tables)}",
                    entity_ids=(identifier,),
                )
            )

    # Records embedded in JE lines / allocations / invoice line items carry ids too.
    line_ids: dict[str, int] = {}
    for entry in book.journal_entries:
        for line in entry.lines:
            line_ids[line.line_id] = line_ids.get(line.line_id, 0) + 1
    for key, count in sorted(line_ids.items()):
        if count > 1:
            violations.append(
                Violation(
                    invariant_id="INV-11",
                    entity_key=f"journal_entries.lines:{key}",
                    expected_delta_minor=None,
                    currency=None,
                    direction="invalid",
                    tolerance_minor=0,
                    detail=f"journal line id repeated {count} times",
                    entity_ids=(key,),
                )
            )
    return violations


def check_referential(book: Book) -> list[Violation]:
    violations: list[Violation] = []
    accounts = book.by_id("accounts")
    counterparts = book.by_id("counterparties")
    invoices = book.by_id("invoices")
    payments = book.by_id("payments")

    credit_note_ids = book.by_id("credit_notes")
    for entry in book.journal_entries:
        if entry.source_document_id is not None:
            if (
                entry.source_document_id not in invoices
                and entry.source_document_id not in payments
                and entry.source_document_id not in credit_note_ids
            ):
                violations.append(
                    _ref_violation(
                        f"journal_entries:{entry.je_id}",
                        entry.je_id,
                        f"source_document_id {entry.source_document_id} unresolved",
                    )
                )
        for line in entry.lines:
            if line.account_id not in accounts:
                violations.append(
                    _ref_violation(f"journal_entries:{entry.je_id}", line.line_id,
                                   f"account_id {line.account_id} unresolved")
                )
            if line.counterparty_id is not None and line.counterparty_id not in counterparts:
                violations.append(
                    _ref_violation(f"journal_entries:{entry.je_id}", line.line_id,
                                   f"counterparty_id {line.counterparty_id} unresolved")
                )
    for invoice in book.invoices:
        if invoice.counterparty_id not in counterparts:
            violations.append(
                _ref_violation(f"invoices:{invoice.doc_id}", invoice.doc_id,
                               "counterparty_id unresolved")
            )
    for note in book.credit_notes:
        if note.invoice_id not in invoices:
            violations.append(
                _ref_violation(f"credit_notes:{note.credit_note_id}", note.credit_note_id,
                               f"invoice_id {note.invoice_id} unresolved")
            )
        if note.counterparty_id not in counterparts:
            violations.append(
                _ref_violation(f"credit_notes:{note.credit_note_id}", note.credit_note_id,
                               "counterparty_id unresolved")
            )
    for payment in book.payments:
        if payment.counterparty_id not in counterparts:
            violations.append(
                _ref_violation(f"payments:{payment.pay_id}", payment.pay_id,
                               "counterparty_id unresolved")
            )
        for allocation in payment.allocations:
            if allocation.document_id not in invoices:
                violations.append(
                    _ref_violation(f"payments:{payment.pay_id}", payment.pay_id,
                                   f"allocation to {allocation.document_id} unresolved")
                )
    for line in book.bank_lines:
        if line.matched_payment_id is not None and line.matched_payment_id not in payments:
            violations.append(
                _ref_violation(f"bank_lines:{line.bank_line_id}", line.bank_line_id,
                               "matched_payment_id unresolved")
            )
        if line.bank_account_id not in accounts:
            violations.append(
                _ref_violation(f"bank_lines:{line.bank_line_id}", line.bank_line_id,
                               "bank_account_id unresolved")
            )
    return violations


def check_je_balance(book: Book) -> list[Violation]:
    violations: list[Violation] = []
    for entry in book.journal_entries:
        currencies = {line.currency for line in entry.lines}
        # A single-currency entry must balance in transaction currency. Multi-currency
        # entries (an FX revaluation plug) are only required to balance functionally,
        # which is how double-entry works for foreign-currency settlements.
        if len(currencies) == 1 and entry.debit_total != entry.credit_total:
            violations.append(
                Violation(
                    invariant_id="INV-01",
                    entity_key=f"journal_entries:{entry.je_id}",
                    expected_delta_minor=entry.debit_total - entry.credit_total,
                    currency=_entry_currency(entry),
                    direction="mismatch",
                    tolerance_minor=0,
                    detail="transaction-currency debit != credit",
                    entity_ids=(entry.je_id,),
                )
            )
        if entry.functional_debit_total != entry.functional_credit_total:
            violations.append(
                Violation(
                    invariant_id="INV-01",
                    entity_key=f"journal_entries:{entry.je_id}",
                    expected_delta_minor=entry.functional_debit_total - entry.functional_credit_total,
                    currency=book.company["functional_currency"],
                    direction="mismatch",
                    tolerance_minor=0,
                    detail="functional debit != credit",
                    entity_ids=(entry.je_id,),
                )
            )
    return violations


def check_currency_exponent(book: Book) -> list[Violation]:
    violations: list[Violation] = []
    for entry in book.journal_entries:
        for line in entry.lines:
            if line.currency not in SUPPORTED_CURRENCIES:
                violations.append(
                    _invalid("INV-13", f"journal_entries:{entry.je_id}", line.line_id,
                             f"unregistered currency {line.currency}")
                )
            try:
                parse_rate(line.fx_rate_decimal)
            except (ContractError, MoneyError) as exc:
                violations.append(
                    _invalid("INV-13", f"journal_entries:{entry.je_id}", line.line_id,
                             f"invalid fx rate: {exc.message}")
                )
            if isinstance(line.fx_rate_decimal, float):  # pragma: no cover - type guard
                violations.append(
                    _invalid("INV-13", f"journal_entries:{entry.je_id}", line.line_id,
                             "float rate found")
                )
            for value in (line.debit_minor, line.credit_minor,
                          line.functional_debit_minor, line.functional_credit_minor):
                if abs(value) > MAX_ABS_MINOR:
                    violations.append(
                        _invalid("INV-13", f"journal_entries:{entry.je_id}", line.line_id,
                                 "minor units exceed safe range")
                    )
    for invoice in book.invoices:
        if invoice.currency not in SUPPORTED_CURRENCIES:
            violations.append(_invalid("INV-13", f"invoices:{invoice.doc_id}", invoice.doc_id,
                                       "unregistered currency"))
        exponent_of(invoice.currency)
    return violations


def check_timezone(book: Book) -> list[Violation]:
    violations: list[Violation] = []
    calendar = book.calendar()
    stamps: list[tuple[str, str, str]] = []
    for entry in book.journal_entries:
        stamps.append(("journal_entries", entry.je_id, entry.timestamp))
    for invoice in book.invoices:
        stamps.append(("invoices", invoice.doc_id, invoice.issue_timestamp))
        stamps.append(("invoices", invoice.doc_id, invoice.due_timestamp))
        if invoice.service_end is not None:
            stamps.append(("invoices", invoice.doc_id, invoice.service_end))
    for note in book.credit_notes:
        stamps.append(("credit_notes", note.credit_note_id, note.timestamp))
    for payment in book.payments:
        stamps.append(("payments", payment.pay_id, payment.timestamp))
        for allocation in payment.allocations:
            stamps.append(("payments", payment.pay_id, allocation.allocation_timestamp))
    for line in book.bank_lines:
        stamps.append(("bank_lines", line.bank_line_id, line.timestamp))
    for table, entity_id, text in stamps:
        try:
            moment = parse_timestamp(text, field=f"{table}.timestamp")
        except Exception:
            violations.append(_invalid("INV-14", f"{table}:{entity_id}", entity_id,
                                       "timestamp is not unambiguous ISO-8601 with offset"))
            continue
        try:
            moment.astimezone(calendar.zone)
        except Exception:  # pragma: no cover - zone already validated
            violations.append(_invalid("INV-14", f"{table}:{entity_id}", entity_id,
                                       "timestamp not representable in company timezone"))
    return violations


def check_cutoff(book: Book) -> list[Violation]:
    """INV-09: revenue-recognition entries must post in the recognition period.

    Scope is deliberately narrow (9.1 / 11.5): only entries that touch a revenue or
    expense account and reference an invoice are recognition postings. Settlement
    postings (bank/receivable movements) are governed by INV-10 and post in the
    period of their own timestamp, which is legitimate accounting behaviour.
    """
    violations: list[Violation] = []
    calendar = book.calendar()
    recognition = book.policy["recognition_rule"]
    invoices = book.by_id("invoices")
    revenue_account = book.policy["revenue_account_id"]
    expense_account = _expense_account_id(book)
    credit_notes_by_id = book.by_id("credit_notes")
    for entry in book.journal_entries:
        touches_recognition = any(
            line.account_id in (revenue_account, expense_account) for line in entry.lines
        )
        if not touches_recognition or entry.source_document_id is None:
            continue
        if entry.source_document_id in credit_notes_by_id:
            # A credit note is an adjustment event: it posts in the period of the
            # adjustment (INV-10 covers period/timestamp consistency).
            continue
        if entry.source_document_id not in invoices:
            continue
        basis = _recognition_moment(entry.source_document_id, invoices, recognition, entry.timestamp)
        expected = calendar.posting_period(basis)
        if entry.posting_period != expected:
            violations.append(
                Violation(
                    invariant_id="INV-09",
                    entity_key=f"journal_entries:{entry.je_id}",
                    expected_delta_minor=None,
                    currency=_entry_currency(entry),
                    direction="mismatch",
                    tolerance_minor=0,
                    detail=f"posting_period {entry.posting_period} != expected {expected}",
                    entity_ids=(entry.je_id,),
                )
            )
    return violations


def check_period_totals(book: Book) -> list[Violation]:
    """INV-10: every entry's period must be consistent with its own timestamp date."""
    violations: list[Violation] = []
    calendar = book.calendar()
    for entry in book.journal_entries:
        try:
            derived = calendar.posting_period(parse_timestamp(entry.timestamp))
        except (ContractError, MoneyError, TimeRuleError):
            # INV-14 owns malformed timestamps.
            continue
        if entry.posting_period != derived:
            violations.append(
                Violation(
                    invariant_id="INV-10",
                    entity_key=f"period:{entry.posting_period}",
                    expected_delta_minor=None,
                    currency=None,
                    direction="mismatch",
                    tolerance_minor=0,
                    detail=f"{entry.je_id} posted in {entry.posting_period} but dated {derived}",
                    entity_ids=(entry.je_id,),
                )
            )
    return violations


def check_fx_policy(book: Book) -> list[Violation]:
    """INV-07: booked rate must equal the policy-required rate."""
    violations: list[Violation] = []
    functional = book.company["functional_currency"]
    invoices = book.by_id("invoices")
    rate_basis = book.policy.get("fx_rate_date_basis", "document_date")
    payments_by_id = book.by_id("payments")
    credit_notes_by_id = book.by_id("credit_notes")
    for entry in book.journal_entries:
        try:
            moment = parse_timestamp(entry.timestamp)
        except (ContractError, MoneyError, TimeRuleError):
            # Malformed timestamps are reported by INV-14; a policy check cannot
            # judge a date it cannot read, and must not crash the whole suite.
            continue
        # The policy's rate basis governs postings that settle or adjust a document
        # (payments and credit notes): they relieve the receivable at the invoice's
        # document-date rate so no artificial FX difference is created. Recognition
        # entries use their own event date, which is the document date anyway.
        if _is_document_settlement(book, entry):
            invoice_ctx = _resolve_invoice_context(book, entry.source_document_id)
            day = _rate_basis_day_for_invoice(book.calendar(), invoice_ctx, rate_basis, moment)
        else:
            day = book.calendar().effective_date(moment)
        for line in entry.lines:
            if line.currency == functional:
                continue
            pair = f"{line.currency}/{functional}"
            try:
                required = book.rate_for(line.currency, day)
            except ContractError as exc:
                violations.append(_invalid("INV-07", f"journal_entries:{entry.je_id}",
                                           line.line_id, str(exc.message)))
                continue
            try:
                booked = parse_rate(line.fx_rate_decimal)
            except ContractError:
                violations.append(_invalid("INV-07", f"journal_entries:{entry.je_id}",
                                           line.line_id, "invalid booked rate"))
                continue
            if booked != required:
                violations.append(
                    Violation(
                        invariant_id="INV-07",
                        entity_key=f"journal_entries:{entry.je_id}",
                        expected_delta_minor=None,
                        currency=line.currency,
                        direction="mismatch",
                        tolerance_minor=0,
                        detail=f"booked {booked} vs policy {required} for {pair} on {day}",
                        entity_ids=(entry.je_id, line.line_id),
                    )
                )
    # One violation per (entry, currency): a whole entry uses one policy rate.
    unique: dict[tuple[str, str], Violation] = {}
    for violation in violations:
        unique.setdefault((violation.entity_key, str(violation.currency)), violation)
    return [unique[key] for key in sorted(unique)]


def check_fx_recalc(book: Book) -> list[Violation]:
    """INV-08: functional amounts must recompute from the booked rate."""
    violations: list[Violation] = []
    functional = book.company["functional_currency"]
    for entry in book.journal_entries:
        for line in entry.lines:
            try:
                _functional_amount(1, line.currency, line.fx_rate_decimal, functional)
            except (ContractError, MoneyError, TimeRuleError):
                # Currency and rate validity belong to INV-07/INV-13.
                continue
            if line.debit_minor:
                expected = _functional_amount(line.debit_minor, line.currency, line.fx_rate_decimal, functional)
                if abs(expected - line.functional_debit_minor) > 1:
                    violations.append(
                        Violation(
                            invariant_id="INV-08",
                            entity_key=f"journal_entries:{entry.je_id}",
                            expected_delta_minor=line.functional_debit_minor - expected,
                            currency=line.currency,
                            direction="mismatch",
                            tolerance_minor=1,
                            detail=f"functional debit {line.functional_debit_minor} != recomputed {expected}",
                            entity_ids=(entry.je_id, line.line_id),
                        )
                    )
            if line.credit_minor:
                expected = _functional_amount(line.credit_minor, line.currency, line.fx_rate_decimal, functional)
                if abs(expected - line.functional_credit_minor) > 1:
                    violations.append(
                        Violation(
                            invariant_id="INV-08",
                            entity_key=f"journal_entries:{entry.je_id}",
                            expected_delta_minor=line.functional_credit_minor - expected,
                            currency=line.currency,
                            direction="mismatch",
                            tolerance_minor=1,
                            detail=f"functional credit {line.functional_credit_minor} != recomputed {expected}",
                            entity_ids=(entry.je_id, line.line_id),
                        )
                    )
    return violations


def check_allocation_conservation(book: Book) -> list[Violation]:
    """INV-15: allocations must not exceed the payment they belong to."""
    violations: list[Violation] = []
    for payment in book.payments:
        allocated = payment.allocated_minor
        if allocated > payment.amount_minor:
            violations.append(
                Violation(
                    invariant_id="INV-15",
                    entity_key=f"payments:{payment.pay_id}",
                    expected_delta_minor=allocated - payment.amount_minor,
                    currency=payment.currency,
                    direction="over",
                    tolerance_minor=0,
                    detail=f"allocated {allocated} exceeds payment {payment.amount_minor}",
                    entity_ids=(payment.pay_id,),
                )
            )
    return violations


def check_credit_note_limit(book: Book) -> list[Violation]:
    """INV-16: credit notes may not exceed the policy cap of the invoice total."""
    violations: list[Violation] = []
    cap_bps = int(book.policy.get("credit_note_cap_bps", 0))
    credited: dict[str, int] = {}
    for note in book.credit_notes:
        credited[note.invoice_id] = credited.get(note.invoice_id, 0) + note.amount_minor
    for invoice in book.invoices:
        total = credited.get(invoice.doc_id, 0)
        cap = invoice.total_minor * cap_bps // 10000
        if total > cap:
            violations.append(
                Violation(
                    invariant_id="INV-16",
                    entity_key=f"invoices:{invoice.doc_id}",
                    expected_delta_minor=total - cap,
                    currency=invoice.currency,
                    direction="over",
                    tolerance_minor=0,
                    detail=f"credit notes {total} exceed cap {cap}",
                    entity_ids=(invoice.doc_id,),
                )
            )
    return violations


def check_open_balance(book: Book) -> list[Violation]:
    """INV-04: no silent overpayment — open balance may not go below zero."""
    violations: list[Violation] = []
    for balance in sorted(invoice_open_balances(book).values(), key=lambda item: item.doc_id):
        if balance.remaining_minor < 0:
            violations.append(
                Violation(
                    invariant_id="INV-04",
                    entity_key=f"invoices:{balance.doc_id}",
                    expected_delta_minor=-balance.remaining_minor,
                    currency=balance.currency,
                    direction="over",
                    tolerance_minor=0,
                    detail=(
                        f"overpaid by {-balance.remaining_minor}: total {balance.total_minor}, "
                        f"credited {balance.credited_minor}, allocated {balance.allocated_minor}"
                    ),
                    entity_ids=(balance.doc_id,),
                )
            )
    return violations


def check_document_status(book: Book) -> list[Violation]:
    """INV-17: stored status must equal the derived status."""
    violations: list[Violation] = []
    found = 0
    for balance in sorted(invoice_open_balances(book).values(), key=lambda item: item.doc_id):
        invoice = _optional_invoice(book, balance.doc_id)
        if invoice is None:
            continue
        derived = _derived_status(balance, invoice)
        if invoice.status != derived:
            violations.append(
                Violation(
                    invariant_id="INV-17",
                    entity_key=f"invoices:{invoice.doc_id}",
                    expected_delta_minor=balance.remaining_minor,
                    currency=invoice.currency,
                    direction="mismatch",
                    tolerance_minor=0,
                    detail=f"stored status {invoice.status} != derived {derived}",
                    entity_ids=(invoice.doc_id,),
                )
            )
    return violations


def check_bank_match(book: Book) -> list[Violation]:
    """INV-06: matched bank lines must agree with their payment."""
    violations: list[Violation] = []
    payments = book.by_id("payments")
    for line in book.bank_lines:
        if line.matched_payment_id is None:
            if line.status == "MATCHED":
                violations.append(
                    _invalid("INV-06", f"bank_lines:{line.bank_line_id}", line.bank_line_id,
                             "MATCHED bank line without a payment reference")
                )
            continue
        payment = payments.get(line.matched_payment_id)
        if payment is None:
            # Referential integrity is INV-12; report and continue.
            violations.append(
                _invalid("INV-06", f"bank_lines:{line.bank_line_id}", line.bank_line_id,
                         f"matched payment {line.matched_payment_id} not found")
            )
            continue
        if line.amount_minor != payment.amount_minor or line.currency != payment.currency:
            violations.append(
                Violation(
                    invariant_id="INV-06",
                    entity_key=f"bank_lines:{line.bank_line_id}",
                    expected_delta_minor=line.amount_minor - payment.amount_minor,
                    currency=line.currency,
                    direction="mismatch",
                    tolerance_minor=0,
                    detail="bank line amount/currency differs from matched payment",
                    entity_ids=(line.bank_line_id, payment.pay_id),
                )
            )
        if line.status != "MATCHED":
            violations.append(
                _invalid("INV-06", f"bank_lines:{line.bank_line_id}", line.bank_line_id,
                         f"matched payment but status {line.status}")
            )
    return violations


def check_trial_balance(book: Book) -> list[Violation]:
    """INV-02: functional postings must net to zero across the whole book."""
    debit = sum(entry.functional_debit_total for entry in book.journal_entries)
    credit = sum(entry.functional_credit_total for entry in book.journal_entries)
    if debit == credit:
        return []
    return [
        Violation(
            invariant_id="INV-02",
            entity_key="trial_balance",
            expected_delta_minor=debit - credit,
            currency=book.company["functional_currency"],
            direction="mismatch",
            tolerance_minor=0,
            detail=f"functional debit {debit} != credit {credit}",
            entity_ids=(),
        )
    ]


def check_ar_subledger(book: Book) -> list[Violation]:
    """INV-03: receivable ledger vs sum of document open balances."""
    violations: list[Violation] = []
    receivable = book.account_by_role("receivable")
    # Compare in transaction minor units per (currency, counterparty): the subledger
    # and the document open balances are both expressed in document currency.
    ledger: dict[tuple[str, str | None], int] = {}
    for entry in book.journal_entries:
        for line in entry.lines:
            if line.account_id == receivable.account_id:
                key = (line.currency, line.counterparty_id)
                ledger[key] = ledger.get(key, 0) + line.debit_minor - line.credit_minor
    documents: dict[tuple[str, str | None], int] = {}
    for balance in invoice_open_balances(book).values():
        invoice = book.invoice(balance.doc_id)
        key = (balance.currency, invoice.counterparty_id)
        documents[key] = documents.get(key, 0) + balance.remaining_minor
    for key in sorted(set(ledger) | set(documents)):
        currency, counterparty_id = key
        ledger_amount = ledger.get(key, 0)
        document_amount = documents.get(key, 0)
        if ledger_amount != document_amount:
            violations.append(
                Violation(
                    invariant_id="INV-03",
                    entity_key=f"receivable_subledger:{currency}:{counterparty_id}",
                    expected_delta_minor=ledger_amount - document_amount,
                    currency=currency,
                    direction="mismatch",
                    tolerance_minor=0,
                    detail=(
                        f"receivable ledger {ledger_amount} != document open balance "
                        f"{document_amount} for {currency}/{counterparty_id}"
                    ),
                    entity_ids=tuple(sorted(
                        doc_id for doc_id, balance in invoice_open_balances(book).items()
                        if balance.currency == currency
                    )),
                )
            )
    return violations


def check_aging(book: Book) -> list[Violation]:
    """INV-05: aging buckets follow due date and remaining balance.

    The reporting date is the end of the last period the book covers (a *calendar*
    fact, not a document fact): an open amount whose due date has already passed
    must not be reported as a future/undated balance, and a document that carries no
    open amount cannot be in any overdue bucket.
    """
    violations: list[Violation] = []
    calendar = book.calendar()
    # Reporting date: the last day of the latest period the book actually uses.
    periods = sorted({entry.posting_period for entry in book.journal_entries})
    if not periods:
        return []
    reporting_day = calendar.period_bounds(periods[-1])[1]
    for balance in sorted(invoice_open_balances(book).values(), key=lambda item: item.doc_id):
        invoice = _optional_invoice(book, balance.doc_id)
        if invoice is None or invoice.status == "VOID":
            continue
        try:
            due = calendar.effective_date(parse_timestamp(invoice.due_timestamp))
        except (ContractError, MoneyError, TimeRuleError):
            continue
        overdue = (reporting_day - due).days > 0
        if overdue and balance.remaining_minor > 0 and invoice.status in ("PAID", "CREDITED"):
            violations.append(
                _invalid("INV-05", f"invoices:{balance.doc_id}", balance.doc_id,
                         f"overdue open amount {balance.remaining_minor} on a {invoice.status} invoice")
            )
        if not overdue and balance.remaining_minor > 0 and (reporting_day - due).days < 0 \
                and invoice.issue_timestamp and _issued_after(reporting_day, invoice, calendar):
            violations.append(
                _invalid("INV-05", f"invoices:{balance.doc_id}", balance.doc_id,
                         "document issued after the reporting date but carrying an open amount")
            )
    return violations


def _issued_after(reporting_day: date, invoice: Any, calendar: Any) -> bool:
    try:
        return calendar.effective_date(parse_timestamp(invoice.issue_timestamp)) > reporting_day
    except (ContractError, MoneyError, TimeRuleError):
        return False


def check_all(book: Book) -> list[Violation]:
    """Run the complete generator-side invariant suite in a stable order."""
    violations: list[Violation] = []
    for check in (
        check_id_uniqueness,
        check_referential,
        check_currency_exponent,
        check_timezone,
        check_je_balance,
        check_trial_balance,
        check_open_balance,
        check_allocation_conservation,
        check_credit_note_limit,
        check_document_status,
        check_bank_match,
        check_fx_policy,
        check_fx_recalc,
        check_cutoff,
        check_period_totals,
        check_ar_subledger,
        check_aging,
    ):
        violations.extend(check(book))
    return sorted(violations, key=lambda violation: violation.sort_key())


def violations_by_invariant(violations: Iterable[Violation]) -> dict[str, list[Violation]]:
    grouped: dict[str, list[Violation]] = {}
    for violation in violations:
        grouped.setdefault(violation.invariant_id, []).append(violation)
    return dict(sorted(grouped.items()))


# --------------------------------------------------------------------- helpers
_KEY_FIELD = {
    "accounts": "account_id",
    "counterparties": "counterparty_id",
    "journal_entries": "je_id",
    "invoices": "doc_id",
    "credit_notes": "credit_note_id",
    "payments": "pay_id",
    "bank_lines": "bank_line_id",
    "fx_rates": "effective_date",
}


def _ref_violation(entity_key: str, entity_id: str, detail: str) -> Violation:
    return Violation(
        invariant_id="INV-12",
        entity_key=entity_key,
        expected_delta_minor=None,
        currency=None,
        direction="invalid",
        tolerance_minor=0,
        detail=detail,
        entity_ids=(entity_id,),
    )


def _invalid(invariant_id: str, entity_key: str, entity_id: str, detail: str) -> Violation:
    return Violation(
        invariant_id=invariant_id,
        entity_key=entity_key,
        expected_delta_minor=None,
        currency=None,
        direction="invalid",
        tolerance_minor=0,
        detail=detail,
        entity_ids=(entity_id,),
    )


def _entry_currency(entry: Any) -> str | None:
    currencies = {line.currency for line in entry.lines}
    return currencies.pop() if len(currencies) == 1 else None


def _functional_amount(
    amount_minor: int, currency: str, rate: Decimal, functional: str
) -> int:
    """Recompute functional minor units from a booked rate (exact Decimal math)."""
    from core.money import convert_minor

    if currency == functional:
        return amount_minor
    # Rates are quoted as currency -> functional, so converting honours exponents.
    return convert_minor(amount_minor, currency, functional, rate).amount_minor


def _resolve_invoice_context(
    book: Book, document_id: str | None
) -> Any:
    """Resolve the invoice behind an entry's ``source_document_id``.

    A payment JE references the invoice it settles (payments themselves also
    appear as ``source_document_id`` when a bank-line JE is used, so this helper
    falls back to the allocation target). Public evidence only: invoices and
    payment allocations.
    """
    if document_id is None:
        return None
    invoices = book.by_id("invoices")
    if document_id in invoices:
        return invoices[document_id]
    payment = book.by_id("payments").get(document_id)
    if payment is not None and payment.allocations:
        target = payment.allocations[0].document_id
        return invoices.get(target)
    note = book.by_id("credit_notes").get(document_id)
    if note is not None:
        return invoices.get(note.invoice_id)
    return None


def _recognition_moment(
    document_id: str | None,
    invoices: dict[str, Any],
    recognition_rule: str,
    fallback_timestamp: str,
) -> datetime:
    if document_id is None or document_id not in invoices:
        return parse_timestamp(fallback_timestamp)
    invoice = invoices[document_id]
    if recognition_rule == "service_end" and invoice.service_end is not None:
        return parse_timestamp(invoice.service_end)
    if recognition_rule == "issue_date":
        return parse_timestamp(invoice.issue_timestamp)
    if recognition_rule == "delivery_date" and invoice.service_end is not None:
        return parse_timestamp(invoice.service_end)
    return parse_timestamp(invoice.service_start)


def _is_document_settlement(book: Book, entry: Any) -> bool:
    """True when the entry settles or adjusts an existing receivable.

    Public evidence only: the referenced document table and the entry description.
    """
    document_id = entry.source_document_id
    if document_id is None:
        return False
    if document_id in book.by_id("payments") or document_id in book.by_id("credit_notes"):
        return True
    return entry.description.startswith("Customer settlement")


def _rate_basis_day_for_invoice(
    calendar: Any,
    invoice: Any,
    rate_basis: str,
    moment: datetime,
) -> date:
    """Company-local quote date for the policy basis, resolved via the invoice."""
    if invoice is None:
        return calendar.effective_date(moment)
    if rate_basis == "document_date":
        return calendar.effective_date(parse_timestamp(invoice.issue_timestamp))
    if rate_basis == "posting_date":
        return calendar.effective_date(moment)
    if rate_basis == "payment_date":
        return calendar.effective_date(parse_timestamp(invoice.due_timestamp))
    return calendar.effective_date(moment)


def _rate_basis_day(
    calendar: Any,
    document_id: str | None,
    invoices: dict[str, Any],
    rate_basis: str,
    moment: datetime,
) -> date:
    """Company-local quote date for the policy rate basis (never the UTC date)."""
    if document_id is None or document_id not in invoices:
        return calendar.effective_date(moment)
    invoice = invoices[document_id]
    if rate_basis == "document_date":
        return calendar.effective_date(parse_timestamp(invoice.issue_timestamp))
    if rate_basis == "posting_date":
        return calendar.effective_date(moment)
    if rate_basis == "payment_date":
        return calendar.effective_date(parse_timestamp(invoice.due_timestamp))
    return calendar.effective_date(moment)


def _optional_invoice(book: Book, doc_id: str) -> Any:
    """``book.invoice`` but tolerant of a row that lost its identity (INV-11/12)."""
    try:
        return book.invoice(doc_id)
    except (ContractError, MoneyError, TimeRuleError):
        return None


def _expense_account_id(book: Book) -> str:
    for account in book.accounts:
        if account.code == "5000":
            return account.account_id
    return ""


def _derived_status(balance: OpenBalance, invoice: Any) -> str:
    if invoice.status == "VOID":
        return "VOID"
    remaining = balance.remaining_minor
    if remaining < 0:
        return "OVERPAID"
    if remaining == 0:
        return "PAID" if balance.allocated_minor > 0 else "CREDITED" if balance.credited_minor > 0 else "OPEN"
    if balance.allocated_minor > 0 or balance.credited_minor > 0:
        return "PARTIALLY_PAID"
    return "OPEN"
