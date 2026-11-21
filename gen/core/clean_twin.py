"""Phase 3 — Deterministic Clean Twin accounting book generator.

Produces a complete, balanced, invariant-passing 12-file public accounting book
conformance-checked against frozen ``contracts/`` v1.0.0 schemas and
``invariants/checks.py``.

Design guarantees:
  - 100% deterministic from ``(master_seed, episode_index, spec)``;
  - Integer minor units everywhere, exact ``core.money`` FX conversion (zero float);
  - Explicit company timezone + ``core.time_rules.fiscal_period`` (never host TZ);
  - Stateless anti-shortcut IDs via ``core.ids.make_id`` across families A/B/C/D;
  - Balanced double-entry journal entries (INV-01) and zero anomalies on clean twins;
  - Supports deterministic clean distractor weaving via ``gen.distractors.catalog``.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from fractions import Fraction
from typing import Any
from zoneinfo import ZoneInfo

from contracts.currency import exponent_of
from contracts.loader import validate_instance
from core.ids import make_id
from core.money import MODES, convert_minor, parse_rate
from core.time_rules import fiscal_period, instant
from gen.core.rng import derive_bytes, scoped_rng
from invariants.checks import check as invariant_check


@dataclass(frozen=True)
class CleanTwinSpec:
    """Deterministic configuration for generating one Clean Twin."""

    episode_id: str
    master_seed: int
    episode_index: int = 0
    functional_currency: str = "KZT"
    foreign_currencies: tuple[str, ...] = ("USD", "EUR")
    timezone: str = "Asia/Almaty"
    fiscal_period_rule: str = "monthly"
    rounding_mode: str = "half_even"
    rate_date_rule: str = "document_date"
    fallback_rule: str = "last_available"
    quote_convention: str = "functional_per_foreign"
    recognition_event: str = "service_date"
    allow_advances: bool = False
    allow_multi_invoice_split: bool = True
    id_style: str = "A"
    company_size: str = "S"
    num_counterparties: int = 6
    num_domestic_invoices: int = 8
    num_foreign_invoices: int = 6
    distractor_classes: tuple[str, ...] = ()
    max_steps: int = 100
    max_page_size: int = 50
    max_findings: int = 20
    max_evidence_ids: int = 20


@dataclass
class CleanTwin:
    """In-memory representation of a 12-file TwinLedger public accounting book."""

    episode_id: str
    id_key: bytes
    id_style: str
    company: dict[str, Any]
    policy: dict[str, Any]
    accounts: list[dict[str, Any]]
    opening_balances: list[dict[str, Any]]
    period_calendar: list[dict[str, Any]]
    counterparties: list[dict[str, Any]]
    fx_rates: list[dict[str, Any]]
    invoices: list[dict[str, Any]]
    payments: list[dict[str, Any]]
    credit_notes: list[dict[str, Any]]
    bank_lines: list[dict[str, Any]]
    journal_entries: list[dict[str, Any]]
    distractor_log: list[dict[str, Any]] = field(default_factory=list)
    _seq: int = 0

    def next_id(self, namespace: str, salt_key: str | None = None) -> str:
        """Issue a stateless, anti-shortcut entity ID in this episode's family."""
        self._seq += 1
        ek = salt_key if salt_key is not None else f"{namespace}:{self._seq}"
        return make_id(self.id_key, namespace, ek, self.id_style)

    def clone(self) -> CleanTwin:
        return copy.deepcopy(self)

    def public_tables(self) -> dict[str, Any]:
        """Return canonical 12-file public payload dict (keys = filenames)."""
        return {
            "company.json": self.company,
            "policy.json": self.policy,
            "accounts.json": self.accounts,
            "opening_balances.json": self.opening_balances,
            "period_calendar.json": self.period_calendar,
            "counterparties.jsonl": self.counterparties,
            "fx_rates.jsonl": self.fx_rates,
            "invoices.jsonl": self.invoices,
            "payments.jsonl": self.payments,
            "credit_notes.jsonl": self.credit_notes,
            "bank_lines.jsonl": self.bank_lines,
            "journal_entries.jsonl": self.journal_entries,
        }


# Base exchange rates expressed as <functional> per 1 <foreign> (exact strings)
_USD_BASE_RATES: dict[str, str] = {
    "KZT": "485.00",
    "USD": "1",
    "EUR": "0.92",
    "JPY": "152.00",
    "KWD": "0.307",
}

