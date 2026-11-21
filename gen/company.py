"""Company profile generation (contract 8.1; REQ-DATA-020)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gen.rng import NamespacedRNG

#: Company legal names (fictional only; Section 8.1).
_COMPANY_NAMES = [
    "Kazakhstan Logistics Holding",
    "Altyn Packaging Group",
    "Nurlywood Plus",
    "Almaty Textile Mill",
    "Kaztel sp.j",
    "Sunrise Freight",
    "Crystal Foods",
    "Meridian Trading",
    "Skyline Finance",
    "Riverstone Consulting",
]

#: Fictional legal name -> synthetic name variants (ru/kk/en).
_COMPANY_NAME_VARIANTS: dict[str, dict[str, str]] = {
    "Kazakhstan Logistics Holding": {
        "ru": "Холдинг Казахстан Логистика",
        "kk": "Қазақстан Логистикағақ Холдингі",
        "en": "Kazakhstan Logistics Holding",
    },
    "Altyn Packaging Group": {
        "ru": "Группа «Алтын Упаковка»",
        "kk": "«Алтын Тұрғын» тобы",
        "en": "Altyn Packaging Group",
    },
    "Nurlywood Plus": {
        "ru": "«Нурлывуд Плюс»",
        "kk": "«Нұрлывуд Плюс»",
        "en": "Nurlywood Plus",
    },
    "Almaty Textile Mill": {
        "ru": "Текстильный Комбинат Алматы",
        "kk": "Алматы Текстильдік Тұрғын",
        "en": "Almaty Textile Mill",
    },
    "Kaztel sp.j": {
        "ru": "«Казтел» сп.ж.",
        "kk": "«Қазтел» сп.ж.",
        "en": "Kaztel sp.j",
    },
    "Sunrise Freight": {
        "ru": "«Санрайз Фрайт»",
        "kk": "«Санрайз Фрайт»",
        "en": "Sunrise Freight",
    },
    "Crystal Foods": {
        "ru": "«Кристалл Фудс»",
        "kk": "«Кристалл Фудс»",
        "en": "Crystal Foods",
    },
    "Meridian Trading": {
        "ru": "«Меридиан Трейдинг»",
        "kk": "«Меридиан Трейдинг»",
        "en": "Meridian Trading",
    },
    "Skyline Finance": {
        "ru": "«Скайлайн Финанс»",
        "kk": "«Скайлайн Финанс»",
        "en": "Skyline Finance",
    },
    "Riverstone Consulting": {
        "ru": "«Риверстоун Консалтинг»",
        "kk": "«Риверстоун Консалтинг»",
        "en": "Riverstone Consulting",
    },
}

#: Synthetic reserved jurisdiction code for generated companies (Section 8.1:
#: XA–XZ are synthetic reserved designations; do not claim ISO status).
SYNTHETIC_JURISDICTION_CODE = "XA"

#: Synthetic bank account namespace prefix (Section 8.1).
SYNTHETIC_BANK_PREFIX = "BA"


@dataclass
class CompanyProfile:
    """Public company context (contract 8.1, table fields)."""

    company_id: str
    legal_name: str
    name_variants: dict[str, str]
    jurisdiction_code: str
    timezone: str
    functional_currency: str
    supported_currencies: list[str]
    fiscal_year_start: str
    fiscal_period_rule: str
    accounting_basis: dict[str, Any]
    id_style: str
    text_profile: dict[str, Any]
    company_size: str

    def to_public(self) -> dict[str, Any]:
        return {
            "company_id": self.company_id,
            "legal_name": self.legal_name,
            "name_variants": dict(self.name_variants),
            "jurisdiction_code": self.jurisdiction_code,
            "timezone": self.timezone,
            "functional_currency": self.functional_currency,
            "supported_currencies": list(self.supported_currencies),
            "fiscal_year_start": self.fiscal_year_start,
            "fiscal_period_rule": self.fiscal_period_rule,
            "accounting_basis": self.accounting_basis,
            "id_style": self.id_style,
            "text_profile": self.text_profile,
            "company_size": self.company_size,
        }


def generate_company(rng: NamespacedRNG, fiscal_year_start: str = "2025-01-01") -> CompanyProfile:
    """Generate a fictional company profile (Section 8.1)."""
    legal_name = rng.choice(_COMPANY_NAMES)
    if legal_name not in _COMPANY_NAME_VARIANTS:  # pragma: no cover - safety
        raise ValueError(f"missing name variants for {legal_name!r}")
    size_by_name = {
        "Kazakhstan Logistics Holding": "large",
        "Altyn Packaging Group": "medium",
        "Nurlywood Plus": "small",
        "Almaty Textile Mill": "large",
        "Kaztel sp.j": "small",
        "Sunrise Freight": "medium",
        "Crystal Foods": "medium",
        "Meridian Trading": "large",
        "Skyline Finance": "medium",
        "Riverstone Consulting": "small",
    }
    return CompanyProfile(
        company_id="SYN-CMP-0001",
        legal_name=legal_name,
        name_variants=dict(_COMPANY_NAME_VARIANTS[legal_name]),
        jurisdiction_code=SYNTHETIC_JURISDICTION_CODE,
        timezone="Asia/Almaty",
        functional_currency="KZT",
        supported_currencies=["KZT", "USD", "EUR"],
        fiscal_year_start=fiscal_year_start,
        fiscal_period_rule="monthly",
        accounting_basis={
            "method": "accrual",
            "revenue_recognition": "service_start",
            "vat": True,
            "period_rule": "monthly",
        },
        id_style="mixed_random_family_a_to_d",
        text_profile={
            "primary_language": "ru",
            "languages": ["ru", "kk", "en"],
            "probs": {"ru": 0.6, "kk": 0.2, "en": 0.2},
        },
        company_size=size_by_name[legal_name],
    )
