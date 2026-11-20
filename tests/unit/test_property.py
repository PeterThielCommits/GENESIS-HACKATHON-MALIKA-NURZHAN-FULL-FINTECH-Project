"""Stdlib property loops (TZ 20.2 fallback when Hypothesis is absent).

These deterministic loops cover the Phase 1 properties; Hypothesis-based
property tests are added in Phase 13 as optional extras.
"""

import random
import unittest

from contracts.canonical import canonical_json, sha256_hex
from contracts.models import canonical_ids


class TestStdlibProperties(unittest.TestCase):
    def test_canonical_stable_under_key_permutation(self):
        rng = random.Random(42)
        base = {"a": 1, "b": [1, 2, 3], "c": {"x": "y", "n": 7}, "d": "text"}
        keys = list(base.keys())
        for _ in range(50):
            rng.shuffle(keys)
            permuted = {k: base[k] for k in keys}
            self.assertEqual(canonical_json(base), canonical_json(permuted))
            self.assertEqual(sha256_hex(base), sha256_hex(permuted))

    def test_canonical_ids_idempotent(self):
        ids = ["JE:b", "JE:a", "PAY:x", "JE:a"]
        once = canonical_ids(ids)
        twice = canonical_ids(list(once))
        self.assertEqual(once, twice)
        self.assertEqual(list(once), sorted(set(ids)))

    def test_money_int_preserved(self):
        # Money stays int through canonical round-trip (REQ-MONEY-001).
        import json

        payload = {"amount_minor": 123456, "currency": "KZT"}
        parsed = json.loads(canonical_json(payload))
        self.assertIsInstance(parsed["amount_minor"], int)
        self.assertEqual(parsed["amount_minor"], 123456)


if __name__ == "__main__":
    unittest.main()
