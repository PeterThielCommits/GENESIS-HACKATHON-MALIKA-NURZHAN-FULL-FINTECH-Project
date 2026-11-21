"""PARTIAL_PAYMENT_ALLOCATION operator (Phase 4.3, 11.3).

Semantics: an existing partial payment is allocated in a way the public allocation
policy forbids. Exactly one documented subtype is applied per call and recorded in
the sealed provenance, so generator, verifier and scorer agree on the signature:

``OVER_ALLOCATE_TO_ONE_INVOICE``
    The allocator closes a document with its gross total, ignoring a credit note that
    already reduced the obligation. The payment is smaller than the remaining net
    balance, so the document ends up over-paid and allocations exceed the money
    received.

``ALLOCATE_TO_ALREADY_SETTLED_INVOICE``
    Part of a partial payment is allocated to a *different* invoice that is already
    settled, so that document becomes over-paid while the economically targeted
    invoice keeps an unexplained open balance.

``ALLOCATIONS_EXCEED_PAYMENT``
    The payment is spread over two documents for more than the amount received
    (allocation conservation broken) without necessarily over-paying either one.

Invariants that must stay intact in every subtype: JE balance (INV-01), bank
matching (INV-06), the policy FX rate (INV-07), the posting period (INV-09), ID
uniqueness (INV-11), referential integrity (INV-12), currency exponents (INV-13),
timestamps (INV-14) and credit-note caps (INV-16).
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any, Mapping, Sequence

from contracts.errors import OperatorError
from contracts.models import Allocation, Payment
from core.time_rules import parse_timestamp
from gen.core.journal import (
    allocated_totals,
    credited_totals,
    recompute_invoice_statuses,
)
from gen.core.rng import RngStream
from gen.errors.base import MutationOperator, OperatorSpec, require_keys
from gen.errors.signatures import error_matrix_for
from gen.twins import Book

OPERATOR_VERSION = "1.0.0"
SUBTYPES = (
    "OVER_ALLOCATE_TO_ONE_INVOICE",
    "ALLOCATE_TO_ALREADY_SETTLED_INVOICE",
    "ALLOCATIONS_EXCEED_PAYMENT",
)


class PartialAllocationOperator(MutationOperator):
    """Allocate an existing partial payment against the public allocation policy."""

    spec = OperatorSpec(
        operator_id="OP-PARTIAL_PAYMENT_ALLOCATION",
        operator_version=OPERATOR_VERSION,
        anomaly_type="PARTIAL_PAYMENT_ALLOCATION",
        intended_invariants=error_matrix_for("PARTIAL_PAYMENT_ALLOCATION")["intended"],
        allowed_side_effects=error_matrix_for("PARTIAL_PAYMENT_ALLOCATION")["allowed"],
        forbidden_invariants=error_matrix_for("PARTIAL_PAYMENT_ALLOCATION")["forbidden"],
        supported_policy_profiles=("standard_v1",),
    )

    REQUIRED_PARAMS = ("target_payment_id", "subtype")

    # -------------------------------------------------------------- preconditions
    def preconditions(self, book: Book, params: Mapping[str, Any]) -> None:
        require_keys(params, self.REQUIRED_PARAMS, operator=self.spec.operator_id)
        subtype = params["subtype"]
        if subtype not in SUBTYPES:
            raise OperatorError(
                "unknown allocation subtype", subtype=repr(subtype), allowed=list(SUBTYPES)
            )
        pay_id = str(params["target_payment_id"])
        if pay_id not in book.by_id("payments"):
            raise OperatorError("target payment does not exist", pay_id=pay_id)
        payment = book.payment(pay_id)
        if len(payment.allocations) != 1:
            raise OperatorError(
                "target payment must be a single-allocation payment",
                pay_id=payment.pay_id,
                allocations=len(payment.allocations),
            )
        allocation = payment.allocations[0]
        invoice = book.invoice(allocation.document_id)
        if invoice.currency != payment.currency:
            raise OperatorError(
                "payment and invoice currencies differ; allocation mutation is ambiguous",
                pay_id=payment.pay_id,
            )
        credited = credited_totals(book.credit_notes)
        allocated = allocated_totals(book.payments)
        remaining = (
            invoice.total_minor
            - credited.get(invoice.doc_id, 0)
            - allocated.get(invoice.doc_id, 0)
        )
        if remaining <= 0:
            raise OperatorError("target invoice is already settled", invoice_id=invoice.doc_id)

        if subtype == "OVER_ALLOCATE_TO_ONE_INVOICE":
            # The documented subtype is "the allocator closes the invoice completely
            # although the payment is smaller": this needs a document that already
            # carries a prior partial settlement, so the allocator's mistake (using
            # the gross document amount instead of the remaining balance) is visible
            # and produces a genuinely over-paid document.
            if payment.amount_minor >= remaining:
                raise OperatorError(
                    "payment is not smaller than the remaining balance; "
                    "over-allocation would be honest settlement",
                    pay_id=payment.pay_id,
                    amount_minor=payment.amount_minor,
                    remaining_minor=remaining,
                )
            if remaining >= invoice.total_minor - credited.get(invoice.doc_id, 0):
                raise OperatorError(
                    "invoice has no prior partial settlement; over-allocation impossible",
                    invoice_id=invoice.doc_id,
                )
            if credited.get(invoice.doc_id, 0) <= 0:
                raise OperatorError(
                    "invoice carries no credit note; the gross/net confusion "
                    "that defines this subtype is not observable",
                    invoice_id=invoice.doc_id,
                )
            if invoice.total_minor <= payment.amount_minor:
                raise OperatorError(
                    "payment already covers the gross document amount",
                    invoice_id=invoice.doc_id,
                )
        elif subtype == "ALLOCATE_TO_ALREADY_SETTLED_INVOICE":
            if not self._settled_targets(book, payment, invoice):
                raise OperatorError(
                    "no already-settled invoice available for this counterparty/currency",
                    pay_id=payment.pay_id,
                )
        else:  # ALLOCATIONS_EXCEED_PAYMENT
            if payment.amount_minor <= 0:  # pragma: no cover - defensive
                raise OperatorError("payment amount must be positive", pay_id=payment.pay_id)
            if not self._candidate_second_invoices(book, payment, invoice):
                raise OperatorError(
                    "no second open invoice available for the split subtype",
                    pay_id=payment.pay_id,
                )

    # --------------------------------------------------------------------- apply
    def apply_book(self, book: Book, params: Mapping[str, Any], rng: RngStream) -> Book:
        subtype = str(params["subtype"])
        pay_id = str(params["target_payment_id"])
        if pay_id not in book.by_id("payments"):
            raise OperatorError("target payment does not exist", pay_id=pay_id)
        payment = book.payment(pay_id)
        allocation = payment.allocations[0]
        invoice = book.invoice(allocation.document_id)
        credited = credited_totals(book.credit_notes)
        allocated = allocated_totals(book.payments)

        if subtype == "OVER_ALLOCATE_TO_ONE_INVOICE":
            # Allocator bug: it closes the document with its *gross* total, ignoring
            # the credit note that already reduced the obligation. The document ends
            # up over-paid and the allocation exceeds the money actually received.
            gross_open = invoice.total_minor
            new_allocations = (
                Allocation(
                    allocation_id=allocation.allocation_id,
                    document_id=invoice.doc_id,
                    amount_minor=gross_open,
                    allocation_timestamp=allocation.allocation_timestamp,
                ),
            )
            return self._replace_allocations(book, payment, new_allocations)

        if subtype == "ALLOCATE_TO_ALREADY_SETTLED_INVOICE":
            settled = self._settled_targets(book, payment, invoice)[0]
            # Redirect part of the payment to the already-settled document: the
            # payment still conserves its total, but the money is booked against a
            # closed obligation, so that document becomes over-paid.
            split = max(1, payment.amount_minor * rng.randint(2500, 6000) // 10000)
            if split >= payment.amount_minor:
                split = max(1, payment.amount_minor // 2)
            from gen.errors.ids import issue_unique_ids

            new_allocation_id = issue_unique_ids(book, rng, "allocations", 1)[0]
            new_allocations = (
                Allocation(
                    allocation_id=allocation.allocation_id,
                    document_id=invoice.doc_id,
                    amount_minor=payment.amount_minor - split,
                    allocation_timestamp=allocation.allocation_timestamp,
                ),
                Allocation(
                    allocation_id=new_allocation_id,
                    document_id=settled.doc_id,
                    amount_minor=split,
                    allocation_timestamp=allocation.allocation_timestamp,
                ),
            )
            return self._replace_allocations(book, payment, new_allocations)

        # ALLOCATIONS_EXCEED_PAYMENT
        second = self._candidate_second_invoices(book, payment, invoice)[0]
        extra = max(1, payment.amount_minor * rng.randint(2000, 6000) // 10000)
        from gen.errors.ids import issue_unique_ids

        new_allocation_id = issue_unique_ids(book, rng, "allocations", 1)[0]
        new_allocations = (
            Allocation(
                allocation_id=allocation.allocation_id,
                document_id=invoice.doc_id,
                amount_minor=payment.amount_minor,
                allocation_timestamp=allocation.allocation_timestamp,
            ),
            Allocation(
                allocation_id=new_allocation_id,
                document_id=second.doc_id,
                amount_minor=extra,
                allocation_timestamp=allocation.allocation_timestamp,
            ),
        )
        return self._replace_allocations(book, payment, new_allocations)

    # --------------------------------------------------------------- candidates
    def candidate_params(self, book: Book, config: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Every (payment, subtype) pair that satisfies the preconditions."""
        weights = dict(config["subtype_weights_bps"])
        for subtype in SUBTYPES:
            if subtype not in weights:
                raise OperatorError("subtype missing from config weights", subtype=subtype)
        candidates: list[dict[str, Any]] = []
        for subtype in SUBTYPES:
            if weights[subtype] <= 0:
                continue
            for payment in sorted(book.payments, key=lambda row: row.pay_id):
                if len(payment.allocations) != 1:
                    continue
                invoice = book.invoice(payment.allocations[0].document_id)
                if invoice.currency != payment.currency:
                    continue
                params = {"target_payment_id": payment.pay_id, "subtype": subtype}
                try:
                    self.preconditions(book, params)
                except OperatorError:
                    continue
                candidates.append(params)
        return candidates

    # ------------------------------------------------------------- subtype choice
    def selection_table(
        self,
        candidates: Sequence[Mapping[str, Any]],
        config: Mapping[str, Any],
    ) -> tuple[str, dict[str, int]] | None:
        """Subtype proportions come from the frozen generator config."""
        weights = {str(key): int(value) for key, value in dict(config["subtype_weights_bps"]).items()}
        present = {str(candidate["subtype"]) for candidate in candidates}
        if not present:
            return None
        return "subtype", {key: value for key, value in weights.items() if key in present}

    # ------------------------------------------------------------------ affected
    def affected_ids(
        self, book_before: Book, book_after: Book, params: Mapping[str, Any]
    ) -> tuple[str, ...]:
        pay_id = str(params["target_payment_id"])
        before = book_before.payment(pay_id)
        after = book_after.payment(pay_id)
        before_docs = {allocation.document_id for allocation in before.allocations}
        after_docs = {allocation.document_id for allocation in after.allocations}
        # Documented rule: the payment plus every invoice whose remaining balance is
        # directly affected (target and any newly referenced document).
        affected = {pay_id} | after_docs | before_docs
        return tuple(sorted(affected))

    # ------------------------------------------------------------------ helpers
    def _replace_allocations(
        self, book: Book, payment: Payment, allocations: Sequence[Allocation]
    ) -> Book:
        new_payment = replace(payment, allocations=tuple(allocations))
        mutated = book.with_rows(
            "payments",
            [new_payment if row.pay_id == payment.pay_id else row for row in book.payments],
        )
        return recompute_invoice_statuses(mutated)

    def _open_invoices(self, book: Book, payment: Payment, invoice) -> list[Any]:  # noqa: ANN001
        credited = credited_totals(book.credit_notes)
        allocated = allocated_totals(book.payments)
        result = []
        for candidate in book.invoices:
            if candidate.doc_id == invoice.doc_id:
                continue
            if candidate.counterparty_id != payment.counterparty_id:
                continue
            if candidate.currency != payment.currency:
                continue
            if candidate.status == "VOID":
                continue
            remaining = (
                candidate.total_minor
                - credited.get(candidate.doc_id, 0)
                - allocated.get(candidate.doc_id, 0)
            )
            if remaining > 0:
                result.append(candidate)
        return sorted(result, key=lambda item: (item.issue_timestamp, item.doc_id))

    def _candidate_second_invoices(self, book: Book, payment: Payment, invoice) -> list[Any]:  # noqa: ANN001
        """Any other non-void document of the same counterparty and currency.

        The split subtype does not require the second document to be open: sending
        part of a payment to an unrelated (possibly already settled) obligation is
        exactly the misallocation being modelled.
        """
        return [
            candidate
            for candidate in sorted(book.invoices, key=lambda row: (row.issue_timestamp, row.doc_id))
            if candidate.doc_id != invoice.doc_id
            and candidate.counterparty_id == payment.counterparty_id
            and candidate.currency == payment.currency
            and candidate.status != "VOID"
        ]

    def _settled_targets(self, book: Book, payment: Payment, invoice) -> list[Any]:  # noqa: ANN001
        """Invoices of the same counterparty/currency that are already fully settled."""
        credited = credited_totals(book.credit_notes)
        allocated = allocated_totals(book.payments)
        result = []
        for candidate in book.invoices:
            if candidate.doc_id == invoice.doc_id:
                continue
            if candidate.counterparty_id != payment.counterparty_id:
                continue
            if candidate.currency != payment.currency:
                continue
            if candidate.status == "VOID":
                continue
            remaining = (
                candidate.total_minor
                - credited.get(candidate.doc_id, 0)
                - allocated.get(candidate.doc_id, 0)
            )
            if remaining <= 0:
                result.append(candidate)
        return sorted(result, key=lambda item: (item.issue_timestamp, item.doc_id))


def _document_rate(book: Book, invoice, payment: Payment) -> Decimal:  # noqa: ANN001
    """Policy rate for the settled document (document-date basis)."""
    day = book.calendar().effective_date(parse_timestamp(invoice.issue_timestamp))
    return book.rate_for(invoice.currency, day)
