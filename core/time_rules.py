"""Timezone-aware period calendar (REQ-TIME-001..005).

All period and cut-off decisions are derived from the *company* timezone and its
``policy.json`` period rule — never from the local time of the machine.
Wall-clock times that are ambiguous or non-existent (DST transitions) are
resolved by an explicit, documented policy (``prefer_earlier``/``prefer_later``/
``raise``) instead of appearing accidentally.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Any, Final, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from contracts.errors import TimeRuleError

AmbiguityPolicy = Literal["prefer_earlier", "prefer_later", "raise"]
AMBIGUITY_POLICIES: Final[tuple[str, ...]] = ("prefer_earlier", "prefer_later", "raise")

PERIOD_RULES: Final[tuple[str, ...]] = ("monthly", "quarterly", "annual")


def load_zone(name: str) -> ZoneInfo:
    """Load an IANA timezone, rejecting unknown identifiers."""
    if not isinstance(name, str) or not name:
        raise TimeRuleError("timezone name must be a non-empty string")
    if name in {"UTC", "utc"}:
        return ZoneInfo("UTC")
    if "/" not in name:
        raise TimeRuleError("timezone must be an IANA identifier", name=name)
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise TimeRuleError("unknown IANA timezone", name=name) from exc


def parse_timestamp(value: str, *, field: str = "timestamp") -> datetime:
    """Parse an ISO-8601 timestamp that *must* carry a UTC offset (REQ-TIME-001)."""
    if not isinstance(value, str):
        raise TimeRuleError("timestamp must be a string", field=field)
    text = value.strip()
    if not text:
        raise TimeRuleError("timestamp must not be empty", field=field)
    normalised = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        parsed = datetime.fromisoformat(normalised)
    except ValueError as exc:
        raise TimeRuleError("timestamp is not ISO-8601", field=field, value=value) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TimeRuleError(
            "timestamp must include a UTC offset", field=field, value=value
        )
    return parsed


def format_timestamp(moment: datetime) -> str:
    """Serialise to ISO-8601 with an explicit numeric offset (never 'Z')."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise TimeRuleError("cannot serialise a naive datetime")
    return moment.isoformat(timespec="seconds")


def to_company_local(moment: datetime, tz: tzinfo) -> datetime:
    return moment.astimezone(tz)


def local_wall_time(local_date: date, local_clock: time, zone: ZoneInfo) -> datetime:
    """Resolve a local wall-clock time to an unambiguous aware datetime."""
    naive = datetime.combine(local_date, local_clock)
    first = naive.replace(tzinfo=zone, fold=0)
    second = naive.replace(tzinfo=zone, fold=1)
    # Non-existent (spring-forward gap): both folds collapse onto the same instant
    # after normalisation and round-tripping changes the wall clock.
    first_round = first.astimezone(zone)
    if first.utcoffset() == second.utcoffset():
        return first
    raise TimeRuleError(
        "ambiguous local time requires an explicit ambiguity policy",
        local=naive.isoformat(),
        candidates=[first.isoformat(), second.isoformat()],
        _first_roundtrip=first_round.isoformat(),
    )


def resolve_local_wall_time(
    local_date: date,
    local_clock: time,
    zone: ZoneInfo,
    ambiguity: AmbiguityPolicy = "prefer_earlier",
) -> datetime:
    """Resolve a local wall clock honouring an explicit ambiguity policy."""
    if ambiguity not in AMBIGUITY_POLICIES:
        raise TimeRuleError(
            "unknown ambiguity policy", policy=ambiguity, allowed=list(AMBIGUITY_POLICIES)
        )
    naive = datetime.combine(local_date, local_clock)
    first = naive.replace(tzinfo=zone, fold=0)
    second = naive.replace(tzinfo=zone, fold=1)

    # Detect a non-existent local time: converting to UTC and back changes it.
    if first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != naive:
        if ambiguity == "raise":
            raise TimeRuleError(
                "non-existent local time (DST gap)", local=naive.isoformat(), zone=str(zone)
            )
        # Gap: shift forward by the transition delta. ``fold=0`` uses the pre-gap
        # offset and ``fold=1`` the post-gap offset, so the wall clock must move by
        # (post - pre) to land inside the new local time.
        pre = first.utcoffset() or timedelta(0)
        post = second.utcoffset() or timedelta(0)
        return (naive + (post - pre)).replace(tzinfo=zone)
    if first.utcoffset() == second.utcoffset():
        return first
    if ambiguity == "raise":
        raise TimeRuleError(
            "ambiguous local time (DST overlap)", local=naive.isoformat(), zone=str(zone)
        )
    return first if ambiguity == "prefer_earlier" else second


