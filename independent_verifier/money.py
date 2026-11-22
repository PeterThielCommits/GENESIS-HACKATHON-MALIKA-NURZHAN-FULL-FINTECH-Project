"""Independent money / FX primitives (spec ``verifier_algorithm.md`` §2.1).

Second, separate derivation from the frozen specification — not a copy of
``core/money.py`` or ``verifier/money_time.py``. Exact rational arithmetic only;
binary floats never touch money.
"""

from __future__ import annotations

import json
import re
from fractions import Fraction
from pathlib import Path

import contracts

_RATE_RE = re.compile(r"^[0-9]{1,24}(?:\.[0-9]{1,24})?$")


def currency_exponents() -> dict[str, int]:
    registry_path = Path(contracts.__file__).resolve().parent / "currency.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    table = registry.get("currencies", registry)
    rows = table.values() if isinstance(table, dict) else table
    out: dict[str, int] = {}
    for row in rows:
        if isinstance(row, dict) and "code" in row and "exponent" in row:
            out[str(row["code"])] = int(row["exponent"])
    if not out:
        raise ValueError("currency registry carried no exponents")
    return out


def parse_rate(rate_decimal: str) -> Fraction:
    if not isinstance(rate_decimal, str) or not _RATE_RE.fullmatch(rate_decimal):
        raise ValueError(f"FX rate {rate_decimal!r} is not a positive fixed-point decimal")
    rate = Fraction(rate_decimal)
    if rate <= 0:
        raise ValueError("FX rate must be positive")
    return rate


def round_half(value: Fraction, mode: str) -> int:
    """Round a Fraction to the nearest integer; ties per ``mode`` (half_up|half_even)."""
    if mode not in ("half_up", "half_even"):
        raise ValueError(f"unsupported rounding_mode {mode!r}")
    sign = 1 if value >= 0 else -1
    magnitude = abs(value)
    q, r = divmod(magnitude.numerator, magnitude.denominator)
    cmp = 2 * r - magnitude.denominator
    if cmp > 0 or (cmp == 0 and (mode == "half_up" or q % 2 == 1)):
        q += 1
    return sign * q


def convert_minor(
    amount_minor: int,
    rate_decimal: str,
    pair: str,
    source_currency: str,
    target_currency: str,
    rounding_mode: str,
    exponents: dict[str, int] | None = None,
) -> int:
    """Convert ``amount_minor`` of ``source_currency`` into ``target_currency`` minor units.

    ``pair`` is ``BASE/QUOTE`` meaning QUOTE major units per 1 BASE major unit.
    Exact ``Fraction`` arithmetic; ONE final integer rounding step (§2.1).
    """
    if isinstance(amount_minor, bool) or not isinstance(amount_minor, int):
        raise TypeError("amount_minor must be an integer")
    exp = exponents or currency_exponents()
    if source_currency not in exp or target_currency not in exp:
        raise ValueError("unsupported currency in conversion")
    base, _, quote = pair.partition("/")
    if not base or not quote or "/" in quote:
        raise ValueError(f"pair {pair!r} must have exactly one '/'")
    rate = parse_rate(rate_decimal)
    src_exp, dst_exp = exp[source_currency], exp[target_currency]
    if pair == f"{source_currency}/{target_currency}":
        exact = Fraction(amount_minor) * rate * Fraction(10**dst_exp, 10**src_exp)
    elif pair == f"{target_currency}/{source_currency}":
        exact = Fraction(amount_minor) * Fraction(10**dst_exp, 10**src_exp) / rate
    else:
        raise ValueError(f"pair {pair!r} is not oriented to {source_currency}/{target_currency}")
    return round_half(exact, rounding_mode)
