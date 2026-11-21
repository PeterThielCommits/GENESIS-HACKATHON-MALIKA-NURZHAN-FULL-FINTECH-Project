"""Timezone/period calendar utilities (contract 9.4; REQ-TIME-001..005).

Rules implemented:
  - timestamps are serialized as ISO-8601 with timezone offset (REQ-TIME-001);
  - company period rules are evaluated in the company timezone
    (REQ-TIME-002);
  - zoneinfo/IANA identifiers only (REQ-TIME-003);
  - DST handling is delegated to zoneinfo: the generator resolves instants
    through ``astimezone`` so DST is respected when the zone has it.
    Companies without DST (e.g. Asia/Almaty) have control tests showing
    no fake shift.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal  # noqa: F401  (kept for API symmetry)
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from gen.rng import NamespacedRNG


class CalendarError(ValueError):
    pass


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp that carries a timezone offset/zone.

    Rejects naive timestamps and non-string input.
    """
    if not isinstance(value, str):
        raise CalendarError(f"timestamp must be a string, got {type(value).__name__}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CalendarError(f"invalid ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CalendarError(f"timestamp lacks timezone offset: {value!r}")
    return parsed


def get_tz(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise CalendarError(f"unknown timezone: {tz_name!r}") from exc


def local_date(ts: str, tz_name: str) -> date:
    """Local date of ``ts`` in the company timezone (REQ-TIME-002)."""
    return parse_timestamp(ts).astimezone(get_tz(tz_name)).date()


def period_for_date(d: date, tz_name: str) -> str:
    """Company fiscal period id of a local date (monthly rule)."""
    tz = get_tz(tz_name)
    aware = datetime.combine(d, time.min, tzinfo=tz)
    local = aware.astimezone(tz)
    return f"{local.year:04d}-{local.month:02d}"


def period_for_timestamp(ts: str, tz_name: str) -> str:
    return period_for_date(parse_timestamp(ts).astimezone(get_tz(tz_name)).date(), tz_name)


def is_business_day(d: date) -> bool:
    """Mon–Fri check (Section 9.4: рабочий день определён без праздников)."""
    return d.weekday() < 5


def next_business_day(d: date) -> date:
    """First business day strictly after ``d``.

    The loop is bounded to 10,000 steps to protect against an
    inconsistent ``d`` (e.g. a string); ``is_business_day`` is a pure
    ``weekday() < 5`` predicate so 10,000 business-day gaps cannot
    occur with a valid ``date`` input.
    """
    day = d
    for _ in range(10_000):
        day += timedelta(days=1)
        if is_business_day(day):
            return day
    raise ValueError(f"could not advance business day from {d!r}")


def business_days_between(start: date, end: date) -> int:
    day, count = start, 0
    while day <= end:
        if is_business_day(day):
            count += 1
        day += timedelta(days=1)
    return count


def period_bounds(period_id: str, tz_name: str) -> tuple[date, date]:
    """Start/end dates of a monthly fiscal period id like ``2025-03``."""
    try:
        year = int(period_id[:4])
        month = int(period_id[5:7])
    except (ValueError, IndexError) as exc:
        raise CalendarError(f"invalid fiscal period id: {period_id!r}") from exc
    if not (1 <= month <= 12):
        raise CalendarError(f"invalid month in fiscal period id: {period_id!r}")
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    start = date(year, month, 1)
    return start, end


def ts_in_period(rng: NamespacedRNG, tz_name: str, period_id: str) -> str:
    """Random business timestamp inside a fiscal period (local time)."""
    start, end = period_bounds(period_id, tz_name)
    for _ in range(50):
        ts = datetime.combine(start, time.min, tzinfo=get_tz(tz_name)).replace(
            day=rng.randint(start.day, end.day),
            hour=rng.randint(9, 17),
            minute=rng.randint(0, 59),
        )
        if start <= ts.date() <= end:
            return ts.astimezone(get_tz(tz_name)).isoformat()
    raise CalendarError(f"could not place a business timestamp in {period_id}")


def add_days(ts: str, days: int) -> str:
    return (parse_timestamp(ts) + timedelta(days=days)).isoformat()


def add_minutes(ts: str, minutes: int) -> str:
    return (parse_timestamp(ts) + timedelta(minutes=minutes)).isoformat()


def utc_ts(d: date, h: int, m: int = 0) -> str:
    return datetime.combine(d, time(h, m), tzinfo=timezone.utc).isoformat()


def build_period_calendar(period_ids: Iterable[str], tz_name: str) -> list[dict]:
    """Public period calendar rows: period_id, start_date, end_date, is_open."""
    rows = []
    for period_id in sorted(set(period_ids)):
        start, end = period_bounds(period_id, tz_name)
        rows.append(
            {
                "period_id": period_id,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "is_open": True,
            }
        )
    return rows


def fiscal_periods_for_year(year: int) -> list[str]:
    """Monthly fiscal period ids ``YYYY-MM``..``YYYY-12``."""
    return [f"{year:04d}-{m:02d}" for m in range(1, 13)]
