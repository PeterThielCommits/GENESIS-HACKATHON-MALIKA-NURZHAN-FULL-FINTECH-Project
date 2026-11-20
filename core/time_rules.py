"""Company-local Gregorian months. Never infer the host timezone."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


def instant(text: str) -> datetime:
    dt = datetime.fromisoformat(text)
    if dt.utcoffset() is None:
        raise ValueError('offset required')
    return dt


def localize(wall: datetime, zone: str, ambiguity: str = 'reject') -> datetime:
    if wall.tzinfo is not None or ambiguity not in ('earlier', 'later', 'reject'):
        raise ValueError('expected local wall time and a known ambiguity policy')
    tz = ZoneInfo(zone)
    candidates = set()
    for fold in (0, 1):
        utc = wall.replace(tzinfo=tz, fold=fold).astimezone(timezone.utc)
        if utc.astimezone(tz).replace(tzinfo=None) == wall:
            candidates.add(utc)
    if not candidates or (len(candidates) == 2 and ambiguity == 'reject'):
        raise ValueError('nonexistent or ambiguous local time')
    return (max if ambiguity == 'later' else min)(candidates).astimezone(tz)


def period(events: dict, cutoff_policy: dict, company_zone: str) -> str:
    event = cutoff_policy['recognition_event']
    if cutoff_policy['timezone_source'] != 'company' or event not in (
        'service_date', 'delivery_date', 'issue_date'
    ):
        raise ValueError('unknown cutoff policy')
    value = events[event]
    tz = ZoneInfo(company_zone)
    # A date-only event is already a business date in the company calendar.
    local = date.fromisoformat(value) if len(value) == 10 else instant(value).astimezone(tz)
    return local.isoformat()[:7]


def fiscal_period(events: dict, policy: dict, company: dict) -> str:
    month = period(events, policy['cutoff_policy'], company['timezone'])
    start = date.fromisoformat(company['fiscal_year_start'])
    if start.day != 1:
        raise ValueError('only month-aligned fiscal calendars supported')
    year, m = map(int, month.split('-'))
    rule = company['fiscal_period_rule']
    if rule == 'monthly':
        return month
    if rule == 'quarterly':
        return f'{year - (m < start.month):04d}-Q{(m - start.month) % 12 // 3 + 1}'
    raise ValueError('unknown fiscal calendar')