_SYNTHETIC_COMPANY_ROOTS = (
    ("Alatau", "Алатау", "Алатау"),
    ("Saryarka", "Сарыарка", "Сарыарқа"),
    ("Irtysh", "Иртыш", "Ертіс"),
    ("Caspian", "Каспий", "Каспий"),
    ("Zhetysu", "Жетысу", "Жетісу"),
    ("Altai", "Алтай", "Алтай"),
)

_SYNTHETIC_INDUSTRIES = (
    ("Logistics", "Логистика", "Логистика"),
    ("Supply", "Снабжение", "Жабдықтау"),
    ("Engineering", "Инжиниринг", "Инжиниринг"),
    ("Cloud", "Облачные системы", "Бұлтты жүйелер"),
    ("Trade", "Трейдинг", "Сауда"),
    ("Analytics", "Аналитика", "Талдау"),
)


def _standard_accounts() -> list[dict[str, Any]]:
    return [
        {"account_id": "1010", "name": "Cash and Bank", "account_type": "asset", "normal_side": "debit"},
        {"account_id": "1210", "name": "Accounts Receivable", "account_type": "asset", "normal_side": "debit"},
        {"account_id": "1410", "name": "Prepaid Expenses", "account_type": "asset", "normal_side": "debit"},
        {"account_id": "2010", "name": "Accounts Payable", "account_type": "liability", "normal_side": "credit"},
        {"account_id": "3010", "name": "Retained Earnings", "account_type": "equity", "normal_side": "credit"},
        {"account_id": "4010", "name": "Operating Revenue", "account_type": "revenue", "normal_side": "credit"},
        {"account_id": "5010", "name": "Operating Expense", "account_type": "expense", "normal_side": "debit"},
    ]


def _period_calendar(rule: str, year: int = 2025) -> list[dict[str, Any]]:
    if rule == "monthly":
        month_days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        return [
            {
                "period_id": f"{year:04d}-{m:02d}",
                "start_date": f"{year:04d}-{m:02d}-01",
                "end_date": f"{year:04d}-{m:02d}-{month_days[m - 1]:02d}",
                "status": "closed" if m <= 5 else "open",
            }
            for m in range(1, 7)
        ]
    if rule == "quarterly":
        return [
            {"period_id": f"{year:04d}-Q1", "start_date": f"{year:04d}-01-01", "end_date": f"{year:04d}-03-31", "status": "closed"},
            {"period_id": f"{year:04d}-Q2", "start_date": f"{year:04d}-04-01", "end_date": f"{year:04d}-06-30", "status": "open"},
        ]
    raise ValueError(f"unsupported fiscal_period_rule: {rule!r}")


def _iso_local(d: date, hour: int, minute: int, tz_name: str) -> str:
    tz = ZoneInfo(tz_name)
    dt = datetime(d.year, d.month, d.day, hour, minute, 0, tzinfo=tz)
    return dt.isoformat()


def _format_decimal_rate(num: Fraction, decimals: int = 6) -> str:
    """Format a positive rational as a clean fixed-point decimal string."""
    scale = 10 ** decimals
    scaled = round(num * scale)
    if scaled <= 0:
        scaled = 1
    whole, frac = divmod(scaled, scale)
    if frac == 0:
        return str(whole)
    frac_str = f"{frac:0{decimals}d}".rstrip("0")
    return f"{whole}.{frac_str}"


def convert_with_convention(
    amount_minor: int,
    src_currency: str,
    dst_currency: str,
    rate_decimal: str,
    rounding_mode: str,
    quote_convention: str,
) -> int:
    """Exact conversion supporting both ``functional_per_foreign`` and ``foreign_per_functional``."""
    if src_currency == dst_currency:
        return amount_minor
    if quote_convention == "functional_per_foreign":
        return convert_minor(amount_minor, src_currency, dst_currency, rate_decimal, rounding_mode).amount_minor
    if quote_convention == "foreign_per_functional":
        rate = Fraction(parse_rate(rate_decimal))
        inv = Fraction(1) / rate
        shift = exponent_of(dst_currency) - exponent_of(src_currency)
        raw = Fraction(amount_minor) * inv * (Fraction(10) ** shift)
        if rounding_mode not in MODES:
            raise ValueError(f"unsupported rounding_mode: {rounding_mode!r}")
        if rounding_mode == "half_even":
            return round(raw)
        # half_up away from zero
        if raw >= 0:
            return int(raw + Fraction(1, 2))
        return -int(-raw + Fraction(1, 2))
    raise ValueError(f"unsupported quote_convention: {quote_convention!r}")


