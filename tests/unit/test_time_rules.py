"""Hand-authored time-rule tests, including DST and period boundaries (REQ-TIME-001..005)."""

from __future__ import annotations

import unittest
from datetime import date, datetime, time, timedelta, timezone

from contracts.errors import TimeRuleError
from core.time_rules import (
    PeriodCalendar,
    format_timestamp,
    load_zone,
    local_wall_time,
    parse_timestamp,
    resolve_local_wall_time,
    utc_offset_minutes,
)


class TimestampParsingTests(unittest.TestCase):
    def test_requires_offset(self) -> None:
        with self.assertRaises(TimeRuleError):
            parse_timestamp("2025-01-01T10:00:00")

    def test_accepts_zulu(self) -> None:
        moment = parse_timestamp("2025-01-01T10:00:00Z")
        self.assertEqual(moment.utcoffset(), timedelta(0))

    def test_accepts_numeric_offset(self) -> None:
        moment = parse_timestamp("2025-01-01T10:00:00+05:00")
        self.assertEqual(utc_offset_minutes(moment), 300)

    def test_rejects_garbage(self) -> None:
        for bad in ("", "not-a-date", "2025-13-01T00:00:00+00:00"):
            with self.subTest(value=bad), self.assertRaises(TimeRuleError):
                parse_timestamp(bad)

    def test_format_uses_numeric_offset(self) -> None:
        moment = datetime(2025, 3, 1, 10, 0, 0, tzinfo=timezone(timedelta(hours=5)))
        self.assertEqual(format_timestamp(moment), "2025-03-01T10:00:00+05:00")

    def test_format_rejects_naive(self) -> None:
        with self.assertRaises(TimeRuleError):
            format_timestamp(datetime(2025, 1, 1))


class PeriodCalendarTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calendar = PeriodCalendar(
            timezone_name="Asia/Almaty",
            period_rule="monthly",
            fiscal_year_start_month=1,
            fiscal_year_start_day=1,
        )

    def test_month_label(self) -> None:
        moment = datetime(2025, 5, 17, 12, 0, tzinfo=timezone(timedelta(hours=5)))
        self.assertEqual(self.calendar.posting_period(moment), "2025-M05")

    def test_local_date_differs_from_utc_date(self) -> None:
        # 17:30 UTC on 31 March is 22:30 in Almaty (+05:00) — same day.
        same_day = datetime(2025, 3, 31, 17, 30, tzinfo=timezone.utc)
        self.assertEqual(self.calendar.effective_date(same_day), date(2025, 3, 31))
        # 20:00 UTC on 31 March is 01:00 on 1 April in Almaty — next day.
        cross = datetime(2025, 3, 31, 20, 0, tzinfo=timezone.utc)
        self.assertEqual(self.calendar.effective_date(cross), date(2025, 4, 1))
        self.assertEqual(self.calendar.posting_period(cross), "2025-M04")

    def test_cutoff_offset_shifts_period(self) -> None:
        shifted = PeriodCalendar(
            timezone_name="Asia/Almaty",
            period_rule="monthly",
            cutoff_day_offset=1,
        )
        moment = datetime(2025, 5, 31, 12, 0, tzinfo=timezone(timedelta(hours=5)))
        self.assertEqual(shifted.posting_period(moment), "2025-M06")

    def test_quarterly_label(self) -> None:
        quarterly = PeriodCalendar(
            timezone_name="UTC", period_rule="quarterly", fiscal_year_start_month=1
        )
        moment = datetime(2025, 8, 15, tzinfo=timezone.utc)
        self.assertEqual(quarterly.posting_period(moment), "2025-Q3")

    def test_annual_label(self) -> None:
        annual = PeriodCalendar(
            timezone_name="UTC", period_rule="annual", fiscal_year_start_month=4,
            fiscal_year_start_day=1,
        )
        self.assertEqual(
            annual.posting_period(datetime(2025, 2, 1, tzinfo=timezone.utc)), "2024-FY"
        )
        self.assertEqual(
            annual.posting_period(datetime(2025, 5, 1, tzinfo=timezone.utc)), "2025-FY"
        )

    def test_period_bounds_month(self) -> None:
        self.assertEqual(
            self.calendar.period_bounds("2025-M02"), (date(2025, 2, 1), date(2025, 2, 28))
        )

    def test_period_bounds_leap_year(self) -> None:
        self.assertEqual(
            self.calendar.period_bounds("2024-M02"), (date(2024, 2, 1), date(2024, 2, 29))
        )

    def test_period_bounds_rejects_bad_label(self) -> None:
        with self.assertRaises(TimeRuleError):
            self.calendar.period_bounds("2025-Q1")

    def test_within_cutoff(self) -> None:
        last_moment = datetime(2025, 5, 31, 23, 0, tzinfo=timezone(timedelta(hours=5)))
        self.assertTrue(self.calendar.within_cutoff(last_moment))
        first_next = datetime(2025, 6, 1, 0, 30, tzinfo=timezone(timedelta(hours=5)))
        self.assertTrue(self.calendar.within_cutoff(first_next))

    def test_non_dst_zone_has_no_shift(self) -> None:
        moments = [
            datetime(2025, 3, 30, 12, tzinfo=timezone.utc),
            datetime(2025, 10, 26, 12, tzinfo=timezone.utc),
        ]
        offsets = {utc_offset_minutes(moment.astimezone(self.calendar.zone)) for moment in moments}
        self.assertEqual(offsets, {300})


