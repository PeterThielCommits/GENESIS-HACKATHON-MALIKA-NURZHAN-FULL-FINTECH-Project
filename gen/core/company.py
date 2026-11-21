"""Company context, chart of accounts and counterparties (Phase 3.2).

Every field is derived from its own RNG stream, so the company identity, the chart
and the counterparty list never perturb each other (REQ-GEN-002/003).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from contracts.errors import ConfigError
from contracts.models import Account, Counterparty
from core.ids import IdFactory, style_for_config
from gen.config import GeneratorConfig
from gen.core.reference import CHART_TEMPLATE, bank_account_marker, make_company_name, make_counterparty_name
from gen.core.rng import RngService

POLICY_VERSION: Final[str] = "1.0.0"


@dataclass(frozen=True)
class CompanyContext:
    company: dict[str, Any]
    policy: dict[str, Any]
    accounts: tuple[Account, ...]
    counterparties: tuple[Counterparty, ...]
    id_factory: IdFactory
    bank_account_marker: str

    def account_id_for_role(self, role: str) -> str:
        key = {
            "bank": "bank_account_id",
            "receivable": "receivable_account_id",
            "advance": "advance_account_id",
            "revenue": "revenue_account_id",
            "fx_gain_loss": "fx_gain_loss_account_id",
        }.get(role)
        if key is None:
            for account in self.accounts:
                if account.code == "2000" and role == "payable":
                    return account.account_id
                if account.code == "5000" and role == "expense":
                    return account.account_id
            raise ConfigError("unknown account role", role=role)
        return str(self.policy[key])


def build_company_context(rng: RngService, config: GeneratorConfig) -> CompanyContext:
    raw = config.raw
    company_cfg = raw["company"]
    history_cfg = raw["history"]

    company_stream = rng.stream("company")
    chart_stream = rng.stream("chart")
    cp_stream = rng.stream("counterparties")
    id_stream = rng.stream("ids/company")

    style = style_for_config(
        str(company_stream.choice(company_cfg["id_style_pool"]))
    )
    legal = make_company_name(company_stream, 0)
    company_id = f"CO-{company_stream.random.getrandbits(40):010X}"
    jurisdiction = str(company_stream.choice(company_cfg["jurisdiction_pool"]))
    timezone = str(company_stream.choice(company_cfg["timezone_pool"]))

    fiscal_start_month = int(history_cfg["fiscal_year_start_month"])
    fiscal_start_day = int(history_cfg["fiscal_year_start_day"])
    calendar_payload = {
        "period_rule": history_cfg["period_rule"],
        "fiscal_year_start_month": fiscal_start_month,
        "fiscal_year_start_day": fiscal_start_day,
        "cutoff_day_offset": int(history_cfg["cutoff_day_offset"]),
        "ambiguity_policy": history_cfg["ambiguity_policy"],
    }
    company = {
        "company_id": company_id,
        "legal_name": legal.en,
        "name_variants": legal.variants(),
        "jurisdiction_code": jurisdiction,
        "timezone": timezone,
        "functional_currency": company_cfg["functional_currency"],
        "supported_currencies": list(company_cfg["supported_currencies"]),
        "fiscal_year_start": f"{fiscal_start_month:02d}-{fiscal_start_day:02d}",
        "fiscal_period_rule": history_cfg["period_rule"],
        "accounting_basis": "accrual",
        "id_style": style,
        "text_profile": company_cfg["text_profile"],
        "company_size": company_cfg["size"],
        "fiscal_calendar": calendar_payload,
        "synthetic": True,
    }

    accounts: list[Account] = []
    account_ids: dict[str, str] = {}
    for entry in CHART_TEMPLATE:
        account_id = f"ACC-{entry['code']}"
        account_ids[entry["role"]] = account_id
        accounts.append(
            Account(
                account_id=account_id,
                code=entry["code"],
                name=entry["name"],
                type=entry["type"],
                normal_balance=entry["normal_balance"],
                currency_scope=entry["currency_scope"],
            )
        )
    if len({account.account_id for account in accounts}) != len(accounts):
        raise ConfigError("chart of accounts produced duplicate ids")

    policy = {
        "policy_version": POLICY_VERSION,
        "rounding_mode": "ROUND_HALF_EVEN",
        "functional_currency": company_cfg["functional_currency"],
        "fx_source_priority": list(raw["fx"]["sources"]),
        "fx_fallback_rule": "last_available_on_or_before",
        "fx_rate_date_basis": "document_date",
        "recognition_rule": "service_start",
        "allocation_rule": "oldest_open_first",
        "credit_note_cap_bps": 4000,
        "tolerance_rule_version": "rounding_ops_v1",
        "advance_account_id": account_ids["advance"],
        "revenue_account_id": account_ids["revenue"],
        "receivable_account_id": account_ids["receivable"],
        "bank_account_id": account_ids["bank"],
        "fx_gain_loss_account_id": account_ids["fx_gain_loss"],
        "notes": [
            "Synthetic policy: recognition at service_start in the company timezone.",
            "FX rates follow last_available_on_or_before from the primary synthetic source.",
            "Partial payments allocate oldest-open-first; unapplied cash stays unallocated.",
            "Credit notes are capped at 40% of the document total.",
        ],
    }

    counterparties = _build_counterparties(cp_stream, config)
    id_factory = IdFactory(style=style, rng=id_stream, year=int(history_cfg["start_year"]))
    bank_marker = bank_account_marker(chart_stream)

    return CompanyContext(
        company=company,
        policy=policy,
        accounts=tuple(accounts),
        counterparties=tuple(counterparties),
        id_factory=id_factory,
        bank_account_marker=bank_marker,
    )


def _build_counterparties(stream, config: GeneratorConfig) -> list[Counterparty]:
    volumes = config.raw["volumes"]
    count = int(volumes["counterparty_count"])
    customer_bps = int(volumes["customer_ratio_bps"])
    jurisdictions = list(config.raw["company"]["jurisdiction_pool"])

    used_names: set[str] = set()
    counterparties: list[Counterparty] = []
    for index in range(count):
        for _ in range(50):
            name = make_counterparty_name(stream)
            if name.en not in used_names:
                used_names.add(name.en)
                break
        else:  # pragma: no cover - practically unreachable
            raise ConfigError("counterparty name space exhausted")
        category = (
            "CUSTOMER"
            if stream.ratio_hit(customer_bps) and index < count - 1
            else ("SUPPLIER" if index == count - 1 else "CUSTOMER")
        )
        counterparties.append(
            Counterparty(
                counterparty_id=f"CP-{index + 1:04d}",
                legal_name=name.en,
                country_marker=str(stream.choice(jurisdictions)),
                vat_marker=f"XTV-{stream.random.randrange(10**8):08d}",
                payment_terms_days=int(stream.choice((14, 30, 45, 60))),
                category=category,
                name_variants=name.variants(),
            )
        )
    return counterparties
