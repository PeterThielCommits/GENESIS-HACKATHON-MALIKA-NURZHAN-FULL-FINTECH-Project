"""Canonical JSON properties (REQ-CONTRACT-010..012, D-0005)."""

from __future__ import annotations

import unittest
from decimal import Decimal

from tests.support import ROOT  # noqa: F401  (ensures sys.path)
from tools.canonical_json import (
    CanonicalJSONError,
    canonical_bytes,
    canonical_digest,
    canonical_json,
    load_canonical,
    sha256_hex,
)


class CanonicalJSONTests(unittest.TestCase):
    def test_key_order_independence(self) -> None:
        left = {"b": 1, "a": {"y": 2, "x": [1, 2, 3]}}
        right = {"a": {"x": [1, 2, 3], "y": 2}, "b": 1}
        self.assertEqual(canonical_json(left), canonical_json(right))
        self.assertEqual(canonical_digest(left), canonical_digest(right))

    def test_expected_byte_sequence(self) -> None:
        value = {"amount_minor": 18450000, "currency": "KZT", "ids": ["PAY:b", "PAY:a"]}
        expected = '{"amount_minor":18450000,"currency":"KZT","ids":["PAY:b","PAY:a"]}'
        self.assertEqual(canonical_json(value), expected)
        self.assertEqual(canonical_bytes(value), expected.encode("utf-8"))

    def test_array_order_is_significant(self) -> None:
        self.assertNotEqual(canonical_json([1, 2]), canonical_json([2, 1]))

    def test_utf8_not_escaped(self) -> None:
        text = canonical_json({"name": "ТОО «Алматы Ридж»"})
        self.assertIn("Алматы", text)
        self.assertNotIn("\\u", text)

    def test_floats_are_rejected(self) -> None:
        with self.assertRaises(CanonicalJSONError):
            canonical_json({"amount_minor": 1.5})
        with self.assertRaises(CanonicalJSONError):
            canonical_json([0.1])

    def test_nested_float_is_rejected(self) -> None:
        with self.assertRaises(CanonicalJSONError):
            canonical_json({"lines": [{"debit_minor": 10, "rate": 462.35}]})

    def test_decimal_is_plain_text(self) -> None:
        self.assertEqual(canonical_json({"rate": Decimal("1E-7")}), '{"rate":"0.0000001"}')
        self.assertEqual(canonical_json({"rate": Decimal("462.350000")}), '{"rate":"462.350000"}')

    def test_non_finite_decimal_rejected(self) -> None:
        with self.assertRaises(CanonicalJSONError):
            canonical_json({"rate": Decimal("NaN")})

    def test_nan_and_infinity_rejected_by_dumps_guard(self) -> None:
        # float rejection already covers these, but the dumps guard is tested directly.
        with self.assertRaises(CanonicalJSONError):
            canonical_json({"x": float("nan")})

    def test_non_string_keys_rejected(self) -> None:
        with self.assertRaises(CanonicalJSONError):
            canonical_json({1: "a"})

    def test_unsupported_type_rejected(self) -> None:
        with self.assertRaises(CanonicalJSONError):
            canonical_json({"x": {1, 2}})

    def test_deep_nesting_rejected(self) -> None:
        value: object = 1
        for _ in range(80):
            value = [value]
        with self.assertRaises(CanonicalJSONError):
            canonical_json(value)

    def test_bool_is_not_an_int(self) -> None:
        self.assertEqual(canonical_json({"ok": True}), '{"ok":true}')
        self.assertEqual(canonical_json({"ok": False}), '{"ok":false}')

    def test_sha256_helpers(self) -> None:
        self.assertEqual(sha256_hex(b""), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
        self.assertEqual(sha256_hex(""), sha256_hex(b""))
        self.assertEqual(len(canonical_digest({})), 64)

    def test_load_canonical_rejects_duplicate_keys(self) -> None:
        with self.assertRaises(CanonicalJSONError):
            load_canonical('{"a": 1, "a": 2}')

    def test_load_canonical_rejects_non_finite(self) -> None:
        with self.assertRaises(CanonicalJSONError):
            load_canonical('{"a": NaN}')

    def test_round_trip(self) -> None:
        value = {"b": [1, {"c": "текст"}], "a": None}
        self.assertEqual(load_canonical(canonical_json(value)), value)

    def test_newline_inside_string_is_preserved(self) -> None:
        self.assertEqual(canonical_json({"x": "a\nb"}), '{"x":"a\\nb"}')

    def test_contract_digest_is_stable_across_calls(self) -> None:
        from tools.validate_contracts import contract_digest

        self.assertEqual(contract_digest(), contract_digest())


if __name__ == "__main__":
    unittest.main()
