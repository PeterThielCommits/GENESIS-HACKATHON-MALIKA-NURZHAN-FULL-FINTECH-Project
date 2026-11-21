"""Money arithmetic per TwinLedger contract 9.1.

Rules:
  - stored amounts are integer minor units (REQ-MONEY-001);
  - Decimal rates are created from strings, never floats (REQ-MONEY-002);
  - no implicit currency mixing (REQ-MONEY-004);
  - rounding mode is explicit everywhere it matters (REQ-MONEY-003);
  - float is never used for totals (REQ-MONEY-001);
  - exponent registry: KZT 2, USD 2, EUR 2, JPY 0, KWD 3 (Section 9.1).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any

#: Currency exponent registry (configuration reference, Section 9.1).
CURRENCY_EXPONENTS: dict[str, int] = {
    "KZT": 2,
    "USD": 2,
    "EUR": 2,
    "JPY": 0,
    "KWD": 3,
}


class MoneyError(ValueError):
    """Money arithmetic error."""


def exponent(currency: str) -> int:
    """Exponent of a currency; raises MoneyError for unknown currency."""
    if not isinstance(currency, str) or currency not in CURRENCY_EXPONENTS:
        raise MoneyError(f"unknown currency: {currency!r}")
    return CURRENCY_EXPONENTS[currency]


def minor_divisor(currency: str) -> Decimal:
    return Decimal(10) ** exponent(currency)


def parse_rate(value: Any) -> Decimal:
    """Parse a rate: Decimal passthrough, int passthrough, else from string."""
    if isinstance(value, Decimal):
        rate = value
    elif isinstance(value, bool):
        raise MoneyError("rate must not be a boolean")
    elif isinstance(value, int):
        rate = Decimal(value)
    elif isinstance(value, str):
        try:
            rate = Decimal(value.strip())
        except InvalidOperation as exc:
            raise MoneyError(f"invalid Decimal rate: {value!r}") from exc
    else:
        raise MoneyError(f"invalid rate type: {type(value).__name__}")
    if not rate.is_finite():
        raise MoneyError("rate must be finite")
    return rate


def validate_amount(amount_minor: int) -> None:
    if isinstance(amount_minor, bool) or not isinstance(amount_minor, int):
        raise MoneyError(f"amount_minor must be int, got {type(amount_minor).__name__}")
    if amount_minor < 0:
        raise MoneyError(f"amount_minor must be non-negative, got {amount_minor}")


def validate_amount_value(amount: Decimal) -> None:
    if not isinstance(amount, Decimal) or not amount.is_finite():
        raise MoneyError(f"amount must be a finite Decimal, got {amount!r}")


def to_decimal(amount_minor: int, currency: str) -> Decimal:
    """Minor units -> Decimal of the currency unit (exact)."""
    validate_amount(amount_minor)
    return Decimal(amount_minor) / minor_divisor(currency)


def to_minor(amount: Decimal, currency: str, rounding: str = ROUND_HALF_EVEN) -> int:
    """Decimal of the currency unit -> integer minor units.

    Rounding mode is passed explicitly. ``rounding`` must be a
    ``decimal.ROUND_*`` mode name string.
    """
    validate_amount_value(amount)
    if not isinstance(rounding, str):
        raise MoneyError("rounding mode must be a string")
    scaled = amount * minor_divisor(currency)
    return int(scaled.to_integral_value(rounding=rounding))


def convert_minor(
    amount_minor: int,
    from_currency: str,
    to_currency: str,
    rate: Any,
    rounding: str = ROUND_HALF_EVEN,
) -> tuple[int, dict]:
    """Convert integer minor units between currencies.

    ``rate`` is interpreted as units of ``to_currency`` per unit of
    ``from_currency``: ``converted = (amount / 10**exp(from)) * rate``,
    rounded to integer minor units of ``to_currency`` with explicit
    rounding mode.

    Returns ``(minor_result, meta)`` where meta carries the original and
    rounded values, the rounding mode and the number of rounding
    operations for the REQ-MONEY-009 tolerance model (``n_round * 1``).
    """
    validate_amount(amount_minor)
    if from_currency == to_currency:
        rate_dec = parse_rate(rate)
        return amount_minor, {
            "original": amount_minor,
            "rounded": amount_minor,
            "mode": str(rounding),
            "round_count": 0,
            "rate_applied": f"{rate_dec:f}",
        }
    rate_dec = parse_rate(rate)
    source = Decimal(amount_minor).scaleb(-exponent(from_currency))
    converted = source * rate_dec
    rounded = to_minor(converted, to_currency, rounding=rounding)
    return rounded, {
        "original": amount_minor,
        "rounded": rounded,
        "mode": str(rounding),
        "round_count": int(rounded != converted),
        "rate_applied": f"{rate_dec:f}",
    }
