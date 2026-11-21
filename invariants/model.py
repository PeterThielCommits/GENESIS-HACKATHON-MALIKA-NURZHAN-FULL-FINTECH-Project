"""Normative accounting invariant catalog (12.1, REQ-INV-001..005).

This module holds the *written specification* of the invariants as machine-readable
metadata plus the generator-side checks. It is deliberately small and transparent:
the independent verifier (Phase 8) implements its own discovery algorithms from
public data and does not import the generator, so this file is a **common-mode
dependency only for the generator side** and is reported as such
(docs/INDEPENDENCE.md, 12.4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final, Iterable, Literal

Direction = Literal["over", "under", "mismatch", "invalid"]


@dataclass(frozen=True)
class InvariantSpec:
    invariant_id: str
    name: str
    scope: str
    grouping_key: str
    money_metric: str
    tolerance_rule: str
    null_semantics: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "invariant_id": self.invariant_id,
            "name": self.name,
            "scope": self.scope,
            "grouping_key": self.grouping_key,
            "money_metric": self.money_metric,
            "tolerance_rule": self.tolerance_rule,
            "null_semantics": self.null_semantics,
            "description": self.description,
        }


INVARIANT_CATALOG: Final[tuple[InvariantSpec, ...]] = (
    InvariantSpec(
        "INV-01",
        "JE_BALANCE",
        "each journal_entries row",
        "je_id",
        "debit_minor vs credit_minor and functional totals",
        "exact (0 minor units)",
        "null source_document_id means 'no linked document', never 'unknown'",
        "Each journal entry must balance in transaction currency and in functional currency.",
    ),
    InvariantSpec(
        "INV-02",
        "TRIAL_BALANCE",
        "whole book",
        "account_id",
        "sum of functional debits minus functional credits",
        "exact (0 minor units)",
        "accounts with no postings have zero balance",
        "The trial balance must net to zero across all accounts.",
    ),
    InvariantSpec(
        "INV-03",
        "AR_SUBLEDGER_VS_DOCS",
        "whole book",
        "counterparty_id",
        "receivable ledger balance vs sum of document open balances",
        "exact (0 minor units)",
        "documents without payments contribute their full total",
        "The receivable subledger must agree with the sum of document open balances.",
    ),
    InvariantSpec(
        "INV-04",
        "OPEN_BALANCE",
        "each invoice",
        "doc_id",
        "total_minor - credit_notes - allocated payments",
        "tolerance_minor per finding",
        "service_end null means single-date service",
        "A document's open balance may never become negative (no silent overpayment).",
    ),
    InvariantSpec(
        "INV-05",
        "AGING",
        "each invoice bucket",
        "doc_id",
        "open balance by due-date bucket",
        "exact",
        "void documents are excluded from aging",
        "Aging buckets must follow due date and remaining open balance.",
    ),
    InvariantSpec(
        "INV-06",
        "BANK_MATCH",
        "each bank line",
        "bank_line_id",
        "matched payment amount vs bank line amount",
        "exact",
        "unmatched lines must carry UNMATCHED status",
        "Matched bank lines must agree with the matched payment; a duplicate real transfer may legitimately appear twice.",
    ),
    InvariantSpec(
        "INV-07",
        "FX_POLICY",
        "each posted line in foreign currency",
        "line_id",
        "booked rate vs policy-required rate",
        "rate equality at registry scale",
        "functional currency lines use rate 1",
        "The booked FX rate must equal the rate the public policy requires for the event date.",
    ),
    InvariantSpec(
        "INV-08",
        "FX_RECALC",
        "each posted line in foreign currency",
        "line_id",
        "functional amount vs recomputed functional amount",
        "tolerance_minor derived from rounding trace",
        "n/a",
        "Functional amounts must be recomputable from the booked rate within tolerance.",
    ),
    InvariantSpec(
        "INV-09",
        "CUTOFF",
        "each journal entry",
        "je_id",
        "posting_period vs policy recognition period",
        "exact period equality",
        "n/a",
        "The posting period must equal the period implied by the recognition rule and company timezone.",
    ),
    InvariantSpec(
        "INV-10",
        "PERIOD_TOTALS",
        "each period",
        "posting_period",
        "sum of functional postings per period",
        "exact",
        "n/a",
        "Period totals must be derived from the entries assigned to that period.",
    ),
    InvariantSpec(
        "INV-11",
        "ID_UNIQUENESS",
        "each table",
        "primary key",
        "n/a",
        "exact",
        "n/a",
        "Primary keys must be unique inside their table and namespace.",
    ),
    InvariantSpec(
        "INV-12",
        "REFERENTIAL",
        "whole book",
        "referencing id",
        "n/a",
        "exact",
        "explicit null means 'not applicable'; it never permits guessing",
        "Every explicit reference must resolve to an existing row.",
    ),
    InvariantSpec(
        "INV-13",
        "CURRENCY_EXPONENT",
        "each money field",
        "row id",
        "scale and minor-unit magnitude",
        "exact",
        "n/a",
        "Money must be integer minor units of a registered currency within the safe range.",
    ),
    InvariantSpec(
        "INV-14",
        "TIMEZONE_VALID",
        "each timestamp",
        "row id",
        "n/a",
        "exact",
        "n/a",
        "Timestamps must be ISO-8601 with an offset and unambiguous in the company timezone.",
    ),
    InvariantSpec(
        "INV-15",
        "ALLOCATION_CONSERVATION",
        "each payment",
        "pay_id",
        "sum of allocations vs payment amount, and allocation targets vs policy rule",
        "exact (0 minor units)",
        "an allocation with document_id is always an explicit reference",
        "Allocations must conserve the payment amount and settle documents the policy allows.",
    ),
    InvariantSpec(
        "INV-16",
        "CREDIT_NOTE_LIMIT",
        "each invoice",
        "doc_id",
        "sum of credit notes vs policy cap",
        "exact",
        "n/a",
        "Credit notes may not exceed the policy-defined cap of the document total.",
    ),
    InvariantSpec(
        "INV-17",
        "DOCUMENT_STATUS",
        "each invoice",
        "doc_id",
        "derived status vs stored status",
        "exact",
        "n/a",
        "The stored document status must match the status derived from open balance and events.",
    ),
)

INVARIANT_BY_ID: Final[dict[str, InvariantSpec]] = {
    spec.invariant_id: spec for spec in INVARIANT_CATALOG
}


def require_invariant(invariant_id: str) -> InvariantSpec:
    spec = INVARIANT_BY_ID.get(invariant_id)
    if spec is None:
        from contracts.errors import ContractError

        raise ContractError("unknown invariant id", invariant_id=invariant_id)
    return spec


@dataclass(frozen=True)
class Violation:
    """One invariant violation with a comparable, deterministic signature (12.3)."""

    invariant_id: str
    entity_key: str
    expected_delta_minor: int | None
    currency: str | None
    direction: Direction
    tolerance_minor: int
    side_effect_class: str = "intended"
    detail: str = ""
    entity_ids: tuple[str, ...] = field(default_factory=tuple)

    def signature(self) -> dict[str, Any]:
        return {
            "invariant_id": self.invariant_id,
            "entity_key": self.entity_key,
            "expected_delta_minor": self.expected_delta_minor,
            "currency": self.currency,
            "direction": self.direction,
            "tolerance_minor": self.tolerance_minor,
            "side_effect_class": self.side_effect_class,
        }

    def sort_key(self) -> tuple:
        return (
            self.invariant_id,
            self.entity_key,
            self.direction,
            self.expected_delta_minor if self.expected_delta_minor is not None else 0,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.signature())
        payload["detail"] = self.detail
        payload["entity_ids"] = list(self.entity_ids)
        return payload


def summarise(violations: Iterable[Violation]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for violation in violations:
        counts[violation.invariant_id] = counts.get(violation.invariant_id, 0) + 1
    return dict(sorted(counts.items()))
