"""Independent PARTIAL_PAYMENT_ALLOCATION detector (Zone 3, TZ 11.3, 13.6).

Detects:
  - Case A: payment allocations exceeding payment amount (INV-15) or negative
    allocation amounts;
  - Case B: unallocated payment balance when ``allow_advances`` is False;
  - Case C: multi-invoice split when ``allow_multi_invoice_split`` is False;
  - Case D: allocation to an invoice with wrong counterparty or wrong currency;
  - Case E: premature invoice closure (``status == "paid"``) while net
    allocated partial payment(s) leave a positive unpaid balance (INV-04/INV-17).

Emits explicit ProofGraph ``excludes`` paths for distractors D-PART-01..04.
Dependencies: ``contracts`` + ``verifier`` stdlib helpers only (never ``gen``).
"""

from __future__ import annotations

from typing import Any

from verifier.duplicate_payment import (
    OVERPAYMENT_OFFSET_CN_REASONS,
    REVERSAL_PAYMENT_TYPES,
    DetectorResult,
)
from verifier.money_time import require_minor_int
from verifier.proof_graph import ProofGraph
from verifier.public_loader import PublicEpisode, make_typed_id
from verifier.result import VerifierFinding


def _is_reversal_payment(pay: dict[str, Any]) -> bool:
    ptype = str(pay.get("payment_type") or "").lower()
    if ptype in REVERSAL_PAYMENT_TYPES:
        return True
    amt = pay.get("amount_minor")
    return type(amt) is int and amt < 0


