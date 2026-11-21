"""Phase 4 + Phase 7 episode-level anomaly mutation operators.

Covers all four TwinLedger v3.0 anomaly types on a cloned ``CleanTwin``:
  - ``DUPLICATE_PAYMENT``
  - ``PARTIAL_PAYMENT_ALLOCATION``
  - ``FX_RATE_MISMATCH`` (delegates core math/check to ``gen.errors.fx_cutoff``)
  - ``PERIOD_CUTOFF`` (delegates core period/check to ``gen.errors.fx_cutoff``)

Every operator:
  - mutates a copy cleanly while preserving double-entry balance (INV-01);
  - uses stateless anti-shortcut IDs (zero ``DUP``/``ERR`` leak in public IDs);
  - returns an exact ``OperatorOutcome`` with frozen-schema-valid
    ``TruthFinding`` dict and structural provenance metadata.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from contracts.loader import validate_instance
from core.time_rules import fiscal_period, instant
from gen.core.clean_twin import (
    CleanTwin,
    make_balanced_je,
    select_permitted_fx,
)
from gen.errors.fx_cutoff import (
    Journal,
    Quote,
    fx_rate_mismatch as normalized_fx_mismatch,
    period_cutoff as normalized_period_cutoff,
)

OPERATOR_VERSION = "gen-operators@1.0.0"


@dataclass(frozen=True)
class OperatorOutcome:
    """Result of applying one anomaly operator to a CleanTwin."""

    operator_name: str
    truth_finding: dict[str, Any]
    mutated_ids: tuple[str, ...]
    provenance: dict[str, Any]


def _make_truth_dict(
    *,
    truth_id: str,
    anomaly_type: str,
    affected_ids: list[str],
    amount_minor: int,
    currency: str,
    evidence_sets: list[list[str]],
    invariant_signature: dict[str, Any],
    tolerance_minor: int = 0,
    evidence_enumeration_complete: bool = True,
) -> dict[str, Any]:
    norm_aff = sorted(set(affected_ids))
    norm_ev = sorted({tuple(sorted(set(s))) for s in evidence_sets})
    ev_lists = [list(s) for s in norm_ev]
    min_size = min(len(s) for s in ev_lists)
    doc = {
        "schema_version": "1.0.0",
        "truth_id": truth_id,
        "type": anomaly_type,
        "affected_ids": norm_aff,
        "amount_minor": amount_minor,
        "currency": currency,
        "tolerance_minor": tolerance_minor,
        "evidence_sets": ev_lists,
        "evidence_enumeration_complete": evidence_enumeration_complete,
        "minimal_evidence_size": min_size,
        "invariant_signature": invariant_signature,
        "operator_version": OPERATOR_VERSION,
    }
    errs = validate_instance("truth", doc)
    if errs:
        raise ValueError(f"generated truth failed frozen schema: {errs}")
    return doc


def _iso_shift(ts: str, delta_days: int, tz_name: str) -> str:
    dt = instant(ts).astimezone(ZoneInfo(tz_name)) + timedelta(days=delta_days)
    return dt.isoformat()


def inject_duplicate_payment(
    twin: CleanTwin,
    rng: random.Random,
    *,
    truth_index: int = 1,
    excluded_inv_ids: set[str] | None = None,
) -> OperatorOutcome:
    """Inject a real duplicate payment + bank line + balanced JE on a clean paid invoice."""
    excluded = excluded_inv_ids or set()
    # Find clean paid domestic invoices with exactly 1 prior payment and 0 credit notes
    cn_invs = {cn["invoice_id"] for cn in twin.credit_notes}
    alloc_by_inv: dict[str, list[dict[str, Any]]] = {}
    for p in twin.payments:
        for al in p.get("allocations", []):
            alloc_by_inv.setdefault(al["document_id"], []).append(p)

    candidates = [
        inv for inv in twin.invoices
        if inv["status"] == "paid"
        and inv["doc_id"] not in excluded
        and inv["doc_id"] not in cn_invs
        and inv["currency"] == twin.company["functional_currency"]
        and len(alloc_by_inv.get(inv["doc_id"], [])) == 1
        and alloc_by_inv[inv["doc_id"]][0]["amount_minor"] == inv["total_minor"]
    ]
    if not candidates:
        raise ValueError("no eligible paid invoice for duplicate_payment operator")

    inv = candidates[rng.randrange(len(candidates))]
    orig_pay = alloc_by_inv[inv["doc_id"]][0]
    tz = twin.company["timezone"]
    dup_ts = _iso_shift(orig_pay["timestamp"], 1, tz)
    dup_pay_id = twin.next_id("PAY", f"op_dup_pay:{truth_index}:{inv['doc_id']}")
    dup_bank_id = twin.next_id("BANK", f"op_dup_bank:{truth_index}:{inv['doc_id']}")
    dup_je_id = twin.next_id("JE", f"op_dup_je:{truth_index}:{inv['doc_id']}")
    dup_al_id = twin.next_id("AL", f"op_dup_al:{truth_index}:{inv['doc_id']}")

    amt = inv["total_minor"]
    cur = inv["currency"]
    twin.payments.append(
        {
            "pay_id": dup_pay_id,
            "timestamp": dup_ts,
            "counterparty_id": inv["counterparty_id"],
            "currency": cur,
            "amount_minor": amt,
            "allocations": [
                {
                    "allocation_id": dup_al_id,
                    "document_id": inv["doc_id"],
                    "amount_minor": amt,
                    "allocation_timestamp": dup_ts,
                }
            ],
            "bank_reference": dup_bank_id,
            "payment_channel": orig_pay.get("payment_channel", "wire"),
        }
    )
    twin.bank_lines.append(
        {
            "bank_line_id": dup_bank_id,
            "timestamp": dup_ts,
            "amount_minor": amt,
            "currency": cur,
            "direction": "outbound",
            "counterparty_text": inv["counterparty_id"],
            "reference_text": f"Settlement {inv['doc_id']}",
        }
    )
    pp = fiscal_period(
        {"service_date": dup_ts, "delivery_date": dup_ts, "issue_date": dup_ts},
        twin.policy,
        twin.company,
    )
    twin.journal_entries.append(
        make_balanced_je(
            je_id=dup_je_id,
            timestamp=dup_ts,
            posting_period=pp,
            source_document_id=dup_pay_id,
            description=f"Settle invoice {inv['doc_id']}",
            debit_account="2010",
            credit_account="1010",
            amount_minor=amt,
            currency=cur,
            fx_rate_decimal="1",
            functional_amount_minor=amt,
            counterparty_id=inv["counterparty_id"],
        )
    )

    affected = [f"JE:{dup_je_id}", f"PAY:{dup_pay_id}"]
    ev_set = [f"INV:{inv['doc_id']}", f"JE:{dup_je_id}", f"PAY:{orig_pay['pay_id']}", f"PAY:{dup_pay_id}"]
    truth = _make_truth_dict(
        truth_id=f"T-{twin.episode_id}-{truth_index:03d}",
        anomaly_type="DUPLICATE_PAYMENT",
        affected_ids=affected,
        amount_minor=amt,
        currency=cur,
        evidence_sets=[ev_set],
        invariant_signature={
            "invariant_id": "INV-04",
            "invoice_id": inv["doc_id"],
            "duplicate_payment_id": dup_pay_id,
            "prior_payment_id": orig_pay["pay_id"],
        },
    )
    return OperatorOutcome(
        operator_name="duplicate_payment",
        truth_finding=truth,
        mutated_ids=tuple(sorted(set(affected + [f"BANK:{dup_bank_id}"]))),
        provenance={
            "target_invoice": inv["doc_id"],
            "original_payment": orig_pay["pay_id"],
            "injected_payment": dup_pay_id,
            "injected_je": dup_je_id,
        },
    )


def inject_partial_allocation(
    twin: CleanTwin,
    rng: random.Random,
    *,
    truth_index: int = 1,
    subcase: str = "premature_paid",
    excluded_inv_ids: set[str] | None = None,
) -> OperatorOutcome:
    """Inject a PARTIAL_PAYMENT_ALLOCATION anomaly on a clean paid invoice."""
    excluded = excluded_inv_ids or set()
    cn_invs = {cn["invoice_id"] for cn in twin.credit_notes}
    alloc_by_inv: dict[str, list[dict[str, Any]]] = {}
    for p in twin.payments:
        for al in p.get("allocations", []):
            alloc_by_inv.setdefault(al["document_id"], []).append(p)

    candidates = [
        inv for inv in twin.invoices
        if inv["status"] == "paid"
        and inv["doc_id"] not in excluded
        and inv["doc_id"] not in cn_invs
        and inv["currency"] == twin.company["functional_currency"]
        and inv["total_minor"] >= 1000
        and len(alloc_by_inv.get(inv["doc_id"], [])) == 1
        and len(alloc_by_inv[inv["doc_id"]][0].get("allocations", [])) == 1
    ]
    if not candidates:
        raise ValueError("no eligible paid invoice for partial_allocation operator")

    inv = candidates[rng.randrange(len(candidates))]
    pay = alloc_by_inv[inv["doc_id"]][0]
    total = inv["total_minor"]
    cur = inv["currency"]

    if subcase == "premature_paid":
        # Reduce payment + allocation + corresponding payment JE symmetrically to 60%
        # while leaving invoice.status == "paid" (unpaid remainder = 40%)
        paid_amt = (total * 6) // 10
        unpaid_amt = total - paid_amt
        pay["amount_minor"] = paid_amt
        pay["allocations"][0]["amount_minor"] = paid_amt
        for bl in twin.bank_lines:
            if bl["bank_line_id"] == pay.get("bank_reference"):
                bl["amount_minor"] = paid_amt
        for je in twin.journal_entries:
            if je.get("source_document_id") == pay["pay_id"]:
                for ln in je["lines"]:
                    if ln["debit_minor"] > 0:
                        ln["debit_minor"] = paid_amt
                        ln["functional_debit_minor"] = paid_amt
                    if ln["credit_minor"] > 0:
                        ln["credit_minor"] = paid_amt
                        ln["functional_credit_minor"] = paid_amt
        affected = [f"INV:{inv['doc_id']}", f"PAY:{pay['pay_id']}"]
        ev_set = [f"INV:{inv['doc_id']}", f"PAY:{pay['pay_id']}"]
        amount_minor = unpaid_amt
        sig = {"invariant_id": "INV-06", "subcase": "premature_paid", "invoice_id": inv["doc_id"], "pay_id": pay["pay_id"]}

    elif subcase == "over_allocated_payment":
        # Payment amount is 70%, but allocation claims 100% -> over-allocated by 30%
        # (Invoice total matches allocation so INV-04 does not fire; INV-05 fires on payment)
        pay_amt = (total * 7) // 10
        over_amt = total - pay_amt
        pay["amount_minor"] = pay_amt
        for bl in twin.bank_lines:
            if bl["bank_line_id"] == pay.get("bank_reference"):
                bl["amount_minor"] = pay_amt
        for je in twin.journal_entries:
            if je.get("source_document_id") == pay["pay_id"]:
                for ln in je["lines"]:
                    if ln["debit_minor"] > 0:
                        ln["debit_minor"] = pay_amt
                        ln["functional_debit_minor"] = pay_amt
                    if ln["credit_minor"] > 0:
                        ln["credit_minor"] = pay_amt
                        ln["functional_credit_minor"] = pay_amt
        affected = [f"INV:{inv['doc_id']}", f"PAY:{pay['pay_id']}"]
        ev_set = [f"INV:{inv['doc_id']}", f"PAY:{pay['pay_id']}"]
        amount_minor = over_amt
        sig = {"invariant_id": "INV-05", "subcase": "over_allocated_payment", "pay_id": pay["pay_id"]}
    else:
        raise ValueError(f"unsupported partial_allocation subcase: {subcase!r}")

    truth = _make_truth_dict(
        truth_id=f"T-{twin.episode_id}-{truth_index:03d}",
        anomaly_type="PARTIAL_PAYMENT_ALLOCATION",
        affected_ids=affected,
        amount_minor=amount_minor,
        currency=cur,
        evidence_sets=[ev_set],
        invariant_signature=sig,
    )
    return OperatorOutcome(
        operator_name="partial_allocation",
        truth_finding=truth,
        mutated_ids=tuple(sorted(set(affected))),
        provenance={"subcase": subcase, "target_invoice": inv["doc_id"], "target_payment": pay["pay_id"]},
    )


def inject_fx_mismatch(
    twin: CleanTwin,
    rng: random.Random,
    *,
    truth_index: int = 1,
    excluded_je_ids: set[str] | None = None,
) -> OperatorOutcome:
    """Inject an FX_RATE_MISMATCH using Phase 7's ``gen.errors.fx_cutoff.fx_rate_mismatch``."""
    excluded = excluded_je_ids or set()
    func_cur = twin.company["functional_currency"]
    inv_by_id = {inv["doc_id"]: inv for inv in twin.invoices}
    conv = twin.policy["fx_policy"]["quote_convention"]
    tz = ZoneInfo(twin.company["timezone"])

    # Build Quote timeline per foreign currency compatible with gen/errors/fx_cutoff.py
    def _quotes_for(fcur: str) -> dict[str, Quote]:
        expected_pair = f"{fcur}/{func_cur}" if conv == "functional_per_foreign" else f"{func_cur}/{fcur}"
        out: dict[str, Quote] = {}
        for row in twin.fx_rates:
            if row["pair"] != expected_pair:
                continue
            out[row["fx_id"]] = Quote(
                id=row["fx_id"],
                business_date=date.fromisoformat(row["effective_date"]),
                source=row["source_code"],
                foreign=fcur,
                functional=func_cur,
                rate=row["rate_decimal"],
            )
        return out

    candidates: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for je in twin.journal_entries:
        if je["je_id"] in excluded:
            continue
        src_doc = inv_by_id.get(je.get("source_document_id", ""))
        if not src_doc or src_doc["currency"] == func_cur:
            continue
        if len(je["lines"]) != 2:
            continue
        candidates.append((je, src_doc, src_doc["currency"]))

    if not candidates:
        raise ValueError("no eligible foreign-currency journal entry for fx_mismatch operator")

    rng.shuffle(candidates)
    last_err: Exception | None = None
    for je, inv, fcur in candidates:
        quotes = _quotes_for(fcur)
        rate_rule = twin.policy["fx_policy"]["rate_date_rule"]
        events = {
            "document_date": inv["issue_timestamp"],
            "operation_date": inv["service_start"],
            "payment_date": inv["issue_timestamp"],
        }
        target_d = instant(events[rate_rule]).astimezone(tz).date()
        permitted_rows = select_permitted_fx(twin.fx_rates, fcur, func_cur, target_d, twin.policy)
        permitted_ids = {r["fx_id"] for r in permitted_rows}
        # Find a non-permitted published quote (prefer MKT same date, else different NBK date)
        non_perm = [q for qid, q in sorted(quotes.items()) if qid not in permitted_ids]
        non_perm.sort(key=lambda q: (0 if q.source != "NBK" and q.business_date == target_d else 1, q.id))
        if not non_perm:
            continue

        debit_ln = next(ln for ln in je["lines"] if ln["debit_minor"] > 0)
        credit_ln = next(ln for ln in je["lines"] if ln["credit_minor"] > 0)
        clean_journal = Journal(
            id=je["je_id"],
            source_currency=fcur,
            currency=func_cur,
            source_minor=debit_ln["debit_minor"],
            debit_minor=debit_ln["functional_debit_minor"],
            credit_minor=credit_ln["functional_credit_minor"],
            rate_id=permitted_rows[0]["fx_id"],
            posting_period=je["posting_period"],
        )
        for wrong_q in non_perm:
            try:
                mutated_j, (sig_inv07, sig_inv08) = normalized_fx_mismatch(
                    clean_journal, quotes, wrong_q.id, events, twin.policy, twin.company
                )
            except ValueError as exc:
                last_err = exc
                continue

            # Apply balanced mutation to JE
            debit_ln["fx_rate_decimal"] = wrong_q.rate
            debit_ln["functional_debit_minor"] = mutated_j.debit_minor
            credit_ln["fx_rate_decimal"] = wrong_q.rate
            credit_ln["functional_credit_minor"] = mutated_j.credit_minor

            ev_sets = [[f"FX:{r['fx_id']}", f"INV:{inv['doc_id']}", f"JE:{je['je_id']}"] for r in permitted_rows]
            delta_minor = int(sig_inv08.expected_delta_minor or 0)
            truth = _make_truth_dict(
                truth_id=f"T-{twin.episode_id}-{truth_index:03d}",
                anomaly_type="FX_RATE_MISMATCH",
                affected_ids=[f"JE:{je['je_id']}"],
                amount_minor=abs(delta_minor),
                currency=func_cur,
                evidence_sets=ev_sets,
                invariant_signature={
                    "invariant_id": sig_inv07.invariant_id,
                    "secondary_invariant": sig_inv08.invariant_id,
                    "je_id": je["je_id"],
                    "wrong_quote_id": wrong_q.id,
                    "permitted_quote_ids": sorted(permitted_ids),
                    "signed_delta_minor": delta_minor,
                },
            )
            return OperatorOutcome(
                operator_name="fx_rate_mismatch",
                truth_finding=truth,
                mutated_ids=(f"JE:{je['je_id']}",),
                provenance={
                    "je_id": je["je_id"],
                    "invoice_id": inv["doc_id"],
                    "clean_quote_id": clean_journal.rate_id,
                    "wrong_quote_id": wrong_q.id,
                },
            )

    raise ValueError(f"could not apply fx_mismatch to any candidate JE: {last_err}")


