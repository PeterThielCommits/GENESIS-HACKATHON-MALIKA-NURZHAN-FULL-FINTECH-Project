"""Independent tests of verifier money/FX/time primitives (Phase 8).

Cross-checks our independent stdlib-only rational FX converter and
timezone/fiscal period logic against the hand-authored manual reference
vectors in ``tests/fixtures/manual/fx.json`` and ``edges.json`` WITHOUT
sharing any code with ``core/`` (TZ 9.3, 12.4).
"""

from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from verifier.money_time import (
    compute_fiscal_period,
    convert_minor_with_pair,
    parse_iso_instant,
    parse_rate_fraction,
    require_minor_int,
    to_company_date,
)

MANUAL_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "manual"


class TestVerifierMoneyTime(unittest.TestCase):
    def test_manual_fx_reference_vectors(self):
        vectors = json.loads((MANUAL_DIR / "fx.json").read_text(encoding="utf-8"))
        self.assertGreater(len(vectors), 0)
        for amount, src, dst, rate, mode, expected in vectors:
            pair = f"{src}/{dst}"
            res = convert_minor_with_pair(amount, src, dst, pair, rate, mode)
            self.assertEqual(
                res.rounded_minor,
                expected,
                msg=f"failed on {(amount, src, dst, rate, mode, expected)}",
            )
            self.assertFalse(res.inverted)

    def test_exact_inverse_pair_repeating_decimal(self):
        # 100 JPY (exp 0) -> KWD (exp 3) with inverse pair KWD/JPY rate 3 (3 JPY per 1 KWD)
        # Exact = 100 * 1000 / 3 = 33333.333... -> 33333
        res = convert_minor_with_pair(100, "JPY", "KWD", "KWD/JPY", "3", "half_even")
        self.assertTrue(res.inverted)
        self.assertEqual(res.rounded_minor, 33333)

        # Exact tie: 15 USD minor (0.15 USD) -> KZT (exp 2) with inverse pair KZT/USD rate 0.002 -> 7500
        res2 = convert_minor_with_pair(15, "USD", "KZT", "KZT/USD", "0.002", "half_even")
        self.assertEqual(res2.rounded_minor, 7500)

    def test_half_even_vs_half_up_ties(self):
        # 5 minor * 0.5 = 2.5 -> half_even=2, half_up=3
        r_even = convert_minor_with_pair(5, "USD", "KZT", "USD/KZT", "0.5", "half_even")
        r_up = convert_minor_with_pair(5, "USD", "KZT", "USD/KZT", "0.5", "half_up")
        self.assertEqual(r_even.rounded_minor, 2)
        self.assertEqual(r_up.rounded_minor, 3)

        # 7 minor * 0.5 = 3.5 -> half_even=4, half_up=4
        r_even2 = convert_minor_with_pair(7, "USD", "KZT", "USD/KZT", "0.5", "half_even")
        self.assertEqual(r_even2.rounded_minor, 4)

    def test_rejects_float_bool_zero_and_bad_rates(self):
        with self.assertRaises(ValueError):
            require_minor_int(10.5)
        with self.assertRaises(ValueError):
            require_minor_int(True)
        with self.assertRaises(ValueError):
            parse_rate_fraction("0")
        with self.assertRaises(ValueError):
            parse_rate_fraction("-1.5")
        with self.assertRaises(ValueError):
            parse_rate_fraction("1e5")

    def test_company_timezone_and_dst_rollover(self):
        # 2025-03-31T21:30:00+00:00 in Asia/Almaty (UTC+5) is 2025-04-01
        d_almaty = to_company_date("2025-03-31T21:30:00+00:00", "Asia/Almaty")
        self.assertEqual(d_almaty, date(2025, 4, 1))

        # NYC DST fall-back / month rollover: 2025-11-01T02:30:00+00:00 -> 2025-10-31 in America/New_York
        d_ny = to_company_date("2025-11-01T02:30:00+00:00", "America/New_York")
        self.assertEqual(d_ny, date(2025, 10, 31))

        # Naive timestamp rejected (REQ-TIME-001)
        with self.assertRaises(ValueError):
            parse_iso_instant("2025-03-31T10:00:00")

    def test_fiscal_period_monthly_quarterly_and_calendar(self):
        self.assertEqual(
            compute_fiscal_period(date(2025, 4, 1), "2025-01-01", "monthly"),
            "2025-04",
        )
        # Fiscal year starting April 1: March 2025 is 2024-Q4; April 2025 is 2025-Q1
        self.assertEqual(
            compute_fiscal_period(date(2025, 3, 31), "2025-04-01", "quarterly"),
            "2024-Q4",
        )
        self.assertEqual(
            compute_fiscal_period(date(2025, 4, 1), "2025-04-01", "quarterly"),
            "2025-Q1",
        )
        # Explicit period_calendar override
        cal = [{"period_id": "FY25-P04", "start_date": "2025-04-01", "end_date": "2025-04-30"}]
        self.assertEqual(
            compute_fiscal_period(date(2025, 4, 15), "2025-01-01", "monthly", cal),
            "FY25-P04",
        )


if __name__ == "__main__":
    unittest.main()
