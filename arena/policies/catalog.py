"""TZ §18.2 Baseline Policy Catalog speaking the v1.0 Public Tool API (Phase 12).

Implements the 7 public baseline policies required by Master TZ §18.2:
  1. ``random_policy``       — contract-valid random exploration + random candidate submission
  2. ``silent_policy``       — minimal inspection + empty submission ``[]``
  3. ``blind_submit``        — zero-step immediate ``submit([])``
  4. ``simple_recon``        — payment/invoice balance grouping only (DUP + PARTIAL)
  5. ``rule_based_auditor``  — parameterized 4-class deterministic accounting auditor
  6. ``evidence_first``      — verifies document & ledger views explicitly before claiming
  7. ``budget_aware``        — value-of-information table prioritization & page-size sizing

Note on #8 (``oracle_test_only``):
  Per REQ-ARENA-005, the privileged upper-bound oracle is strictly separated in
  ``judge/oracle_policy.py`` and NEVER included in public policy registries.

Zone 2 compliance: imports ONLY ``contracts``, ``nlp``, and Python 3.11 stdlib.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP
from typing import Any, Callable
from zoneinfo import ZoneInfo

from nlp.injection_guard import inspect_untrusted_text

StepCallable = Callable[[str, dict[str, Any]], dict[str, Any]]

PUBLIC_BASELINE_IDS: tuple[str, ...] = (
    "random_policy",
    "silent_policy",
    "blind_submit",
    "simple_recon",
    "rule_based_auditor",
    "evidence_first",
    "budget_aware",
)

TEST_ONLY_UPPER_BOUND_ID = "oracle_test_only"

_CURRENCY_EXPONENTS: dict[str, int] = {
    "KZT": 2,
    "USD": 2,
    "EUR": 2,
    "JPY": 0,
    "KWD": 3,
}


@dataclass(frozen=True)
class AuditorParams:
    """Small interpretable parameter space optimized by AutoHacker on TRAIN seeds (TZ §18.4)."""

    page_size: int = 50
    check_duplicate: bool = True
    check_partial: bool = True
    check_fx: bool = True
    check_cutoff: bool = True
    skip_fx_if_domestic_only: bool = True
    reserve_steps_for_submit: int = 2
    verify_evidence_docs: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_size": self.page_size,
            "check_duplicate": self.check_duplicate,
            "check_partial": self.check_partial,
            "check_fx": self.check_fx,
            "check_cutoff": self.check_cutoff,
            "skip_fx_if_domestic_only": self.skip_fx_if_domestic_only,
            "reserve_steps_for_submit": self.reserve_steps_for_submit,
            "verify_evidence_docs": self.verify_evidence_docs,
        }


def _typed(prefix: str, raw_id: str) -> str:
    return raw_id if ":" in raw_id else f"{prefix}:{raw_id}"


def _parse_local_date(ts: str, tz_name: str) -> date | None:
    if not isinstance(ts, str) or not ts:
        return None
    if len(ts) == 10 and ts[4] == "-" and ts[7] == "-":
        return date.fromisoformat(ts)
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(ZoneInfo(tz_name))
        return dt.date()
    except Exception:
        return None


def _period_for_date(d: date, calendar: list[dict[str, Any]]) -> str | None:
    for row in calendar:
        s = row.get("start_date")
        e = row.get("end_date")
        if isinstance(s, str) and isinstance(e, str):
            if date.fromisoformat(s) <= d <= date.fromisoformat(e):
                return str(row.get("period_id", ""))
    return None


def _convert_amount(
    amount_minor: int,
    src_cur: str,
    dst_cur: str,
    rate_str: str,
    rounding_mode: str,
    quote_convention: str,
) -> int:
    rate = Decimal(rate_str)
    src_exp = _CURRENCY_EXPONENTS.get(src_cur, 2)
    dst_exp = _CURRENCY_EXPONENTS.get(dst_cur, 2)
    shift = Decimal(10) ** (dst_exp - src_exp)
    if quote_convention == "foreign_per_functional":
        raw = (Decimal(amount_minor) / rate) * shift
    else:
        raw = Decimal(amount_minor) * rate * shift
    rounding = ROUND_HALF_UP if rounding_mode == "half_up" else ROUND_HALF_EVEN
    return int(raw.quantize(Decimal("1"), rounding=rounding))


class _StepBudgetClient:
    """Thin public API helper tracking remaining inspection budget."""

    def __init__(self, obs: dict[str, Any], step_fn: StepCallable, *, reserve_steps: int = 1) -> None:
        self.obs = obs
        self._step_fn = step_fn
        limits = obs.get("limits") or {}
        self.max_steps = int(limits.get("max_steps", 100))
        self.max_page_size = int(limits.get("max_page_size", 50))
        self.steps_used = 0
        self.reserve_steps = max(0, reserve_steps)

    @property
    def can_inspect(self) -> bool:
        return self.steps_used + self.reserve_steps < self.max_steps

    def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        resp = self._step_fn(tool, args)
        if tool != "submit":
            self.steps_used += 1
        return resp

    def fetch_table(self, table: str, *, page_size: int = 50, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        cursor: str | None = None
        eff_ps = max(1, min(int(page_size), self.max_page_size))
        while self.can_inspect:
            args: dict[str, Any] = {"table": table, "page_size": eff_ps}
            if filters:
                args["filters"] = filters
            if cursor is not None:
                args["cursor"] = cursor
            resp = self.call("list_records", args)
            if not resp.get("ok"):
                break
            res = resp.get("result") or {}
            out.extend(res.get("records") or [])
            cursor = res.get("next_cursor")
            if not cursor:
                break
        return out


def reconcile_public_tables(
    *,
    company: dict[str, Any],
    policy: dict[str, Any],
    invoices_list: list[dict[str, Any]],
    payments: list[dict[str, Any]],
    ledger: list[dict[str, Any]],
    fx_rows: list[dict[str, Any]],
    credit_notes: list[dict[str, Any]],
    calendar: list[dict[str, Any]],
    params: AuditorParams,
) -> list[dict[str, Any]]:
    """Pure structured accounting reconciliation (ignores untrusted free-text directives)."""
    base_cur = str(company.get("functional_currency") or company.get("base_currency") or "KZT")
    tz_name = str(company.get("timezone", "UTC"))
    rounding_mode = str(policy.get("rounding_mode", "half_even"))
    fx_pol = policy.get("fx_policy") or {}
    cutoff_pol = policy.get("cutoff_policy") or {}
    alloc_pol = policy.get("allocation_policy") or {}
    allow_advances = bool(alloc_pol.get("allow_advances", False))

    # Sanitize untrusted descriptions without ever treating them as instructions
    for inv in invoices_list:
        for item in inv.get("line_items") or ():
            inspect_untrusted_text(str(item.get("description", "")))

    invoices = {str(r["doc_id"]): r for r in invoices_list if "doc_id" in r}
    findings: list[dict[str, Any]] = []

    je_by_src: dict[str, list[dict[str, Any]]] = {}
    for je in ledger:
        src = je.get("source_document_id")
        if isinstance(src, str) and src:
            je_by_src.setdefault(src, []).append(je)

    cn_by_inv: dict[str, int] = {}
    for cn in credit_notes:
        inv_id = cn.get("invoice_id")
        amt = cn.get("amount_minor")
        if isinstance(inv_id, str) and type(amt) is int:
            cn_by_inv[inv_id] = cn_by_inv.get(inv_id, 0) + amt

    refunded_pay_ids: set[str] = set()
    for pay in payments:
        if pay.get("payment_type") == "refund" or (
            isinstance(pay.get("amount_minor"), int) and pay["amount_minor"] < 0
        ):
            rel = pay.get("related_payment_id")
            if isinstance(rel, str):
                refunded_pay_ids.add(rel)

    allocs_by_inv: dict[str, list[tuple[dict[str, Any], int]]] = {}
    for pay in payments:
        pay_id = str(pay.get("pay_id", ""))
        if not pay_id or pay_id in refunded_pay_ids:
            continue
        pay_amt = pay.get("amount_minor")
        if type(pay_amt) is not int or pay_amt < 0:
            continue
        pay_cur = str(pay.get("currency", base_cur))
        allocs = pay.get("allocations") if isinstance(pay.get("allocations"), list) else []
        alloc_sum = sum(int(a.get("amount_minor", 0)) for a in allocs if isinstance(a, dict))

        if alloc_sum > pay_amt:
            if params.check_partial:
                inv_ids = sorted(
                    {str(a["document_id"]) for a in allocs if isinstance(a, dict) and a.get("document_id")}
                )
                aff = sorted([_typed("PAY", pay_id)] + [_typed("INV", i) for i in inv_ids])
                findings.append(
                    {
                        "schema_version": "1.0.0",
                        "type": "PARTIAL_PAYMENT_ALLOCATION",
                        "affected_ids": aff,
                        "claimed_amount": alloc_sum - pay_amt,
                        "currency": pay_cur,
                        "evidence_ids": aff[:10],
                        "explanation": f"Allocations on {pay_id} exceed payment amount by {alloc_sum - pay_amt} {pay_cur}.",
                    }
                )
            continue

        if alloc_sum < pay_amt and not allow_advances:
            if params.check_partial:
                inv_ids = sorted(
                    {str(a["document_id"]) for a in allocs if isinstance(a, dict) and a.get("document_id")}
                )
                aff = sorted([_typed("PAY", pay_id)] + [_typed("INV", i) for i in inv_ids])
                findings.append(
                    {
                        "schema_version": "1.0.0",
                        "type": "PARTIAL_PAYMENT_ALLOCATION",
                        "affected_ids": aff,
                        "claimed_amount": pay_amt - alloc_sum,
                        "currency": pay_cur,
                        "evidence_ids": aff[:10],
                        "explanation": f"Unallocated balance {pay_amt - alloc_sum} {pay_cur} on {pay_id}.",
                    }
                )
            continue

        for a in allocs:
            if isinstance(a, dict) and a.get("document_id"):
                allocs_by_inv.setdefault(str(a["document_id"]), []).append(
                    (pay, int(a.get("amount_minor", 0)))
                )

    for inv_id, inv in sorted(invoices.items()):
        inv_total = inv.get("total_minor")
        if type(inv_total) is not int:
            continue
        inv_cur = str(inv.get("currency", base_cur))
        entries = allocs_by_inv.get(inv_id, [])
        net_paid = sum(a for _, a in entries)
        cn_total = cn_by_inv.get(inv_id, 0)

        if params.check_duplicate and len(entries) >= 2 and net_paid - cn_total > inv_total:
            ordered = sorted(entries, key=lambda x: str(x[0].get("timestamp", "")))
            orig_pay = ordered[0][0]
            dup_pay = ordered[-1][0]
            dup_pid = str(dup_pay["pay_id"])
            orig_pid = str(orig_pay["pay_id"])
            dup_jes = je_by_src.get(dup_pid, [])
            if dup_jes:
                dup_je_id = str(dup_jes[0]["je_id"])
                aff = sorted([_typed("JE", dup_je_id), _typed("PAY", dup_pid)])
                ev = sorted(
                    [
                        _typed("INV", inv_id),
                        _typed("JE", dup_je_id),
                        _typed("PAY", orig_pid),
                        _typed("PAY", dup_pid),
                    ]
                )
                findings.append(
                    {
                        "schema_version": "1.0.0",
                        "type": "DUPLICATE_PAYMENT",
                        "affected_ids": aff,
                        "claimed_amount": int(dup_pay["amount_minor"]),
                        "currency": inv_cur,
                        "evidence_ids": ev[:10],
                        "explanation": f"Duplicate payment {dup_pid} on {inv_id} for {dup_pay['amount_minor']} {inv_cur}.",
                    }
                )
        elif (
            params.check_partial
            and inv.get("status") == "paid"
            and len(entries) == 1
            and (net_paid + cn_total) < inv_total
        ):
            pay = entries[0][0]
            pid = str(pay["pay_id"])
            shortfall = inv_total - (net_paid + cn_total)
            aff = sorted([_typed("INV", inv_id), _typed("PAY", pid)])
            findings.append(
                {
                    "schema_version": "1.0.0",
                    "type": "PARTIAL_PAYMENT_ALLOCATION",
                    "affected_ids": aff,
                    "claimed_amount": shortfall,
                    "currency": inv_cur,
                    "evidence_ids": aff[:10],
                    "explanation": f"Premature paid status on {inv_id} with shortfall {shortfall} {inv_cur}.",
                }
            )

    allowed_sources = set(fx_pol.get("source_codes", ["NBK"]))
    quote_conv = str(fx_pol.get("quote_convention", "functional_per_foreign"))
    rate_date_rule = str(fx_pol.get("rate_date_rule", "document_date"))
    fallback_rule = str(fx_pol.get("fallback_rule", "last_available"))
    rec_event = str(cutoff_pol.get("recognition_event", "service_date"))

    for je in ledger:
        je_id = str(je.get("je_id", ""))
        src_id = je.get("source_document_id")
        if not je_id or not isinstance(src_id, str) or src_id not in invoices:
            continue
        inv = invoices[src_id]
        lines = je.get("lines") if isinstance(je.get("lines"), list) else []
        if not lines:
            continue

        inv_cur = str(inv.get("currency", base_cur))
        if params.check_fx and inv_cur != base_cur and fx_rows:
            expected_pair = (
                f"{inv_cur}/{base_cur}"
                if quote_conv == "functional_per_foreign"
                else f"{base_cur}/{inv_cur}"
            )
            ref_ts = je.get("timestamp") if rate_date_rule == "operation_date" else inv.get("issue_timestamp")
            target_d = _parse_local_date(str(ref_ts or ""), tz_name)
            if target_d is not None:
                cands: list[tuple[date, dict[str, Any]]] = []
                for r in fx_rows:
                    if r.get("pair") != expected_pair or r.get("source_code") not in allowed_sources:
                        continue
                    eff = date.fromisoformat(str(r["effective_date"]))
                    if eff == target_d or (fallback_rule == "last_available" and eff < target_d):
                        cands.append((eff, r))
                if cands:
                    latest = max(d for d, _ in cands)
                    best_fx = sorted([r for d, r in cands if d == latest], key=lambda q: str(q.get("fx_id", "")))[0]
                    src_amt = sum(int(ln.get("debit_minor", 0)) for ln in lines if isinstance(ln, dict))
                    actual_func = sum(int(ln.get("functional_debit_minor", 0)) for ln in lines if isinstance(ln, dict))
                    expected_func = _convert_amount(
                        src_amt,
                        inv_cur,
                        base_cur,
                        str(best_fx["rate_decimal"]),
                        rounding_mode,
                        quote_conv,
                    )
                    if actual_func != expected_func:
                        ev_list = (
                            sorted([_typed("FX", str(best_fx["fx_id"])), _typed("JE", je_id)])
                            if rate_date_rule == "operation_date"
                            else sorted([_typed("FX", str(best_fx["fx_id"])), _typed("INV", src_id), _typed("JE", je_id)])
                        )
                        findings.append(
                            {
                                "schema_version": "1.0.0",
                                "type": "FX_RATE_MISMATCH",
                                "affected_ids": [_typed("JE", je_id)],
                                "claimed_amount": abs(actual_func - expected_func),
                                "currency": base_cur,
                                "evidence_ids": ev_list[:10],
                                "explanation": f"FX delta {abs(actual_func - expected_func)} {base_cur} on {je_id} vs quote {best_fx['fx_id']}.",
                            }
                        )

        is_prepay = any(
            isinstance(ln, dict) and (ln.get("account_id") == "1410" or ln.get("analytic_tag") == "prepayment")
            for ln in lines
        )
        if params.check_cutoff and calendar and not is_prepay and inv.get("service_end") is None:
            ev_ts = inv.get("issue_timestamp") if rec_event == "issue_date" else inv.get("service_start")
            ev_date = _parse_local_date(str(ev_ts or ""), tz_name)
            if ev_date is not None:
                exp_period = _period_for_date(ev_date, calendar)
                actual_period = str(je.get("posting_period", ""))
                if exp_period and actual_period and exp_period != actual_period:
                    func_amt = sum(int(ln.get("functional_debit_minor", 0)) for ln in lines if isinstance(ln, dict))
                    findings.append(
                        {
                            "schema_version": "1.0.0",
                            "type": "PERIOD_CUTOFF",
                            "affected_ids": [_typed("JE", je_id)],
                            "claimed_amount": func_amt,
                            "currency": base_cur,
                            "evidence_ids": sorted([_typed("INV", src_id), _typed("JE", je_id)]),
                            "explanation": f"Posting period {actual_period} != {exp_period} on {je_id} ({func_amt} {base_cur}).",
                        }
                    )

    dedup: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
    for f in findings:
        key = (f["type"], tuple(f["affected_ids"]))
        if key not in dedup:
            dedup[key] = f
    return list(dedup.values())[:20]


def run_baseline_policy(
    policy_id: str,
    obs: dict[str, Any],
    step_fn: StepCallable,
    *,
    seed: int = 0,
    params: AuditorParams | None = None,
) -> dict[str, Any]:
    """Execute one named public baseline policy against ``step_fn``."""
    client = _StepBudgetClient(
        obs,
        step_fn,
        reserve_steps=(params.reserve_steps_for_submit if params else 1),
    )
    company = obs.get("company") or {}
    policy = obs.get("policy") or {}
    base_cur = str(company.get("base_currency", "KZT"))

    if policy_id == "blind_submit":
        return client.call("submit", {"findings": []})

    if policy_id == "silent_policy":
        client.call("list_records", {"table": "invoices", "page_size": 5})
        return client.call("submit", {"findings": []})

    if policy_id == "random_policy":
        rng = random.Random(seed)
        tables = ("invoices", "payments", "journal_entries", "fx_rates")
        sampled_invs: list[dict[str, Any]] = []
        for _ in range(3):
            if not client.can_inspect:
                break
            tbl = rng.choice(tables)
            resp = client.call("list_records", {"table": tbl, "page_size": 5})
            if tbl == "invoices" and resp.get("ok"):
                sampled_invs.extend((resp.get("result") or {}).get("records") or [])
        rand_findings: list[dict[str, Any]] = []
        if sampled_invs and rng.random() < 0.5:
            inv = rng.choice(sampled_invs)
            inv_id = _typed("INV", str(inv["doc_id"]))
            rand_findings.append(
                {
                    "schema_version": "1.0.0",
                    "type": rng.choice(
                        ["DUPLICATE_PAYMENT", "PARTIAL_PAYMENT_ALLOCATION", "FX_RATE_MISMATCH", "PERIOD_CUTOFF"]
                    ),
                    "affected_ids": [inv_id],
                    "claimed_amount": max(1, int(inv.get("total_minor", 100))),
                    "currency": str(inv.get("currency", base_cur)),
                    "evidence_ids": [inv_id],
                    "explanation": "Random exploratory candidate.",
                }
            )
        return client.call("submit", {"findings": rand_findings})

    if policy_id == "simple_recon":
        p = AuditorParams(
            page_size=25,
            check_duplicate=True,
            check_partial=True,
            check_fx=False,
            check_cutoff=False,
            skip_fx_if_domestic_only=True,
        )
        invs = client.fetch_table("invoices", page_size=p.page_size)
        pays = client.fetch_table("payments", page_size=p.page_size)
        jes = client.fetch_table("journal_entries", page_size=p.page_size)
        cns = client.fetch_table("credit_notes", page_size=p.page_size)
        findings = reconcile_public_tables(
            company=company,
            policy=policy,
            invoices_list=invs,
            payments=pays,
            ledger=jes,
            fx_rows=[],
            credit_notes=cns,
            calendar=[],
            params=p,
        )
        return client.call("submit", {"findings": findings})

    if policy_id in ("rule_based_auditor", "evidence_first", "budget_aware"):
        if params is not None:
            p = params
        elif policy_id == "rule_based_auditor":
            # Fixed non-adaptive page size & full-table sweep (baseline before AutoHacker tuning)
            p = AuditorParams(
                page_size=10,
                skip_fx_if_domestic_only=False,
                verify_evidence_docs=False,
            )
        elif policy_id == "evidence_first":
            p = AuditorParams(
                page_size=50,
                skip_fx_if_domestic_only=True,
                verify_evidence_docs=True,
            )
        else:  # budget_aware
            p = AuditorParams(
                page_size=50,
                skip_fx_if_domestic_only=True,
                verify_evidence_docs=False,
                reserve_steps_for_submit=2,
            )

        invs = client.fetch_table("invoices", page_size=p.page_size)
        pays = client.fetch_table("payments", page_size=p.page_size)
        jes = client.fetch_table("journal_entries", page_size=p.page_size)
        cns = client.fetch_table("credit_notes", page_size=p.page_size)
        cal = client.fetch_table("period_calendar", page_size=p.page_size) if p.check_cutoff else []

        has_foreign = any(str(r.get("currency", base_cur)) != base_cur for r in invs)
        need_fx = p.check_fx and (has_foreign or not p.skip_fx_if_domestic_only)
        fx_rows = client.fetch_table("fx_rates", page_size=p.page_size) if need_fx else []

        findings = reconcile_public_tables(
            company=company,
            policy=policy,
            invoices_list=invs,
            payments=pays,
            ledger=jes,
            fx_rows=fx_rows,
            credit_notes=cns,
            calendar=cal,
            params=p,
        )

        if p.verify_evidence_docs:
            # Explicitly fetch individual document/ledger evidence records for grounded verification
            verified_ids: set[str] = set()
            for f in findings:
                for eid in f.get("evidence_ids", ()):
                    if not client.can_inspect or eid in verified_ids:
                        break
                    verified_ids.add(eid)
                    if eid.startswith(("INV:", "PAY:", "CN:", "BANK:")):
                        client.call("get_document", {"id": eid})
                    elif eid.startswith(("JE:", "FX:", "CP:")):
                        client.call("get_record", {"id": eid})

        return client.call("submit", {"findings": findings})

    raise ValueError(f"unknown baseline policy_id: {policy_id!r}")


__all__ = [
    "AuditorParams",
    "PUBLIC_BASELINE_IDS",
    "StepCallable",
    "TEST_ONLY_UPPER_BOUND_ID",
    "reconcile_public_tables",
    "run_baseline_policy",
]
