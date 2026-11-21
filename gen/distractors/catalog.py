"""Clean distractor generator covering all 16 minimum classes (TZ 11.6).

Every distractor injected here is a LEGITIMATE accounting scenario that MUST:
  - pass all clean invariants;
  - produce ZERO ground-truth anomalies;
  - use the same stateless anti-shortcut IDs as regular transactions.
"""

from __future__ import annotations

import random
from datetime import date, datetime
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from contracts.currency import exponent_of
from core.time_rules import fiscal_period
from gen.core.clean_twin import (
    CleanTwin,
    convert_with_convention,
    make_balanced_je,
    select_permitted_fx,
)

ALL_16_DISTRACTORS: tuple[str, ...] = (
    "D-DUP-01",
    "D-DUP-02",
    "D-DUP-03",
    "D-DUP-04",
    "D-PART-01",
    "D-PART-02",
    "D-PART-03",
    "D-PART-04",
    "D-FX-01",
    "D-FX-02",
    "D-FX-03",
    "D-FX-04",
    "D-CUT-01",
    "D-CUT-02",
    "D-CUT-03",
    "D-CUT-04",
)


def _iso(d: date, h: int, m: int, tz_name: str) -> str:
    return datetime(d.year, d.month, d.day, h, m, 0, tzinfo=ZoneInfo(tz_name)).isoformat()


def _add_inv_and_je(
    twin: CleanTwin,
    tag: str,
    cp_id: str,
    total_minor: int,
    currency: str,
    svc_ts: str,
    iss_ts: str,
    status: str = "paid",
    service_end: str | None = None,
    extra: dict[str, Any] | None = None,
    fx_rate: str = "1",
    func_minor: int | None = None,
    debit_acc: str = "5010",
    credit_acc: str = "2010",
    analytic_tag: str | None = None,
    posting_period_override: str | None = None,
) -> str:
    inv_id = twin.next_id("INV", f"d_inv:{tag}")
    inv: dict[str, Any] = {
        "doc_id": inv_id,
        "counterparty_id": cp_id,
        "issue_timestamp": iss_ts,
        "service_start": svc_ts,
        "service_end": service_end,
        "due_timestamp": _iso(date(2025, 5, 15), 18, 0, twin.company["timezone"]),
        "currency": currency,
        "total_minor": total_minor,
        "tax_minor": 0,
        "line_items": [{"description": "Standard service delivery", "amount_minor": total_minor}],
        "status": status,
    }
    if extra:
        inv.update(extra)
    twin.invoices.append(inv)
    events = {"service_date": svc_ts, "delivery_date": svc_ts, "issue_date": iss_ts}
    pp = posting_period_override or fiscal_period(events, twin.policy, twin.company)
    je_id = twin.next_id("JE", f"d_je:{tag}")
    famt = total_minor if func_minor is None else func_minor
    twin.journal_entries.append(
        make_balanced_je(
            je_id=je_id,
            timestamp=iss_ts,
            posting_period=pp,
            source_document_id=inv_id,
            description=f"Book invoice {inv_id}",
            debit_account=debit_acc,
            credit_account=credit_acc,
            amount_minor=total_minor,
            currency=currency,
            fx_rate_decimal=fx_rate,
            functional_amount_minor=famt,
            counterparty_id=cp_id,
            analytic_tag=analytic_tag,
        )
    )
    return inv_id


def _add_payment(
    twin: CleanTwin,
    tag: str,
    cp_id: str,
    amount_minor: int,
    currency: str,
    ts: str,
    allocs: list[tuple[str, int]],
    extra: dict[str, Any] | None = None,
) -> str:
    pay_id = twin.next_id("PAY", f"d_pay:{tag}")
    bank_id = twin.next_id("BANK", f"d_bank:{tag}")
    pay: dict[str, Any] = {
        "pay_id": pay_id,
        "timestamp": ts,
        "counterparty_id": cp_id,
        "currency": currency,
        "amount_minor": amount_minor,
        "allocations": [
            {
                "allocation_id": twin.next_id("AL", f"d_al:{tag}:{i}"),
                "document_id": doc_id,
                "amount_minor": a_amt,
                "allocation_timestamp": ts,
            }
            for i, (doc_id, a_amt) in enumerate(allocs)
        ],
        "bank_reference": bank_id,
        "payment_channel": "wire",
    }
    if extra:
        pay.update(extra)
    twin.payments.append(pay)
    twin.bank_lines.append(
        {
            "bank_line_id": bank_id,
            "timestamp": ts,
            "amount_minor": abs(amount_minor),
            "currency": currency,
            "direction": "inbound" if amount_minor < 0 else "outbound",
            "counterparty_text": cp_id,
            "reference_text": f"Ref {pay_id}",
        }
    )
    return pay_id


