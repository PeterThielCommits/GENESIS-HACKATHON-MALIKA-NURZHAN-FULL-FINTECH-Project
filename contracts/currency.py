"""Currency exponent registry (TZ 9.1).

This is a configuration reference of the environment, not an attempt to
derive exponents from external code at runtime. Exponents are stored in
``contracts/currency.json`` (single source of truth); this module loads
and validates it.
"""

from __future__ import annotations

import json
from pathlib import Path

_CURRENCY_PATH = Path(__file__).with_name("currency.json")


def load_currency_registry() -> dict[str, int]:
    """Load {currency_code: exponent} from contracts/currency.json."""
    data = json.loads(_CURRENCY_PATH.read_text(encoding="utf-8"))
    registry: dict[str, int] = {}
    for entry in data["currencies"]:
        code = entry["code"]
        exp = entry["exponent"]
        if not isinstance(code, str) or not code:
            raise ValueError("currency code must be a non-empty string")
        if not isinstance(exp, int) or exp < 0 or exp > 6:
            raise ValueError(f"invalid exponent for {code}: {exp!r}")
        if code in registry:
            raise ValueError(f"duplicate currency code: {code}")
        registry[code] = exp
    return registry


def exponent_of(currency: str, registry: dict[str, int] | None = None) -> int:
    reg = registry if registry is not None else load_currency_registry()
    if currency not in reg:
        raise ValueError(f"unknown currency: {currency!r}")
    return reg[currency]


def is_known_currency(currency: str, registry: dict[str, int] | None = None) -> bool:
    reg = registry if registry is not None else load_currency_registry()
    return currency in reg
