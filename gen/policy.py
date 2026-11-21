"""Company policy (contracts/policy.json + contract 7.4; Section 4)."""
from __future__ import annotations

from typing import Any

from gen.chart import Account
from gen.company import CompanyProfile


def build_policy(company: CompanyProfile, accounts: list[Account]) -> dict[str, Any]:
    """Build the public policy document (contract 8.3 + contract 7.4)."""
    account_ids = {a.account_id: a for a in accounts}
    ap = account_ids.get("1100")
    cash = account_ids.get("1020")
    return {
        "policy_version": "1.0.0",
        "accounting_basis": company.accounting_basis,
        "rounding_mode": "ROUND_HALF_EVEN",
        "currency_exponents": {
            c: _exponent(c) for c in company.supported_currencies
        },
        "ledger_rules": {
            "AP_account_id": ap.account_id if ap else "1100",
            "CASH_account_id": cash.account_id if cash else "1020",
            "open_balance_per_invoice": True,
            "ap_subledger_equals_invoice_opens": True,
        },
        "fx_selection_policy": {
            "primary_date": "event_date",
            "fallback": "last_published_before_event",
            "reverse_quoting": True,
            "conversion_rounding_mode": "ROUND_HALF_EVEN",
        },
        "distribution_rules": {
            "credit_note_limit_percent": 100,
            "allocations_must_cover_payment": True,
        },
        "aging_rules": {
            "buckets": ["0-30", "30-60", "60-90", "90+"],
            "bucket_horizon_days": 120,
        },
        "cutoff_rules": {
            "revenue_recognition": "service_start",
            "ap_posting": "timestamp",
        },
        "bank_match_rules": {
            "match_by": ["payment_id", "bank_reference_text"],
            "amount_tolerance_minor": 0,
        },
        "document_status_rules": {
            "status_open_when_open_balance": True,
            "status_fully_paid_when_zero": True,
        },
        "notes": (
            "Generated clean policy per contract 8.1/9.3; production values "
            "are configured via configs/policy/*.json by the environment "
            "engineer after Phase 1 (contract freeze). This Phase-3 document "
            "is the synthetic clean policy used by the generator."
        ),
    }


def _exponent(currency: str) -> int:
    from gen.money import CURRENCY_EXPONENTS

    return CURRENCY_EXPONENTS.get(currency, 2)
