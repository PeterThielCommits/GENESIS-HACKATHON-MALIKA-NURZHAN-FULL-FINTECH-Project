"""FX timeline generation (contract 9.3).

Approach: mean-reverting random walk / discrete Ornstein-Uhlenbeck process
per pair, applied on micro-rate integers with fixed precision. Only pairs
that need conversion to the functional currency are generated. Weekend gaps
are not published (Section 9.3: "В выходные дни значения могут отсутствовать
согласно профилю рынка").

Policy direction implemented in ``rate_for_event`` (Section 9.3):
  - primary date = event date;
  - fallback = last published rate before the event date (weekend gap);
  - reverse quoting allowed when the inverse pair exists;
  - for same-currency events the rate is 1.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from gen.calendar import is_business_day, next_business_day, period_bounds
from gen.company import CompanyProfile
from gen.rng import NamespacedRNG


class FXError(ValueError):
    pass


#: Deterministic OU parameters per pair (synthetic market levels).
#: ``mean_micro``/``vol_micro`` are in units of 10^-4 (rate = micro/10^4).
_PAIR_PARAMS: dict[str, dict[str, object]] = {
    "USD/KZT": {"mean_micro": 33000, "theta": 0.3, "vol_micro": 1200},
    "EUR/KZT": {"mean_micro": 56000, "theta": 0.3, "vol_micro": 1600},
}

_FX_SOURCE_CODES = ["SRC-FX-SIM-A", "SRC-FX-SIM-B"]

#: Decimal places of the generated rate values (fixed precision).
_RATE_PRECISION = 4


@dataclass
class FXRate:
    pair: str
    effective_date: str
    rate_decimal: str
    source_code: str
    publication_timestamp: str

    def to_public(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "effective_date": self.effective_date,
            "rate_decimal": self.rate_decimal,
            "source_code": self.source_code,
            "publication_timestamp": self.publication_timestamp,
        }


def _pair_params(pair: str) -> dict[str, object]:
    params = _PAIR_PARAMS.get(pair)
    if params is None:
        raise FXError(f"no FX parameters for pair: {pair!r}")
    return params


def generate_fx_rates(
    rng: NamespacedRNG,
    company: CompanyProfile,
    periods: list[str],
) -> list[FXRate]:
    """Generate the public FX rate timeline for every supported pair."""
    functional = company.functional_currency
    pairs = sorted(
        {f"{c}/{functional}" for c in company.supported_currencies if c != functional}
    )
    rates: list[FXRate] = []
    for pair in pairs:
        params = _pair_params(pair)
        mean = Decimal(params["mean_micro"])  # type: ignore[arg-type]
        theta = Decimal(str(params["theta"]))  # type: ignore[arg-type]
        vol = Decimal(params["vol_micro"])  # type: ignore[arg-type]
        state = mean
        for period in periods:
            start, end = period_bounds(period, company.timezone)
            day = start
            while day <= end:
                if is_business_day(day):
                    state = int(
                        mean
                        + theta * (state - mean)
                        + vol * (Decimal(str(rng.random())) - Decimal("0.5"))
                    )
                    rate = Decimal(state) / Decimal(10**_RATE_PRECISION)
                    rates.append(FXRate(
                        pair=pair,
                        effective_date=day.isoformat(),
                        rate_decimal=f"{rate:f}",
                        source_code=rng.choice(_FX_SOURCE_CODES),
                        publication_timestamp=f"{day.isoformat()}T09:00:00+06:00",
                    ))
                day = next_business_day(day)
    return sorted(rates, key=lambda r: (r.pair, r.effective_date, r.publication_timestamp))


def rate_on_or_before(rates: list[FXRate], pair: str, date_str: str) -> Decimal | None:
    """Latest published rate for ``pair`` effective on or before ``date_str``."""
    best: Decimal | None = None
    best_eff = ""
    for r in rates:
        if r.pair == pair and r.effective_date <= date_str and r.effective_date > best_eff:
            best = Decimal(r.rate_decimal)
            best_eff = r.effective_date
    return best


def rate_for_event(
    rates: list[FXRate],
    from_currency: str,
    to_currency: str,
    event_date: str,
) -> Decimal:
    """Rate to apply for an event (policy-defined direction, Section 9.3)."""
    if from_currency == to_currency:
        return Decimal("1")
    pair = f"{from_currency}/{to_currency}"
    rate = rate_on_or_before(rates, pair, event_date)
    if rate is None:
        # Reverse quoting (Section 9.3): try the inverse pair.
        rev = rate_on_or_before(rates, f"{to_currency}/{from_currency}", event_date)
        if rev is not None:
            rate = Decimal(1) / rev
    if rate is None:
        raise FXError(f"no FX rate for {pair} on or before {event_date}")
    return rate


def functional_rate(
    rates: list[FXRate],
    functional_currency: str,
    source_currency: str,
    event_date: str,
) -> Decimal:
    """Rate from ``source_currency`` to ``functional_currency`` for an event."""
    return rate_for_event(rates, source_currency, functional_currency, event_date)


def rate_for_line(
    rates: list[FXRate],
    functional_currency: str,
    source_currency: str,
    event_date: str,
) -> Decimal:
    """Alias of :func:`functional_rate` for JE line rates (Section 9.3)."""
    return functional_rate(rates, functional_currency, source_currency, event_date)