def select_permitted_fx(
    fx_rates: list[dict[str, Any]],
    foreign_currency: str,
    functional_currency: str,
    target_date: date,
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    """Select policy-permitted FX quotes for ``(foreign, functional)`` on ``target_date``."""
    fx_pol = policy["fx_policy"]
    sources = set(fx_pol["source_codes"])
    fallback = fx_pol["fallback_rule"]
    conv = fx_pol["quote_convention"]
    expected_pair = (
        f"{foreign_currency}/{functional_currency}"
        if conv == "functional_per_foreign"
        else f"{functional_currency}/{foreign_currency}"
    )
    candidates: list[tuple[date, dict[str, Any]]] = []
    for row in fx_rates:
        if row["pair"] != expected_pair or row["source_code"] not in sources:
            continue
        eff = date.fromisoformat(row["effective_date"])
        if eff == target_date or (fallback == "last_available" and eff < target_date):
            candidates.append((eff, row))
    if not candidates:
        raise ValueError(f"no permitted FX rate for {expected_pair} on {target_date}")
    latest = max(d for d, _ in candidates)
    return [row for d, row in candidates if d == latest]


def make_balanced_je(
    je_id: str,
    timestamp: str,
    posting_period: str,
    source_document_id: str,
    description: str,
    debit_account: str,
    credit_account: str,
    amount_minor: int,
    currency: str,
    fx_rate_decimal: str,
    functional_amount_minor: int,
    counterparty_id: str | None = None,
    analytic_tag: str | None = None,
) -> dict[str, Any]:
    """Construct a balanced 2-line journal entry."""
    return {
        "je_id": je_id,
        "timestamp": timestamp,
        "posting_period": posting_period,
        "source_document_id": source_document_id,
        "description": description,
        "lines": [
            {
                "line_id": "L1",
                "account_id": debit_account,
                "debit_minor": amount_minor,
                "credit_minor": 0,
                "currency": currency,
                "fx_rate_decimal": fx_rate_decimal,
                "functional_debit_minor": functional_amount_minor,
                "functional_credit_minor": 0,
                "counterparty_id": counterparty_id,
                "analytic_tag": analytic_tag,
            },
            {
                "line_id": "L2",
                "account_id": credit_account,
                "debit_minor": 0,
                "credit_minor": amount_minor,
                "currency": currency,
                "fx_rate_decimal": fx_rate_decimal,
                "functional_debit_minor": 0,
                "functional_credit_minor": functional_amount_minor,
                "counterparty_id": counterparty_id,
                "analytic_tag": analytic_tag,
            },
        ],
    }


def verify_clean_invariants(twin: CleanTwin) -> list[str]:
    """Run core clean accounting invariant checks on a CleanTwin. Returns errors."""
    errors: list[str] = []
    errors.extend(validate_instance("company", twin.company))
    errors.extend(validate_instance("policy", twin.policy))

    func_cur = twin.company["functional_currency"]
    # Opening balances balanced per currency
    ob_by_cur: dict[str, list[int]] = {}
    for row in twin.opening_balances:
        cur = row["currency"]
        ob_by_cur.setdefault(cur, [0, 0])
        ob_by_cur[cur][0] += row["debit_minor"]
        ob_by_cur[cur][1] += row["credit_minor"]
    for cur, (deb, cred) in ob_by_cur.items():
        if deb != cred:
            errors.append(f"opening_balances unbalanced in {cur}: {deb} != {cred}")

    # Every JE balanced in both transaction & functional currency (INV-01)
    for je in twin.journal_entries:
        debs = [ln["functional_debit_minor"] for ln in je["lines"]]
        creds = [ln["functional_credit_minor"] for ln in je["lines"]]
        if invariant_check("INV-01", je["je_id"], {"debits": debs, "credits": creds, "currency": func_cur}):
            errors.append(f"INV-01 functional imbalance on {je['je_id']}")
        by_cur: dict[str, tuple[list[int], list[int]]] = {}
        for ln in je["lines"]:
            d_list, c_list = by_cur.setdefault(ln["currency"], ([], []))
            d_list.append(ln["debit_minor"])
            c_list.append(ln["credit_minor"])
        for cur, (d_list, c_list) in by_cur.items():
            if invariant_check("INV-01", je["je_id"], {"debits": d_list, "credits": c_list, "currency": cur}):
                errors.append(f"INV-01 transaction imbalance on {je['je_id']} ({cur})")

    # Unique primary keys per table
    key_fields = [
        ("counterparties", "counterparty_id", twin.counterparties),
        ("fx_rates", "fx_id", twin.fx_rates),
        ("invoices", "doc_id", twin.invoices),
        ("payments", "pay_id", twin.payments),
        ("credit_notes", "credit_note_id", twin.credit_notes),
        ("bank_lines", "bank_line_id", twin.bank_lines),
        ("journal_entries", "je_id", twin.journal_entries),
    ]
    for tbl, fld, rows in key_fields:
        seen: set[str] = set()
        for r in rows:
            val = r[fld]
            if val in seen:
                errors.append(f"duplicate primary key {tbl}.{fld}={val}")
            seen.add(val)

    return errors


def generate_clean_twin(spec: CleanTwinSpec) -> CleanTwin:
    """Deterministically generate a complete Clean Twin accounting book."""
    rng = scoped_rng(spec.master_seed, "clean_twin", spec.episode_id, spec.episode_index)
    id_key = derive_bytes(spec.master_seed, "id_key", spec.episode_id, spec.episode_index)

    supported = list(dict.fromkeys([spec.functional_currency, *spec.foreign_currencies]))
    root_en, root_ru, root_kk = _SYNTHETIC_COMPANY_ROOTS[rng.randrange(len(_SYNTHETIC_COMPANY_ROOTS))]
    ind_en, ind_ru, ind_kk = _SYNTHETIC_INDUSTRIES[rng.randrange(len(_SYNTHETIC_INDUSTRIES))]
    comp_id = make_id(id_key, "CO", f"company:{spec.episode_id}", spec.id_style)

    company: dict[str, Any] = {
        "schema_version": "1.0.0",
        "company_id": comp_id,
        "legal_name": f"{root_en} {ind_en} Synthetic LLP",
        "name_variants": {
            "ru": f"ТОО «{root_ru} {ind_ru} Синтетик»",
            "kk": f"«{root_kk} {ind_kk} Синтетик» ЖШС",
            "en": f"{root_en} {ind_en} Synthetic LLP",
        },
        "jurisdiction_code": "KZ" if spec.functional_currency == "KZT" else "INTL",
        "timezone": spec.timezone,
        "functional_currency": spec.functional_currency,
        "supported_currencies": supported,
        "fiscal_year_start": "2025-01-01",
        "fiscal_period_rule": spec.fiscal_period_rule,
        "accounting_basis": "IFRS_accrual_synthetic",
        "id_style": spec.id_style,
        "text_profile": "synthetic_clean_v1",
        "company_size": spec.company_size,
    }

    policy: dict[str, Any] = {
        "schema_version": "1.0.0",
        "rounding_mode": spec.rounding_mode,
        "fx_policy": {
            "rate_date_rule": spec.rate_date_rule,
            "fallback_rule": spec.fallback_rule,
            "source_codes": ["NBK"],
            "quote_convention": spec.quote_convention,
        },
        "cutoff_policy": {
            "recognition_event": spec.recognition_event,
            "timezone_source": "company",
        },
        "allocation_policy": {
            "allow_advances": spec.allow_advances,
            "allow_multi_invoice_split": spec.allow_multi_invoice_split,
        },
        "credit_note_cap_minor": 500_000_000,
        "max_steps": spec.max_steps,
        "max_page_size": spec.max_page_size,
        "max_findings": spec.max_findings,
        "max_evidence_ids": spec.max_evidence_ids,
        "eta": 0.1,
    }

    accounts = _standard_accounts()
    period_calendar = _period_calendar(spec.fiscal_period_rule, 2025)
    opening_cash = 50_000_000 * (10 ** max(0, exponent_of(spec.functional_currency) - 2))
    opening_balances = [
        {"account_id": "1010", "currency": spec.functional_currency, "debit_minor": opening_cash, "credit_minor": 0, "as_of_date": "2025-01-01"},
        {"account_id": "3010", "currency": spec.functional_currency, "debit_minor": 0, "credit_minor": opening_cash, "as_of_date": "2025-01-01"},
    ]

    twin = CleanTwin(
        episode_id=spec.episode_id,
        id_key=id_key,
        id_style=spec.id_style,
        company=company,
        policy=policy,
        accounts=accounts,
        opening_balances=opening_balances,
        period_calendar=period_calendar,
        counterparties=[],
        fx_rates=[],
        invoices=[],
        payments=[],
        credit_notes=[],
        bank_lines=[],
        journal_entries=[],
    )

    # 1. Counterparties
    for idx in range(spec.num_counterparties):
        cp_id = twin.next_id("CP", f"cp:{idx}")
        r_en, r_ru, _ = _SYNTHETIC_COMPANY_ROOTS[(idx + 1) % len(_SYNTHETIC_COMPANY_ROOTS)]
        i_en, _, _ = _SYNTHETIC_INDUSTRIES[(idx + 2) % len(_SYNTHETIC_INDUSTRIES)]
        twin.counterparties.append(
            {
                "counterparty_id": cp_id,
                "name": f"{r_en} {i_en} Partner {idx + 1}",
                "role": "vendor" if idx % 2 == 0 else "customer",
                "country": "KZ" if idx % 2 == 0 else "DE",
                "aliases": [f"{r_ru} Партнер {idx + 1}"],
            }
        )

    # 2. FX timelines across 2025-03-01 .. 2025-05-15 (weekdays only for NBK, plus non-permitted MKT quotes)
    func_usd = Fraction(parse_rate(_USD_BASE_RATES[spec.functional_currency]))
    for fcur in spec.foreign_currencies:
        if fcur == spec.functional_currency:
            continue
        for_usd = Fraction(parse_rate(_USD_BASE_RATES[fcur]))
        # functional per foreign
        base_direct = func_usd / for_usd
        pair = (
            f"{fcur}/{spec.functional_currency}"
            if spec.quote_convention == "functional_per_foreign"
            else f"{spec.functional_currency}/{fcur}"
        )
        start_d = date(2025, 3, 1)
        for offset in range(76):
            cur_d = start_d + timedelta(days=offset)
            # Skip weekends for NBK so fallback_rule="last_available" is naturally exercised
            if cur_d.weekday() >= 5:
                continue
            # Small deterministic smooth drift (+/- 2%)
            bps = ((offset * 17 + rng.randrange(0, 7)) % 41) - 20
            direct_rate = base_direct * Fraction(10000 + bps, 10000)
            quote_val = direct_rate if spec.quote_convention == "functional_per_foreign" else (Fraction(1) / direct_rate)
            rate_str = _format_decimal_rate(quote_val, decimals=6 if quote_val < 1 else 4)
            fx_id = twin.next_id("FX", f"fx:nbk:{pair}:{cur_d.isoformat()}")
            twin.fx_rates.append(
                {
                    "fx_id": fx_id,
                    "pair": pair,
                    "effective_date": cur_d.isoformat(),
                    "rate_decimal": rate_str,
                    "source_code": "NBK",
                    "publication_timestamp": _iso_local(cur_d, 8, 30, spec.timezone),
                }
            )
            # Also publish an off-policy MKT quote (+3.5% higher) every 3rd weekday
            if offset % 3 == 0:
                mkt_val = quote_val * Fraction(1035, 1000)
                mkt_str = _format_decimal_rate(mkt_val, decimals=6 if mkt_val < 1 else 4)
                mkt_id = twin.next_id("FX", f"fx:mkt:{pair}:{cur_d.isoformat()}")
                twin.fx_rates.append(
                    {
                        "fx_id": mkt_id,
                        "pair": pair,
                        "effective_date": cur_d.isoformat(),
                        "rate_decimal": mkt_str,
                        "source_code": "MKT",
                        "publication_timestamp": _iso_local(cur_d, 9, 0, spec.timezone),
                    }
                )

    # 3. Clean domestic invoices + payments + bank lines + JEs
    base_minor_unit = 10 ** exponent_of(spec.functional_currency)
    for idx in range(spec.num_domestic_invoices):
        cp = twin.counterparties[idx % len(twin.counterparties)]
        inv_id = twin.next_id("INV", f"dom_inv:{idx}")
        # Ensure at least half have service_date in March and issue_date in April (clean cutoff candidates!)
        if idx % 2 == 0:
            svc_d = date(2025, 3, 25 + (idx % 5))
            iss_d = date(2025, 4, 2 + (idx % 5))
        else:
            svc_d = date(2025, 4, 5 + (idx % 12))
            iss_d = svc_d + timedelta(days=1)
        due_d = iss_d + timedelta(days=15)
        svc_ts = _iso_local(svc_d, 10, 0, spec.timezone)
        iss_ts = _iso_local(iss_d, 11, 0, spec.timezone)
        due_ts = _iso_local(due_d, 18, 0, spec.timezone)
        total_minor = (rng.randint(150, 950) * 10) * base_minor_unit
        is_paid = idx < max(2, spec.num_domestic_invoices - 2)
        status = "paid" if is_paid else "open"

        twin.invoices.append(
            {
                "doc_id": inv_id,
                "counterparty_id": cp["counterparty_id"],
                "issue_timestamp": iss_ts,
                "service_start": svc_ts,
                "service_end": None,
                "due_timestamp": due_ts,
                "currency": spec.functional_currency,
                "total_minor": total_minor,
                "tax_minor": 0,
                "line_items": [{"description": f"Synthetic service #{idx + 1}", "amount_minor": total_minor}],
                "status": status,
            }
        )

        # Recognition journal entry in exact policy fiscal period
        events = {"service_date": svc_ts, "delivery_date": svc_ts, "issue_date": iss_ts}
        rec_period = fiscal_period(events, policy, company)
        je_inv_id = twin.next_id("JE", f"dom_je_inv:{idx}")
        twin.journal_entries.append(
            make_balanced_je(
                je_id=je_inv_id,
                timestamp=_iso_local(iss_d, 12, 0, spec.timezone),
                posting_period=rec_period,
                source_document_id=inv_id,
                description=f"Recognize invoice {inv_id}",
                debit_account="5010",
                credit_account="2010",
                amount_minor=total_minor,
                currency=spec.functional_currency,
                fx_rate_decimal="1",
                functional_amount_minor=total_minor,
                counterparty_id=cp["counterparty_id"],
            )
        )

        if is_paid:
            pay_d = iss_d + timedelta(days=3)
            pay_ts = _iso_local(pay_d, 14, 0, spec.timezone)
            pay_id = twin.next_id("PAY", f"dom_pay:{idx}")
            bank_id = twin.next_id("BANK", f"dom_bank:{idx}")
            alloc_id = twin.next_id("AL", f"dom_al:{idx}")
            twin.payments.append(
                {
                    "pay_id": pay_id,
                    "timestamp": pay_ts,
                    "counterparty_id": cp["counterparty_id"],
                    "currency": spec.functional_currency,
                    "amount_minor": total_minor,
                    "allocations": [
                        {
                            "allocation_id": alloc_id,
                            "document_id": inv_id,
                            "amount_minor": total_minor,
                            "allocation_timestamp": pay_ts,
                        }
                    ],
                    "bank_reference": bank_id,
                    "payment_channel": "wire",
                }
            )
            twin.bank_lines.append(
                {
                    "bank_line_id": bank_id,
                    "timestamp": pay_ts,
                    "amount_minor": total_minor,
                    "currency": spec.functional_currency,
                    "direction": "outbound",
                    "counterparty_text": cp["name"],
                    "reference_text": f"Settlement {inv_id}",
                }
            )
            pay_period = fiscal_period(
                {"service_date": pay_ts, "delivery_date": pay_ts, "issue_date": pay_ts},
                policy,
                company,
            )
            je_pay_id = twin.next_id("JE", f"dom_je_pay:{idx}")
            twin.journal_entries.append(
                make_balanced_je(
                    je_id=je_pay_id,
                    timestamp=_iso_local(pay_d, 14, 15, spec.timezone),
                    posting_period=pay_period,
                    source_document_id=pay_id,
                    description=f"Settle invoice {inv_id}",
                    debit_account="2010",
                    credit_account="1010",
                    amount_minor=total_minor,
                    currency=spec.functional_currency,
                    fx_rate_decimal="1",
                    functional_amount_minor=total_minor,
                    counterparty_id=cp["counterparty_id"],
                )
            )

    # 4. Clean foreign-currency invoices + JEs (all policy-compliant FX rates & periods)
    active_foreign = [c for c in spec.foreign_currencies if c != spec.functional_currency]
    for idx in range(spec.num_foreign_invoices):
        if not active_foreign:
            break
        fcur = active_foreign[idx % len(active_foreign)]
        cp = twin.counterparties[(idx + 1) % len(twin.counterparties)]
        inv_id = twin.next_id("INV", f"fx_inv:{idx}")
        # Pick weekdays in March/April so exact NBK dates exist
        svc_d = date(2025, 3, 17) + timedelta(days=idx * 5)
        while svc_d.weekday() >= 5:
            svc_d += timedelta(days=1)
        iss_d = svc_d + timedelta(days=2)
        while iss_d.weekday() >= 5:
            iss_d += timedelta(days=1)
        due_d = iss_d + timedelta(days=20)
        svc_ts = _iso_local(svc_d, 10, 0, spec.timezone)
        iss_ts = _iso_local(iss_d, 11, 0, spec.timezone)
        due_ts = _iso_local(due_d, 18, 0, spec.timezone)

        f_unit = 10 ** exponent_of(fcur)
        total_minor = rng.randint(50, 400) * f_unit
        twin.invoices.append(
            {
                "doc_id": inv_id,
                "counterparty_id": cp["counterparty_id"],
                "issue_timestamp": iss_ts,
                "service_start": svc_ts,
                "service_end": None,
                "due_timestamp": due_ts,
                "currency": fcur,
                "total_minor": total_minor,
                "tax_minor": 0,
                "line_items": [{"description": f"Cross-border service #{idx + 1}", "amount_minor": total_minor}],
                "status": "open",
            }
        )

        # Compute exact target FX date per policy (spec/policy_semantics.md)
        je_ts = _iso_local(iss_d, 13, 0, spec.timezone)
        if spec.rate_date_rule == "document_date":
            fx_target = instant(iss_ts).astimezone(ZoneInfo(spec.timezone)).date()
        elif spec.rate_date_rule == "operation_date":
            fx_target = instant(je_ts).astimezone(ZoneInfo(spec.timezone)).date()
        else:
            fx_target = instant(svc_ts).astimezone(ZoneInfo(spec.timezone)).date()
        permitted = select_permitted_fx(twin.fx_rates, fcur, spec.functional_currency, fx_target, policy)
        chosen_fx = permitted[0]
        func_amt = convert_with_convention(
            total_minor,
            fcur,
            spec.functional_currency,
            chosen_fx["rate_decimal"],
            spec.rounding_mode,
            spec.quote_convention,
        )
        events = {"service_date": svc_ts, "delivery_date": svc_ts, "issue_date": iss_ts}
        rec_period = fiscal_period(events, policy, company)
        je_fx_id = twin.next_id("JE", f"fx_je:{idx}")
        twin.journal_entries.append(
            make_balanced_je(
                je_id=je_fx_id,
                timestamp=je_ts,
                posting_period=rec_period,
                source_document_id=inv_id,
                description=f"Foreign invoice recognition {inv_id}",
                debit_account="5010",
                credit_account="2010",
                amount_minor=total_minor,
                currency=fcur,
                fx_rate_decimal=chosen_fx["rate_decimal"],
                functional_amount_minor=func_amt,
                counterparty_id=cp["counterparty_id"],
            )
        )

    # 5. Optional clean distractors woven into the clean book
    if spec.distractor_classes:
        from gen.distractors.catalog import apply_clean_distractors

        apply_clean_distractors(twin, spec.distractor_classes, rng)

    # 6. Verify clean invariants before returning
    inv_errors = verify_clean_invariants(twin)
    if inv_errors:
        raise RuntimeError(f"clean twin failed invariants: {inv_errors}")

    return twin


__all__ = [
    "CleanTwin",
    "CleanTwinSpec",
    "convert_with_convention",
    "generate_clean_twin",
    "make_balanced_je",
    "select_permitted_fx",
    "verify_clean_invariants",
]
