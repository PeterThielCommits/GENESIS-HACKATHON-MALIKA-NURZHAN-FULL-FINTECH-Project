"""DUPLICATE_PAYMENT operator (Phase 4.2, 11.2).

Semantics: one document is factually settled more than once without a credit note,
refund or void that would explain the excess. The operator appends a *second*
payment — with a normal new id, a realistic timestamp, its own bank line and a
balanced journal entry — that allocates to an already-settled invoice.

Deliberate design choices (they make the anomaly reachable from public data only):

* the duplicate gets a **new** bank reference, so BANK_MATCH and REFERENTIAL stay
  clean (INV-06/INV-12 are forbidden invariants for this type);
* the journal entry is balanced in both transaction and functional currency
  (INV-01 untouched), and books the document-date rate (INV-07 untouched);
* the posting period comes from the duplicate's own timestamp (INV-09/INV-10);
* only INV-04 (negative open balance) and INV-17 (status drift) break, with
  INV-03/INV-05 allowed as documented settlement side effects;
* the operator never touches the clean twin's ids, ordering or counts elsewhere.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Mapping, Sequence

from contracts.errors import OperatorError
from contracts.models import Allocation, BankLine, JournalEntry, Payment
from core.time_rules import format_timestamp, parse_timestamp
from gen.core.journal import build_line, credited_totals
from gen.core.rng import RngStream
from gen.errors.base import MutationOperator, OperatorApplication, OperatorSpec, require_keys
from gen.errors.signatures import ERROR_MATRIX
from gen.twins import Book

OPERATOR_VERSION = "1.0.0"


class DuplicatePaymentOperator(MutationOperator):
    """Create a second, unex-plained settlement of an already-settled invoice."""

    spec = OperatorSpec(
        operator_id="OP-DUPLICATE_PAYMENT",
        operator_version=OPERATOR_VERSION,
        anomaly_type="DUPLICATE_PAYMENT",
        intended_invariants=ERROR_MATRIX["DUPLICATE_PAYMENT"]["intended"],
        allowed_side_effects=ERROR_MATRIX["DUPLICATE_PAYMENT"]["allowed"],
        forbidden_invariants=ERROR_MATRIX["DUPLICATE_PAYMENT"]["forbidden"],
        supported_policy_profiles=("standard_v1",),
    )

    REQUIRED_PARAMS = ("target_invoice_id", "replay_delay_days", "payment_channel")

    # -------------------------------------------------------------- preconditions
    def preconditions(self, book: Book, params: Mapping[str, Any]) -> None:
        require_keys(params, self.REQUIRED_PARAMS, operator=self.spec.operator_id)
        invoice_id = str(params["target_invoice_id"])
        invoices = book.by_id("invoices")
        if invoice_id not in invoices:
            raise OperatorError("target invoice does not exist", invoice_id=invoice_id)
        invoice = invoices[invoice_id]
        if invoice.status == "VOID":
            raise OperatorError("target invoice is void", invoice_id=invoice_id)

        credited = credited_totals(book.credit_notes).get(invoice_id, 0)
        settled = sum(
            allocation.amount_minor
            for payment in book.payments
            for allocation in payment.allocations
            if allocation.document_id == invoice_id
        )
        if settled <= 0:
            raise OperatorError(
                "target invoice has no settlement to duplicate", invoice_id=invoice_id
            )
        if credited >= invoice.total_minor:
            raise OperatorError(
                "target invoice is fully credited; excess would be explainable",
                invoice_id=invoice_id,
            )
        delay = params["replay_delay_days"]
        if isinstance(delay, bool) or not isinstance(delay, int) or not 1 <= delay <= 90:
            raise OperatorError("replay_delay_days must be an int in 1..90", value=repr(delay))
        channel = params["payment_channel"]
        if channel not in ("WIRE", "ACH", "CARD"):
            raise OperatorError("unsupported payment channel", channel=repr(channel))
        if params.get("bank_reference_strategy") not in (None, "new_reference"):
            raise OperatorError(
                "only 'new_reference' keeps BANK_MATCH out of the anomaly",
                strategy=params["bank_reference_strategy"],
            )

    # --------------------------------------------------------------------- apply
    def apply_book(self, book: Book, params: Mapping[str, Any], rng: RngStream) -> Book:
        invoice = book.invoice(str(params["target_invoice_id"]))
        delay = int(params["replay_delay_days"])
        channel = str(params["payment_channel"])

        # The duplicate replays the *latest* settlement of this invoice: same amount,
        # same allocation target, a realistic later timestamp.
        settled_payments = sorted(
            (
                payment
                for payment in book.payments
                if any(allocation.document_id == invoice.doc_id for allocation in payment.allocations)
            ),
            key=lambda payment: (payment.timestamp, payment.pay_id),
        )
        if not settled_payments:  # pragma: no cover - guarded by preconditions
            raise OperatorError("no settlement payment found", invoice_id=invoice.doc_id)
        original = settled_payments[-1]
        duplicate_amount = sum(
            allocation.amount_minor
            for allocation in original.allocations
            if allocation.document_id == invoice.doc_id
        )
        if duplicate_amount <= 0:  # pragma: no cover - defensive
            raise OperatorError("original settlement amount is zero", invoice_id=invoice.doc_id)

        pay_id = _new_payment_id(book, rng)
        bank_line_id = _new_bank_line_id(book, rng)
        allocation_id = _new_allocation_id(book, rng)
        moment = parse_timestamp(original.timestamp) + timedelta(days=delay)
        moment = moment.replace(minute=(moment.minute + 7) % 60)
        timestamp = format_timestamp(moment)

        rate = _document_rate(book, invoice)
        mode = str(book.policy["rounding_mode"])
        functional = str(book.company["functional_currency"])
        from core.money import convert_minor
        from gen.errors.ids import issue_unique_ids

        line_ids = issue_unique_ids(book, rng, "journal_entry_lines", 2)
        functional_amount = (
            duplicate_amount
            if invoice.currency == functional
            else convert_minor(
                duplicate_amount, invoice.currency, functional, rate, mode=mode
            ).amount_minor
        )

        allocation = Allocation(
            allocation_id=allocation_id,
            document_id=invoice.doc_id,
            amount_minor=duplicate_amount,
            allocation_timestamp=timestamp,
        )
        duplicate = Payment(
            pay_id=pay_id,
            timestamp=timestamp,
            counterparty_id=original.counterparty_id,
            currency=original.currency,
            amount_minor=duplicate_amount,
            functional_amount_minor=functional_amount,
            fx_rate_decimal=rate,
            allocations=(allocation,),
            bank_reference=bank_line_id,
            payment_channel=channel,
        )

        bank_line = BankLine(
            bank_line_id=bank_line_id,
            timestamp=timestamp,
            amount_minor=duplicate_amount,
            currency=invoice.currency,
            direction="IN",
            reference_text=_bank_reference(rng, pay_id, invoice.counterparty_id),
            matched_payment_id=pay_id,
            bank_account_id=str(book.policy["bank_account_id"]),
            status="MATCHED",
        )

        entry = JournalEntry(
            je_id=_new_je_id(book, rng, moment),
            timestamp=timestamp,
            posting_period=book.calendar().posting_period(moment),
            source_document_id=invoice.doc_id,
            description=f"Customer settlement for {pay_id}",
            lines=(
                build_line(
                    line_id=line_ids[0],
                    account_id=str(book.policy["bank_account_id"]),
                    currency=invoice.currency,
                    rate=rate,
                    functional=functional,
                    rounding_mode=mode,
                    counterparty_id=invoice.counterparty_id,
                    analytic_tag=pay_id,
                    debit=duplicate_amount,
                ),
                build_line(
                    line_id=line_ids[1],
                    account_id=str(book.policy["receivable_account_id"]),
                    currency=invoice.currency,
                    rate=rate,
                    functional=functional,
                    rounding_mode=mode,
                    counterparty_id=invoice.counterparty_id,
                    analytic_tag=invoice.doc_id,
                    credit=duplicate_amount,
                ),
            ),
        )

        mutated = book.with_rows("payments", list(book.payments) + [duplicate])
        mutated = mutated.with_rows("bank_lines", list(mutated.bank_lines) + [bank_line])
        mutated = mutated.with_rows("journal_entries", list(mutated.journal_entries) + [entry])
        from gen.core.journal import recompute_invoice_statuses

        return recompute_invoice_statuses(mutated)

    # --------------------------------------------------------------- candidates
    def candidate_params(self, book: Book, config: Mapping[str, Any]) -> list[dict[str, Any]]:
        credited = credited_totals(book.credit_notes)
        allocated: dict[str, int] = {}
        for payment in book.payments:
            for allocation in payment.allocations:
                allocated[allocation.document_id] = (
                    allocated.get(allocation.document_id, 0) + allocation.amount_minor
                )
        delay_low, delay_high = _delay_bounds(config)
        channels = list(config["payment_channel_pool"])
        candidates: list[dict[str, Any]] = []
        for invoice in sorted(book.invoices, key=lambda row: row.doc_id):
            if invoice.status == "VOID":
                continue
            settled = allocated.get(invoice.doc_id, 0)
            if settled <= 0:
                continue
            if credited.get(invoice.doc_id, 0) >= invoice.total_minor:
                continue
            for index, channel in enumerate(channels):
                delay = delay_low + (index % max(1, delay_high - delay_low + 1))
                candidates.append(
                    {
                        "target_invoice_id": invoice.doc_id,
                        "replay_delay_days": delay,
                        "payment_channel": channel,
                        "bank_reference_strategy": "new_reference",
                    }
                )
        return candidates

    # ------------------------------------------------------------------ affected
    def affected_ids(
        self, book_before: Book, book_after: Book, params: Mapping[str, Any]
    ) -> tuple[str, ...]:
        new_payments = _ids(book_after.payments, book_before.payments, "pay_id")
        new_entries = _ids(book_after.journal_entries, book_before.journal_entries, "je_id")
        affected = tuple(sorted(set(new_payments) | set(new_entries)))
        return affected


# --------------------------------------------------------------------- helpers
def _delay_bounds(config: Mapping[str, Any]) -> tuple[int, int]:
    bounds = config.get("replay_delay_days", [3, 14])
    if (
        not isinstance(bounds, (list, tuple))
        or len(bounds) != 2
        or not all(isinstance(value, int) and value > 0 for value in bounds)
    ):
        raise OperatorError("replay_delay_days config must be [low, high]", bounds=repr(bounds))
    low, high = int(bounds[0]), int(bounds[1])
    if low > high:
        raise OperatorError("replay_delay_days bounds inverted", bounds=list(bounds))
    return low, high


def _bank_reference(rng: RngStream, pay_id: str, counterparty_id: str) -> str:
    """Ordinary-looking bank narrative; shares the clean generator's shape."""
    token = f"{rng.random.getrandbits(20):05X}"
    return f"INV-REF {pay_id} {counterparty_id} {token}"


