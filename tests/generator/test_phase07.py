"""Hand-authored normalized fixtures; not claims about episode-level discovery."""
from dataclasses import replace
from datetime import date
import unittest

from gen.errors.fx_cutoff import Journal, Quote, fx_rate_mismatch, period_cutoff


COMPANY = {'timezone': 'America/New_York', 'fiscal_year_start': '2024-02-01',
           'fiscal_period_rule': 'monthly'}
FX_POLICY = {'rounding_mode': 'half_even', 'fx_policy': {
    'rate_date_rule': 'document_date', 'fallback_rule': 'last_available',
    'source_codes': ['central'], 'quote_convention': 'functional_per_foreign'}}
CUTOFF_POLICY = {'cutoff_policy': {'timezone_source': 'company',
                                  'recognition_event': 'service_date'}}


class FxTests(unittest.TestCase):
    def setUp(self):
        self.events = {'document_date': '2024-03-31', 'payment_date': '2024-04-01'}
        self.good = Quote('fri', date(2024, 3, 29), 'central', 'JPY', 'KWD', '0.0025')
        self.bad = replace(self.good, id='mon', business_date=date(2024, 4, 1), rate='0.004')
        self.quotes = {'fri': self.good, 'mon': self.bad}
        self.clean = Journal('JE:sample', 'JPY', 'KWD', 5, 12, 12, 'fri', '2024-03')

    def mutate(self, clean=None, quotes=None, policy=FX_POLICY, replacement='mon'):
        return fx_rate_mismatch(clean or self.clean, quotes or self.quotes, replacement,
                                self.events, policy, COMPANY)

    def test_mixed_currency_distractor_pairs(self):
        for label, good_rate, bad_rate, convention, distinguishing_fact in (
            ('D-FX-01', '0.0025', '0.004', 'functional_per_foreign', 'weekend fallback'),
            ('D-FX-02', '0.0025', '0.004', 'functional_per_foreign', 'document date'),
            ('D-FX-03', '400', '250', 'foreign_per_functional', 'inverse quote'),
            ('D-FX-04', '0.0025', '0.004', 'functional_per_foreign', '12.5 rounds to 12'),
        ):
            with self.subTest(label=label, fact=distinguishing_fact):
                good = replace(self.good, rate=good_rate)
                events = dict(self.events)
                if label != 'D-FX-01':
                    events['document_date'] = '2024-03-29'
                if label == 'D-FX-04':
                    # Isolate the rounding rule from inverse quotes and fallback.
                    events['payment_date'] = events['document_date']
                policy = dict(FX_POLICY, fx_policy=dict(FX_POLICY['fx_policy'],
                                                        quote_convention=convention))
                quotes = {'fri': good, 'mon': replace(self.bad, rate=bad_rate)}
                actual = fx_rate_mismatch(self.clean, quotes, 'mon', events, policy, COMPANY)
                reordered = dict(reversed(list(quotes.items())))
                self.assertEqual(actual, fx_rate_mismatch(self.clean, reordered, 'mon',
                                                          events, policy, COMPANY))
                mutated, (signature, amount_signature) = actual
                self.assertEqual(mutated, replace(self.clean, debit_minor=20, credit_minor=20,
                                                   rate_id='mon'))
                self.assertEqual((signature.invariant_id, signature.entity_key),
                                 ('INV-07', self.clean.id))
                self.assertEqual((amount_signature.invariant_id, amount_signature.expected_delta_minor,
                                  amount_signature.currency), ('INV-08', 8, 'KWD'))
                self.assertEqual((self.clean.debit_minor, self.clean.rate_id), (12, 'fri'))

    def test_rejects_dirty_entry_and_rounded_no_op(self):
        with self.assertRaisesRegex(ValueError, 'unbalanced'):
            self.mutate(clean=replace(self.clean, credit_minor=11))
        with self.assertRaisesRegex(ValueError, 'must change'):
            self.mutate(quotes=dict(self.quotes, mon=replace(self.bad, rate='0.0024')))
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            self.mutate(quotes=dict(self.quotes, other=replace(self.good, id='other', rate='0.005')))
        with self.assertRaisesRegex(ValueError, 'non-permitted'):
            self.mutate(replacement='fri')

    def test_half_up_and_no_fallback(self):
        with self.assertRaisesRegex(ValueError, 'incorrect clean'):
            self.mutate(policy=dict(FX_POLICY, rounding_mode='half_up'))
        with self.assertRaisesRegex(ValueError, 'no permitted rate'):
            self.mutate(policy=dict(FX_POLICY, fx_policy=dict(FX_POLICY['fx_policy'],
                                                             fallback_rule='none')))


class CutoffTests(unittest.TestCase):
    def test_period_distractor_pairs(self):
        for label, service, issued, event, expected, wrong in (
            ('D-CUT-01', '2024-04-01T03:30:00+00:00', '2024-04-02', 'service_date',
             '2024-03', '2024-04'),
            ('D-CUT-02', '2024-04-02', '2024-03-29', 'service_date', '2024-04', '2024-03'),
            ('D-CUT-03', '2024-03-29', '2024-04-02', 'delivery_date', '2024-04', '2024-03'),
            ('D-CUT-04', '2024-11-03T01:30:00-05:00', '2024-12-01', 'service_date',
             '2024-11', '2024-12'),
        ):
            with self.subTest(label=label):
                events = {'service_date': service, 'issue_date': issued, 'delivery_date': issued}
                policy = dict(cutoff_policy=dict(CUTOFF_POLICY['cutoff_policy'],
                                                 recognition_event=event))
                entry = Journal('JE:sample', 'USD', 'USD', 500, 500, 500, None, expected)
                alternate = 'service_date' if event == 'delivery_date' else 'issue_date'
                before = dict(events)
                mutated, signature = period_cutoff(entry, alternate, events, policy, COMPANY)
                self.assertEqual(mutated, replace(entry, posting_period=wrong))
                self.assertEqual((signature.invariant_id, signature.entity_key), ('INV-09', entry.id))
                self.assertEqual(events, before)
                with self.assertRaisesRegex(ValueError, 'already violates'):
                    period_cutoff(mutated, alternate, events, policy, COMPANY)

    def test_quarter_and_invalid_events(self):
        company = dict(COMPANY, fiscal_period_rule='quarterly')
        entry = Journal('JE:sample', 'USD', 'USD', 500, 500, 500, None, '2023-Q4')
        events = {'service_date': '2024-01-31', 'issue_date': '2024-02-01'}
        self.assertEqual(period_cutoff(entry, 'issue_date', events, CUTOFF_POLICY, company)[0]
                         .posting_period, '2024-Q1')
        for bad in ('2024-01-01', '2024-02-01T10:00:00'):
            with self.assertRaises(ValueError):
                period_cutoff(entry, 'issue_date', dict(events, issue_date=bad),
                              CUTOFF_POLICY, company)
