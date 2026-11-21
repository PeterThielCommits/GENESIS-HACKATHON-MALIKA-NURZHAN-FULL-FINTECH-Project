"""Synthetic reference data: chart of accounts, names, banks (Phase 3.2).

Everything here is invented. Names are assembled from generated syllables so no
real person, company or bank is reproduced; VAT/bank markers live in a private
synthetic namespace (``XTV-``/``XBL-``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from contracts.errors import ConfigError

CHART_TEMPLATE: Final[tuple[dict[str, str], ...]] = (
    {"code": "1000", "name": "Cash — operating bank account", "type": "ASSET",
     "normal_balance": "DEBIT", "currency_scope": "FUNCTIONAL", "role": "bank"},
    {"code": "1100", "name": "Trade receivables", "type": "ASSET",
     "normal_balance": "DEBIT", "currency_scope": "FUNCTIONAL", "role": "receivable"},
    {"code": "1200", "name": "Customer advances received", "type": "ASSET",
     "normal_balance": "DEBIT", "currency_scope": "FUNCTIONAL", "role": "advance"},
    {"code": "2000", "name": "Trade payables", "type": "LIABILITY",
     "normal_balance": "CREDIT", "currency_scope": "FUNCTIONAL", "role": "payable"},
    {"code": "4000", "name": "Service revenue", "type": "REVENUE",
     "normal_balance": "CREDIT", "currency_scope": "FUNCTIONAL", "role": "revenue"},
    {"code": "4900", "name": "FX gain / loss", "type": "REVENUE",
     "normal_balance": "CREDIT", "currency_scope": "FUNCTIONAL", "role": "fx_gain_loss"},
    {"code": "5000", "name": "Operating expenses", "type": "EXPENSE",
     "normal_balance": "DEBIT", "currency_scope": "FUNCTIONAL", "role": "expense"},
    {"code": "3000", "name": "Share capital", "type": "EQUITY",
     "normal_balance": "CREDIT", "currency_scope": "FUNCTIONAL", "role": "equity"},
)

ROLE_TO_ACCOUNT_CODE: Final[dict[str, str]] = {
    entry["role"]: entry["code"] for entry in CHART_TEMPLATE
}

_ONSET: Final[tuple[str, ...]] = (
    "Al", "Bar", "Dzh", "Er", "Ka", "Nur", "Sar", "Tal", "Zha", "Kus", "Te", "Mir",
)
_NUCLEUS: Final[tuple[str, ...]] = ("an", "en", "ik", "or", "ul", "ay", "es", "im")
_CODA: Final[tuple[str, ...]] = ("bek", "zhan", "ta", "dor", "mir", "khan", "sai", "tai")

_COMPANY_SUFFIX: Final[dict[str, str]] = {
    "en": ("Logistics Group", "Trading House", "Industrial Services", "Technology Partners",
           "Agro Holding", "Engineering Bureau"),
    "ru": ("Логистическая группа", "Торговый дом", "Индустриальные сервисы",
           "Технологическое партнёрство", "Агрохолдинг", "Инженерное бюро"),
    "kk": ("Логистикалық тобы", "Сауда үйі", "Индустриялық сервистер",
           "Технологиялық серіктестік", "Агрохолдинг", "Инженерлік бюро"),
}

_BANK_NAMES: Final[tuple[str, ...]] = (
    "Synthetic Steppe Bank", "Synthetic Orda Bank", "Synthetic Meridian Bank",
    "Synthetic Tien-Shan Bank",
)


@dataclass(frozen=True)
class GeneratedName:
    en: str
    ru: str
    kk: str

    def variants(self) -> dict[str, str]:
        return {"en": self.en, "ru": self.ru, "kk": self.kk}


def make_stem(rng_stream, syllables: int = 2) -> str:
    """Build a synthetic proper-noun stem from syllables."""
    parts: list[str] = []
    first = str(rng_stream.choice(_ONSET))
    parts.append(first)
    for _ in range(max(1, syllables - 1)):
        parts.append(str(rng_stream.choice(_NUCLEUS)))
    parts.append(str(rng_stream.choice(_CODA)))
    return "".join(parts)


def make_company_name(rng_stream, index: int) -> GeneratedName:
    stem = make_stem(rng_stream)
    second = make_stem(rng_stream)
    english_suffix = str(rng_stream.choice(_COMPANY_SUFFIX["en"]))
    russian_suffix = str(rng_stream.choice(_COMPANY_SUFFIX["ru"]))
    kazakh_suffix = str(rng_stream.choice(_COMPANY_SUFFIX["kk"]))
    return GeneratedName(
        en=f"{stem} {second} {english_suffix}",
        ru=f"{stem} {second} {russian_suffix}",
        kk=f"{stem} {second} {kazakh_suffix}",
    )


def make_counterparty_name(rng_stream) -> GeneratedName:
    stem = make_stem(rng_stream)
    second = make_stem(rng_stream)
    english_suffix = str(rng_stream.choice(_COMPANY_SUFFIX["en"]))
    russian_suffix = str(rng_stream.choice(_COMPANY_SUFFIX["ru"]))
    kazakh_suffix = str(rng_stream.choice(_COMPANY_SUFFIX["kk"]))
    return GeneratedName(
        en=f"{stem} {second} {english_suffix}",
        ru=f"{stem} {second} {russian_suffix}",
        kk=f"{stem} {second} {kazakh_suffix}",
    )


def bank_name(rng_stream) -> str:
    return str(rng_stream.choice(_BANK_NAMES))


def bank_account_marker(rng_stream) -> str:
    return f"XBL-{rng_stream.random.randrange(10**9):09d}"


def chart_for_role(role: str) -> dict[str, str]:
    code = ROLE_TO_ACCOUNT_CODE.get(role)
    if code is None:
        raise ConfigError("unknown account role", role=role)
    for entry in CHART_TEMPLATE:
        if entry["code"] == code:
            return entry
    raise ConfigError("chart template inconsistent", role=role)  # pragma: no cover


SERVICE_CATALOG: Final[tuple[dict[str, str], ...]] = (
    {"en": "Freight forwarding, north corridor", "ru": "Экспедирование грузов, северный коридор",
     "kk": "Жүк экспедициясы, солтүстік дәліз"},
    {"en": "Warehouse handling services", "ru": "Услуги складской обработки",
     "kk": "Қойма өңдеу қызметтері"},
    {"en": "Monthly platform subscription", "ru": "Ежемесячная подписка на платформу",
     "kk": "Платформаға ай сайынғы жазылым"},
    {"en": "Customs documentation support", "ru": "Сопровождение таможенных документов",
     "kk": "Кедендік құжаттаманы сүйемелдеу"},
    {"en": "Industrial equipment maintenance", "ru": "Техническое обслуживание оборудования",
     "kk": "Жабдыққа техникалық қызмет"},
    {"en": "Engineering survey works", "ru": "Инженерно-изыскательские работы",
     "kk": "Инженерлік-іздестіру жұмыстары"},
)
