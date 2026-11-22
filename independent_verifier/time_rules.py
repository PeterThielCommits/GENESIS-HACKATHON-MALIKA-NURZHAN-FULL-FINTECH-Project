"""Independent timezone / fiscal-period primitives (spec §2.2).

Second derivation from the frozen specification. Never consults host local time;
company timezone and calendar come from the public episode only.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


def parse_instant(value: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError("timestamp must be a string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must carry an explicit UTC offset")
    return parsed


def parse_date(value: str) -> date:
    if not isinstance(value, str):
        raise TypeError("date must be a string")
    return date.fromisoformat(value.strip())


def local_date(value: str, timezone: str) -> date:
    return parse_instant(value).astimezone(ZoneInfo(timezone)).date()


def fiscal_period(
    local: date,
    fiscal_year_start: date,
    rule: str,
    period_calendar: list[dict] | None,
) -> str:
    """Fiscal period for a company-local calendar date.

    An explicit ``period_calendar.json`` range covering the date wins over the
    rule computation (spec §2.2: cross-checked and used).
    """
    for row in period_calendar or []:
        try:
            start = parse_date(row.get("start_date", ""))
            end = parse_date(row.get("end_date", ""))
        except ValueError:
            continue
        if start <= local <= end and row.get("period_id"):
            return str(row["period_id"])
    fy_month = fiscal_year_start.month
    if rule == "monthly":
        return f"{local.year:04d}-{local.month:02d}"
    if rule == "quarterly":
        fiscal_year = local.year if local.month >= fy_month else local.year - 1
        quarter = ((local.month - fy_month) % 12) // 3 + 1
        return f"{fiscal_year:04d}-Q{quarter}"
    raise ValueError(f"unsupported fiscal_period_rule {rule!r}")