def apply_clean_distractors(
    twin: CleanTwin,
    distractor_classes: Sequence[str],
    rng: random.Random,
) -> None:
    """Weave clean distractors into ``twin`` in-place and log them privately."""
    tz = twin.company["timezone"]
    cur = twin.company["functional_currency"]
    unit = 10 ** exponent_of(cur)
    cp_id = twin.counterparties[0]["counterparty_id"]
    foreign_candidates = [c for c in twin.company["supported_currencies"] if c != cur]
    fcur = foreign_candidates[0] if foreign_candidates else None

    for idx, cls in enumerate(distractor_classes):
        tag = f"{cls}:{idx}"
        if cls == "D-DUP-01":
            amt = 450 * unit
            inv_id = _add_inv_and_je(twin, tag, cp_id, amt, cur, _iso(date(2025, 4, 2), 9, 0, tz), _iso(date(2025, 4, 2), 10, 0, tz))
            _add_payment(twin, f"{tag}:p1", cp_id, amt, cur, _iso(date(2025, 4, 4), 10, 0, tz), [(inv_id, amt)])
            _add_payment(twin, f"{tag}:p2", cp_id, amt, cur, _iso(date(2025, 4, 5), 10, 0, tz), [(inv_id, amt)])
            cn_id = twin.next_id("CN", f"d_cn:{tag}")
            twin.credit_notes.append(
                {
                    "credit_note_id": cn_id,
                    "invoice_id": inv_id,
                    "counterparty_id": cp_id,
                    "timestamp": _iso(date(2025, 4, 6), 10, 0, tz),
                    "amount_minor": amt,
                    "currency": cur,
                    "reason_code": "overpayment_credit",
                }
            )
            twin.distractor_log.append({"class": cls, "ids": [f"INV:{inv_id}", f"CN:{cn_id}"]})

        elif cls == "D-DUP-02":
            amt = 380 * unit
            inv_a = _add_inv_and_je(twin, f"{tag}:a", cp_id, amt, cur, _iso(date(2025, 4, 3), 9, 0, tz), _iso(date(2025, 4, 3), 10, 0, tz))
            inv_b = _add_inv_and_je(twin, f"{tag}:b", cp_id, amt, cur, _iso(date(2025, 4, 3), 11, 0, tz), _iso(date(2025, 4, 3), 12, 0, tz))
            _add_payment(twin, f"{tag}:pa", cp_id, amt, cur, _iso(date(2025, 4, 5), 10, 0, tz), [(inv_a, amt)])
            _add_payment(twin, f"{tag}:pb", cp_id, amt, cur, _iso(date(2025, 4, 5), 11, 0, tz), [(inv_b, amt)])
            twin.distractor_log.append({"class": cls, "ids": [f"INV:{inv_a}", f"INV:{inv_b}"]})

        elif cls == "D-DUP-03":
            amt = 250 * unit
            inv_m = _add_inv_and_je(
                twin, f"{tag}:m", cp_id, amt, cur, _iso(date(2025, 3, 1), 9, 0, tz), _iso(date(2025, 3, 2), 10, 0, tz),
                service_end="2025-03-31", extra={"subscription_period": "2025-03"},
            )
            inv_a = _add_inv_and_je(
                twin, f"{tag}:a", cp_id, amt, cur, _iso(date(2025, 4, 1), 9, 0, tz), _iso(date(2025, 4, 2), 10, 0, tz),
                service_end="2025-04-30", extra={"subscription_period": "2025-04"},
            )
            _add_payment(twin, f"{tag}:pm", cp_id, amt, cur, _iso(date(2025, 3, 5), 10, 0, tz), [(inv_m, amt)])
            _add_payment(twin, f"{tag}:pa", cp_id, amt, cur, _iso(date(2025, 4, 5), 10, 0, tz), [(inv_a, amt)])
            twin.distractor_log.append({"class": cls, "ids": [f"INV:{inv_m}", f"INV:{inv_a}"]})

        elif cls == "D-DUP-04":
            amt = 510 * unit
            inv_id = _add_inv_and_je(twin, tag, cp_id, amt, cur, _iso(date(2025, 4, 4), 9, 0, tz), _iso(date(2025, 4, 4), 10, 0, tz))
            _add_payment(twin, f"{tag}:p1", cp_id, amt, cur, _iso(date(2025, 4, 6), 10, 0, tz), [(inv_id, amt)])
            p2 = _add_payment(twin, f"{tag}:p2", cp_id, amt, cur, _iso(date(2025, 4, 7), 10, 0, tz), [(inv_id, amt)])
            pref = _add_payment(
                twin, f"{tag}:ref", cp_id, -amt, cur, _iso(date(2025, 4, 8), 10, 0, tz), [],
                extra={"payment_type": "refund", "related_payment_id": p2},
            )
            twin.distractor_log.append({"class": cls, "ids": [f"INV:{inv_id}", f"PAY:{pref}"]})

        elif cls == "D-PART-01":
            amt = 600 * unit
            inv_id = _add_inv_and_je(twin, tag, cp_id, amt, cur, _iso(date(2025, 4, 3), 9, 0, tz), _iso(date(2025, 4, 3), 10, 0, tz), status="paid")
            _add_payment(twin, f"{tag}:p1", cp_id, 350 * unit, cur, _iso(date(2025, 4, 5), 10, 0, tz), [(inv_id, 350 * unit)])
            _add_payment(twin, f"{tag}:p2", cp_id, 250 * unit, cur, _iso(date(2025, 4, 9), 10, 0, tz), [(inv_id, 250 * unit)])
            twin.distractor_log.append({"class": cls, "ids": [f"INV:{inv_id}"]})

        elif cls == "D-PART-02":
            if twin.policy["allocation_policy"]["allow_advances"]:
                amt = 400 * unit
                inv_id = _add_inv_and_je(twin, tag, cp_id, amt, cur, _iso(date(2025, 4, 4), 9, 0, tz), _iso(date(2025, 4, 4), 10, 0, tz))
                p = _add_payment(twin, f"{tag}:adv", cp_id, 550 * unit, cur, _iso(date(2025, 4, 6), 10, 0, tz), [(inv_id, amt)])
                twin.distractor_log.append({"class": cls, "ids": [f"INV:{inv_id}", f"PAY:{p}"]})

        elif cls == "D-PART-03":
            if twin.policy["allocation_policy"]["allow_multi_invoice_split"]:
                a1, a2 = 220 * unit, 330 * unit
                i1 = _add_inv_and_je(twin, f"{tag}:1", cp_id, a1, cur, _iso(date(2025, 4, 5), 9, 0, tz), _iso(date(2025, 4, 5), 10, 0, tz))
                i2 = _add_inv_and_je(twin, f"{tag}:2", cp_id, a2, cur, _iso(date(2025, 4, 5), 11, 0, tz), _iso(date(2025, 4, 5), 12, 0, tz))
                p = _add_payment(twin, f"{tag}:sp", cp_id, a1 + a2, cur, _iso(date(2025, 4, 7), 10, 0, tz), [(i1, a1), (i2, a2)])
                twin.distractor_log.append({"class": cls, "ids": [f"PAY:{p}", f"INV:{i1}", f"INV:{i2}"]})

        elif cls == "D-PART-04":
            amt = 500 * unit
            inv_id = _add_inv_and_je(twin, tag, cp_id, amt, cur, _iso(date(2025, 4, 6), 9, 0, tz), _iso(date(2025, 4, 6), 10, 0, tz), status="paid")
            _add_payment(twin, f"{tag}:p", cp_id, 420 * unit, cur, _iso(date(2025, 4, 8), 10, 0, tz), [(inv_id, 420 * unit)])
            cn_id = twin.next_id("CN", f"d_cn:{tag}")
            twin.credit_notes.append(
                {
                    "credit_note_id": cn_id,
                    "invoice_id": inv_id,
                    "counterparty_id": cp_id,
                    "timestamp": _iso(date(2025, 4, 9), 10, 0, tz),
                    "amount_minor": 80 * unit,
                    "currency": cur,
                    "reason_code": "return",
                }
            )
            twin.distractor_log.append({"class": cls, "ids": [f"INV:{inv_id}", f"CN:{cn_id}"]})

        elif cls == "D-FX-01" and fcur and twin.policy["fx_policy"]["fallback_rule"] == "last_available":
            # Saturday 2025-04-12 falls back cleanly to Friday 2025-04-11 NBK quote
            sat = date(2025, 4, 12)
            perm = select_permitted_fx(twin.fx_rates, fcur, cur, sat, twin.policy)
            famt_src = 125 * (10 ** exponent_of(fcur))
            famt_dst = convert_with_convention(
                famt_src, fcur, cur, perm[0]["rate_decimal"], twin.policy["rounding_mode"], twin.policy["fx_policy"]["quote_convention"]
            )
            inv_id = _add_inv_and_je(
                twin, tag, cp_id, famt_src, fcur, _iso(sat, 10, 0, tz), _iso(sat, 10, 0, tz),
                status="open", fx_rate=perm[0]["rate_decimal"], func_minor=famt_dst,
            )
            twin.distractor_log.append({"class": cls, "ids": [f"INV:{inv_id}"]})

        elif cls == "D-FX-02" and fcur and twin.policy["fx_policy"]["rate_date_rule"] == "document_date":
            d_doc = date(2025, 4, 10)
            d_pay = date(2025, 4, 15)
            perm = select_permitted_fx(twin.fx_rates, fcur, cur, d_doc, twin.policy)
            famt_src = 140 * (10 ** exponent_of(fcur))
            famt_dst = convert_with_convention(
                famt_src, fcur, cur, perm[0]["rate_decimal"], twin.policy["rounding_mode"], twin.policy["fx_policy"]["quote_convention"]
            )
            inv_id = _add_inv_and_je(
                twin, tag, cp_id, famt_src, fcur, _iso(d_doc, 9, 0, tz), _iso(d_doc, 10, 0, tz),
                status="paid", fx_rate=perm[0]["rate_decimal"], func_minor=famt_dst,
            )
            _add_payment(twin, f"{tag}:p", cp_id, famt_src, fcur, _iso(d_pay, 10, 0, tz), [(inv_id, famt_src)])
            twin.distractor_log.append({"class": cls, "ids": [f"INV:{inv_id}"]})

        elif cls == "D-CUT-01":
            # 2025-03-31T21:30:00+00:00 -> 2025-04-01 local in Asia/Almaty (UTC+5)
            if tz == "Asia/Almaty":
                amt = 310 * unit
                inv_id = _add_inv_and_je(
                    twin, tag, cp_id, amt, cur, "2025-03-31T21:30:00+00:00", _iso(date(2025, 4, 1), 9, 0, tz), status="open"
                )
                twin.distractor_log.append({"class": cls, "ids": [f"INV:{inv_id}"]})

        elif cls == "D-CUT-02":
            amt = 290 * unit
            inv_id = _add_inv_and_je(
                twin, tag, cp_id, amt, cur, _iso(date(2025, 4, 10), 10, 0, tz), _iso(date(2025, 3, 20), 10, 0, tz),
                status="open", debit_acc="1410", credit_acc="1010", analytic_tag="prepayment",
                posting_period_override="2025-03" if twin.company["fiscal_period_rule"] == "monthly" else "2025-Q1",
            )
            twin.distractor_log.append({"class": cls, "ids": [f"INV:{inv_id}"]})

        elif cls == "D-CUT-03":
            amt = 400 * unit
            inv_id = _add_inv_and_je(
                twin, tag, cp_id, amt, cur, "2025-03-15", _iso(date(2025, 3, 15), 10, 0, tz),
                status="open", service_end="2025-04-15", extra={"recognition_rule": "pro_rata"},
                posting_period_override="2025-04" if twin.company["fiscal_period_rule"] == "monthly" else "2025-Q2",
            )
            twin.distractor_log.append({"class": cls, "ids": [f"INV:{inv_id}"]})

        elif cls == "D-CUT-04":
            amt = 340 * unit
            inv_id = _add_inv_and_je(
                twin, tag, cp_id, amt, cur, _iso(date(2025, 3, 28), 10, 0, tz), _iso(date(2025, 4, 4), 10, 0, tz), status="open"
            )
            twin.distractor_log.append({"class": cls, "ids": [f"INV:{inv_id}"]})
        _ = rng


__all__ = ["ALL_16_DISTRACTORS", "apply_clean_distractors"]