def inject_period_cutoff(
    twin: CleanTwin,
    rng: random.Random,
    *,
    truth_index: int = 1,
    excluded_je_ids: set[str] | None = None,
) -> OperatorOutcome:
    """Inject a PERIOD_CUTOFF using Phase 7's ``gen.errors.fx_cutoff.period_cutoff``."""
    excluded = excluded_je_ids or set()
    func_cur = twin.company["functional_currency"]
    inv_by_id = {inv["doc_id"]: inv for inv in twin.invoices}
    rec_event = twin.policy["cutoff_policy"]["recognition_event"]
    alt_event = "issue_date" if rec_event != "issue_date" else "service_date"

    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for je in twin.journal_entries:
        if je["je_id"] in excluded:
            continue
        inv = inv_by_id.get(je.get("source_document_id", ""))
        if not inv or inv.get("service_end") is not None:
            continue
        # Exclude prepayment JEs
        if any(ln.get("account_id") == "1410" or ln.get("analytic_tag") == "prepayment" for ln in je["lines"]):
            continue
        if len(je["lines"]) != 2:
            continue
        candidates.append((je, inv))

    if not candidates:
        raise ValueError("no eligible journal entry for period_cutoff operator")

    rng.shuffle(candidates)
    last_err: Exception | None = None
    for je, inv in candidates:
        events = {
            "service_date": inv["service_start"],
            "delivery_date": inv["service_start"],
            "issue_date": inv["issue_timestamp"],
        }
        debit_ln = next(ln for ln in je["lines"] if ln["debit_minor"] > 0)
        credit_ln = next(ln for ln in je["lines"] if ln["credit_minor"] > 0)
        clean_journal = Journal(
            id=je["je_id"],
            source_currency=debit_ln["currency"],
            currency=func_cur,
            source_minor=debit_ln["debit_minor"],
            debit_minor=debit_ln["functional_debit_minor"],
            credit_minor=credit_ln["functional_credit_minor"],
            rate_id=None,
            posting_period=je["posting_period"],
        )
        try:
            mutated_j, sig = normalized_period_cutoff(
                clean_journal, alt_event, events, twin.policy, twin.company
            )
        except ValueError as exc:
            last_err = exc
            continue

        old_period = je["posting_period"]
        je["posting_period"] = mutated_j.posting_period
        cutoff_amt = sum(ln["functional_debit_minor"] for ln in je["lines"])
        truth = _make_truth_dict(
            truth_id=f"T-{twin.episode_id}-{truth_index:03d}",
            anomaly_type="PERIOD_CUTOFF",
            affected_ids=[f"JE:{je['je_id']}"],
            amount_minor=cutoff_amt,
            currency=func_cur,
            evidence_sets=[[f"INV:{inv['doc_id']}", f"JE:{je['je_id']}"]],
            invariant_signature={
                "invariant_id": sig.invariant_id,
                "je_id": je["je_id"],
                "expected_period": old_period,
                "actual_period": mutated_j.posting_period,
            },
        )
        return OperatorOutcome(
            operator_name="period_cutoff",
            truth_finding=truth,
            mutated_ids=(f"JE:{je['je_id']}",),
            provenance={
                "je_id": je["je_id"],
                "invoice_id": inv["doc_id"],
                "expected_period": old_period,
                "mutated_period": mutated_j.posting_period,
            },
        )

    raise ValueError(f"could not apply period_cutoff to any candidate JE: {last_err}")


__all__ = [
    "OPERATOR_VERSION",
    "OperatorOutcome",
    "inject_duplicate_payment",
    "inject_fx_mismatch",
    "inject_partial_allocation",
    "inject_period_cutoff",
]
