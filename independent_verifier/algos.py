"""Independent discovery algorithms for the four anomaly types (spec §3.1–§3.4).

Second, separate derivation from the frozen specification. Only ``contracts``
and the standard library are used. Every function is pure with respect to its
``PublicData`` input and never touches wall-clock time, randomness, or the
filesystem.

Cross-invoice distractor families D-DUP-02 / D-DUP-03 (same amount paid to two
different invoices of one counterparty; recurring subscription amounts on
invoices with distinct service periods) can never produce two payments on the
SAME invoice, so they fall out of a per-invoice walk by construction — no
special case is needed and none is applied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from independent_verifier.money import convert_minor, currency_exponents
from independent_verifier.time_rules import fiscal_period, local_date, parse_date, parse_instant

OFFSET_CN_CODES = frozenset(
    {
        "overpayment_credit",
        "duplicate_reversal",
        "duplicate_credit",
        "refund_credit",
        "credit_adjustment",
    }
)
REFUND_PAYMENT_TYPES = frozenset({"refund", "reversal", "void"})
PREPAYMENT_ACCOUNT_TYPES = frozenset({"prepayment", "advance", "deferred_revenue", "deferred_expense"})
PREPAYMENT_ANALYTIC_TAGS = frozenset({"prepayment", "advance", "deferred"})


@dataclass
class RawFinding:
    type: str
    affected_ids: list[str]
    claimed_amount_minor: int
    currency: str
    evidence_candidates: list[list[str]]
    explanation_code: str
    rule_id: str
    basis_ids: list[str] = field(default_factory=list)


def is_refund_like(payment: dict[str, Any]) -> bool:
    if payment.get("payment_type") in REFUND_PAYMENT_TYPES:
        return True
    if int(payment.get("amount_minor", 0)) < 0:
        return True
    return any(int(a.get("amount_minor", 0)) < 0 for a in payment.get("allocations", []))


def _parse_instant(value: str):
    try:
        return parse_instant(str(value))
    except (ValueError, TypeError):
        return parse_instant("1970-01-01T00:00:00+00:00")


def _cn_partition(
    cn_rows: list[dict[str, Any]], signed_alloc_total: int, invoice_total: int
) -> tuple[int, int, list[dict[str, Any]]]:
    reducing = 0
    offsetting = 0
    reducing_rows: list[dict[str, Any]] = []
    for cn in cn_rows:
        amount = int(cn.get("amount_minor", 0))
        code = cn.get("reason_code")
        if code in OFFSET_CN_CODES and signed_alloc_total > invoice_total:
            offsetting += amount
        else:
            reducing += amount
            reducing_rows.append(cn)
    return reducing, offsetting, reducing_rows


def _invoice_events(data, invoice: dict[str, Any], canceled: set[str]) -> list[tuple]:
    """Signed allocation events to one invoice from non-canceled payments."""
    doc_id = invoice["doc_id"]
    events: list[tuple] = []
    for payment in data.payments:
        pay_id = payment.get("pay_id")
        if not pay_id or pay_id in canceled:
            continue
        here = sum(
            int(a.get("amount_minor", 0))
            for a in payment.get("allocations", [])
            if a.get("document_id") == doc_id
        )
        if here == 0:
            continue
        events.append((_parse_instant(payment.get("timestamp", "")), pay_id, here, payment))
    events.sort(key=lambda e: (e[0], e[1]))
    return events


def _canceled_payment_ids(data) -> set[str]:
    """Refund/reversal/void payments neutralize their referenced payment (D-DUP-04)."""
    canceled: set[str] = set()
    for payment in data.payments:
        if is_refund_like(payment):
            related = payment.get("related_payment_id")
            if related:
                canceled.add(str(related))
                canceled.add(str(payment.get("pay_id")))
    return canceled


def _alloc_total(payment: dict[str, Any]) -> int:
    return sum(int(a.get("amount_minor", 0)) for a in payment.get("allocations", []))


def _passes_inv15(payment: dict[str, Any]) -> bool:
    alloc_all = _alloc_total(payment)
    amount = int(payment.get("amount_minor", 0))
    if alloc_all > amount or alloc_all < 0:
        return False
    return all(int(a.get("amount_minor", 0)) >= 0 for a in payment.get("allocations", []))


def _je_links_to_payment(journal_entries, pay_id: str) -> list[dict[str, Any]]:
    return [je for je in journal_entries if je.get("source_document_id") == pay_id]


def _minimal_crossing_subsets(priors: list[tuple[str, int]], needed: int, cap: int = 32) -> list[list[str]]:
    """Inclusion-minimal subsets of ``priors`` whose signed sum is >= ``needed``.

    ``priors`` is a list of (typed_id, amount). Enumerate by size; a subset is
    kept only if no proper subset already satisfies the threshold.
    """
    if needed <= 0:
        return [[]]
    selected: list[list[str]] = []
    chosen_id_sets: list[frozenset[str]] = []
    priors = list(priors)
    n = len(priors)

    def subset_sum(subset):
        return sum(priors[i][1] for i in subset)

    from itertools import combinations

    for size in range(1, n + 1):
        for combo in combinations(range(n), size):
            ids = frozenset(priors[i][0] for i in combo)
            if any(ids >= cs for cs in chosen_id_sets):
                continue  # not minimal — a proper subset already crosses
            if subset_sum(combo) >= needed:
                selected.append(sorted(ids))
                chosen_id_sets.append(ids)
                if len(selected) >= cap:
                    return selected
    return selected


def discover_duplicates(data) -> list[RawFinding]:
    findings: list[RawFinding] = []
    canceled = _canceled_payment_ids(data)
    cn_by_invoice: dict[str, list[dict[str, Any]]] = {}
    for cn in data.credit_notes:
        cn_by_invoice.setdefault(str(cn.get("invoice_id")), []).append(cn)

    for inv in data.invoices:
        doc_id = inv.get("doc_id")
        if not doc_id:
            continue
        events = _invoice_events(data, inv, canceled)
        if not events:
            continue
        signed_alloc_total = sum(e[2] for e in events)
        invoice_total = int(inv.get("total_minor", 0))
        reducing, offsetting, reducing_rows = _cn_partition(
            cn_by_invoice.get(doc_id, []), signed_alloc_total, invoice_total
        )
        net_payable = max(0, invoice_total - reducing)
        inv_ccy = inv.get("currency")
        inv_cp = inv.get("counterparty_id")

        cumulative = 0
        for instant, pay_id, here, payment in events:
            prev = cumulative
            cumulative += here
            reduce_cns = reducing_rows
            candidate = (
                isinstance(payment.get("amount_minor"), int)
                and payment["amount_minor"] > 0
                and not is_refund_like(payment)
                and _passes_inv15(payment)
                and payment.get("currency") == inv_ccy
                and payment.get("counterparty_id") == inv_cp
            )
            if not candidate:
                continue
            prev_effective = prev - offsetting
            effective = cumulative - offsetting
            if effective > net_payable and prev_effective <= net_payable:
                excess = effective - net_payable
                claimed = min(here, excess)
                je_links = _je_links_to_payment(data.journal_entries, pay_id)
                affected = sorted({f"PAY:{pay_id}", *(f"JE:{je['je_id']}" for je in je_links)})
                required = [
                    f"INV:{doc_id}",
                    f"PAY:{pay_id}",
                    *(f"CN:{cn['credit_note_id']}" for cn in reduce_cns),
                    *(f"JE:{je['je_id']}" for je in je_links),
                ]
                priors: list[tuple[str, int]] = [
                    (f"PAY:{e[1]}", e[2])
                    for e in events
                    if e[1] != pay_id
                    and isinstance(e[3].get("amount_minor"), int)
                    and e[3]["amount_minor"] > 0
                    and not is_refund_like(e[3])
                    and _passes_inv15(e[3])
                    and e[3].get("currency") == inv_ccy
                    and e[3].get("counterparty_id") == inv_cp
                ]
                needed = net_payable + offsetting - here + 1
                seed_subsets = _minimal_crossing_subsets(priors, needed)
                seeds: list[list[str]] = []
                if seed_subsets:
                    for subset in seed_subsets:
                        seeds.append(sorted(required + list(subset)))
                else:
                    seeds.append(sorted(required))
                findings.append(
                    RawFinding(
                        type="DUPLICATE_PAYMENT",
                        affected_ids=affected,
                        claimed_amount_minor=int(claimed),
                        currency=str(inv_ccy),
                        evidence_candidates=seeds,
                        explanation_code="V-DUP-PAYMENT",
                        rule_id="V-DUP-05",
                        basis_ids=affected,
                    )
                )
    return findings


def discover_partial_allocation(data) -> list[RawFinding]:
    findings: list[RawFinding] = []
    allocation_policy = data.policy.get("allocation_policy", {})
    allow_advances = bool(allocation_policy.get("allow_advances", False))
    allow_multi = bool(allocation_policy.get("allow_multi_invoice_split", False))
    invoices_by_id = {inv.get("doc_id"): inv for inv in data.invoices}
    canceled = _canceled_payment_ids(data)
    cn_by_invoice: dict[str, list[dict[str, Any]]] = {}
    for cn in data.credit_notes:
        cn_by_invoice.setdefault(str(cn.get("invoice_id")), []).append(cn)

    for p in data.payments:
        pay_id = p.get("pay_id")
        amount = p.get("amount_minor")
        if not pay_id or isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            continue
        if is_refund_like(p):
            continue
        allocs = p.get("allocations", [])
        unknown_targets = {
            a.get("document_id") for a in allocs if a.get("document_id")
        } - set(invoices_by_id)
        if unknown_targets:
            # Proof requires the referenced documents to be present in the
            # (sub)episode; an allocation pointing into a missing document is
            # unverifiable, so no finding is derived from it (REQ-VER-005/014).
            continue
        alloc_total = _alloc_total(p)
        doc_ids = [a.get("document_id") for a in allocs if a.get("document_id")]
        unique_docs = sorted(set(doc_ids))
        base_affected = [f"PAY:{pay_id}", *(f"INV:{d}" for d in unique_docs)]
        if alloc_total > amount or any(int(a.get("amount_minor", 0)) < 0 for a in allocs):
            over = alloc_total - amount if alloc_total > amount else 0
            neg = max([abs(int(a.get("amount_minor", 0))) for a in allocs if int(a.get("amount_minor", 0)) < 0] + [0])
            claimed = over if over > 0 else neg
            findings.append(
                RawFinding(
                    type="PARTIAL_PAYMENT_ALLOCATION",
                    affected_ids=sorted(base_affected),
                    claimed_amount_minor=int(claimed),
                    currency=str(p.get("currency")),
                    evidence_candidates=[sorted(base_affected)],
                    explanation_code="V-PART-OVERALLOC",
                    rule_id="V-PART-A",
                    basis_ids=sorted(base_affected),
                )
            )
            continue
        if alloc_total < amount:
            if allow_advances:
                pass  # D-PART-02: valid advance — recorded as an exclusion, not a finding
            else:
                claimed = amount - alloc_total
                findings.append(
                    RawFinding(
                        type="PARTIAL_PAYMENT_ALLOCATION",
                        affected_ids=sorted(base_affected),
                        claimed_amount_minor=int(claimed),
                        currency=str(p.get("currency")),
                        evidence_candidates=[sorted(base_affected)],
                        explanation_code="V-PART-UNALLOCATED",
                        rule_id="V-PART-B",
                        basis_ids=sorted(base_affected),
                    )
                )
                continue
        if len(unique_docs) >= 2:
            conservation = alloc_total == amount
            if not (allow_multi and conservation):
                claimed = alloc_total
                findings.append(
                    RawFinding(
                        type="PARTIAL_PAYMENT_ALLOCATION",
                        affected_ids=sorted(base_affected),
                        claimed_amount_minor=int(claimed),
                        currency=str(p.get("currency")),
                        evidence_candidates=[sorted(base_affected)],
                        explanation_code="V-PART-SPLIT",
                        rule_id="V-PART-C",
                        basis_ids=sorted(base_affected),
                    )
                )
        for a in allocs:
            target = invoices_by_id.get(a.get("document_id"))
            if target is None:
                continue
            if (
                target.get("counterparty_id") != p.get("counterparty_id")
                or target.get("currency") != p.get("currency")
            ):
                claimed = int(a.get("amount_minor", 0))
                affected = sorted([f"PAY:{pay_id}", f"INV:{target['doc_id']}"])
                findings.append(
                    RawFinding(
                        type="PARTIAL_PAYMENT_ALLOCATION",
                        affected_ids=affected,
                        claimed_amount_minor=claimed,
                        currency=str(p.get("currency")),
                        evidence_candidates=[affected],
                        explanation_code="V-PART-TARGET",
                        rule_id="V-PART-D",
                        basis_ids=affected,
                    )
                )

    for inv in data.invoices:
        doc_id = inv.get("doc_id")
        if not doc_id:
            continue
        events = _invoice_events(data, inv, canceled)
        signed_alloc_total = sum(e[2] for e in events)
        invoice_total = int(inv.get("total_minor", 0))
        reducing, _, _ = _cn_partition(
            cn_by_invoice.get(doc_id, []), signed_alloc_total, invoice_total
        )
        net_payable = max(0, invoice_total - reducing)
        net_allocated = signed_alloc_total
        if inv.get("status") == "paid" and 0 < net_allocated < net_payable:
            contributing = sorted(
                {
                    f"PAY:{e[1]}"
                    for e in events
                    if isinstance(e[3].get("amount_minor"), int)
                    and e[3]["amount_minor"] > 0
                    and not is_refund_like(e[3])
                    and e[3].get("currency") == inv.get("currency")
                    and e[3].get("counterparty_id") == inv.get("counterparty_id")
                    and _passes_inv15(e[3])
                }
            )
            claimed = net_payable - net_allocated
            affected = sorted([f"INV:{doc_id}", *contributing])
            findings.append(
                RawFinding(
                    type="PARTIAL_PAYMENT_ALLOCATION",
                    affected_ids=affected,
                    claimed_amount_minor=int(claimed),
                    currency=str(inv.get("currency")),
                    evidence_candidates=[affected],
                    explanation_code="V-PART-PREMATURE-PAID",
                    rule_id="V-PART-E",
                    basis_ids=affected,
                )
            )
    return findings
