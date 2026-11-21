"""Independent DUPLICATE_PAYMENT detector (Zone 3, TZ 11.2, 13.6).

Detects invoices overpaid across multiple distinct positive payments with
no explaining credit note, refund, reversal, or void event. Emits explicit
ProofGraph ``excludes`` / ``contradicts`` paths for distractors
D-DUP-01..04.

Dependencies: ``contracts`` + ``verifier`` stdlib helpers only (never ``gen``).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any

from verifier.money_time import parse_iso_instant, require_minor_int
from verifier.proof_graph import ProofGraph
from verifier.public_loader import PublicEpisode, make_typed_id
from verifier.result import MAX_SCHEMA_EVIDENCE_SETS, VerifierFinding

REVERSAL_PAYMENT_TYPES: frozenset[str] = frozenset({"refund", "reversal", "void"})
OVERPAYMENT_OFFSET_CN_REASONS: frozenset[str] = frozenset(
    {
        "overpayment_credit",
        "duplicate_reversal",
        "duplicate_credit",
        "refund_credit",
        "credit_adjustment",
    }
)


@dataclass(frozen=True)
class DetectorResult:
    findings: tuple[VerifierFinding, ...]
    ambiguities: tuple[str, ...]


def _is_reversal_payment(pay: dict[str, Any]) -> bool:
    ptype = str(pay.get("payment_type") or "").lower()
    if ptype in REVERSAL_PAYMENT_TYPES:
        return True
    amt = pay.get("amount_minor")
    if type(amt) is int and amt < 0:
        return True
    return False


def _payment_allocation_sum(pay: dict[str, Any]) -> int:
    return sum(
        require_minor_int(a["amount_minor"], "allocation.amount_minor")
        for a in pay.get("allocations", ())
    )


def _minimal_prior_subsets(
    prior_entries: list[tuple[str, int]],
    dup_alloc: int,
    net_payable: int,
    target_excess: int,
    max_sets: int,
) -> tuple[list[tuple[str, ...]], bool]:
    """Find minimal subsets of prior payments proving ``dup_alloc`` overpays.

    A subset ``S`` of prior payments is sufficient when:
      1. ``sum(S) + dup_alloc - net_payable >= target_excess`` (i.e. with
         ``dup_alloc`` bounded by ``min(dup_alloc, sum(S) + dup_alloc - net_payable) == target_excess``),
         which simplifies to ``sum(S) >= net_payable - dup_alloc + target_excess``.
      2. No strict subset of ``S`` already meets that threshold.
    """
    needed_prior = net_payable - dup_alloc + target_excess
    if needed_prior <= 0:
        return [()], True

    # Sort deterministically by typed ID
    ordered = sorted(prior_entries, key=lambda item: item[0])
    minimal_sets: list[tuple[str, ...]] = []
    complete = True

    # Small exact search by increasing cardinality (bounded for safety)
    n = len(ordered)
    if n > 14:
        # Take deterministic prefix needed to cross threshold; mark incomplete
        acc = 0
        chosen: list[str] = []
        for pid, amt in sorted(ordered, key=lambda x: (-x[1], x[0])):
            chosen.append(pid)
            acc += amt
            if acc >= needed_prior:
                break
        return ([tuple(sorted(chosen))] if acc >= needed_prior else []), False

    for r in range(1, n + 1):
        for comb in combinations(ordered, r):
            total = sum(amt for _, amt in comb)
            if total < needed_prior:
                continue
            cand_ids = tuple(pid for pid, _ in comb)
            cand_set = frozenset(cand_ids)
            if any(frozenset(existing).issubset(cand_set) for existing in minimal_sets):
                continue
            minimal_sets.append(cand_ids)
            if len(minimal_sets) >= max_sets:
                complete = False
                return minimal_sets, complete

    return minimal_sets, complete


def detect_duplicate_payments(
    episode: PublicEpisode,
    graph: ProofGraph,
    *,
    max_evidence_sets: int = MAX_SCHEMA_EVIDENCE_SETS,
) -> DetectorResult:
    """Independently discover DUPLICATE_PAYMENT anomalies from public data."""
    findings: list[VerifierFinding] = []
    ambiguities: list[str] = []

    invoices_by_id = episode.invoices_by_id

    # Index JEs by source_document_id
    jes_by_source: dict[str, list[dict[str, Any]]] = {}
    for je in episode.journal_entries:
        src = je.get("source_document_id")
        if isinstance(src, str) and src:
            jes_by_source.setdefault(src, []).append(je)

    # Index credit notes by invoice_id
    cns_by_invoice: dict[str, list[dict[str, Any]]] = {}
    for cn in episode.credit_notes:
        inv_id = cn.get("invoice_id")
        if isinstance(inv_id, str) and inv_id:
            cns_by_invoice.setdefault(inv_id, []).append(cn)

    # Identify reversed/refunded payment IDs and per-invoice refund offsets (D-DUP-04)
    reversed_payment_ids: dict[str, list[dict[str, Any]]] = {}
    refund_offsets_by_inv: dict[str, list[tuple[dict[str, Any], int]]] = {}
    for pay in episode.payments:
        if not _is_reversal_payment(pay):
            continue
        rel = pay.get("related_payment_id")
        if isinstance(rel, str) and rel:
            reversed_payment_ids.setdefault(rel, []).append(pay)
        for alloc in pay.get("allocations", ()):
            doc_id = str(alloc.get("document_id", ""))
            amt = abs(require_minor_int(alloc["amount_minor"], "refund.allocation.amount_minor"))
            if doc_id:
                refund_offsets_by_inv.setdefault(doc_id, []).append((pay, amt))

    # Group valid positive payment allocations by invoice_id
    # Exclude single-payment over-allocations or wrong-counterparty/currency allocations
    # (those belong to PARTIAL_PAYMENT_ALLOCATION).
    pos_allocs_by_inv: dict[str, list[tuple[dict[str, Any], int]]] = {}
    all_positive_payments: list[dict[str, Any]] = []
    for pay in episode.payments:
        if _is_reversal_payment(pay):
            continue
        pay_amt = require_minor_int(pay["amount_minor"], "payment.amount_minor")
        if pay_amt <= 0:
            continue
        all_positive_payments.append(pay)
        allocs = pay.get("allocations", ())
        if not allocs:
            continue
        if any(require_minor_int(a["amount_minor"]) < 0 for a in allocs):
            continue
        if _payment_allocation_sum(pay) > pay_amt:
            # INV-15 over-allocation is handled by PARTIAL_PAYMENT_ALLOCATION
            continue
        for alloc in allocs:
            doc_id = str(alloc.get("document_id", ""))
            inv = invoices_by_id.get(doc_id)
            if inv is None:
                continue
            if inv.get("currency") != pay.get("currency"):
                continue
            if inv.get("counterparty_id") != pay.get("counterparty_id"):
                continue
            alloc_amt = require_minor_int(alloc["amount_minor"], "allocation.amount_minor")
            if alloc_amt > 0:
                pos_allocs_by_inv.setdefault(doc_id, []).append((pay, alloc_amt))

    dup_rule_node = graph.add_rule(
        rule_id="RULE:DUPLICATE_PAYMENT:INV-04",
        payload={
            "invariant": "INV-04",
            "rule": "Multiple non-reversed payments allocating more than net payable on one invoice",
        },
        source_files=("policy.json",),
        label="Duplicate payment overpayment rule",
    )

    # Check each invoice with >= 2 positive payment events
    for doc_id in sorted(pos_allocs_by_inv):
        inv = invoices_by_id[doc_id]
        inv_tid = make_typed_id("INV", doc_id)
        entries = pos_allocs_by_inv[doc_id]
        # Aggregate per distinct payment on this invoice
        per_pay: dict[str, tuple[dict[str, Any], int]] = {}
        for pay, amt in entries:
            pid = str(pay["pay_id"])
            if pid in per_pay:
                per_pay[pid] = (pay, per_pay[pid][1] + amt)
            else:
                per_pay[pid] = (pay, amt)

        if len(per_pay) < 2:
            continue

        inv_total = require_minor_int(inv["total_minor"], "invoice.total_minor")
        inv_currency = str(inv["currency"])
        cns = [
            cn for cn in cns_by_invoice.get(doc_id, ())
            if cn.get("currency") == inv_currency
        ]
        gross_allocated = sum(amt for _, amt in per_pay.values())

        # Partition credit notes: obligation-reducing vs overpayment-offsetting (D-DUP-01)
        reducing_cns: list[dict[str, Any]] = []
        offsetting_cns: list[dict[str, Any]] = []
        for cn in cns:
            reason = str(cn.get("reason_code") or "").lower()
            if reason in OVERPAYMENT_OFFSET_CN_REASONS and gross_allocated > inv_total:
                offsetting_cns.append(cn)
            else:
                reducing_cns.append(cn)

        reducing_cn_total = sum(
            require_minor_int(cn["amount_minor"], "credit_note.amount_minor")
            for cn in reducing_cns
        )
        offsetting_cn_total = sum(
            require_minor_int(cn["amount_minor"], "credit_note.amount_minor")
            for cn in offsetting_cns
        )
        net_payable = max(0, inv_total - reducing_cn_total)

        # Account for explicit payment reversals/refunds (D-DUP-04)
        active_payments: list[tuple[dict[str, Any], int]] = []
        reversal_records: list[dict[str, Any]] = []
        for pid, (pay, amt) in per_pay.items():
            revs = reversed_payment_ids.get(pid, ())
            rev_sum = sum(abs(require_minor_int(r["amount_minor"])) for r in revs)
            if rev_sum >= amt:
                reversal_records.extend(revs)
                continue
            active_payments.append((pay, amt - rev_sum))

        inv_refund_offsets = refund_offsets_by_inv.get(doc_id, ())
        # Only count refund offsets not already applied via related_payment_id
        already_counted_rev_ids = {str(r["pay_id"]) for r in reversal_records}
        extra_refund_total = 0
        for rpay, ramt in inv_refund_offsets:
            if str(rpay["pay_id"]) not in already_counted_rev_ids:
                extra_refund_total += ramt
                reversal_records.append(rpay)

        active_total = sum(amt for _, amt in active_payments)
        effective_allocated = active_total - offsetting_cn_total - extra_refund_total

        # Build ProofGraph nodes for this invoice candidate
        inv_rec_node = graph.add_record(inv_tid, inv)
        pay_rec_nodes: list[str] = []
        pay_tids: list[str] = []
        for pay, _ in sorted(per_pay.values(), key=lambda x: str(x[0]["pay_id"])):
            ptid = make_typed_id("PAY", str(pay["pay_id"]))
            pay_tids.append(ptid)
            pay_rec_nodes.append(graph.add_record(ptid, pay))

        cand_calc = graph.add_calculation(
            calc_key=f"dup_check:{doc_id}",
            rule_id="RULE:DUPLICATE_PAYMENT:INV-04",
            source_ids=[inv_tid] + pay_tids,
            parent_node_ids=[inv_rec_node] + pay_rec_nodes,
            governed_by_nodes=[dup_rule_node],
            payload={
                "doc_id": doc_id,
                "invoice_total_minor": inv_total,
                "net_payable_minor": net_payable,
                "gross_allocated_minor": gross_allocated,
                "effective_allocated_minor": effective_allocated,
                "currency": inv_currency,
            },
            label=f"Duplicate payment check on {inv_tid}",
        )

        # Case 1: Excluded by D-DUP-04 (refund/reversal explains overpayment)
        if effective_allocated <= net_payable:
            if reversal_records:
                rev_rule = graph.add_rule(
                    rule_id="RULE:D-DUP-04:REFUND_REVERSAL_EXCLUSION",
                    payload={"distractor": "D-DUP-04", "reason": "refund or reversal offsets duplicate"},
                    source_files=("policy.json",),
                )
                rev_nodes = []
                for rpay in sorted(reversal_records, key=lambda r: str(r["pay_id"])):
                    rtid = make_typed_id("PAY", str(rpay["pay_id"]))
                    rnode = graph.add_record(rtid, rpay)
                    fnode = graph.add_fact(
                        fact_key=f"d_dup_04:{doc_id}:{rpay['pay_id']}",
                        rule_id="RULE:D-DUP-04:REFUND_REVERSAL_EXCLUSION",
                        source_ids=[rtid, inv_tid],
                        parent_node_ids=[rnode, inv_rec_node],
                        payload={"refund_pay_id": rpay["pay_id"], "doc_id": doc_id},
                    )
                    rev_nodes.append(fnode)
                graph.record_exclusion("D-DUP-04", cand_calc, rev_nodes, rule_node_id=rev_rule, edge_type="excludes")
            elif offsetting_cns:
                cn_rule = graph.add_rule(
                    rule_id="RULE:D-DUP-01:CREDIT_NOTE_EXCLUSION",
                    payload={"distractor": "D-DUP-01", "reason": "credit adjustment offsets overpayment"},
                    source_files=("policy.json",),
                )
                cn_nodes = []
                for cn in sorted(offsetting_cns, key=lambda c: str(c["credit_note_id"])):
                    ctid = make_typed_id("CN", str(cn["credit_note_id"]))
                    cnode = graph.add_record(ctid, cn)
                    fnode = graph.add_fact(
                        fact_key=f"d_dup_01:{doc_id}:{cn['credit_note_id']}",
                        rule_id="RULE:D-DUP-01:CREDIT_NOTE_EXCLUSION",
                        source_ids=[ctid, inv_tid],
                        parent_node_ids=[cnode, inv_rec_node],
                        payload={"credit_note_id": cn["credit_note_id"], "amount_minor": cn["amount_minor"]},
                    )
                    cn_nodes.append(fnode)
                graph.record_exclusion("D-DUP-01", cand_calc, cn_nodes, rule_node_id=cn_rule, edge_type="excludes")
            continue

        # Chronologically identify duplicate payment(s) pushing net above net_payable
        # Apply offsetting credits/refunds against overpayment threshold
        effective_threshold = net_payable + offsetting_cn_total + extra_refund_total
        ordered_active = sorted(
            active_payments,
            key=lambda item: (parse_iso_instant(str(item[0]["timestamp"])), str(item[0]["pay_id"])),
        )

        cumulative = 0
        prior_so_far: list[tuple[str, int]] = []
        reducing_cn_tids = tuple(
            sorted(make_typed_id("CN", str(cn["credit_note_id"])) for cn in reducing_cns)
        )

        for pay, alloc_amt in ordered_active:
            prev_cum = cumulative
            cumulative += alloc_amt
            ptid = make_typed_id("PAY", str(pay["pay_id"]))

            if cumulative > effective_threshold and prior_so_far:
                excess_here = min(alloc_amt, cumulative - effective_threshold)
                if excess_here <= 0:
                    prior_so_far.append((ptid, alloc_amt))
                    continue

                dup_jes = sorted(
                    jes_by_source.get(str(pay["pay_id"]), ()),
                    key=lambda j: str(j["je_id"]),
                )
                dup_je_tids = [make_typed_id("JE", str(j["je_id"])) for j in dup_jes]
                affected = tuple(sorted([ptid] + dup_je_tids))

                # Determine whether reducing credit notes are needed to establish overpayment
                need_cns = (prev_cum + alloc_amt) <= (inv_total + offsetting_cn_total + extra_refund_total)
                base_evidence = [inv_tid, ptid] + dup_je_tids
                if need_cns:
                    base_evidence.extend(reducing_cn_tids)

                prior_combos, complete = _minimal_prior_subsets(
                    prior_so_far,
                    dup_alloc=alloc_amt,
                    net_payable=effective_threshold,
                    target_excess=excess_here,
                    max_sets=max_evidence_sets,
                )
                evidence_sets: list[tuple[str, ...]] = []
                for combo in prior_combos:
                    ev = tuple(sorted(set(base_evidence) | set(combo)))
                    if ev not in evidence_sets:
                        evidence_sets.append(ev)
                evidence_sets.sort(key=lambda s: (len(s), s))
                if not evidence_sets:
                    evidence_sets = [tuple(sorted(set(base_evidence) | {p for p, _ in prior_so_far}))]

                # Record JE nodes and FindingNode in ProofGraph
                supporting_nodes = [cand_calc]
                for je, jtid in zip(dup_jes, dup_je_tids):
                    jnode = graph.add_record(jtid, je)
                    fnode = graph.add_fact(
                        fact_key=f"dup_je:{pay['pay_id']}:{je['je_id']}",
                        rule_id="RULE:DUPLICATE_PAYMENT:AFFECTED_JE",
                        source_ids=[jtid, ptid],
                        parent_node_ids=[jnode, graph.add_record(ptid, pay)],
                        payload={"je_id": je["je_id"], "source_document_id": pay["pay_id"]},
                    )
                    supporting_nodes.append(fnode)

                finding_payload = {
                    "type": "DUPLICATE_PAYMENT",
                    "affected_ids": list(affected),
                    "claimed_amount_minor": excess_here,
                    "currency": inv_currency,
                    "doc_id": doc_id,
                }
                finding_node_id = graph.add_finding(
                    finding_key=f"DUPLICATE_PAYMENT:{pay['pay_id']}",
                    rule_id="RULE:DUPLICATE_PAYMENT:INV-04",
                    source_ids=sorted({eid for s in evidence_sets for eid in s}),
                    supporting_node_ids=supporting_nodes,
                    governed_by_nodes=[dup_rule_node],
                    payload=finding_payload,
                    label=f"Duplicate payment {ptid} on {inv_tid}",
                )

                findings.append(
                    VerifierFinding(
                        type="DUPLICATE_PAYMENT",
                        affected_ids=affected,
                        claimed_amount_minor=excess_here,
                        currency=inv_currency,
                        evidence_sets=tuple(evidence_sets[:max_evidence_sets]),
                        explanation_code="DUP_PAY_OVERPAID_INVOICE",
                        proof_graph_ref=f"proof:{finding_node_id}",
                        evidence_enumeration_complete=complete,
                    )
                )

            prior_so_far.append((ptid, alloc_amt))

    # Explicit ProofGraph exclusions for D-DUP-02 (same amount, different invoices)
    # and D-DUP-03 (recurring subscription across different service periods)
    by_cp_amt_cur: dict[tuple[str, int, str], list[dict[str, Any]]] = {}
    for pay in all_positive_payments:
        allocs = pay.get("allocations", ())
        if len(allocs) == 1:
            key = (
                str(pay.get("counterparty_id", "")),
                require_minor_int(pay["amount_minor"]),
                str(pay.get("currency", "")),
            )
            by_cp_amt_cur.setdefault(key, []).append(pay)

    for (cp_id, amt, cur), pays in sorted(by_cp_amt_cur.items()):
        if len(pays) < 2:
            continue
        doc_ids = sorted({str(p["allocations"][0]["document_id"]) for p in pays})
        if len(doc_ids) < 2:
            continue
        invs = [invoices_by_id[d] for d in doc_ids if d in invoices_by_id]
        if len(invs) < 2:
            continue

        # Distinguish D-DUP-03 (recurring subscription for different service periods) vs D-DUP-02
        service_windows = {
            (str(inv.get("service_start", "")), str(inv.get("service_end", "")))
            for inv in invs
        }
        has_subscription = any(
            inv.get("subscription_period") is not None
            or "subscription" in str(inv.get("recognition_rule") or "").lower()
            or (inv.get("service_start") and inv.get("service_end") and len(service_windows) >= 2)
            for inv in invs
        )
        distractor_code = "D-DUP-03" if has_subscription else "D-DUP-02"
        rule_id = (
            "RULE:D-DUP-03:RECURRING_SUBSCRIPTION_PERIODS"
            if has_subscription
            else "RULE:D-DUP-02:DISTINCT_INVOICES_SAME_AMOUNT"
        )
        excl_rule = graph.add_rule(
            rule_id=rule_id,
            payload={"distractor": distractor_code, "counterparty_id": cp_id, "amount_minor": amt},
            source_files=("policy.json",),
        )
        p_nodes = []
        p_tids = []
        for p in sorted(pays, key=lambda x: str(x["pay_id"])):
            ptid = make_typed_id("PAY", str(p["pay_id"]))
            p_tids.append(ptid)
            p_nodes.append(graph.add_record(ptid, p))
        cand_fact = graph.add_fact(
            fact_key=f"same_amt_pair:{cp_id}:{amt}:{cur}",
            rule_id="RULE:DUPLICATE_PAYMENT:CANDIDATE_SAME_AMOUNT",
            source_ids=p_tids,
            parent_node_ids=p_nodes,
            payload={"counterparty_id": cp_id, "amount_minor": amt, "currency": cur, "payments": p_tids},
        )
        inv_nodes = []
        for inv in sorted(invs, key=lambda x: str(x["doc_id"])):
            itid = make_typed_id("INV", str(inv["doc_id"]))
            inode = graph.add_record(itid, inv)
            inv_fact = graph.add_fact(
                fact_key=f"distinct_inv:{distractor_code}:{inv['doc_id']}",
                rule_id=rule_id,
                source_ids=[itid],
                parent_node_ids=[inode],
                payload={
                    "doc_id": inv["doc_id"],
                    "service_start": inv.get("service_start"),
                    "service_end": inv.get("service_end"),
                    "subscription_period": inv.get("subscription_period"),
                },
            )
            inv_nodes.append(inv_fact)
        graph.record_exclusion(distractor_code, cand_fact, inv_nodes, rule_node_id=excl_rule, edge_type="excludes")

    return DetectorResult(findings=tuple(findings), ambiguities=tuple(ambiguities))


__all__ = ["DetectorResult", "detect_duplicate_payments"]
