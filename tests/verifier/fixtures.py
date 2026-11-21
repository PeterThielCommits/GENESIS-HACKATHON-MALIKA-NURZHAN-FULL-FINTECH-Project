"""Hand-authored public episode fixtures for independent verifier tests (Phase 8).

Every fixture is hand-authored from frozen ``contracts/`` v1.0.0 and
``docs/DATA_DICTIONARY.md`` (Master TZ 8.2-8.3) with zero generator code
dependencies. All companies, counterparties, documents, banks, and amounts
are completely fictional.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from contracts.models import TruthFinding
from verifier.public_loader import PublicEpisode, build_public_episode


def make_company(
    *,
    company_id: str = "SYN-COMP-001",
    timezone: str = "Asia/Almaty",
    functional_currency: str = "KZT",
    supported_currencies: list[str] | None = None,
    fiscal_year_start: str = "2025-01-01",
    fiscal_period_rule: str = "monthly",
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "company_id": company_id,
        "legal_name": "Synthetic Steppe Logistics LLP",
        "name_variants": {
            "ru": "ТОО Синтетическая Степная Логистика",
            "kk": "Синтетикалық Дала Логистика ЖШС",
            "en": "Synthetic Steppe Logistics LLP",
        },
        "jurisdiction_code": "XZ",
        "timezone": timezone,
        "functional_currency": functional_currency,
        "supported_currencies": supported_currencies or ["KZT", "USD", "EUR", "JPY", "KWD"],
        "fiscal_year_start": fiscal_year_start,
        "fiscal_period_rule": fiscal_period_rule,
        "accounting_basis": "accrual_service_recognition_v1",
        "id_style": "A",
        "text_profile": "ru_kk_en_mixed",
        "company_size": "S",
    }


def make_policy(
    *,
    rounding_mode: str = "half_even",
    rate_date_rule: str = "document_date",
    fallback_rule: str = "last_available",
    source_codes: list[str] | None = None,
    quote_convention: str = "functional_per_foreign",
    recognition_event: str = "service_date",
    allow_advances: bool = True,
    allow_multi_invoice_split: bool = True,
    credit_note_cap_minor: int = 50000000,
    max_evidence_ids: int = 20,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "rounding_mode": rounding_mode,
        "fx_policy": {
            "rate_date_rule": rate_date_rule,
            "fallback_rule": fallback_rule,
            "source_codes": source_codes or ["NBK", "ECB"],
            "quote_convention": quote_convention,
        },
        "cutoff_policy": {
            "recognition_event": recognition_event,
            "timezone_source": "company",
        },
        "allocation_policy": {
            "allow_advances": allow_advances,
            "allow_multi_invoice_split": allow_multi_invoice_split,
        },
        "credit_note_cap_minor": credit_note_cap_minor,
        "max_steps": 100,
        "max_page_size": 50,
        "max_findings": 25,
        "max_evidence_ids": max_evidence_ids,
        "eta": 0.05,
    }


def standard_accounts() -> list[dict[str, Any]]:
    return [
        {"account_id": "1010", "name": "Cash Bank", "account_type": "cash"},
        {"account_id": "1410", "name": "Prepaid Expenses", "account_type": "prepayment"},
        {"account_id": "2010", "name": "Accounts Payable", "account_type": "ap"},
        {"account_id": "2410", "name": "Deferred Revenue", "account_type": "deferred_revenue"},
        {"account_id": "5010", "name": "Operating Expense", "account_type": "expense"},
    ]


def standard_counterparties() -> list[dict[str, Any]]:
    return [
        {"counterparty_id": "CP-001", "legal_name": "Synthetic Nomad Cloud LLC"},
        {"counterparty_id": "CP-002", "legal_name": "Synthetic Alatau Freight Co"},
    ]


def write_public_dir(public_dir: Path, episode: PublicEpisode) -> None:
    """Materialize a :class:`PublicEpisode` onto disk as standard public files."""
    public_dir.mkdir(parents=True, exist_ok=True)
    (public_dir / "company.json").write_text(
        json.dumps(episode.company, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (public_dir / "policy.json").write_text(
        json.dumps(episode.policy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (public_dir / "accounts.json").write_text(
        json.dumps(list(episode.accounts), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (public_dir / "opening_balances.json").write_text(
        json.dumps(episode.opening_balances, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (public_dir / "period_calendar.json").write_text(
        json.dumps(episode.period_calendar, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    jsonl_tables = {
        "counterparties.jsonl": episode.counterparties,
        "journal_entries.jsonl": episode.journal_entries,
        "invoices.jsonl": episode.invoices,
        "credit_notes.jsonl": episode.credit_notes,
        "payments.jsonl": episode.payments,
        "bank_lines.jsonl": episode.bank_lines,
        "fx_rates.jsonl": episode.fx_rates,
    }
    for filename, rows in jsonl_tables.items():
        text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        (public_dir / filename).write_text(text, encoding="utf-8")


def clean_episode() -> PublicEpisode:
    """Fully clean multi-currency, multi-period public episode (0 anomalies)."""
    invoices = [
        {
            "doc_id": "INV-2025-0001",
            "counterparty_id": "CP-001",
            "issue_timestamp": "2025-03-10T10:00:00+05:00",
            "service_start": "2025-03-10T09:00:00+05:00",
            "service_end": "2025-03-10T18:00:00+05:00",
            "due_timestamp": "2025-03-25T18:00:00+05:00",
            "currency": "KZT",
            "total_minor": 100000,
            "tax_minor": 0,
            "line_items": [{"line_id": "L1", "description": "Cloud compute", "amount_minor": 100000}],
            "status": "paid",
        },
        {
            "doc_id": "INV-2025-0002",
            "counterparty_id": "CP-002",
            "issue_timestamp": "2025-03-12T11:00:00+05:00",
            "service_start": "2025-03-12T08:00:00+05:00",
            "service_end": None,
            "due_timestamp": "2025-03-27T18:00:00+05:00",
            "currency": "USD",
            "total_minor": 20000,  # 200.00 USD -> 100,000.00 KZT at 500.00
            "tax_minor": 0,
            "line_items": [{"line_id": "L1", "description": "Freight service", "amount_minor": 20000}],
            "status": "paid",
        },
    ]
    payments = [
        {
            "pay_id": "PAY-0001",
            "timestamp": "2025-03-15T14:00:00+05:00",
            "counterparty_id": "CP-001",
            "currency": "KZT",
            "amount_minor": 100000,
            "allocations": [
                {
                    "allocation_id": "AL-001",
                    "document_id": "INV-2025-0001",
                    "amount_minor": 100000,
                    "allocation_timestamp": "2025-03-15T14:00:00+05:00",
                }
            ],
            "bank_reference": "BNK-REF-001",
            "payment_channel": "wire",
        },
        {
            "pay_id": "PAY-0002",
            "timestamp": "2025-03-20T15:00:00+05:00",
            "counterparty_id": "CP-002",
            "currency": "USD",
            "amount_minor": 20000,
            "allocations": [
                {
                    "allocation_id": "AL-002",
                    "document_id": "INV-2025-0002",
                    "amount_minor": 20000,
                    "allocation_timestamp": "2025-03-20T15:00:00+05:00",
                }
            ],
            "bank_reference": "BNK-REF-002",
            "payment_channel": "wire",
        },
    ]
    journal_entries = [
        {
            "je_id": "JE-0001",
            "timestamp": "2025-03-10T10:30:00+05:00",
            "posting_period": "2025-03",
            "source_document_id": "INV-2025-0001",
            "description": "Recognize INV-2025-0001",
            "lines": [
                {
                    "line_id": "JL-1",
                    "account_id": "5010",
                    "debit_minor": 100000,
                    "credit_minor": 0,
                    "currency": "KZT",
                    "fx_rate_decimal": "1",
                    "functional_debit_minor": 100000,
                    "functional_credit_minor": 0,
                    "counterparty_id": "CP-001",
                    "analytic_tag": None,
                },
                {
                    "line_id": "JL-2",
                    "account_id": "2010",
                    "debit_minor": 0,
                    "credit_minor": 100000,
                    "currency": "KZT",
                    "fx_rate_decimal": "1",
                    "functional_debit_minor": 0,
                    "functional_credit_minor": 100000,
                    "counterparty_id": "CP-001",
                    "analytic_tag": None,
                },
            ],
        },
        {
            "je_id": "JE-0002",
            "timestamp": "2025-03-12T11:30:00+05:00",
            "posting_period": "2025-03",
            "source_document_id": "INV-2025-0002",
            "description": "Recognize INV-2025-0002 USD",
            "lines": [
                {
                    "line_id": "JL-3",
                    "account_id": "5010",
                    "debit_minor": 20000,
                    "credit_minor": 0,
                    "currency": "USD",
                    "fx_rate_decimal": "500.00",
                    "functional_debit_minor": 10000000,
                    "functional_credit_minor": 0,
                    "counterparty_id": "CP-002",
                    "analytic_tag": None,
                },
                {
                    "line_id": "JL-4",
                    "account_id": "2010",
                    "debit_minor": 0,
                    "credit_minor": 20000,
                    "currency": "USD",
                    "fx_rate_decimal": "500.00",
                    "functional_debit_minor": 0,
                    "functional_credit_minor": 10000000,
                    "counterparty_id": "CP-002",
                    "analytic_tag": None,
                },
            ],
        },
    ]
    fx_rates = [
        {
            "fx_id": "FX-USD-KZT-2025-03-12-NBK",
            "pair": "USD/KZT",
            "effective_date": "2025-03-12",
            "rate_decimal": "500.00",
            "source_code": "NBK",
            "publication_timestamp": "2025-03-12T08:00:00+05:00",
        }
    ]
    bank_lines = [
        {
            "bank_line_id": "BANK-0001",
            "timestamp": "2025-03-15T14:05:00+05:00",
            "amount_minor": 100000,
            "currency": "KZT",
            "direction": "outflow",
            "reference_text": "PAY-0001",
            "matched_payment_id": "PAY-0001",
            "bank_account_id": "ACC-KZT-1",
        }
    ]
    return build_public_episode(
        company=make_company(),
        policy=make_policy(),
        accounts=standard_accounts(),
        counterparties=standard_counterparties(),
        journal_entries=journal_entries,
        invoices=invoices,
        payments=payments,
        bank_lines=bank_lines,
        fx_rates=fx_rates,
    )


def duplicate_payment_episode() -> tuple[PublicEpisode, list[TruthFinding]]:
    """Single DUPLICATE_PAYMENT anomaly on INV-2025-0010."""
    invoices = [
        {
            "doc_id": "INV-2025-0010",
            "counterparty_id": "CP-001",
            "issue_timestamp": "2025-04-05T10:00:00+05:00",
            "service_start": "2025-04-05T09:00:00+05:00",
            "service_end": None,
            "due_timestamp": "2025-04-20T18:00:00+05:00",
            "currency": "KZT",
            "total_minor": 75000,
            "tax_minor": 0,
            "line_items": [{"line_id": "L1", "description": "Hosting", "amount_minor": 75000}],
            "status": "paid",
        }
    ]
    payments = [
        {
            "pay_id": "PAY-0101",
            "timestamp": "2025-04-08T10:00:00+05:00",
            "counterparty_id": "CP-001",
            "currency": "KZT",
            "amount_minor": 75000,
            "allocations": [
                {
                    "allocation_id": "AL-101",
                    "document_id": "INV-2025-0010",
                    "amount_minor": 75000,
                    "allocation_timestamp": "2025-04-08T10:00:00+05:00",
                }
            ],
            "bank_reference": "REF-101",
            "payment_channel": "wire",
        },
        {
            "pay_id": "PAY-0102",
            "timestamp": "2025-04-11T16:30:00+05:00",
            "counterparty_id": "CP-001",
            "currency": "KZT",
            "amount_minor": 75000,
            "allocations": [
                {
                    "allocation_id": "AL-102",
                    "document_id": "INV-2025-0010",
                    "amount_minor": 75000,
                    "allocation_timestamp": "2025-04-11T16:30:00+05:00",
                }
            ],
            "bank_reference": "REF-102",
            "payment_channel": "wire",
        },
    ]
    journal_entries = [
        {
            "je_id": "JE-0102",
            "timestamp": "2025-04-11T16:35:00+05:00",
            "posting_period": "2025-04",
            "source_document_id": "PAY-0102",
            "description": "Payment settlement PAY-0102",
            "lines": [
                {
                    "line_id": "JL-1",
                    "account_id": "2010",
                    "debit_minor": 75000,
                    "credit_minor": 0,
                    "currency": "KZT",
                    "fx_rate_decimal": "1",
                    "functional_debit_minor": 75000,
                    "functional_credit_minor": 0,
                    "counterparty_id": "CP-001",
                    "analytic_tag": None,
                },
                {
                    "line_id": "JL-2",
                    "account_id": "1010",
                    "debit_minor": 0,
                    "credit_minor": 75000,
                    "currency": "KZT",
                    "fx_rate_decimal": "1",
                    "functional_debit_minor": 0,
                    "functional_credit_minor": 75000,
                    "counterparty_id": "CP-001",
                    "analytic_tag": None,
                },
            ],
        }
    ]
    bank_lines = [
        {
            "bank_line_id": "BANK-0101",
            "timestamp": "2025-04-08T10:10:00+05:00",
            "amount_minor": 75000,
            "currency": "KZT",
            "direction": "outflow",
            "reference_text": "REF-101",
            "matched_payment_id": "PAY-0101",
            "bank_account_id": "ACC-KZT-1",
        },
        {
            "bank_line_id": "BANK-0102",
            "timestamp": "2025-04-11T16:40:00+05:00",
            "amount_minor": 75000,
            "currency": "KZT",
            "direction": "outflow",
            "reference_text": "REF-102",
            "matched_payment_id": "PAY-0102",
            "bank_account_id": "ACC-KZT-1",
        },
    ]
    ep = build_public_episode(
        company=make_company(),
        policy=make_policy(),
        accounts=standard_accounts(),
        counterparties=standard_counterparties(),
        journal_entries=journal_entries,
        invoices=invoices,
        payments=payments,
        bank_lines=bank_lines,
    )
    truths = [
        TruthFinding(
            truth_id="TRUTH-DUP-001",
            type="DUPLICATE_PAYMENT",
            affected_ids=("JE:JE-0102", "PAY:PAY-0102"),
            amount_minor=75000,
            currency="KZT",
            tolerance_minor=0,
            evidence_sets=(("INV:INV-2025-0010", "JE:JE-0102", "PAY:PAY-0101", "PAY:PAY-0102"),),
            minimal_evidence_size=4,
            invariant_signature={"invariant_id": "INV-04", "entity_key": "INV-2025-0010"},
            operator_version="manual-hand-fixture@1.0",
        )
    ]
    return ep, truths


def partial_allocation_episode() -> tuple[PublicEpisode, list[TruthFinding]]:
    """Single PARTIAL_PAYMENT_ALLOCATION anomaly (over-allocation INV-15)."""
    invoices = [
        {
            "doc_id": "INV-2025-0020",
            "counterparty_id": "CP-001",
            "issue_timestamp": "2025-04-02T09:00:00+05:00",
            "service_start": "2025-04-02T09:00:00+05:00",
            "service_end": None,
            "due_timestamp": "2025-04-17T18:00:00+05:00",
            "currency": "KZT",
            "total_minor": 120000,
            "tax_minor": 0,
            "line_items": [{"line_id": "L1", "description": "Consulting", "amount_minor": 120000}],
            "status": "paid",
        }
    ]
    payments = [
        {
            "pay_id": "PAY-0201",
            "timestamp": "2025-04-05T12:00:00+05:00",
            "counterparty_id": "CP-001",
            "currency": "KZT",
            "amount_minor": 70000,
            "allocations": [
                {
                    "allocation_id": "AL-201",
                    "document_id": "INV-2025-0020",
                    "amount_minor": 120000,  # exceeds payment 70000 by 50000
                    "allocation_timestamp": "2025-04-05T12:00:00+05:00",
                }
            ],
            "bank_reference": "REF-201",
            "payment_channel": "wire",
        }
    ]
    ep = build_public_episode(
        company=make_company(),
        policy=make_policy(),
        accounts=standard_accounts(),
        counterparties=standard_counterparties(),
        invoices=invoices,
        payments=payments,
    )
    truths = [
        TruthFinding(
            truth_id="TRUTH-PART-001",
            type="PARTIAL_PAYMENT_ALLOCATION",
            affected_ids=("INV:INV-2025-0020", "PAY:PAY-0201"),
            amount_minor=50000,
            currency="KZT",
            tolerance_minor=0,
            evidence_sets=(("INV:INV-2025-0020", "PAY:PAY-0201"),),
            minimal_evidence_size=2,
            invariant_signature={"invariant_id": "INV-15", "entity_key": "PAY-0201"},
            operator_version="manual-hand-fixture@1.0",
        )
    ]
    return ep, truths


def fx_mismatch_episode() -> tuple[PublicEpisode, list[TruthFinding]]:
    """Single FX_RATE_MISMATCH anomaly with dual agreeing sources (2 alternative evidence sets)."""
    invoices = [
        {
            "doc_id": "INV-2025-0030",
            "counterparty_id": "CP-002",
            "issue_timestamp": "2025-04-10T10:00:00+05:00",
            "service_start": "2025-04-10T10:00:00+05:00",
            "service_end": None,
            "due_timestamp": "2025-04-25T18:00:00+05:00",
            "currency": "USD",
            "total_minor": 10000,  # 100.00 USD
            "tax_minor": 0,
            "line_items": [{"line_id": "L1", "description": "API license", "amount_minor": 10000}],
            "status": "open",
        }
    ]
    # Policy requires 500.00 KZT/USD -> 5,000,000 minor KZT; booked at 515.00 -> 5,150,000 (diff 150,000)
    journal_entries = [
        {
            "je_id": "JE-0301",
            "timestamp": "2025-04-10T11:00:00+05:00",
            "posting_period": "2025-04",
            "source_document_id": "INV-2025-0030",
            "description": "Book INV-2025-0030",
            "lines": [
                {
                    "line_id": "JL-1",
                    "account_id": "5010",
                    "debit_minor": 10000,
                    "credit_minor": 0,
                    "currency": "USD",
                    "fx_rate_decimal": "515.00",
                    "functional_debit_minor": 5150000,
                    "functional_credit_minor": 0,
                    "counterparty_id": "CP-002",
                    "analytic_tag": None,
                },
                {
                    "line_id": "JL-2",
                    "account_id": "2010",
                    "debit_minor": 0,
                    "credit_minor": 10000,
                    "currency": "USD",
                    "fx_rate_decimal": "515.00",
                    "functional_debit_minor": 0,
                    "functional_credit_minor": 5150000,
                    "counterparty_id": "CP-002",
                    "analytic_tag": None,
                },
            ],
        }
    ]
    fx_rates = [
        {
            "fx_id": "FX-USD-KZT-0410-NBK",
            "pair": "USD/KZT",
            "effective_date": "2025-04-10",
            "rate_decimal": "500.00",
            "source_code": "NBK",
            "publication_timestamp": "2025-04-10T08:00:00+05:00",
        },
        {
            "fx_id": "FX-USD-KZT-0410-ECB",
            "pair": "USD/KZT",
            "effective_date": "2025-04-10",
            "rate_decimal": "500.00",
            "source_code": "ECB",
            "publication_timestamp": "2025-04-10T08:30:00+05:00",
        },
    ]
    ep = build_public_episode(
        company=make_company(),
        policy=make_policy(rate_date_rule="document_date"),
        accounts=standard_accounts(),
        counterparties=standard_counterparties(),
        journal_entries=journal_entries,
        invoices=invoices,
        fx_rates=fx_rates,
    )
    truths = [
        TruthFinding(
            truth_id="TRUTH-FX-001",
            type="FX_RATE_MISMATCH",
            affected_ids=("JE:JE-0301",),
            amount_minor=150000,
            currency="KZT",
            tolerance_minor=1,
            evidence_sets=(
                ("FX:FX-USD-KZT-0410-ECB", "INV:INV-2025-0030", "JE:JE-0301"),
                ("FX:FX-USD-KZT-0410-NBK", "INV:INV-2025-0030", "JE:JE-0301"),
            ),
            minimal_evidence_size=3,
            invariant_signature={"invariant_id": "INV-07", "entity_key": "JE-0301"},
            operator_version="manual-hand-fixture@1.0",
        )
    ]
    return ep, truths


def period_cutoff_episode() -> tuple[PublicEpisode, list[TruthFinding]]:
    """Single PERIOD_CUTOFF anomaly: March service posted in April."""
    invoices = [
        {
            "doc_id": "INV-2025-0040",
            "counterparty_id": "CP-001",
            "issue_timestamp": "2025-04-02T10:00:00+05:00",
            "service_start": "2025-03-29T15:00:00+05:00",
            "service_end": "2025-03-29T17:00:00+05:00",
            "due_timestamp": "2025-04-17T18:00:00+05:00",
            "currency": "KZT",
            "total_minor": 90000,
            "tax_minor": 0,
            "line_items": [{"line_id": "L1", "description": "March maintenance", "amount_minor": 90000}],
            "status": "open",
        }
    ]
    journal_entries = [
        {
            "je_id": "JE-0401",
            "timestamp": "2025-04-02T10:30:00+05:00",
            "posting_period": "2025-04",  # expected 2025-03
            "source_document_id": "INV-2025-0040",
            "description": "Book INV-2025-0040",
            "lines": [
                {
                    "line_id": "JL-1",
                    "account_id": "5010",
                    "debit_minor": 90000,
                    "credit_minor": 0,
                    "currency": "KZT",
                    "fx_rate_decimal": "1",
                    "functional_debit_minor": 90000,
                    "functional_credit_minor": 0,
                    "counterparty_id": "CP-001",
                    "analytic_tag": None,
                },
                {
                    "line_id": "JL-2",
                    "account_id": "2010",
                    "debit_minor": 0,
                    "credit_minor": 90000,
                    "currency": "KZT",
                    "fx_rate_decimal": "1",
                    "functional_debit_minor": 0,
                    "functional_credit_minor": 90000,
                    "counterparty_id": "CP-001",
                    "analytic_tag": None,
                },
            ],
        }
    ]
    ep = build_public_episode(
        company=make_company(),
        policy=make_policy(recognition_event="service_date"),
        accounts=standard_accounts(),
        counterparties=standard_counterparties(),
        journal_entries=journal_entries,
        invoices=invoices,
    )
    truths = [
        TruthFinding(
            truth_id="TRUTH-CUT-001",
            type="PERIOD_CUTOFF",
            affected_ids=("JE:JE-0401",),
            amount_minor=90000,
            currency="KZT",
            tolerance_minor=0,
            evidence_sets=(("INV:INV-2025-0040", "JE:JE-0401"),),
            minimal_evidence_size=2,
            invariant_signature={"invariant_id": "INV-09", "entity_key": "JE-0401"},
            operator_version="manual-hand-fixture@1.0",
        )
    ]
    return ep, truths


def compound_four_type_episode() -> tuple[PublicEpisode, list[TruthFinding]]:
    """Compound episode containing ALL FOUR anomaly types simultaneously (TZ 11.7)."""
    dup_ep, dup_t = duplicate_payment_episode()
    part_ep, part_t = partial_allocation_episode()
    fx_ep, fx_t = fx_mismatch_episode()
    cut_ep, cut_t = period_cutoff_episode()

    ep = build_public_episode(
        company=make_company(),
        policy=make_policy(),
        accounts=standard_accounts(),
        counterparties=standard_counterparties(),
        invoices=list(dup_ep.invoices) + list(part_ep.invoices) + list(fx_ep.invoices) + list(cut_ep.invoices),
        payments=list(dup_ep.payments) + list(part_ep.payments),
        journal_entries=list(dup_ep.journal_entries) + list(fx_ep.journal_entries) + list(cut_ep.journal_entries),
        bank_lines=list(dup_ep.bank_lines),
        fx_rates=list(fx_ep.fx_rates),
    )
    return ep, dup_t + part_t + fx_t + cut_t