def _document_rate(book: Book, invoice) -> Decimal:  # noqa: ANN001
    """Policy rate on the document (issue) date in company-local time."""
    day = book.calendar().effective_date(parse_timestamp(invoice.issue_timestamp))
    return book.rate_for(invoice.currency, day)


def _ids(rows: Sequence[Any], baseline: Sequence[Any], field: str) -> set[str]:
    existing = {getattr(row, field) for row in baseline}
    return {getattr(row, field) for row in rows} - existing


def _new_payment_id(book: Book, rng: RngStream) -> str:
    from gen.errors.ids import issue_unique_id

    return issue_unique_id(book, rng, "payments")


def _new_bank_line_id(book: Book, rng: RngStream) -> str:
    from gen.errors.ids import issue_unique_id

    return issue_unique_id(book, rng, "bank_lines")


def _new_allocation_id(book: Book, rng: RngStream) -> str:
    from gen.errors.ids import issue_unique_id

    return issue_unique_id(book, rng, "allocations")


def _new_line_id(book: Book, rng: RngStream) -> str:
    from gen.errors.ids import issue_unique_id

    return issue_unique_id(book, rng, "journal_entry_lines")


def _new_je_id(book: Book, rng: RngStream, moment: datetime) -> str:
    from gen.errors.ids import issue_unique_id

    return issue_unique_id(book, rng, "journal_entries", month=moment.month)