class DstTests(unittest.TestCase):
    """DST behaviour is tested on zones that actually observe it."""

    def setUp(self) -> None:
        self.berlin = load_zone("Europe/Berlin")

    def test_spring_forward_gap_needs_policy(self) -> None:
        # 02:30 does not exist on 2025-03-30 in Europe/Berlin.
        with self.assertRaises(TimeRuleError):
            local_wall_time(date(2025, 3, 30), time(2, 30), self.berlin)

    def test_gap_resolved_forward(self) -> None:
        resolved = resolve_local_wall_time(
            date(2025, 3, 30), time(2, 30), self.berlin, "prefer_earlier"
        )
        self.assertEqual(resolved.utcoffset(), timedelta(hours=2))
        self.assertEqual(resolved.hour, 3)

    def test_fall_back_overlap_prefers_earlier(self) -> None:
        earlier = resolve_local_wall_time(
            date(2025, 10, 26), time(2, 30), self.berlin, "prefer_earlier"
        )
        later = resolve_local_wall_time(
            date(2025, 10, 26), time(2, 30), self.berlin, "prefer_later"
        )
        self.assertEqual(earlier.utcoffset(), timedelta(hours=2))
        self.assertEqual(later.utcoffset(), timedelta(hours=1))
        # Same wall clock, different instants: compare in UTC (aware datetimes with
        # identical zone + wall clock compare equal locally by design).
        self.assertLess(earlier.astimezone(timezone.utc), later.astimezone(timezone.utc))
        self.assertEqual(
            later.astimezone(timezone.utc) - earlier.astimezone(timezone.utc), timedelta(hours=1)
        )

    def test_overlap_raise_policy(self) -> None:
        with self.assertRaises(TimeRuleError):
            resolve_local_wall_time(date(2025, 10, 26), time(2, 30), self.berlin, "raise")

    def test_utc_boundary_across_dst(self) -> None:
        before = datetime(2025, 3, 30, 0, 30, tzinfo=timezone.utc).astimezone(self.berlin)
        after = datetime(2025, 3, 30, 1, 30, tzinfo=timezone.utc).astimezone(self.berlin)
        self.assertEqual(before.hour, 1)
        self.assertEqual(after.hour, 3)  # 02:00-02:59 does not exist

    def test_unknown_zone_rejected(self) -> None:
        with self.assertRaises(TimeRuleError):
            load_zone("Mars/Olympus")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
