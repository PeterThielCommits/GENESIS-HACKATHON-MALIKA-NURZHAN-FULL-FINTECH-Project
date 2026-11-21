"""Independent money, FX and company-timezone primitives for the verifier.

Implemented solely on Python 3.11 stdlib + ``contracts.currency`` without
importing ``core/``, ``invariants/``, or ``gen/`` to avoid common-mode
implementation dependencies (Master TZ sections 9.3, 12.4, 13.2).

Money conversion uses exact rational arithmetic (``fractions.Fraction``)
with one single integer rounding step under the policy rounding mode
(``half_even`` or ``half_up``), eliminating intermediate precision loss
even for inverse FX division.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from contracts.currency import exponent_of

_RATE_RE = re.compile(r"^[0-9]{1,24}(?:\.[0-9]{1,24})?$")
_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1


@dataclass(frozen=True)
class FxConversionResult:
    """Exact outcome of converting an integer minor-unit amount."""

    exact_minor: Fraction
    rounded_minor: int
    rounding_mode: str
    inverted: bool
    n_round: int = 1


def require_minor_int(value: Any, label: str = "amount_minor") -> int:
    """Validate that ``value`` is a signed int64 integer (never bool/float)."""
    if type(value) is not int:
        raise ValueError(f"{label}: integer minor units required, got {type(value).__name__}")
    if not (_INT64_MIN <= value <= _INT64_MAX):
        raise ValueError(f"{label}: value outside signed int64 range")
    return value


def parse_rate_fraction(rate_text: str) -> Fraction:
    """Parse a strictly positive fixed-point decimal rate string as Fraction."""
    if not isinstance(rate_text, str) or _RATE_RE.fullmatch(rate_text) is None:
        raise ValueError(
            f"invalid FX rate {rate_text!r}: expected positive fixed-point string"
        )
    dec = Decimal(rate_text)
    if dec <= 0:
        raise ValueError(f"FX rate must be strictly positive, got {rate_text!r}")
    return Fraction(dec)


def round_fraction_to_int(value: Fraction, rounding_mode: str) -> int:
    """Round an exact rational to an integer using ``half_even`` or ``half_up``."""
    if rounding_mode not in ("half_even", "half_up"):
        raise ValueError(f"unsupported rounding mode: {rounding_mode!r}")
    if value == 0:
        return 0
    sign = -1 if value < 0 else 1
    num = abs(value.numerator)
    den = value.denominator
    quotient, remainder = divmod(num, den)
    twice_rem = 2 * remainder
    if twice_rem < den:
        rounded_abs = quotient
    elif twice_rem > den:
        rounded_abs = quotient + 1
    else:
        if rounding_mode == "half_up":
            rounded_abs = quotient + 1
        else:
            rounded_abs = quotient + (quotient & 1)
    return sign * rounded_abs


def convert_minor_with_pair(
    amount_minor: int,
    source_currency: str,
    target_currency: str,
    pair: str,
    rate_text: str,
    rounding_mode: str,
) -> FxConversionResult:
    """Convert ``amount_minor`` from ``source_currency`` to ``target_currency``.

    Pair notation ``BASE/QUOTE`` means ``QUOTE`` major units per 1 ``BASE``
    major unit:
      - ``pair == f"{source_currency}/{target_currency}"`` -> multiply by rate
      - ``pair == f"{target_currency}/{source_currency}"`` -> divide by rate
    """
    amt = require_minor_int(amount_minor, "amount_minor")
    exp_src = exponent_of(source_currency)
    exp_tgt = exponent_of(target_currency)
    rate_frac = parse_rate_fraction(rate_text)

    if source_currency == target_currency:
        if rate_frac != 1:
            raise ValueError("same-currency conversion rate must equal 1")
        return FxConversionResult(
            exact_minor=Fraction(amt),
            rounded_minor=amt,
            rounding_mode=rounding_mode,
            inverted=False,
            n_round=0,
        )

    direct_pair = f"{source_currency}/{target_currency}"
    inverse_pair = f"{target_currency}/{source_currency}"
    scale = Fraction(10**exp_tgt, 10**exp_src)

    if pair == direct_pair:
        exact = Fraction(amt) * rate_frac * scale
        inverted = False
    elif pair == inverse_pair:
        exact = Fraction(amt) * scale / rate_frac
        inverted = True
    else:
        raise ValueError(
            f"FX pair {pair!r} does not match {source_currency}->{target_currency}"
        )

    rounded = round_fraction_to_int(exact, rounding_mode)
    if not (_INT64_MIN <= rounded <= _INT64_MAX):
        raise ValueError("converted minor amount outside signed int64 range")
    return FxConversionResult(
        exact_minor=exact,
        rounded_minor=rounded,
        rounding_mode=rounding_mode,
        inverted=inverted,
        n_round=1,
    )


def parse_iso_instant(text: str) -> datetime:
    """Parse an ISO-8601 timestamp string that MUST carry a UTC offset."""
    if not isinstance(text, str) or not text:
        raise ValueError(f"invalid ISO-8601 timestamp: {text!r}")
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    dt = datetime.fromisoformat(normalized)
    if dt.utcoffset() is None:
        raise ValueError(f"timestamp missing explicit timezone offset: {text!r}")
    return dt


def to_company_date(ts_or_date: str, company_timezone: str) -> date:
    """Resolve an ISO date or offset-aware timestamp in ``company_timezone``."""
    if not isinstance(ts_or_date, str) or not ts_or_date:
        raise ValueError(f"missing event date/timestamp: {ts_or_date!r}")
    try:
        tz = ZoneInfo(company_timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown IANA timezone: {company_timezone!r}") from exc

    if _DATE_ONLY_RE.fullmatch(ts_or_date):
        return date.fromisoformat(ts_or_date)
    inst = parse_iso_instant(ts_or_date)
    return inst.astimezone(tz).date()


def to_utc_date(ts_or_date: str) -> date | None:
    """Return the UTC calendar date if ``ts_or_date`` carries an offset, else None."""
    if not isinstance(ts_or_date, str) or _DATE_ONLY_RE.fullmatch(ts_or_date):
        return None
    inst = parse_iso_instant(ts_or_date)
    return inst.astimezone(ZoneInfo("UTC")).date()


def compute_fiscal_period(
    local_date: date,
    fiscal_year_start: str,
    fiscal_period_rule: str,
    period_calendar: Any = None,
) -> str:
    """Compute fiscal period from company local date and fiscal settings."""
    if isinstance(period_calendar, list):
        for entry in period_calendar:
            if (
                isinstance(entry, dict)
                and isinstance(entry.get("start_date"), str)
                and isinstance(entry.get("end_date"), str)
                and isinstance(entry.get("period_id"), str)
            ):
                s = date.fromisoformat(entry["start_date"])
                e = date.fromisoformat(entry["end_date"])
                if s <= local_date <= e:
                    return entry["period_id"]

    fy_start = date.fromisoformat(fiscal_year_start)
    if fy_start.day != 1:
        raise ValueError(f"fiscal_year_start must be month-aligned (day=1): {fiscal_year_start!r}")

    if fiscal_period_rule == "monthly":
        return f"{local_date.year:04d}-{local_date.month:02d}"
    if fiscal_period_rule == "quarterly":
        fy_year = local_date.year if local_date.month >= fy_start.month else local_date.year - 1
        quarter = ((local_date.month - fy_start.month) % 12) // 3 + 1
        return f"{fy_year:04d}-Q{quarter}"
    raise ValueError(f"unsupported fiscal_period_rule: {fiscal_period_rule!r}")


__all__ = [
    "FxConversionResult",
    "compute_fiscal_period",
    "convert_minor_with_pair",
    "parse_iso_instant",
    "parse_rate_fraction",
    "require_minor_int",
    "round_fraction_to_int",
    "to_company_date",
    "to_utc_date",
]
