import json
import unittest
from datetime import datetime
from decimal import localcontext
from pathlib import Path

from core.ids import make_id
from core.money import convert_minor, parse_rate
from core.time_rules import fiscal_period, localize
from invariants.checks import check

FIX = Path(__file__).resolve().parents[1] / 'fixtures' / 'manual'


class PhaseTwo(unittest.TestCase):
    def test_fx(self):
        with localcontext() as ctx:
            ctx.prec = 1
            for *args, expected in json.loads((FIX / 'fx.json').read_text()):
                result = convert_minor(*args)
                self.assertEqual((result.amount_minor, result.n_round), (expected, 1))
            self.assertEqual(str(convert_minor(250,'KWD','JPY','10','half_even').unrounded_minor), '2.500')

    def test_invalid_fx(self):
        for rate in (1.5, 'NaN', '-1', '0', 'Infinity', '1e99', '9'*25):
            with self.assertRaises(ValueError):
                parse_rate(rate)
        for args in [(2**63-1,'USD','EUR','2','half_up'), (True,'USD','EUR','1','half_even'),
                     (1,'XYZ','KZT','1','half_up'), (1,'USD','EUR','1','floor')]:
            with self.assertRaises(ValueError):
                convert_minor(*args)

    def test_dst(self):
        zone = 'America/New_York'
        gap, fold = datetime(2025,3,9,2,30), datetime(2025,11,2,1,30)
        for wall in (gap, fold):
            with self.assertRaises(ValueError):
                localize(wall, zone)
        for mode, offset in [('earlier','-04:00'), ('later','-05:00')]:
            self.assertTrue(localize(fold, zone, mode).isoformat().endswith(offset))
        for wall in (gap, fold):
            self.assertTrue(localize(wall, 'Asia/Almaty').isoformat().endswith('+05:00'))

    def test_quarter(self):
        policy = {'cutoff_policy': {'timezone_source':'company','recognition_event':'service_date'}}
        company = {'timezone':'Asia/Tokyo','fiscal_period_rule':'quarterly','fiscal_year_start':'2024-04-01'}
        for event, expected in [('2025-03-31','2024-Q4'),('2025-03-31T23:00:00Z','2025-Q1')]:
            self.assertEqual(fiscal_period({'service_date':event},policy,company),expected)

    def test_ids(self):
        for family in 'ABCD':
            def identifier(i, ns='pay'):
                return make_id(b'fixture', ns, str(i), family)
            ids = [identifier(i) for i in range(100)]
            self.assertEqual(len(set(ids)),100)
            self.assertEqual(ids[::-1],[identifier(i) for i in reversed(range(100))])
            self.assertNotEqual(ids[0],identifier(0,'je'))
            if family == 'D':
                self.assertTrue(all(s.isdigit() and int(s)%7 == 0 for s in ids))

    def test_manual_groups(self):
        groups = json.loads((FIX / 'groups.json').read_text())
        edges = json.loads((FIX / "edges.json").read_text())
        self.assertEqual(set(groups), {f'INV-{i:02}' for i in range(1,18)})
        for code,(base,patch1,d1,patch2,d2) in groups.items():
            row = {'currency':'USD', **base}
            with self.subTest(code=code):
                self.assertIsNone(check(code,'x',row))
                for patch,delta in [(patch1,d1),(patch2,d2)]:
                    sig = check(code,'x',row | patch)
                    self.assertEqual(sig.expected_delta_minor,delta)
                    self.assertEqual(sig.to_dict()['entity_key'],'x')
                for patch,valid in edges[code]:
                    self.assertEqual(check(code,'x',row | patch) is None, valid)
