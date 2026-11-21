"""Deterministic FX timeline on integer scaled rates (Phase 3.3, 9.3).

The process is a discrete mean-reverting (Ornstein–Uhlenbeck style) random walk
expressed in *integer* scaled units. No floats are ever involved:

     rate[t+1] = rate[t] + (base - rate[t]) * num // den + noise

Rates are published on business days only (configurable), and the lookup helper
implements the policy's ``last_available_on_or_before`` fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, Sequence

from contracts.errors import ConfigError
from gen.core.rng import RngService


@dataclass(frozen=True)
class FxPoint:
    pair: str
    effective_date: date
    rate_scaled: int
    scale: int
    source_code: str

    @property
    def rate_decimal(self) -> Decimal:
        return Decimal(self.rate_scaled).scaleb(-self.scale)


@dataclass(frozen=True)
class FxTimeline:
    """Immutable per-pair rate history with policy-aware lookups."""

    scale: int
    points: tuple[FxPoint, ...]
    weekend_publication: bool

    def pairs(self) -> tuple[str, ...]:
        return tuple(sorted({point.pair for point in self.points}))

    def _ordered(self, pair: str) -> list[FxPoint]:
        selected = [point for point in self.points if point.pair == pair]
        return sorted(selected, key=lambda point: point.effective_date)

    def rate_on(self, pair: str, day: date, *, fallback: str = "last_available_on_or_before") -> FxPoint:
        """Resolve the policy rate for ``pair`` on ``day``."""
        series = self._ordered(pair)
        if not series:
            raise ConfigError("no FX history for pair", pair=pair)
        if fallback == "exact_date_only":
            for point in series:
                if point.effective_date == day:
                    return point
            raise ConfigError("no FX rate published on exact date", pair=pair, day=day.isoformat())
        if fallback != "last_available_on_or_before":
            raise ConfigError("unknown fx fallback rule", rule=fallback)
        candidates = [point for point in series if point.effective_date <= day]
        if not candidates:
            raise ConfigError("no FX rate available before date", pair=pair, day=day.isoformat())
        return candidates[-1]

    def describe(self) -> dict[str, object]:
        return {
            "scale": self.scale,
            "weekend_publication": self.weekend_publication,
            "pairs": {pair: len(self._ordered(pair)) for pair in self.pairs()},
        }


def generate_fx_timeline(
    rng: RngService,
    *,
    pairs: Sequence[str],
    base_rate_scaled: dict[str, int],
    noise_amplitude_scaled: dict[str, int],
    mean_reversion_numerator: int,
    mean_reversion_denominator: int,
    scale: int,
    sources: Sequence[str],
    weekend_publication: bool,
    first_day: date,
    last_day: date,
) -> FxTimeline:
    """Deterministically build a rate history for every configured pair."""
    if not pairs:
        raise ConfigError("FX timeline requires at least one pair")
    if first_day > last_day:
        raise ConfigError("FX timeline range is inverted")
    if not 1 <= scale <= 12:
        raise ConfigError("FX scale out of range", scale=scale)

    days = _business_days(first_day, last_day, weekend_publication)
    if not days:
        # Fall back to every calendar day so a tiny range still produces a rate.
        days = list(_all_days(first_day, last_day))

    points: list[FxPoint] = []
    for pair in sorted(pairs):
        if pair not in base_rate_scaled or pair not in noise_amplitude_scaled:
            raise ConfigError("pair lacks base rate or noise amplitude", pair=pair)
        stream = rng.stream(f"fx/{pair}")
        base = base_rate_scaled[pair]
        amplitude = noise_amplitude_scaled[pair]
        current = base
        for day in days:
            drift = (base - current) * mean_reversion_numerator // mean_reversion_denominator
            noise = stream.randint(-amplitude, amplitude)
            current = max(1, current + drift + noise)
            source = str(stream.choice(sources))
            points.append(
                FxPoint(
                    pair=pair,
                    effective_date=day,
                    rate_scaled=current,
                    scale=scale,
                    source_code=source,
                )
            )
    points.sort(key=lambda point: (point.pair, point.effective_date))
    return FxTimeline(scale=scale, points=tuple(points), weekend_publication=weekend_publication)


def _all_days(first_day: date, last_day: date) -> Iterable[date]:
    cursor = first_day
    while cursor <= last_day:
        yield cursor
        cursor += timedelta(days=1)


def _business_days(first_day: date, last_day: date, weekend_publication: bool) -> list[date]:
    if weekend_publication:
        return list(_all_days(first_day, last_day))
    return [day for day in _all_days(first_day, last_day) if day.weekday() < 5]
