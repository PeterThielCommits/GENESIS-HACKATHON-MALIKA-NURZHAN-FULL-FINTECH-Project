"""Independent FX-rate and period-cutoff discovery (spec §3.3–§3.4)."""

from __future__ import annotations

from itertools import product
from typing import Any

from independent_verifier.algos import RawFinding
from independent_verifier.money import convert_minor, currency_exponents
from independent_verifier.time_rules import (
    fiscal_period,
    local_date,
    parse_date,
)
import re

_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _to_local_date(value, timezone):
    """Bare ISO date -> itself; timestamp -> company-local calendar date."""
    text = str(value).strip()
    if _DATE_ONLY.match(text):
        return parse_date(text)
    return local_date(text, timezone)

PREPAYMENT_ACCOUNT_TYPES = frozenset({"prepayment", "advance", "deferred_revenue", "deferred_expense"})
PREPAYMENT_ANALYTIC_TAGS = frozenset({"prepayment", "advance", "deferred"})


def _cns_by_id(data) -> dict[str, dict[str, Any]]:
    return {str(cn.get("credit_note_id")): cn for cn in data.credit_notes}


def _invoices_by_id(data) -> dict[str, dict[str, Any]]:
    return {str(inv.get("doc_id")): inv for inv in data.invoices}


def _payments_by_id(data) -> dict[str, dict[str, Any]]:
    return {str(p.get("pay_id")): p for p in data.payments}


def _invoice_issue_ts(inv: dict[str, Any]) -> str | None:
    return inv.get("issue_timestamp")


def _resolve_document_date(je, invoices, cns, payments, timezone):
    src = je.get("source_document_id")
    if not src:
        return None, None, f"JE:{je.get('je_id')}:no source document for document_date rule"
    inv = invoices.get(src)
    if inv is not None:
        ts = _invoice_issue_ts(inv)
        if ts:
            return local_date(ts, timezone), f"INV:{inv['doc_id']}", None
        return None, None, f"JE:{je.get('je_id')}:linked invoice lacks issue_timestamp"
    cn = cns.get(src)
    if cn is not None:
        ts = cn.get("timestamp")
        if ts:
            return local_date(ts, timezone), f"CN:{cn['credit_note_id']}", None
        return None, None, f"JE:{je.get('je_id')}:linked credit note lacks timestamp"
    pay = payments.get(src)
    if pay is not None:
        alloc_doc_ids = []
        for a in pay.get("allocations", []):
            d = a.get("document_id")
            if d and d not in alloc_doc_ids:
                alloc_doc_ids.append(d)
        issue_dates = []
        for d in alloc_doc_ids:
            inv = invoices.get(d)
            if inv and _invoice_issue_ts(inv):
                issue_dates.append((d, local_date(_invoice_issue_ts(inv), timezone)))
        if len({d for _, d in issue_dates}) > 1:
            distinct = {dt for _, dt in issue_dates}
            if len(distinct) > 1:
                return None, None, f"JE:{je.get('je_id')}:payment allocates to invoices with different issue dates"
        if issue_dates:
            d, dt = issue_dates[0]
            return dt, f"INV:{d}", None
        return None, None, f"JE:{je.get('je_id')}:payment has no dated invoice allocation"
    return None, None, f"JE:{je.get('je_id')}:source document {src!r} not found"


def _resolve_payment_date(je, invoices, payments, timezone):
    src = je.get("source_document_id")
    if not src:
        return None, None, f"JE:{je.get('je_id')}:no source document for payment_date rule"
    pay = payments.get(src)
    if pay is not None and pay.get("timestamp"):
        return local_date(pay["timestamp"], timezone), f"PAY:{pay['pay_id']}", None
    inv = invoices.get(src)
    if inv is not None:
        linked = []
        for p in payments.values():
            for a in p.get("allocations", []):
                if a.get("document_id") == inv.get("doc_id"):
                    linked.append(p)
                    break
        dated = [p for p in linked if p.get("timestamp")]
        if len(dated) == 1:
            return local_date(dated[0]["timestamp"], timezone), f"PAY:{dated[0]['pay_id']}", None
        if len(dated) > 1:
            distinct = {local_date(p["timestamp"], timezone) for p in dated}
            if len(distinct) > 1:
                return None, None, f"JE:{je.get('je_id')}:invoice has payments with different dates"
            p = dated[0]
            return local_date(p["timestamp"], timezone), f"PAY:{p['pay_id']}", None
        return None, None, f"JE:{je.get('je_id')}:invoice has no linked payment"
    return None, None, f"JE:{je.get('je_id')}:source document {src!r} not found"