def detect_partial_allocations(
    episode: PublicEpisode,
    graph: ProofGraph,
) -> DetectorResult:
    """Independently discover PARTIAL_PAYMENT_ALLOCATION anomalies."""
    findings: list[VerifierFinding] = []
    ambiguities: list[str] = []

    alloc_policy = episode.policy["allocation_policy"]
    allow_advances = bool(alloc_policy["allow_advances"])
    allow_multi_split = bool(alloc_policy["allow_multi_invoice_split"])
    invoices_by_id = episode.invoices_by_id

    cns_by_invoice: dict[str, list[dict[str, Any]]] = {}
    for cn in episode.credit_notes:
        inv_id = cn.get("invoice_id")
        if isinstance(inv_id, str) and inv_id:
            cns_by_invoice.setdefault(inv_id, []).append(cn)

    inv15_rule = graph.add_rule(
        rule_id="RULE:PARTIAL_ALLOCATION:INV-15",
        payload={
            "invariant": "INV-15",
            "allow_advances": allow_advances,
            "allow_multi_invoice_split": allow_multi_split,
        },
        source_files=("policy.json",),
        label="Allocation conservation and policy rules",
    )
    inv04_rule = graph.add_rule(
        rule_id="RULE:PARTIAL_ALLOCATION:INV-04_INV-17",
        payload={"invariants": ["INV-04", "INV-17"], "rule": "Invoice open balance and status consistency"},
        source_files=("policy.json",),
        label="Invoice open balance and paid status consistency",
    )

    # Track valid allocations per invoice for Case E and D-PART-01 / D-PART-04
    valid_pays_by_inv: dict[str, list[tuple[dict[str, Any], int]]] = {}
    refunds_by_inv: dict[str, list[tuple[dict[str, Any], int]]] = {}

    for pay in sorted(episode.payments, key=lambda p: str(p["pay_id"])):
        if _is_reversal_payment(pay):
            for alloc in pay.get("allocations", ()):
                doc_id = str(alloc.get("document_id", ""))
                amt = abs(require_minor_int(alloc["amount_minor"], "refund.allocation.amount_minor"))
                if doc_id:
                    refunds_by_inv.setdefault(doc_id, []).append((pay, amt))
            continue

        pay_id = str(pay["pay_id"])
        pay_tid = make_typed_id("PAY", pay_id)
        pay_amt = require_minor_int(pay["amount_minor"], "payment.amount_minor")
        pay_cur = str(pay["currency"])
        allocs = list(pay.get("allocations", ()))

        # Resolve referenced invoices
        referenced_doc_ids = sorted({str(a["document_id"]) for a in allocs if a.get("document_id")})
        all_refs_present = all(doc_id in invoices_by_id for doc_id in referenced_doc_ids)

        pay_node = graph.add_record(pay_tid, pay)

        # Case D: Wrong counterparty or wrong currency on an allocation
        wrong_target_found = False
        for alloc in allocs:
            doc_id = str(alloc.get("document_id", ""))
            inv = invoices_by_id.get(doc_id)
            if inv is None:
                continue
            alloc_amt = require_minor_int(alloc["amount_minor"], "allocation.amount_minor")
            inv_tid = make_typed_id("INV", doc_id)
            if inv.get("counterparty_id") != pay.get("counterparty_id"):
                wrong_target_found = True
                inv_node = graph.add_record(inv_tid, inv)
                calc_node = graph.add_calculation(
                    calc_key=f"wrong_cp:{pay_id}:{doc_id}",
                    rule_id="RULE:PARTIAL_ALLOCATION:COUNTERPARTY_MATCH",
                    source_ids=[pay_tid, inv_tid],
                    parent_node_ids=[pay_node, inv_node],
                    governed_by_nodes=[inv15_rule],
                    payload={
                        "pay_counterparty": pay.get("counterparty_id"),
                        "inv_counterparty": inv.get("counterparty_id"),
                        "allocated_minor": alloc_amt,
                    },
                )
                affected = tuple(sorted([pay_tid, inv_tid]))
                fnode = graph.add_finding(
                    finding_key=f"PARTIAL_WRONG_CP:{pay_id}:{doc_id}",
                    rule_id="RULE:PARTIAL_ALLOCATION:COUNTERPARTY_MATCH",
                    source_ids=affected,
                    supporting_node_ids=[calc_node],
                    governed_by_nodes=[inv15_rule],
                    payload={
                        "type": "PARTIAL_PAYMENT_ALLOCATION",
                        "affected_ids": list(affected),
                        "claimed_amount_minor": abs(alloc_amt),
                        "currency": pay_cur,
                    },
                )
                findings.append(
                    VerifierFinding(
                        type="PARTIAL_PAYMENT_ALLOCATION",
                        affected_ids=affected,
                        claimed_amount_minor=abs(alloc_amt),
                        currency=pay_cur,
                        evidence_sets=(affected,),
                        explanation_code="PARTIAL_ALLOC_WRONG_COUNTERPARTY",
                        proof_graph_ref=f"proof:{fnode}",
                        evidence_enumeration_complete=True,
                    )
                )
            elif inv.get("currency") != pay_cur:
                wrong_target_found = True
                inv_node = graph.add_record(inv_tid, inv)
                calc_node = graph.add_calculation(
                    calc_key=f"wrong_cur:{pay_id}:{doc_id}",
                    rule_id="RULE:PARTIAL_ALLOCATION:CURRENCY_MATCH",
                    source_ids=[pay_tid, inv_tid],
                    parent_node_ids=[pay_node, inv_node],
                    governed_by_nodes=[inv15_rule],
                    payload={
                        "pay_currency": pay_cur,
                        "inv_currency": inv.get("currency"),
                        "allocated_minor": alloc_amt,
                    },
                )
                affected = tuple(sorted([pay_tid, inv_tid]))
                fnode = graph.add_finding(
                    finding_key=f"PARTIAL_WRONG_CUR:{pay_id}:{doc_id}",
                    rule_id="RULE:PARTIAL_ALLOCATION:CURRENCY_MATCH",
                    source_ids=affected,
                    supporting_node_ids=[calc_node],
                    governed_by_nodes=[inv15_rule],
                    payload={
                        "type": "PARTIAL_PAYMENT_ALLOCATION",
                        "affected_ids": list(affected),
                        "claimed_amount_minor": abs(alloc_amt),
                        "currency": pay_cur,
                    },
                )
                findings.append(
                    VerifierFinding(
                        type="PARTIAL_PAYMENT_ALLOCATION",
                        affected_ids=affected,
                        claimed_amount_minor=abs(alloc_amt),
                        currency=pay_cur,
                        evidence_sets=(affected,),
                        explanation_code="PARTIAL_ALLOC_CURRENCY_MISMATCH",
                        proof_graph_ref=f"proof:{fnode}",
                        evidence_enumeration_complete=True,
                    )
                )

        if wrong_target_found:
            continue

        # Require referenced invoices to exist in public episode before emitting
        # invoice-linked allocation findings (ensures strict reachability & ablation).
        if referenced_doc_ids and not all_refs_present:
            continue

        alloc_amounts = [require_minor_int(a["amount_minor"], "allocation.amount_minor") for a in allocs]
        alloc_total = sum(alloc_amounts)
        has_negative = any(a < 0 for a in alloc_amounts)
        inv_tids = [make_typed_id("INV", d) for d in referenced_doc_ids]
        inv_nodes = [graph.add_record(make_typed_id("INV", d), invoices_by_id[d]) for d in referenced_doc_ids]

        # Case A: Over-allocation or negative allocation (INV-15)
        if has_negative or alloc_total > pay_amt:
            excess = (
                alloc_total - pay_amt
                if alloc_total > pay_amt
                else sum(abs(a) for a in alloc_amounts if a < 0)
            )
            affected = tuple(sorted([pay_tid] + inv_tids))
            calc_node = graph.add_calculation(
                calc_key=f"inv15_over:{pay_id}",
                rule_id="RULE:PARTIAL_ALLOCATION:INV-15",
                source_ids=affected,
                parent_node_ids=[pay_node] + inv_nodes,
                governed_by_nodes=[inv15_rule],
                payload={
                    "pay_id": pay_id,
                    "payment_amount_minor": pay_amt,
                    "allocated_total_minor": alloc_total,
                    "excess_minor": excess,
                },
            )
            fnode = graph.add_finding(
                finding_key=f"PARTIAL_OVERALLOC:{pay_id}",
                rule_id="RULE:PARTIAL_ALLOCATION:INV-15",
                source_ids=affected,
                supporting_node_ids=[calc_node],
                governed_by_nodes=[inv15_rule],
                payload={
                    "type": "PARTIAL_PAYMENT_ALLOCATION",
                    "affected_ids": list(affected),
                    "claimed_amount_minor": excess,
                    "currency": pay_cur,
                },
            )
            findings.append(
                VerifierFinding(
                    type="PARTIAL_PAYMENT_ALLOCATION",
                    affected_ids=affected,
                    claimed_amount_minor=excess,
                    currency=pay_cur,
                    evidence_sets=(affected,),
                    explanation_code="PARTIAL_ALLOC_EXCEEDS_PAYMENT",
                    proof_graph_ref=f"proof:{fnode}",
                    evidence_enumeration_complete=True,
                )
            )
            continue

        # Case B: Unallocated payment balance vs allow_advances (D-PART-02)
        if alloc_total < pay_amt:
            unallocated = pay_amt - alloc_total
            affected = tuple(sorted([pay_tid] + inv_tids))
            calc_node = graph.add_calculation(
                calc_key=f"unalloc:{pay_id}",
                rule_id="RULE:PARTIAL_ALLOCATION:INV-15",
                source_ids=affected,
                parent_node_ids=[pay_node] + inv_nodes,
                governed_by_nodes=[inv15_rule],
                payload={
                    "pay_id": pay_id,
                    "payment_amount_minor": pay_amt,
                    "allocated_total_minor": alloc_total,
                    "unallocated_minor": unallocated,
                    "allow_advances": allow_advances,
                },
            )
            if allow_advances:
                adv_rule = graph.add_rule(
                    rule_id="RULE:D-PART-02:ALLOW_ADVANCES",
                    payload={"distractor": "D-PART-02", "allow_advances": True},
                    source_files=("policy.json",),
                )
                graph.record_exclusion(
                    "D-PART-02", calc_node, [adv_rule], rule_node_id=adv_rule, edge_type="excludes"
                )
            else:
                fnode = graph.add_finding(
                    finding_key=f"PARTIAL_UNALLOC:{pay_id}",
                    rule_id="RULE:PARTIAL_ALLOCATION:INV-15",
                    source_ids=affected,
                    supporting_node_ids=[calc_node],
                    governed_by_nodes=[inv15_rule],
                    payload={
                        "type": "PARTIAL_PAYMENT_ALLOCATION",
                        "affected_ids": list(affected),
                        "claimed_amount_minor": unallocated,
                        "currency": pay_cur,
                    },
                )
                findings.append(
                    VerifierFinding(
                        type="PARTIAL_PAYMENT_ALLOCATION",
                        affected_ids=affected,
                        claimed_amount_minor=unallocated,
                        currency=pay_cur,
                        evidence_sets=(affected,),
                        explanation_code="PARTIAL_ALLOC_UNALLOWED_ADVANCE",
                        proof_graph_ref=f"proof:{fnode}",
                        evidence_enumeration_complete=True,
                    )
                )
                continue

        # Case C: Multi-invoice split vs allow_multi_invoice_split (D-PART-03)
        if len(referenced_doc_ids) >= 2:
            affected = tuple(sorted([pay_tid] + inv_tids))
            split_calc = graph.add_calculation(
                calc_key=f"split:{pay_id}",
                rule_id="RULE:PARTIAL_ALLOCATION:MULTI_SPLIT",
                source_ids=affected,
                parent_node_ids=[pay_node] + inv_nodes,
                governed_by_nodes=[inv15_rule],
                payload={
                    "pay_id": pay_id,
                    "invoice_count": len(referenced_doc_ids),
                    "allocated_total_minor": alloc_total,
                    "allow_multi_invoice_split": allow_multi_split,
                },
            )
            if allow_multi_split:
                split_rule = graph.add_rule(
                    rule_id="RULE:D-PART-03:ALLOW_MULTI_INVOICE_SPLIT",
                    payload={"distractor": "D-PART-03", "allow_multi_invoice_split": True},
                    source_files=("policy.json",),
                )
                graph.record_exclusion(
                    "D-PART-03", split_calc, [split_rule], rule_node_id=split_rule, edge_type="excludes"
                )
            else:
                fnode = graph.add_finding(
                    finding_key=f"PARTIAL_DISALLOWED_SPLIT:{pay_id}",
                    rule_id="RULE:PARTIAL_ALLOCATION:MULTI_SPLIT",
                    source_ids=affected,
                    supporting_node_ids=[split_calc],
                    governed_by_nodes=[inv15_rule],
                    payload={
                        "type": "PARTIAL_PAYMENT_ALLOCATION",
                        "affected_ids": list(affected),
                        "claimed_amount_minor": alloc_total,
                        "currency": pay_cur,
                    },
                )
                findings.append(
                    VerifierFinding(
                        type="PARTIAL_PAYMENT_ALLOCATION",
                        affected_ids=affected,
                        claimed_amount_minor=alloc_total,
                        currency=pay_cur,
                        evidence_sets=(affected,),
                        explanation_code="PARTIAL_ALLOC_DISALLOWED_MULTI_SPLIT",
                        proof_graph_ref=f"proof:{fnode}",
                        evidence_enumeration_complete=True,
                    )
                )
                continue

        # Record valid allocations for invoice-level balance & status verification
        for alloc in allocs:
            doc_id = str(alloc["document_id"])
            amt = require_minor_int(alloc["amount_minor"])
            if amt > 0:
                valid_pays_by_inv.setdefault(doc_id, []).append((pay, amt))

    # Case E: Premature invoice closure on partial payment + D-PART-01 / D-PART-04
    for doc_id in sorted(valid_pays_by_inv):
        inv = invoices_by_id[doc_id]
        inv_tid = make_typed_id("INV", doc_id)
        inv_total = require_minor_int(inv["total_minor"], "invoice.total_minor")
        inv_cur = str(inv["currency"])
        status = str(inv.get("status", "")).lower()

        pay_entries = valid_pays_by_inv[doc_id]
        pay_ids_unique = sorted({str(p["pay_id"]) for p, _ in pay_entries})
        gross_paid = sum(amt for _, amt in pay_entries)

        cns = [
            cn for cn in cns_by_invoice.get(doc_id, ())
            if cn.get("currency") == inv_cur
            and str(cn.get("reason_code") or "").lower() not in OVERPAYMENT_OFFSET_CN_REASONS
        ]
        cn_total = sum(require_minor_int(cn["amount_minor"]) for cn in cns)
        refund_entries = refunds_by_inv.get(doc_id, ())
        refund_total = sum(amt for _, amt in refund_entries)

        net_payable = max(0, inv_total - cn_total)
        net_allocated = gross_paid - refund_total
        remaining = net_payable - net_allocated

        inv_node = graph.add_record(inv_tid, inv)
        pay_nodes = [
            graph.add_record(make_typed_id("PAY", pid), episode.payments_by_id[pid])
            for pid in pay_ids_unique
        ]
        pay_tids = [make_typed_id("PAY", pid) for pid in pay_ids_unique]
        cn_tids = [make_typed_id("CN", str(cn["credit_note_id"])) for cn in cns]
        cn_nodes = [graph.add_record(make_typed_id("CN", str(cn["credit_note_id"])), cn) for cn in cns]

        bal_calc = graph.add_calculation(
            calc_key=f"inv_balance:{doc_id}",
            rule_id="RULE:PARTIAL_ALLOCATION:INV-04_INV-17",
            source_ids=[inv_tid] + pay_tids + cn_tids,
            parent_node_ids=[inv_node] + pay_nodes + cn_nodes,
            governed_by_nodes=[inv04_rule],
            payload={
                "doc_id": doc_id,
                "invoice_total_minor": inv_total,
                "credit_notes_minor": cn_total,
                "net_payable_minor": net_payable,
                "net_allocated_minor": net_allocated,
                "remaining_minor": remaining,
                "status": status,
            },
        )

        # D-PART-01: Multiple partial payments together close the invoice cleanly
        if status == "paid" and remaining == 0 and len(pay_ids_unique) >= 2:
            d1_rule = graph.add_rule(
                rule_id="RULE:D-PART-01:SECOND_PAYMENT_CLOSES_BALANCE",
                payload={"distractor": "D-PART-01", "payment_count": len(pay_ids_unique)},
                source_files=("policy.json",),
            )
            closing_fact = graph.add_fact(
                fact_key=f"d_part_01:{doc_id}",
                rule_id="RULE:D-PART-01:SECOND_PAYMENT_CLOSES_BALANCE",
                source_ids=pay_tids,
                parent_node_ids=pay_nodes,
                payload={"doc_id": doc_id, "combined_payments_minor": net_allocated, "net_payable_minor": net_payable},
            )
            graph.record_exclusion("D-PART-01", bal_calc, [closing_fact], rule_node_id=d1_rule, edge_type="excludes")
            continue

        # D-PART-04: Credit note / partial refund reconciles remaining balance cleanly
        if remaining == 0 and (cn_total > 0 or refund_total > 0):
            d4_rule = graph.add_rule(
                rule_id="RULE:D-PART-04:PARTIAL_REFUND_OR_CREDIT_RECONCILED",
                payload={"distractor": "D-PART-04", "credit_notes_minor": cn_total, "refund_minor": refund_total},
                source_files=("policy.json",),
            )
            adj_sources = cn_tids + [make_typed_id("PAY", str(rp["pay_id"])) for rp, _ in refund_entries]
            adj_parents = cn_nodes + [
                graph.add_record(make_typed_id("PAY", str(rp["pay_id"])), rp) for rp, _ in refund_entries
            ]
            if adj_sources:
                d4_fact = graph.add_fact(
                    fact_key=f"d_part_04:{doc_id}",
                    rule_id="RULE:D-PART-04:PARTIAL_REFUND_OR_CREDIT_RECONCILED",
                    source_ids=adj_sources,
                    parent_node_ids=adj_parents,
                    payload={"doc_id": doc_id, "credit_notes_minor": cn_total, "refund_minor": refund_total},
                )
                graph.record_exclusion("D-PART-04", bal_calc, [d4_fact], rule_node_id=d4_rule, edge_type="excludes")
            continue

        # Premature closure: invoice marked "paid" while partial payment(s) leave unpaid balance
        if status == "paid" and net_allocated > 0 and remaining > 0:
            affected = tuple(sorted([inv_tid] + pay_tids))
            evidence = tuple(sorted(set(affected) | set(cn_tids)))
            fnode = graph.add_finding(
                finding_key=f"PARTIAL_PREMATURE_PAID:{doc_id}",
                rule_id="RULE:PARTIAL_ALLOCATION:INV-04_INV-17",
                source_ids=evidence,
                supporting_node_ids=[bal_calc],
                governed_by_nodes=[inv04_rule],
                payload={
                    "type": "PARTIAL_PAYMENT_ALLOCATION",
                    "affected_ids": list(affected),
                    "claimed_amount_minor": remaining,
                    "currency": inv_cur,
                },
            )
            findings.append(
                VerifierFinding(
                    type="PARTIAL_PAYMENT_ALLOCATION",
                    affected_ids=affected,
                    claimed_amount_minor=remaining,
                    currency=inv_cur,
                    evidence_sets=(evidence,),
                    explanation_code="PARTIAL_ALLOC_PREMATURE_INVOICE_CLOSED",
                    proof_graph_ref=f"proof:{fnode}",
                    evidence_enumeration_complete=True,
                )
            )

    return DetectorResult(findings=tuple(findings), ambiguities=tuple(ambiguities))


__all__ = ["detect_partial_allocations"]
