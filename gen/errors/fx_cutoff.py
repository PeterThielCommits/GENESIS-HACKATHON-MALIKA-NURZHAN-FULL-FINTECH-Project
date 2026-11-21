"""Provisional Phase 7 mutations of normalized, two-line journal entries.

These are generator internals, not a public record schema or a truth builder.
Callers must supply public document events and the published FX timeline.
"""
from dataclasses import dataclass, replace
from datetime import date
from fractions import Fraction
from typing import Mapping
from zoneinfo import ZoneInfo

from contracts.currency import exponent_of
from core.money import MODES, parse_rate
from core.time_rules import fiscal_period, instant
from invariants.checks import Signature, check


@dataclass(frozen=True)
class Journal:
    id: str
    source_currency: str
    currency: str
    source_minor: int
    debit_minor: int
    credit_minor: int
    rate_id: str | None
    posting_period: str


@dataclass(frozen=True)
class Quote:
    id: str
    business_date: date
    source: str
    foreign: str
    functional: str
    rate: str


def _balance(entry: Journal) -> None:
    exponent_of(entry.currency)
    exponent_of(entry.source_currency)
    for value in (entry.source_minor, entry.debit_minor, entry.credit_minor):
        if type(value) is not int or not 0 < value < 2**63:
            raise ValueError('expected positive int64 journal amounts')
    if check('INV-01', entry.id, {'debits': [entry.debit_minor],
                                 'credits': [entry.credit_minor], 'currency': entry.currency}):
        raise ValueError('unbalanced journal')


def _amount(entry: Journal, quote: Quote, policy: dict) -> int:
    if (quote.foreign, quote.functional) != (entry.source_currency, entry.currency):
        raise ValueError('quote currency pair mismatch')
    rate = Fraction(parse_rate(quote.rate))
    convention = policy['fx_policy']['quote_convention']
    if convention == 'foreign_per_functional':
        rate = 1 / rate
    elif convention != 'functional_per_foreign':
        raise ValueError('unsupported quote convention')
    shift = exponent_of(entry.currency) - exponent_of(entry.source_currency)
    raw = entry.source_minor * rate * Fraction(10) ** shift
    mode = policy['rounding_mode']
    if mode not in MODES:
        raise ValueError('unsupported rounding mode')
    # Exact rational inversion and only one rounding, at the posting scale.
    return round(raw) if mode == 'half_even' else int(raw + Fraction(1, 2))


def _permitted(entry: Journal, quotes: Mapping[str, Quote], events: dict,
               policy: dict, company: dict) -> list[Quote]:
    fx = policy['fx_policy']
    event = events[fx['rate_date_rule']]
    zone = ZoneInfo(company['timezone'])
    day = date.fromisoformat(event) if len(event) == 10 else instant(event).astimezone(zone).date()
    if fx['fallback_rule'] not in ('none', 'last_available'):
        raise ValueError('unsupported fallback rule')
    eligible = [q for q in quotes.values()
                if (q.foreign, q.functional) == (entry.source_currency, entry.currency)
                and q.source in fx['source_codes']
                and (q.business_date == day or
                     (fx['fallback_rule'] == 'last_available' and q.business_date < day))]
    if not eligible:
        raise ValueError('no permitted rate on policy date')
    latest = max(q.business_date for q in eligible)
    return [q for q in eligible if q.business_date == latest]


def fx_rate_mismatch(entry: Journal, quotes: Mapping[str, Quote], replacement_id: str,
                     events: dict, policy: dict, company: dict) -> tuple[Journal, tuple[Signature, Signature]]:
    """Rebook both sides using a non-permitted, published quote for the same pair."""
    _balance(entry)
    if entry.source_currency == entry.currency or any(k != q.id for k, q in quotes.items()):
        raise ValueError('expected foreign journal and a consistently keyed timeline')
    permitted = _permitted(entry, quotes, events, policy, company)
    permitted_ids = {quote.id for quote in permitted}
    if entry.rate_id not in permitted_ids:
        raise ValueError('input already violates FX selection policy')
    clean = quotes[entry.rate_id]
    correct = _amount(entry, clean, policy)
    if entry.debit_minor != correct or any(_amount(entry, q, policy) != correct for q in permitted):
        raise ValueError('incorrect clean booking or ambiguous permitted amounts')
    if replacement_id not in quotes or replacement_id in permitted_ids:
        raise ValueError('replacement must be a non-permitted published quote')
    wrong = quotes[replacement_id]
    amount = _amount(entry, wrong, policy)
    if amount == correct:
        raise ValueError('replacement must change the booked amount')
    mutated = replace(entry, rate_id=wrong.id, debit_minor=amount, credit_minor=amount)
    _balance(mutated)
    signature = check('INV-07', entry.id, {'selected_quote': wrong.id,
                                          'permitted_quotes': permitted_ids})
    assert signature is not None
    delta = amount - correct
    return mutated, (signature, Signature('INV-08', entry.id, delta, entry.currency,
                                          'over' if delta > 0 else 'under'))


def period_cutoff(entry: Journal, alternate_event: str, events: dict,
                  policy: dict, company: dict) -> tuple[Journal, Signature]:
    """Use a different public event's fiscal period without altering any timestamp."""
    _balance(entry)
    row = {'events': events, 'policy': policy, 'company': company}
    if check('INV-09', entry.id, dict(row, posting_period=entry.posting_period)):
        raise ValueError('input already violates recognition policy')
    alternate_policy = dict(policy, cutoff_policy=dict(policy['cutoff_policy'],
                                                        recognition_event=alternate_event))
    wrong_period = fiscal_period(events, alternate_policy, company)
    signature = check('INV-09', entry.id, dict(row, posting_period=wrong_period))
    if signature is None:
        raise ValueError('alternate event must cross a fiscal period boundary')
    return replace(entry, posting_period=wrong_period), signature
