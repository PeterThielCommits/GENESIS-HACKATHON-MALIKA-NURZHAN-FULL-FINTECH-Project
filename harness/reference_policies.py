"""Reference and adversarial policy subprocesses speaking JSONL v1.0 (Phase 9).

Used by:
- ``harness/replay.py`` deterministic verification suite
- ``tests/harness/`` and ``tests/security/`` isolation & lifecycle tests

Policies included:
- ``silent_v1``: queries company summary via ``list_records`` and submits ``[]``.
- ``rule_auditor_v1``: deterministic public-only auditor paging public tables over
  JSONL v1.0 and reconciling duplicate payments, partial allocations, FX mismatches,
  and period cutoffs using integer/Decimal arithmetic (zero ``verifier`` imports).
- ``truncate_exhaust_v1``: deliberately consumes step budget without calling ``submit``
  to test deterministic ``truncated=True`` + ``no_submit=True`` handling.
- ``malicious_probe_v1``: adversarial policy that attempts to probe ``os.environ``,
  current directory, parent directories, ``sealed/truth.json``, path traversal in
  tool args, and unsafe ``calc`` expressions, then reports whether every probe was
  blocked via ``submit`` (used in security non-leakage tests).

Zone 2 rule: imports ONLY ``contracts`` and Python 3.11 stdlib.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from contracts.canonical import canonical_json

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


class _JsonlClient:
    def __init__(self) -> None:
        self._req_counter = 0

    def read_frame(self) -> dict[str, Any] | None:
        raw = sys.stdin.readline()
        if raw == "":
            return None
        return json.loads(raw)

    def call_tool(self, tool: str, args: dict[str, Any], *, req_id: str | None = None) -> dict[str, Any]:
        self._req_counter += 1
        rid = req_id or f"req_{self._req_counter:04d}"
        line = canonical_json(
            {
                "protocol_version": "1.0",
                "request_id": rid,
                "action": {"tool": tool, "args": args},
            }
        )
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
        frame = self.read_frame()
        if frame is None:
            raise SystemExit(0)
        if frame.get("type") == "terminate":
            raise SystemExit(0)
        return frame.get("response", {})

    def fetch_all(self, table: str, *, page_size: int = 50) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            args: dict[str, Any] = {"table": table, "page_size": page_size}
            if cursor is not None:
                args["cursor"] = cursor
            resp = self.call_tool("list_records", args)
            if not resp.get("ok"):
                break
            result = resp.get("result", {})
            batch = result.get("records", [])
            rows.extend(batch)
            cursor = result.get("next_cursor")
            if not cursor:
                break
        return rows


def _run_silent_policy(client: _JsonlClient) -> int:
    first = client.read_frame()
    if not first or first.get("type") != "reset":
        return 1
    client.call_tool("list_records", {"table": "invoices", "page_size": 10})
    client.call_tool("calc", {"expression": "1 + 1"})
    client.call_tool("submit", {"findings": []})
    _ = client.read_frame()
    return 0


def _run_truncate_policy(client: _JsonlClient) -> int:
    first = client.read_frame()
    if not first or first.get("type") != "reset":
        return 1
    for _ in range(500):
        resp = client.call_tool("calc", {"expression": "2 + 2"})
        if not resp.get("ok"):
            break
    return 0


def _run_rule_auditor_policy(client: _JsonlClient) -> int:
    first = client.read_frame()
    if not first or first.get("type") != "reset":
        return 1
    obs = first.get("observation", {})
    company = obs.get("company") or {}
    policy = obs.get("policy") or {}

    base_cur = str(company.get("base_currency", "KZT"))
    tz_name = str(company.get("timezone", "UTC"))
    rounding_mode = str(policy.get("rounding_mode", "half_even"))
    fx_pol = policy.get("fx_policy") or {}
    cutoff_pol = policy.get("cutoff_policy") or {}
    alloc_pol = policy.get("allocation_policy") or {}
    allow_advances = bool(alloc_pol.get("allow_advances", False))
    exponents = dict(_CURRENCY_EXPONENTS)

    invoices_list = client.fetch_all("invoices")
    payments = client.fetch_all("payments")
    ledger = client.fetch_all("journal_entries")
    fx_rows = client.fetch_all("fx_rates")
    credit_notes = client.fetch_all("credit_notes")
    calendar = client.fetch_all("period_calendar")

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
        allocs = pay.get("allocations", [])
        if not isinstance(allocs, list):
            allocs = []
        alloc_sum = sum(int(a.get("amount_minor", 0)) for a in allocs if isinstance(a, dict))

        if alloc_sum > pay_amt:
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
                    "explanation": f"Payment {pay_id} allocations exceed payment amount.",
                }
            )
            continue

        if alloc_sum < pay_amt and not allow_advances:
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
                    "explanation": f"Payment {pay_id} has unallocated balance with advances disallowed.",
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
                        "explanation": f"Duplicate payment {dup_pid} settles already-paid invoice {inv_id}.",
                    }
                )
        elif inv.get("status") == "paid" and len(entries) == 1 and (net_paid + cn_total) < inv_total:
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
                    "explanation": f"Invoice {inv_id} marked paid despite shortfall {shortfall}.",
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
        lines = je.get("lines", [])
        if not isinstance(lines, list) or not lines:
            continue

        inv_cur = str(inv.get("currency", base_cur))
        if inv_cur != base_cur:
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
                    best_fx = [r for d, r in cands if d == latest][0]
                    src_amt = sum(int(ln.get("debit_minor", 0)) for ln in lines if isinstance(ln, dict))
                    actual_func = sum(
                        int(ln.get("functional_debit_minor", 0)) for ln in lines if isinstance(ln, dict)
                    )
                    expected_func = _convert_amount(
                        src_amt,
                        inv_cur,
                        base_cur,
                        str(best_fx["rate_decimal"]),
                        rounding_mode,
                        quote_conv,
                        exponents,
                    )
                    if actual_func != expected_func:
                        ev_list = (
                            sorted([_typed("FX", str(best_fx["fx_id"])), _typed("JE", je_id)])
                            if rate_date_rule == "operation_date"
                            else sorted(
                                [
                                    _typed("FX", str(best_fx["fx_id"])),
                                    _typed("INV", src_id),
                                    _typed("JE", je_id),
                                ]
                            )
                        )
                        findings.append(
                            {
                                "schema_version": "1.0.0",
                                "type": "FX_RATE_MISMATCH",
                                "affected_ids": [_typed("JE", je_id)],
                                "claimed_amount": abs(actual_func - expected_func),
                                "currency": base_cur,
                                "evidence_ids": ev_list[:10],
                                "explanation": f"JE {je_id} functional amount differs from policy FX rate.",
                            }
                        )

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
                    func_amt = sum(
                        int(ln.get("functional_debit_minor", 0)) for ln in lines if isinstance(ln, dict)
                    )
                    findings.append(
                        {
                            "schema_version": "1.0.0",
                            "type": "PERIOD_CUTOFF",
                            "affected_ids": [_typed("JE", je_id)],
                            "claimed_amount": func_amt,
                            "currency": base_cur,
                            "evidence_ids": sorted([_typed("INV", src_id), _typed("JE", je_id)]),
                            "explanation": f"JE {je_id} posted to {actual_period} instead of {exp_period}.",
                        }
                    )

    findings.sort(key=lambda f: (f["type"], f["affected_ids"]))
    client.call_tool("submit", {"findings": findings[:20]})
    _ = client.read_frame()
    return 0


def _run_malicious_probe_policy(client: _JsonlClient) -> int:
    first = client.read_frame()
    if not first or first.get("type") != "reset":
        return 1

    cwd = Path.cwd()
    cwd_entries = sorted(p.name for p in cwd.iterdir())

    cwd_writable = False
    try:
        (cwd / "escape_attempt.txt").write_text("x", encoding="utf-8")
        cwd_writable = True
    except OSError:
        cwd_writable = False

    leaked_env_keys = sorted(
        k
        for k in os.environ
        if any(tok in k.upper() for tok in ("SECRET", "TOKEN", "SALT", "CANARY", "SEED", "TRUTH"))
    )

    sealed_found = False
    for probe_rel in (
        "sealed/truth.json",
        "../sealed/truth.json",
        "../../sealed/truth.json",
        "truth.json",
        "provenance.json",
    ):
        try:
            if (cwd / probe_rel).exists():
                sealed_found = True
        except OSError:
            pass

    r_trav = client.call_tool("get_document", {"id": "INV:../../manifest.json"})
    r_calc = client.call_tool("calc", {"expression": "__import__('os').listdir('.')"})

    traversal_blocked = not bool(r_trav.get("ok"))
    calc_inject_blocked = not bool(r_calc.get("ok"))

    status_tag = (
        f"cwd_empty={len(cwd_entries) == 0};"
        f"cwd_writable={cwd_writable};"
        f"env_leaks={len(leaked_env_keys)};"
        f"sealed_found={sealed_found};"
        f"trav_blocked={traversal_blocked};"
        f"calc_blocked={calc_inject_blocked}"
    )

    client.call_tool("submit", {"findings": []}, req_id=status_tag[:120])
    _ = client.read_frame()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m harness.reference_policies")
    parser.add_argument(
        "--policy",
        choices=["silent_v1", "rule_auditor_v1", "truncate_exhaust_v1", "malicious_probe_v1"],
        required=True,
    )
    args = parser.parse_args(argv)

    client = _JsonlClient()
    if args.policy == "silent_v1":
        return _run_silent_policy(client)
    if args.policy == "rule_auditor_v1":
        return _run_rule_auditor_policy(client)
    if args.policy == "truncate_exhaust_v1":
        return _run_truncate_policy(client)
    if args.policy == "malicious_probe_v1":
        return _run_malicious_probe_policy(client)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