@dataclass(frozen=True)
class PeriodCalendar:
    """Deterministic fiscal period calendar for one company."""

    timezone_name: str
    period_rule: str
    fiscal_year_start_month: int = 1
    fiscal_year_start_day: int = 1
    cutoff_day_offset: int = 0
    ambiguity_policy: str = "prefer_earlier"

    def __post_init__(self) -> None:
        if self.period_rule not in PERIOD_RULES:
            raise TimeRuleError(
                "unsupported period rule", rule=self.period_rule, allowed=list(PERIOD_RULES)
            )
        if not 1 <= self.fiscal_year_start_month <= 12:
            raise TimeRuleError("fiscal_year_start_month must be 1..12")
        if not 1 <= self.fiscal_year_start_day <= 31:
            raise TimeRuleError("fiscal_year_start_day must be 1..31")
        if not isinstance(self.cutoff_day_offset, int):
            raise TimeRuleError("cutoff_day_offset must be an int")
        if self.ambiguity_policy not in AMBIGUITY_POLICIES:
            raise TimeRuleError("unknown ambiguity policy", policy=self.ambiguity_policy)
        load_zone(self.timezone_name)

    @property
    def zone(self) -> ZoneInfo:
        return load_zone(self.timezone_name)

    def fiscal_year_of(self, local_date: date) -> int:
        start = date(local_date.year, self.fiscal_year_start_month, self.fiscal_year_start_day)
        return local_date.year if local_date >= start else local_date.year - 1

    def fiscal_year_start(self, fiscal_year: int) -> date:
        return date(fiscal_year, self.fiscal_year_start_month, self.fiscal_year_start_day)

    def period_index(self, local_date: date) -> int:
        """0-based period index within the fiscal year (month or quarter)."""
        start = self.fiscal_year_start(self.fiscal_year_of(local_date))
        months = (local_date.year - start.year) * 12 + (local_date.month - start.month)
        # Months before the anniversary day still belong to the previous period.
        if local_date.day < self.fiscal_year_start_day and months > 0:
            months -= 1
        months = max(months, 0)
        return months if self.period_rule == "monthly" else (
            months // 3 if self.period_rule == "quarterly" else 0
        )

    def period_label(self, local_date: date) -> str:
        """Canonical period label, e.g. ``2025-M01``, ``2025-Q2``, ``2025-FY``."""
        fiscal_year = self.fiscal_year_of(local_date)
        index = self.period_index(local_date)
        if self.period_rule == "monthly":
            return f"{fiscal_year}-M{index + 1:02d}"
        if self.period_rule == "quarterly":
            return f"{fiscal_year}-Q{index + 1}"
        return f"{fiscal_year}-FY"

    def period_bounds(self, label: str) -> tuple[date, date]:
        """Inclusive local-date bounds for a period label."""
        try:
            fiscal_year_text, suffix = label.split("-", 1)
            fiscal_year = int(fiscal_year_text)
        except (AttributeError, ValueError) as exc:
            raise TimeRuleError("period label must look like YYYY-Mnn/Qn/FY", label=label) from exc
        start_year_date = self.fiscal_year_start(fiscal_year)
        if self.period_rule == "monthly":
            if not suffix.startswith("M"):
                raise TimeRuleError("period label does not match monthly rule", label=label)
            index = int(suffix[1:]) - 1
            if not 0 <= index <= 11:
                raise TimeRuleError("month index out of range", label=label)
        elif self.period_rule == "quarterly":
            if not suffix.startswith("Q"):
                raise TimeRuleError("period label does not match quarterly rule", label=label)
            index = (int(suffix[1:]) - 1) * 3
            if not 0 <= index <= 9:
                raise TimeRuleError("quarter index out of range", label=label)
        else:
            index = 0
        first = _add_months(start_year_date, index)
        last = _add_months(first, 1 if self.period_rule == "monthly" else (
            3 if self.period_rule == "quarterly" else 12
        )) - timedelta(days=1)
        return first, last

    def effective_date(self, moment: datetime) -> date:
        """Local calendar date in the company timezone for ``moment``."""
        return moment.astimezone(self.zone).date()

    def posting_period(self, moment: datetime) -> str:
        """Period a posting lands in, honouring the company cut-off offset."""
        local_date = self.effective_date(moment) + timedelta(days=self.cutoff_day_offset)
        return self.period_label(local_date)

    def within_cutoff(self, moment: datetime) -> bool:
        """True when the moment falls before the closing boundary of its period."""
        local_date = self.effective_date(moment)
        _, last = self.period_bounds(self.period_label(local_date))
        return local_date <= last

    def describe(self) -> dict[str, Any]:
        return {
            "timezone": self.timezone_name,
            "period_rule": self.period_rule,
            "fiscal_year_start_month": self.fiscal_year_start_month,
            "fiscal_year_start_day": self.fiscal_year_start_day,
            "fiscal_year_start": [self.fiscal_year_start_month, self.fiscal_year_start_day],
            "cutoff_day_offset": self.cutoff_day_offset,
            "ambiguity_policy": self.ambiguity_policy,
        }


def _add_months(day: date, months: int) -> date:
    total = day.month - 1 + months
    year = day.year + total // 12
    month = total % 12 + 1
    # Clamp to month length so the anniversary day stays valid.
    day_number = min(day.day, _days_in_month(year, month))
    return date(year, month, day_number)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day


def utc_offset_minutes(moment: datetime) -> int:
    offset = moment.utcoffset()
    if offset is None:
        raise TimeRuleError("datetime has no UTC offset")
    return int(offset.total_seconds() // 60)
