"""Synthetic counterparties generation (contract 8.1, counterparty model)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gen.rng import NamespacedRNG

#: Fictional counterparty legal names (Section 8.1: synthetic only).
_CP_NAMES = [
    "Kaz Logistics Co",
    "Delta Freight",
    "Alpha Supplies",
    "Omega Solutions",
    "Stellar Retail",
    "Titan Energy",
    "Vertex Media",
    "Polaris Bank (simulated)",
    "Orion Traders",
    "Nova Health Services",
]

_CP_NAME_VARIANTS: dict[str, dict[str, str]] = {
    "Kaz Logistics Co": {
        "ru": "Каз Логистикс Ко",
        "kk": "Қаз Логистикс Ко",
        "en": "Kaz Logistics Co",
    },
    "Delta Freight": {
        "ru": "«Дельта Фрайт»",
        "kk": "«Дельта Фрайт»",
        "en": "Delta Freight",
    },
    "Alpha Supplies": {
        "ru": "«Альфа Саплайс»",
        "kk": "«Альфа Саплайс»",
        "en": "Alpha Supplies",
    },
    "Omega Solutions": {
        "ru": "«Омега Солюшнс»",
        "kk": "«Омега Солюшнс»",
        "en": "Omega Solutions",
    },
    "Stellar Retail": {
        "ru": "«Стеллар Ритейл»",
        "kk": "«Стеллар Ритейл»",
        "en": "Stellar Retail",
    },
    "Titan Energy": {
        "ru": "«Титан Энерджи»",
        "kk": "«Титан Энерджи»",
        "en": "Titan Energy",
    },
    "Vertex Media": {
        "ru": "«Вертекс Медиа»",
        "kk": "«Вертекс Медиа»",
        "en": "Vertex Media",
    },
    "Polaris Bank (simulated)": {
        "ru": "«Полярис Банк» (симуляция)",
        "kk": "«Полярис Банк» (симуляция)",
        "en": "Polaris Bank (simulated)",
    },
    "Orion Traders": {
        "ru": "«Орион Трейдерс»",
        "kk": "«Орион Трейдерс»",
        "en": "Orion Traders",
    },
    "Nova Health Services": {
        "ru": "«Нова Хилз Сервис»",
        "kk": "«Нова Хилз Сервис»",
        "en": "Nova Health Services",
    },
}


@dataclass
class Counterparty:
    counterparty_id: str
    name_variants: dict[str, str]
    jurisdiction_code: str

    def to_public(self) -> dict[str, Any]:
        return {
            "counterparty_id": self.counterparty_id,
            "name_variants": dict(self.name_variants),
            "jurisdiction_code": self.jurisdiction_code,
        }


def generate_counterparties(rng: NamespacedRNG, count: int) -> list[Counterparty]:
    """Generate ``count`` synthetic counterparties with unique IDs."""
    cps = []
    seen: set[str] = set()
    for i in range(count):
        legal = rng.choice(_CP_NAMES)
        cid = f"CP-{rng.randint(100000, 999999):06d}"
        while cid in seen or any(c.counterparty_id == cid for c in cps):
            cid = f"CP-{rng.randint(100000, 999999):06d}"
        seen.add(cid)
        cps.append(Counterparty(
            counterparty_id=cid,
            name_variants=dict(_CP_NAME_VARIANTS[legal]),
            jurisdiction_code="XA",
        ))
    return sorted(cps, key=lambda c: c.counterparty_id)
