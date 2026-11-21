"""Candidate-truth construction from diff + invariants + operator declaration (4.5).

Why truth cannot be a hand-written label (P-002, 10.3, REQ-GEN-010):

    candidate mutation -> diff facts -> invariant signature -> (later) verifier

This module builds the *candidate* truth and proves the first three links:

1. every finding must be backed by concrete diff facts (added/modified rows);
2. every finding must match an actual invariant violation of the mutated twin,
   with a concrete amount, currency, tolerance and direction;
3. every finding's affected ids must be exactly the operator's documented ids and
   must be reachable from public rows.

The independent verifier cross-check (G13/G14) happens in Phase 8; here we expose
``reachable_evidence`` so the verifier can be compared against a stable contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from contracts.canonical import digest_of
from contracts.errors import ContractError
from core.money import parse_decimal
from gen.twins import Book
from gen.truthdiff import TABLE_KEY_FIELDS, RowChange, TwinDiff
from invariants.checks_clean import invoice_open_balances
from invariants.model import Violation

TRUTH_VERSION = "1.0.0"
OPTIMAL_STEPS_MODEL_ID = "query_plan_v1"

# Which invariant of the mutated twin carries the finding's money for each subtype.
# The map is explicit so nothing depends on incidental ordering of violations.
AMOUNT_INVARIANT_BY_SIGNATURE: dict[tuple[str, str | None], str] = {
    ("DUPLICATE_PAYMENT", None): "INV-04",
    ("PARTIAL_PAYMENT_ALLOCATION", "OVER_ALLOCATE_TO_ONE_INVOICE"): "INV-04",
    ("PARTIAL_PAYMENT_ALLOCATION", "ALLOCATE_TO_ALREADY_SETTLED_INVOICE"): "INV-04",
    ("PARTIAL_PAYMENT_ALLOCATION", "ALLOCATIONS_EXCEED_PAYMENT"): "INV-15",
}

# Which public row ids form the minimal evidence set for each anomaly type.
EVIDENCE_RULE_BY_TYPE: dict[str, str] = {
    "DUPLICATE_PAYMENT": "v1: invoice + original allocation + duplicate payment + absence of credit/refund",
    "PARTIAL_PAYMENT_ALLOCATION": "v1: payment + allocations + target invoice + policy allocation rule",
}


@dataclass(frozen=True)
class CandidateFinding:
    """A truth candidate derived from evidence — not from a label."""

    anomaly_type: str
    subtype: str | None
    affected_ids: tuple[str, ...]
    amount_minor: int
    currency: str
    tolerance_minor: int
    invariant_signature: Mapping[str, Any]
    evidence_sets: tuple[tuple[str, ...], ...]
    minimal_evidence_size: int
    depends_on: tuple[str, ...]
    diff_refs: tuple[str, ...]
    operator_id: str
    operator_version: str
    detail: str = ""

    def to_truth_finding(self, truth_id: str, optimal_steps: int | None = None) -> dict[str, Any]:
        return {
            "truth_id": truth_id,
            "type": self.anomaly_type,
            "affected_ids": sorted(self.affected_ids),
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "tolerance_minor": self.tolerance_minor,
            "evidence_sets": [sorted(items) for items in self.evidence_sets],
            "minimal_evidence_size": self.minimal_evidence_size,
            "invariant_signature": dict(self.invariant_signature),
            "operator_version": self.operator_version,
            "depends_on": sorted(self.depends_on),
            "optimal_steps_model_id": OPTIMAL_STEPS_MODEL_ID,
            "optimal_steps": optimal_steps,
        }

    def describe(self) -> dict[str, Any]:
        return {
            "type": self.anomaly_type,
            "subtype": self.subtype,
            "affected_ids": list(self.affected_ids),
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "minimal_evidence_size": self.minimal_evidence_size,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class TruthBuild:
    findings: tuple[CandidateFinding, ...]
    diff: TwinDiff
    evidence_index: Mapping[str, tuple[str, ...]]
    notes: tuple[str, ...] = ()

    @property
    def is_clean(self) -> bool:
        return not self.findings

    def to_truth_document(self, *, episode_id: str, mode: str) -> dict[str, Any]:
        findings = [
            finding.to_truth_finding(f"TR-{index + 1:03d}")
            for index, finding in enumerate(self.findings)
        ]
        return {
            "truth_version": TRUTH_VERSION,
            "episode_id": episode_id,
            "mode": mode,
            "findings": findings,
            "diff_summary": {
                "added": len(self.diff.added()),
                "removed": len(self.diff.removed()),
                "modified": len(self.diff.modified()),
                "unchanged_tables_digest": digest_of(self.diff.by_table()),
            },
            "distractors": [],
        }

    def digest(self) -> str:
        return digest_of([finding.describe() for finding in self.findings])


def build_candidate_truth(
    *,
    clean: Book,
    mutated: Book,
    diff: TwinDiff,
    violations: Sequence[Violation],
    application: Any,
    subtype: str | None,
) -> TruthBuild:
    """Derive the candidate truth for exactly one operator application."""
    anomaly_type = _anomaly_type_for(application.operator_id)
    violations = [violation for violation in violations if violation.side_effect_class != "allowed"]
    build = TruthBuild(
        findings=(),
        diff=diff,
        evidence_index=reachable_evidence(mutated),
        notes=(),
    )

    if not diff.added("payments") and anomaly_type == "DUPLICATE_PAYMENT":
        raise ContractError("duplicate-payment truth without an added payment row")

    if anomaly_type == "DUPLICATE_PAYMENT":
        finding = _duplicate_finding(mutated, diff, violations, application)
    elif anomaly_type == "PARTIAL_PAYMENT_ALLOCATION":
        finding = _partial_finding(mutated, diff, violations, application, subtype)
    else:
        raise ContractError("unsupported anomaly type for truth construction", anomaly_type=anomaly_type)

    _assert_diff_backed(finding, diff)
    _assert_reachable(finding, build.evidence_index)
    return TruthBuild(
        findings=(finding,),
        diff=diff,
        evidence_index=build.evidence_index,
        notes=(f"amount invariant: {AMOUNT_INVARIANT_BY_SIGNATURE.get((anomaly_type, subtype), 'n/a')}",),
    )


# --------------------------------------------------------------- anomaly types
def _duplicate_finding(
    mutated: Book,
    diff: TwinDiff,
    violations: Sequence[Violation],
    application: Any,
) -> CandidateFinding:
    new_payment_keys = diff.new_ids("payments")
    if len(new_payment_keys) != 1:
        raise ContractError(
            "duplicate-payment diff must add exactly one payment",
            added=new_payment_keys,
        )
    pay_id = new_payment_keys[0]
    new_entries = diff.new_ids("journal_entries")
    if len(new_entries) != 1:
        raise ContractError(
            "duplicate-payment diff must add exactly one journal entry",
            added=new_entries,
        )
    je_id = new_entries[0]
    payment = mutated.payment(pay_id)
    target_doc = payment.allocations[0].document_id
    invoice = mutated.invoice(target_doc)

    violation = _require_violation(violations, ("DUPLICATE_PAYMENT", None))
    amount = abs(int(violation.expected_delta_minor or 0))
    evidence = _duplicate_evidence(mutated, payment, invoice, je_id)

    return CandidateFinding(
        anomaly_type="DUPLICATE_PAYMENT",
        subtype=None,
        affected_ids=(pay_id, je_id),
        amount_minor=amount,
        currency=invoice.currency,
        tolerance_minor=0,
        invariant_signature=violation.signature(),
        evidence_sets=(evidence,),
        minimal_evidence_size=len(evidence),
        depends_on=(),
        diff_refs=(
            f"payments:added:{pay_id}",
            f"journal_entries:added:{je_id}",
            *(() if invoice.doc_id not in _modified_keys(diff, "invoices") else (
                f"invoices:modified:{invoice.doc_id}",
            )),
        ),
        operator_id=application.operator_id,
        operator_version=application.operator_version,
        detail=violation.detail,
    )


def _partial_finding(
    mutated: Book,
    diff: TwinDiff,
    violations: Sequence[Violation],
    application: Any,
    subtype: str | None,
) -> CandidateFinding:
    if subtype is None:
        raise ContractError("partial-allocation truth requires an explicit subtype")
    modified_payments = diff.modified("payments")
    if len(modified_payments) != 1:
        raise ContractError(
            "partial-allocation diff must modify exactly one payment",
            modified=[change.key for change in modified_payments],
        )
    pay_id = modified_payments[0].key
    payment = mutated.payment(pay_id)
    target_doc = payment.allocations[0].document_id
    invoice = mutated.invoice(target_doc)

    violation = _require_violation(violations, ("PARTIAL_PAYMENT_ALLOCATION", subtype))
    amount = abs(int(violation.expected_delta_minor or 0))
    evidence = _partial_evidence(mutated, payment, invoice)

    affected = {pay_id}
    affected |= {allocation.document_id for allocation in payment.allocations}
    before = modified_payments[0].before or {}
    for allocation in before.get("allocations", []) or []:
        affected.add(str(allocation["document_id"]))
    affected.add(target_doc)

    return CandidateFinding(
        anomaly_type="PARTIAL_PAYMENT_ALLOCATION",
        subtype=subtype,
        affected_ids=tuple(sorted(affected)),
        amount_minor=amount,
        currency=invoice.currency,
        tolerance_minor=0,
        invariant_signature=violation.signature(),
        evidence_sets=(evidence,),
        minimal_evidence_size=len(evidence),
        depends_on=(),
        diff_refs=(
            f"payments:modified:{pay_id}",
            *tuple(
                f"invoices:modified:{key}" for key in _modified_keys(diff, "invoices")
            ),
        ),
        operator_id=application.operator_id,
        operator_version=application.operator_version,
        detail=violation.detail,
    )


# -------------------------------------------------------------------- evidence
def _duplicate_evidence(
    book: Book, payment: Any, invoice: Any, je_id: str
) -> tuple[str, ...]:
    evidence: set[str] = {payment.pay_id, invoice.doc_id, je_id}
    for allocation in payment.allocations:
        evidence.add(allocation.document_id)
    # Original settlement(s) of the same document are part of the proof too.
    for other in book.payments:
        if other.pay_id == payment.pay_id:
            continue
        if any(allocation.document_id == invoice.doc_id for allocation in other.allocations):
            evidence.add(other.pay_id)
    for bank_line in book.bank_lines:
        if bank_line.matched_payment_id == payment.pay_id:
            evidence.add(bank_line.bank_line_id)
    return tuple(sorted(evidence))


def _partial_evidence(book: Book, payment: Any, invoice: Any) -> tuple[str, ...]:
    evidence: set[str] = {payment.pay_id, invoice.doc_id}
    for allocation in payment.allocations:
        evidence.add(allocation.document_id)
    credited = [note for note in book.credit_notes if note.invoice_id == invoice.doc_id]
    for other in book.payments:
        if other.pay_id == payment.pay_id:
            continue
        if any(allocation.document_id == invoice.doc_id for allocation in other.allocations):
            evidence.add(other.pay_id)
    # The policy row itself is public evidence (get_policy), not an id.
    return tuple(sorted(evidence))


def reachable_evidence(book: Book) -> dict[str, tuple[str, ...]]:
    """Map of every public id reachable from the mutated book (public tools only)."""
    index: dict[str, set[str]] = {}
    for table in book.table_names():
        key_fields = TABLE_KEY_FIELDS[table]
        for row in book.rows(table):
            primary = "/".join(str(getattr(row, field_name)) for field_name in key_fields)
            ids = {primary}
            for value in row.to_row().values():
                _collect_ids(value, ids)
            index[table] = index.get(table, set())
            index[table].update(ids)
    # Embedded collection ids (journal lines, allocations, invoice line items).
    embedded: set[str] = set()
    for entry in book.journal_entries:
        for line in entry.lines:
            embedded.add(line.line_id)
            embedded.add(line.account_id)
            if line.counterparty_id:
                embedded.add(line.counterparty_id)
    for payment in book.payments:
        for allocation in payment.allocations:
            embedded.add(allocation.allocation_id)
    index.setdefault("embedded", set()).update(embedded)
    return {table: tuple(sorted(ids)) for table, ids in sorted(index.items())}


def _collect_ids(value: Any, sink: set[str]) -> None:
    if isinstance(value, str):
        if _looks_like_id(value):
            sink.add(value)
    elif isinstance(value, Mapping):
        for item in value.values():
            _collect_ids(item, sink)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _collect_ids(item, sink)


def _looks_like_id(value: str) -> bool:
    if not 2 <= len(value) <= 48:
        return False
    return ("-" in value or "_" in value) and not value.startswith(("http", "XTV", "XBL"))


# ----------------------------------------------------------------- assertions
def _modified_keys(diff: TwinDiff, table: str) -> tuple[str, ...]:
    return tuple(change.key for change in diff.modified(table))


def _assert_diff_backed(finding: CandidateFinding, diff: TwinDiff) -> None:
    """Every finding must point at concrete diff facts (10.3)."""
    if not finding.diff_refs:
        raise ContractError("finding has no diff reference", type=finding.anomaly_type)
    available = {
        f"{change.table}:{change.kind}:{change.key}" for change in diff.changes
    }
    missing = [ref for ref in finding.diff_refs if ref not in available]
    if missing:
        raise ContractError(
            "finding references diff facts that do not exist",
            type=finding.anomaly_type,
            missing=missing,
        )


def _assert_reachable(finding: CandidateFinding, index: Mapping[str, tuple[str, ...]]) -> None:
    """Every evidence id must be obtainable through public tools (REQ-PROD-002)."""
    universe: set[str] = set()
    for ids in index.values():
        universe.update(ids)
    missing = [item for item in finding.evidence_sets[0] if item not in universe]
    if missing:
        raise ContractError(
            "evidence id is not reachable from public data",
            type=finding.anomaly_type,
            missing=sorted(missing),
        )


def _require_violation(
    violations: Sequence[Violation], signature_key: tuple[str, str | None]
) -> Violation:
    invariant_id = AMOUNT_INVARIANT_BY_SIGNATURE.get(signature_key)
    if invariant_id is None:
        raise ContractError("no amount invariant mapped", signature=list(signature_key))
    if signature_key[0] == "PARTIAL_PAYMENT_ALLOCATION":
        # Prefer the subtype's own necessary invariant, falling back to the mapped one.
        preferred = {
            "OVER_ALLOCATE_TO_ONE_INVOICE": ("INV-15", "INV-04"),
            "ALLOCATE_TO_ALREADY_SETTLED_INVOICE": ("INV-04",),
            "ALLOCATIONS_EXCEED_PAYMENT": ("INV-15",),
        }[str(signature_key[1])]
    else:
        preferred = (invariant_id,)
    for candidate in preferred:
        matches = [violation for violation in violations if violation.invariant_id == candidate]
        if matches:
            matches.sort(key=lambda violation: violation.sort_key())
            return matches[0]
    raise ContractError(
        "no invariant violation carries the finding amount",
        type=signature_key[0],
        subtype=signature_key[1],
        expected=list(preferred),
    )


def _anomaly_type_for(operator_id: str) -> str:
    mapping = {
        "OP-DUPLICATE_PAYMENT": "DUPLICATE_PAYMENT",
        "OP-PARTIAL_PAYMENT_ALLOCATION": "PARTIAL_PAYMENT_ALLOCATION",
    }
    if operator_id not in mapping:
        raise ContractError("unknown operator id", operator_id=operator_id)
    return mapping[operator_id]