def _select_permitted_quotes(rows, source_codes, fallback_rule, target_iso):
    permitted = [r for r in rows if r.get("source_code") in source_codes]
    if fallback_rule == "none":
        selected = [r for r in permitted if r.get("effective_date") == target_iso]
        return selected, target_iso
    prior = [r for r in permitted if str(r.get("effective_date") or "") <= target_iso]
    if not prior:
        return [], target_iso
    max_date = max(str(r.get("effective_date")) for r in prior)
    return [r for r in prior if str(r.get("effective_date")) == max_date], max_date


def discover_fx_rate_mismatch(data) -> tuple[list[RawFinding], list[str]]:
    functional = data.company.get("functional_currency")
    timezone = data.company.get("timezone")
    fxp = data.policy.get("fx_policy", {})
    rmode = data.policy.get("rounding_mode", "half_even")
    source_codes = fxp.get("source_codes", [])
    fallback_rule = fxp.get("fallback_rule", "last_available")
    rate_rule = fxp.get("rate_date_rule", "document_date")
    exp_map = currency_exponents()
    invoices = _invoices_by_id(data)
    cns = _cns_by_id(data)
    payments = _payments_by_id(data)
    findings: list[RawFinding] = []
    ambiguities: list[str] = []

    for je in data.journal_entries:
        foreign_lines = [ln for ln in je.get("lines", []) if ln.get("currency") != functional]
        if not foreign_lines:
            continue
        currencies = sorted({ln.get("currency") for ln in foreign_lines})
        if rate_rule == "operation_date":
            try:
                target = local_date(je.get("timestamp", ""), timezone)
                date_source_id = None
                resolve_error = None
            except (ValueError, TypeError):
                target, date_source_id, resolve_error = None, None, f"JE:{je.get('je_id')}:unparseable timestamp"
        elif rate_rule == "document_date":
            target, date_source_id, resolve_error = _resolve_document_date(je, invoices, cns, payments, timezone)
        elif rate_rule == "payment_date":
            target, date_source_id, resolve_error = _resolve_payment_date(je, invoices, payments, timezone)
        else:
            target, date_source_id, resolve_error = None, None, f"JE:{je.get('je_id')}:unknown rate_date_rule {rate_rule!r}"
        if resolve_error or target is None:
            ambiguities.append(resolve_error or f"JE:{je.get('je_id')}:unresolvable rate date")
            continue
        target_iso = target.isoformat()

        quotes_by_currency: dict[str, list[dict[str, Any]]] = {}
        failed = False
        for F in currencies:
            rows = [
                r
                for r in data.fx_rates
                if r.get("pair") in (f"{F}/{functional}", f"{functional}/{F}")
            ]
            selected, _ = _select_permitted_quotes(rows, source_codes, fallback_rule, target_iso)
            if not selected:
                ambiguities.append(
                    f"JE:{je.get('je_id')}:no permitted {F}/{functional} quote for {target_iso} (rule {rate_rule})"
                )
                failed = True
                continue
            quotes_by_currency[F] = selected
        if failed:
            continue

        # Expected functional amounts per currency under EACH permitted quote;
        # if quotes disagree the verifier must not guess (REQ-VER-005).
        conflict = False
        expected_debit = 0
        expected_credit = 0
        for F in currencies:
            variants: list[tuple[int, int]] = []
            for quote in quotes_by_currency[F]:
                debit = sum(
                    convert_minor(
                        int(ln.get("debit_minor", 0)),
                        str(quote.get("rate_decimal")),
                        str(quote.get("pair")),
                        F,
                        functional,
                        rmode,
                        exp_map,
                    )
                    for ln in foreign_lines
                    if ln.get("currency") == F and int(ln.get("debit_minor", 0)) > 0
                )
                credit = sum(
                    convert_minor(
                        int(ln.get("credit_minor", 0)),
                        str(quote.get("rate_decimal")),
                        str(quote.get("pair")),
                        F,
                        functional,
                        rmode,
                        exp_map,
                    )
                    for ln in foreign_lines
                    if ln.get("currency") == F and int(ln.get("credit_minor", 0)) > 0
                )
                variants.append((debit, credit))
            if len(set(variants)) > 1:
                ambiguities.append(
                    f"JE:{je.get('je_id')}:permitted {F}/{functional} quotes yield different expected amounts"
                )
                conflict = True
                continue
            expected_debit += variants[0][0]
            expected_credit += variants[0][1]
        if conflict:
            continue

        booked_debit = sum(int(ln.get("functional_debit_minor", 0)) for ln in foreign_lines)
        booked_credit = sum(int(ln.get("functional_credit_minor", 0)) for ln in foreign_lines)
        misstatement = max(abs(booked_debit - expected_debit), abs(booked_credit - expected_credit))
        if misstatement == 0:
            continue

        affected = [f"JE:{je['je_id']}"]
        seeds: list[list[str]] = []
        per_currency_quote_lists = [quotes_by_currency[F] for F in currencies]
        for combo in product(*per_currency_quote_lists):
            seed = [*affected, *(f"FX:{q.get('fx_id') or q.get('rate_id') or (q.get('pair') + '/' + str(q.get('effective_date')) + '/' + str(q.get('source_code')))}" for q in combo)]
            if date_source_id:
                seed.append(date_source_id)
            seeds.append(sorted(set(seed)))
        findings.append(
            RawFinding(
                type="FX_RATE_MISMATCH",
                affected_ids=affected,
                claimed_amount_minor=int(misstatement),
                currency=str(functional),
                evidence_candidates=seeds,
                explanation_code="V-FX-RATE",
                rule_id="V-FX-03",
                basis_ids=affected,
            )
        )
    return findings, ambiguities


