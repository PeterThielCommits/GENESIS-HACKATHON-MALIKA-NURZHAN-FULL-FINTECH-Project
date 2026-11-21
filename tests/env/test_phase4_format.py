"""Contract examples for the separate Phase 4 branch, not official schemas."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from env import Environment
from tests.env.test_environment import PUBLIC, CONFIG, action, result

class Phase4FormatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.public = Path(self.temp.name) / 'public'
        shutil.copytree(PUBLIC, self.public)
        (self.public / 'accounts.json').unlink()
        (self.public / 'accounts.jsonl').write_text('{"account_id":"A-1"}\n')
        (self.public / 'opening_balances.json').write_text('{"balances": []}')
        (self.public / 'period_calendar.json').write_text('{"periods": []}')
        rows = [
            {'pair': 'USD/KZT', 'effective_date': '2025-01-02', 'rate_decimal': '5.2'},
            {'pair': 'USD/KZT', 'effective_date': '2025-01-01', 'rate_decimal': '5.1'},
        ]
        (self.public / 'fx_rates.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        self.env = Environment()

    def test_reset_fx_pagination_and_lookup(self):
        initial = self.env.reset(self.public, CONFIG)
        self.assertEqual(initial['opening_balances'], {'balances': []})
        first = result(self.env.step(action('list_records', table='fx_rates', limit=1)))
        self.assertEqual(first['rows'][0]['effective_date'], '2025-01-01')
        self.assertEqual(result(self.env.step(action('get_record', table='fx_rates', id='USD/KZT@2025-01-01')))['record'], first['rows'][0])
        second = result(self.env.step(action('list_records', table='fx_rates', limit=1, cursor=first['next_cursor'])))
        self.assertEqual(second['rows'][0]['effective_date'], '2025-01-02')
        self.assertIsNone(second['next_cursor'])

    def test_ambiguous_or_missing_accounts_rejected(self):
        (self.public / 'accounts.json').write_text('[]')
        with self.assertRaises(ValueError): self.env.reset(self.public, CONFIG)
        (self.public / 'accounts.json').unlink(); (self.public / 'accounts.jsonl').unlink()
        with self.assertRaises(ValueError): self.env.reset(self.public, CONFIG)

    def test_duplicate_composite_and_malformed_key_rejected(self):
        fx = self.public / 'fx_rates.jsonl'
        row = '{"pair":"USD/KZT","effective_date":"2025-01-01"}\n'
        fx.write_text(row + row)
        with self.assertRaises(ValueError): self.env.reset(self.public, CONFIG)
        fx.write_text('{"pair":"USD@KZT","effective_date":"2025-01-01"}\n')
        with self.assertRaises(ValueError): self.env.reset(self.public, CONFIG)

    def test_replay_is_deterministic_with_cursor_history(self):
        outputs = []
        for _ in range(2):
            e = Environment(); initial = e.reset(self.public, CONFIG)
            first = e.step(action('list_records', table='fx_rates', limit=1))
            cursor = result(first)['next_cursor']
            second = e.step(action('list_records', table='fx_rates', limit=1, cursor=cursor))
            third = e.step(action('submit', findings=[]))
            outputs.append([initial, first, second, third])
        self.assertEqual(outputs[0], outputs[1])

    def test_hardlinked_public_file_rejected(self):
        policy = self.public / 'policy.json'
        policy.unlink()
        sealed = Path(self.temp.name) / 'sealed'; sealed.mkdir()
        private = sealed / 'truth.json'; private.write_text('{"innocuous":"secret"}')
        os.link(private, policy)
        with self.assertRaises(ValueError): self.env.reset(self.public, CONFIG)

if __name__ == '__main__':
    unittest.main()
