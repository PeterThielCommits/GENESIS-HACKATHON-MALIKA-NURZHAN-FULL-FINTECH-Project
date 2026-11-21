"""Baseline Policy 2: Simple deterministic public-only reconciliation policy.

Uses ONLY the public observation, ``policy``, ``manifest``, and the 5 canonical
actions to page through public tables and run straightforward accounting checks
for all 4 documented anomaly classes:
  - ``DUPLICATE_PAYMENT``
  - ``PARTIAL_PAYMENT_ALLOCATION``
  - ``FX_RATE_MISMATCH``
  - ``PERIOD_CUTOFF``

Intentionally a clean, transparent baseline (not a mirror of ``verifier/`` and
never accesses private files or sealed data).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

from arena.policies.base import BasePolicy

_CURRENCY_EXPONENTS: dict[str, int] = {
    "KZT": 2,
    "USD": 2,
    "EUR": 2,
    "JPY": 0,
    "KWD": 3,
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
    exponents: dict[str, int],
) -> int:
    rate = Decimal(rate_str)
    src_exp = exponents.get(src_cur, 2)
    dst_exp = exponents.get(dst_cur, 2)
    shift = Decimal(10) ** (dst_exp - src_exp)
    if quote_convention == "foreign_per_functional":
        raw = (Decimal(amount_minor) / rate) * shift
    else:
        raw = Decimal(amount_minor) * rate * shift
    rounding = ROUND_HALF_UP if rounding_mode == "half_up" else ROUND_HALF_EVEN
    return int(raw.quantize(Decimal("1"), rounding=rounding))


class SimpleReconciliationPolicy(BasePolicy):
    """Pages through public tables and applies basic accounting reconciliation rules."""

    name = "simple_reconciliation"

    _FETCH_ORDER = (
        "invoices",
        "payments",
        "ledger",
        "fx",
        "credit_notes",
        "period_calendar",
    )

    def __init__(self, seed: int = 0) -> None:
        self._seed = int(seed)
        self._manifest: dict[str, Any] = {}
        self._policy: dict[str, Any] = {}
        self._tables: dict[str, list[dict[str, Any]]] = {}
        self._fetch_idx = 0
        self._next_cursor: str | None = None
        self._in_flight_table: str | None = None

    def reset(self, observation: dict[str, Any]) -> None:
        self._manifest = dict(observation.get("manifest") or {})
        self._policy = dict(observation.get("policy") or {})
        self._tables = {t: [] for t in self._FETCH_ORDER}
        self._fetch_idx = 0
        self._next_cursor = None
        self._in_flight_table = None

    def act(self, observation: dict[str, Any]) -> dict[str, Any]:
        # Ingest previous list_records response if any
        if self._in_flight_table is not None:
            res = observation.get("result")
            if isinstance(res, dict) and isinstance(res.get("records"), list):
                self._tables[self._in_flight_table].extend(res["records"])
                self._next_cursor = res.get("next_cursor")
                if self._next_cursor is None:
                    self._fetch_idx += 1
            else:
                self._next_cursor = None
                self._fetch_idx += 1
            self._in_flight_table = None

        remaining = int(observation.get("remaining_steps", 1))
        # Always reserve the last step for submit
        if self._fetch_idx < len(self._FETCH_ORDER) and remaining > 1:
            tbl = self._FETCH_ORDER[self._fetch_idx]
            self._in_flight_table = tbl
            return {
                "name": "list_records",
                "args": {"table": tbl, "cursor": self._next_cursor, "limit": 50},
            }

        findings = self._reconcile()
        return {"name": "submit", "args": {"findings": {"findings": findings[:30]}}}

    def _reconcile(self) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        invoices = {str(r["doc_id"]): r for r in self._tables["invoices"] if "doc_id" in r}
        payments = self._tables["payments"]
        ledger = self._tables["ledger"]
        fx_rows = self._tables["fx"]
        credit_notes = self._tables["credit_notes"]
        calendar = self._tables["period_calendar"]

        base_cur = str(self._manifest.get("base_currency", "KZT"))
        tz_name = str(self._manifest.get("timezone", "UTC"))
        rounding_mode = str(self._policy.get("rounding_mode", "half_even"))
        fx_pol = self._policy.get("fx_policy", {})
        cutoff_pol = self._policy.get("cutoff_policy", {})
        alloc_pol = self._policy.get("allocation_policy", {})
        allow_advances = bool(alloc_pol.get("allow_advances", False))

        exponents = dict(_CURRENCY_EXPONENTS)
        rr = self._manifest.get("rounding_rules", {})
        if isinstance(rr, dict) and isinstance(rr.get("minor_unit_exponents"), dict):
            for k, v in rr["minor_unit_exponents"].items():
                if isinstance(v, int):
                    exponents[str(k)] = v

        # Build helper indices
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
            if pay.get("payment_type") == "refund" or (isinstance(pay.get("amount_minor"), int) and pay["amount_minor"] < 0):
                rel = pay.get("related_payment_id")
                if isinstance(rel, str):
                    refunded_pay_ids.add(rel)

        # 1. Duplicate payments & 2. Partial/missing payment allocation
        allocs_by_inv: dict[str, list[tuple[dict[str, Any], int]]] = {}
        for pay in payments:
            pay_id = str(pay.get("pay_id", ""))
            if not pay_id or pay_id in refunded_pay_ids:
                continue
            pay_amt = pay.get("amount_minor")
            if type(pay_amt) is not int or pay_amt < 0:
                continue
            pay_cur = str(pay.get("currency", base_cur))
            allocs = pay.get("allocations", [])
            if not isinstance(allocs, list):
                allocs = []
            alloc_sum = sum(int(a.get("amount_minor", 0)) for a in allocs if isinstance(a, dict))

            # Over-allocated payment
            if alloc_sum > pay_amt:
                inv_ids = sorted({str(a["document_id"]) for a in allocs if isinstance(a, dict) and a.get("document_id")})
                aff = sorted([_typed("PAY", pay_id)] + [_typed("INV", i) for i in inv_ids])
                findings.append(
                    {
                        "type": "PARTIAL_PAYMENT_ALLOCATION",
                        "affected_ids": aff,
                        "claimed_amount_minor": alloc_sum - pay_amt,
                        "currency": pay_cur,
                        "evidence_ids": aff[:10],
                        "explanation": f"Payment {pay_id} allocations exceed payment amount by {alloc_sum - pay_amt}.",
                    }
                )
                continue

            # Missing allocation (unallocated payment when advances disallowed)
            if alloc_sum < pay_amt and not allow_advances:
                inv_ids = sorted({str(a["document_id"]) for a in allocs if isinstance(a, dict) and a.get("document_id")})
                aff = sorted([_typed("PAY", pay_id)] + [_typed("INV", i) for i in inv_ids])
                findings.append(
                    {
                        "type": "PARTIAL_PAYMENT_ALLOCATION",
                        "affected_ids": aff,
                        "claimed_amount_minor": pay_amt - alloc_sum,
                        "currency": pay_cur,
                        "evidence_ids": aff[:10],
                        "explanation": f"Payment {pay_id} has unallocated balance {pay_amt - alloc_sum} with advances disallowed.",
                    }
                )
                continue

            for a in allocs:
                if isinstance(a, dict) and a.get("document_id"):
                    allocs_by_inv.setdefault(str(a["document_id"]), []).append((pay, int(a.get("amount_minor", 0))))

        for inv_id, inv in invoices.items():
            inv_total = inv.get("total_minor")
            if type(inv_total) is not int:
                continue
            inv_cur = str(inv.get("currency", base_cur))
            entries = allocs_by_inv.get(inv_id, [])
            net_paid = sum(a for _, a in entries)
            cn_total = cn_by_inv.get(inv_id, 0)

            # Duplicate payment: multiple payments summing > invoice total after credit note offset
            if len(entries) >= 2 and net_paid - cn_total > inv_total:
                ordered = sorted(entries, key=lambda x: str(x[0].get("timestamp", "")))
                orig_pay = ordered[0][0]
                dup_pay = ordered[-1][0]
                dup_pid = str(dup_pay["pay_id"])
                orig_pid = str(orig_pay["pay_id"])
                dup_jes = je_by_src.get(dup_pid, [])
                if dup_jes:
                    dup_je_id = str(dup_jes[0]["je_id"])
                    aff = sorted([_typed("JE", dup_je_id), _typed("PAY", dup_pid)])
                    ev = sorted([_typed("INV", inv_id), _typed("JE", dup_je_id), _typed("PAY", orig_pid), _typed("PAY", dup_pid)])
                    findings.append(
                        {
                            "type": "DUPLICATE_PAYMENT",
                            "affected_ids": aff,
                            "claimed_amount_minor": int(dup_pay["amount_minor"]),
                            "currency": inv_cur,
                            "evidence_ids": ev[:10],
                            "explanation": f"Duplicate payment {dup_pid} settles already-paid invoice {inv_id}.",
                        }
                    )
            # Premature paid status with partial payment
            elif inv.get("status") == "paid" and len(entries) == 1 and (net_paid + cn_total) < inv_total:
                pay = entries[0][0]
                pid = str(pay["pay_id"])
                shortfall = inv_total - (net_paid + cn_total)
                aff = sorted([_typed("INV", inv_id), _typed("PAY", pid)])
                findings.append(
                    {
                        "type": "PARTIAL_PAYMENT_ALLOCATION",
                        "affected_ids": aff,
                        "claimed_amount_minor": shortfall,
                        "currency": inv_cur,
                        "evidence_ids": aff[:10],
                        "explanation": f"Invoice {inv_id} marked paid despite shortfall {shortfall}.",
                    }
                )

        # 3. FX rate mismatch & 4. Period cutoff on invoice recognition JEs
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
            lines = je.get("lines", [])
            if not isinstance(lines, list) or not lines:
                continue

            # Check FX mismatch for foreign invoices
            inv_cur = str(inv.get("currency", base_cur))
            if inv_cur != base_cur:
                expected_pair = f"{inv_cur}/{base_cur}" if quote_conv == "functional_per_foreign" else f"{base_cur}/{inv_cur}"
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
                        best_fx = [r for d, r in cands if d == latest][0]
                        src_amt = sum(int(ln.get("debit_minor", 0)) for ln in lines if isinstance(ln, dict))
                        actual_func = sum(int(ln.get("functional_debit_minor", 0)) for ln in lines if isinstance(ln, dict))
                        expected_func = _convert_amount(
                            src_amt, inv_cur, base_cur, str(best_fx["rate_decimal"]), rounding_mode, quote_conv, exponents
                        )
                        if actual_func != expected_func:
                            ev_list = (
                                sorted([_typed("FX", str(best_fx["fx_id"])), _typed("JE", je_id)])
                                if rate_date_rule == "operation_date"
                                else sorted([_typed("FX", str(best_fx["fx_id"])), _typed("INV", src_id), _typed("JE", je_id)])
                            )
                            findings.append(
                                {
                                    "type": "FX_RATE_MISMATCH",
                                    "affected_ids": [_typed("JE", je_id)],
                                    "claimed_amount_minor": abs(actual_func - expected_func),
                                    "currency": base_cur,
                                    "evidence_ids": ev_list[:10],
                                    "explanation": f"JE {je_id} functional amount {actual_func} differs from policy FX conversion {expected_func}.",
                                }
                            )

            # Check period cutoff (skip prepayments & pro-rata spans)
            is_prepay = any(
                isinstance(ln, dict) and (ln.get("account_id") == "1410" or ln.get("analytic_tag") == "prepayment")
                for ln in lines
            )
            if not is_prepay and inv.get("service_end") is None:
                ev_ts = inv.get("issue_timestamp") if rec_event == "issue_date" else inv.get("service_start")
                ev_date = _parse_local_date(str(ev_ts or ""), tz_name)
                if ev_date is not None and calendar:
                    exp_period = _period_for_date(ev_date, calendar)
                    actual_period = str(je.get("posting_period", ""))
                    if exp_period and actual_period and exp_period != actual_period:
                        func_amt = sum(int(ln.get("functional_debit_minor", 0)) for ln in lines if isinstance(ln, dict))
                        findings.append(
                            {
                                "type": "PERIOD_CUTOFF",
                                "affected_ids": [_typed("JE", je_id)],
                                "claimed_amount_minor": func_amt,
                                "currency": base_cur,
                                "evidence_ids": sorted([_typed("INV", src_id), _typed("JE", je_id)]),
                                "explanation": f"JE {je_id} posted to {actual_period} instead of policy period {exp_period}.",
                            }
                        )

        return findings


__all__ = ["SimpleReconciliationPolicy"]