def discover_period_cutoff(data) -> tuple[list[RawFinding], list[str]]:
    functional = data.company.get("functional_currency")
    timezone = data.company.get("timezone")
    fiscal_year_start = parse_date(data.company.get("fiscal_year_start", "2025-01-01"))
    rule = data.company.get("fiscal_period_rule", "monthly")
    recognition_event = data.policy.get("cutoff_policy", {}).get("recognition_event", "service_date")
    invoices = _invoices_by_id(data)
    accounts_by_id = {str(a.get("account_id")): a for a in data.accounts}
    period_calendar = data.period_calendar
    findings: list[RawFinding] = []
    ambiguities: list[str] = []

    for je in data.journal_entries:
        src = je.get("source_document_id")
        inv = invoices.get(src) if src else None
        if inv is None:
            continue  # not an invoice-recognition entry
        credit_lines = [ln for ln in je.get("lines", []) if int(ln.get("credit_minor", 0)) > 0]
        if credit_lines and all(
            (accounts_by_id.get(str(ln.get("account_id")), {}).get("account_type") in PREPAYMENT_ACCOUNT_TYPES)
            or (ln.get("analytic_tag") in PREPAYMENT_ANALYTIC_TAGS)
            for ln in credit_lines
        ):
            continue  # D-CUT-02: deliberate prepayment, excluded
        def _period_of(ts):
            try:
                return fiscal_period(_to_local_date(ts, timezone), fiscal_year_start, rule, period_calendar)
            except (ValueError, TypeError):
                return None

        service_start = inv.get("service_start")
        service_end = inv.get("service_end")
        recognition_rule = inv.get("recognition_rule")
        if service_end:
            p_start = _period_of(service_start) if service_start else None
            p_end = _period_of(service_end)
            if p_start and p_end and p_start != p_end:
                if recognition_rule == "pro_rata" and p_start <= str(je.get("posting_period")) <= p_end:
                    continue  # D-CUT-03: pro-rata interval recognition
                if recognition_rule == "service_end" and str(je.get("posting_period")) == p_end:
                    continue  # D-CUT-03: completion recognition

        event_ts = None
        if recognition_event == "service_date":
            if recognition_rule == "service_end":
                event_ts = service_end or service_start
            else:
                event_ts = service_start
        elif recognition_event == "issue_date":
            event_ts = inv.get("issue_timestamp")
        elif recognition_event == "delivery_date":
            event_ts = inv.get("delivery_timestamp") or service_end
        if not event_ts:
            ambiguities.append(
                f"JE:{je.get('je_id')}:recognition event {recognition_event!r} unavailable"
            )
            continue
        try:
            expected = fiscal_period(
                _to_local_date(event_ts, timezone), fiscal_year_start, rule, period_calendar
            )
        except (ValueError, TypeError):
            ambiguities.append(f"JE:{je.get('je_id')}:unparseable recognition event")
            continue
        if str(je.get("posting_period")) == expected:
            continue
        claimed = sum(int(ln.get("functional_debit_minor", 0)) for ln in je.get("lines", []))
        affected = [f"JE:{je['je_id']}"]
        seed = sorted([f"INV:{inv['doc_id']}", f"JE:{je['je_id']}"])
        findings.append(
            RawFinding(
                type="PERIOD_CUTOFF",
                affected_ids=affected,
                claimed_amount_minor=int(claimed),
                currency=str(functional),
                evidence_candidates=[seed],
                explanation_code="V-PERIOD-CUTOFF",
                rule_id="V-CUT-03",
                basis_ids=affected,
            )
        )
    return findings, ambiguities
