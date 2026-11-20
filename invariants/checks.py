"""Check one normalized catalog group. Callers partition by entity AND currency.

Derived policy choices (e.g. allowed FX quotes) are supplied by the independent
caller, not obtained from generator state. Missing fields are input errors.
"""
from dataclasses import asdict, dataclass
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from contracts.currency import exponent_of
from core.money import convert_minor
from core.time_rules import instant, fiscal_period


@dataclass(frozen=True)
class Signature:
    invariant_id: str
    entity_key: str
    expected_delta_minor: int | None
    currency: str | None
    direction: str
    tolerance_minor: int = 0
    side_effect_class: str = 'primary'

    def to_dict(self):
        return asdict(self)


def minor(value):
    if type(value) is not int:
        raise ValueError('integer minor units required')
    return value


def total(values):
    return sum(map(minor, values))


def check(code: str, key: str, row: dict) -> Signature | None:
    """Return None for PASS, otherwise the signed observed-minus-expected delta."""
    delta = None
    currency = None
    ok = True
    direction = 'mismatch'
    if code in ('INV-01', 'INV-02'):
        delta = total(row['debits']) - total(row['credits'])
    elif code == 'INV-03':
        delta = minor(row['subledger']) - total(row['documents'])
    elif code == 'INV-04':
        delta = minor(row['open']) - (minor(row['gross']) - total(row['payments']) - total(row['credit_notes']))
    elif code == 'INV-05':
        days = (date.fromisoformat(row['as_of']) - date.fromisoformat(row['due'])).days
        bucket = ('closed' if minor(row['open']) == 0 else 'current' if days <= 0 else
                  '1-30' if days <= 30 else '31-60' if days <= 60 else '61+')
        ok = row['bucket'] == bucket
    elif code == 'INV-06':
        match = row['matched_payment_id']
        ok = (bool(row['unmatched_reason']) if match is None else
              match in row['payments'] and row['payments'][match] == [row['currency'], row['signed_minor']])
    elif code == 'INV-07':
        ok = row['selected_quote'] in row['permitted_quotes']
    elif code == 'INV-08':
        result = convert_minor(row['source_minor'], row['source_currency'], row['currency'],
                               row['rate'], row['rounding_mode'])
        delta = minor(row['functional_minor']) - result.amount_minor
    elif code == 'INV-09':
        ok = row['posting_period'] == fiscal_period(row['events'], row['policy'], row['company'])
    elif code == 'INV-10':
        delta = minor(row['reported']) - total(row['lines'])
    elif code == 'INV-11':
        ok = row['ids'].count(key) == 1
    elif code == 'INV-12':
        ref = row['reference']
        ok = row['nullable'] is True if ref is None else ref in row['target_ids']
    elif code == 'INV-13':
        try:
            ok = type(row['amount_minor']) is int and minor(row['scale']) == exponent_of(row['currency'])
        except ValueError:
            ok = False
    elif code == 'INV-14':
        try:
            instant(row['timestamp']).astimezone(ZoneInfo(row['zone']))
        except (TypeError, ValueError, ZoneInfoNotFoundError):
            ok = False
    elif code == 'INV-15':
        allocated = total(row['allocations'])
        if any(a < 0 for a in row['allocations']) or minor(row['payment']) < 0:
            ok = False
        else:
            delta = allocated - row['payment']
            if row['allow_advances'] and delta < 0:
                delta = 0
    elif code == 'INV-16':
        if any(n < 0 for n in row['credit_notes']) or minor(row['cap']) < 0:
            ok = False
        else:
            delta = max(0, total(row['credit_notes']) - row['cap'])
    elif code == 'INV-17':
        balance, gross = minor(row['open']), minor(row['gross'])
        status = 'paid' if balance == 0 else 'open' if balance == gross else 'partial'
        ok = 0 <= balance <= gross and row['status'] == status
    else:
        raise ValueError(f'unknown invariant: {code}')
    if delta is not None:
        currency = row['currency']
        exponent_of(currency)
        ok = delta == 0
        direction = 'over' if delta > 0 else 'under'
    elif code in ('INV-11', 'INV-12', 'INV-13', 'INV-14'):
        direction = 'invalid'
    return None if ok else Signature(code, key, delta, currency, direction)
