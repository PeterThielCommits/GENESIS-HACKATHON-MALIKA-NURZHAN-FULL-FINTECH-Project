"""Canonical JSON golden tests (REQ-CONTRACT-010..012)."""

import unittest
from decimal import Decimal

from contracts.canonical import (
    canonical_bytes,
    canonical_json,
    canonicalize,
    config_hash,
    sha256_hex,
)


class TestCanonicalJson(unittest.TestCase):
    def test_key_order_independence(self):
        a = {"b": 2, "a": 1, "c": {"z": 26, "y": 25}}
        b = {"c": {"y": 25, "z": 26}, "a": 1, "b": 2}
        self.assertEqual(canonical_json(a), canonical_json(b))
        self.assertEqual(sha256_hex(a), sha256_hex(b))

    def test_exact_bytes(self):
        self.assertEqual(canonical_json({"b": 2, "a": 1}), '{"a":1,"b":2}')
        self.assertEqual(canonical_bytes({"a": 1}), b'{"a":1}\n')

    def test_unicode_preserved(self):
        s = canonical_json({"name": "Демо Синтетик"})
        self.assertIn("Демо Синтетик", s)
        self.assertNotIn("\\u", s)

    def test_nan_and_infinity_rejected(self):
        with self.assertRaises(ValueError):
            canonical_json({"x": float("nan")})
        with self.assertRaises(ValueError):
            canonical_json({"x": float("inf")})
        with self.assertRaises(ValueError):
            canonical_json([float("-inf")])

    def test_decimal_must_be_string(self):
        with self.assertRaises(TypeError):
            canonical_json({"amount": Decimal("1.23")})
        # Pre-formatted string is the only allowed Decimal transport.
        self.assertEqual(canonical_json({"rate": "1.2300"}), '{"rate":"1.2300"}')

    def test_non_string_key_rejected(self):
        with self.assertRaises(TypeError):
            canonical_json({1: "x"})

    def test_config_hash_stable_and_self_field_excluded(self):
        cfg = {"config_version": "1.0.0", "max_steps": 100}
        digest = config_hash(cfg)
        stored = {**cfg, "config_hash": digest}
        self.assertEqual(config_hash(cfg), config_hash(dict(cfg)))
        self.assertEqual(config_hash(stored), digest)
        self.assertEqual(len(digest), 64)

    def test_canonicalize_tuple_becomes_list(self):
        self.assertEqual(canonicalize({"a": (1, 2)}), {"a": [1, 2]})


if __name__ == "__main__":
    unittest.main()
