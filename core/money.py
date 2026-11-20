"""Exact FX primitive. Rate is target major units per source major unit."""
import re
from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP, localcontext

from contracts.currency import exponent_of

MODES = {'half_even': ROUND_HALF_EVEN, 'half_up': ROUND_HALF_UP}


def parse_rate(text: str) -> Decimal:
    if not isinstance(text, str) or not re.fullmatch(r'[0-9]{1,24}(?:\.[0-9]{1,24})?', text):
        raise ValueError('expected positive fixed-point rate, at most 24+24 digits')
    rate = Decimal(text)
    if not rate:
        raise ValueError('zero FX rate')
    return rate


@dataclass(frozen=True)
class Conversion:
    unrounded_minor: Decimal
    amount_minor: int
    mode: str
    n_round: int


def convert_minor(amount_minor: int, from_currency: str, to_currency: str,
                  rate: str, mode: str) -> Conversion:
    if type(amount_minor) is not int or not -(2**63) <= amount_minor < 2**63:
        raise ValueError('expected signed int64 minor units')
    if mode not in MODES:
        raise ValueError('unsupported rounding policy')
    multiplier = parse_rate(rate)
    shift = exponent_of(to_currency) - exponent_of(from_currency)
    if from_currency == to_currency and multiplier != 1:
        raise ValueError('same-currency rate must be one')
    # 19 amount digits + at most 48 rate digits; no intermediate rounding.
    with localcontext(Context(prec=68, rounding=MODES[mode])):
        raw = (Decimal(amount_minor) * multiplier).scaleb(shift)
        rounded = int(raw.to_integral_value())
    if not -(2**63) <= rounded < 2**63:
        raise ValueError('converted amount outside int64')
    return Conversion(raw, rounded, mode, 1)
