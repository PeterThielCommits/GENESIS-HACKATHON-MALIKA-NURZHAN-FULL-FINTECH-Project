"""Deterministic ID factory tests (Phase 2.5, 8.4 anti-shortcut)."""

from __future__ import annotations

import random
import unittest

from contracts.errors import IdError
from core.ids import ID_STYLES, IdFactory, style_for_config, validate_luhn


def factory(style: str, seed: int = 7) -> IdFactory:
    return IdFactory(style=style, rng=random.Random(seed), year=2025)  # type: ignore[arg-type]


class StyleTests(unittest.TestCase):
    def test_style_a_formats(self) -> None:
        f = factory("A")
        self.assertRegex(f.new("journal_entries", month=5), r"^JE-\d{6}$")
        self.assertRegex(f.new("invoices"), r"^INV-2025-\d{4}$")
        self.assertRegex(f.new("payments"), r"^PAY-\d{6}$")

    def test_style_b_formats(self) -> None:
        f = factory("B")
        self.assertRegex(f.new("journal_entries", month=5), r"^2025/05/J/\d{4}$")
        self.assertRegex(f.new("invoices"), r"^S-\d{4}-25$")
        self.assertRegex(f.new("payments"), r"^P[0-9A-F]{7}$")

    def test_style_c_formats(self) -> None:
        f = factory("C")
        self.assertRegex(f.new("journal_entries"), r"^je_[0-9a-f]{6}$")
        self.assertRegex(f.new("invoices"), r"^in_[0-9a-f]{6}$")

    def test_style_d_luhn(self) -> None:
        f = factory("D")
        for _ in range(50):
            identifier = f.new("journal_entries")
            self.assertTrue(identifier.isdigit())
            self.assertTrue(validate_luhn(identifier))

    def test_ids_unique_across_tables_in_every_style(self) -> None:
        """``source_document_id`` is a cross-table pointer: ids must not collide."""
        tables = ("invoices", "payments", "credit_notes", "bank_lines")
        for style in ID_STYLES:
            with self.subTest(style=style):
                f = factory(style)
                issued = [f.new(table) for table in tables]
                self.assertEqual(len(set(issued)), len(issued), issued)

    def test_all_styles_supported(self) -> None:
        self.assertEqual(set(ID_STYLES), {"A", "B", "C", "D"})
        for style in ID_STYLES:
            with self.subTest(style=style):
                self.assertTrue(factory(style).new("payments"))


class DeterminismTests(unittest.TestCase):
    def test_same_seed_same_ids(self) -> None:
        left = [factory("A", 11).new("invoices") for _ in range(3)]
        right = [factory("A", 11).new("invoices") for _ in range(3)]
        self.assertEqual(left, right)

    def test_id_does_not_embed_table_position(self) -> None:
        f = factory("A")
        first = f.new("payments")
        second = f.new("payments")
        self.assertEqual(int(second.split("-")[1]) - int(first.split("-")[1]), 1)

    def test_global_random_untouched(self) -> None:
        state = random.getstate()
        f = factory("C", 3)
        f.new("invoices")
        self.assertEqual(state, random.getstate())


class UniquenessAndErrorsTests(unittest.TestCase):
    def test_uniqueness_within_namespace(self) -> None:
        f = factory("C")
        issued = {f.new("payments") for _ in range(500)}
        self.assertEqual(len(issued), 500)

    def test_namespaces_are_independent(self) -> None:
        f = factory("A")
        f.new("payments")
        self.assertEqual(f.issued("invoices"), ())

    def test_unknown_table_rejected(self) -> None:
        with self.assertRaises(IdError):
            factory("A").new("unicorns")

    def test_unknown_style_rejected(self) -> None:
        with self.assertRaises(IdError):
            factory("Z")

    def test_year_range_validated(self) -> None:
        with self.assertRaises(IdError):
            IdFactory(style="A", rng=random.Random(1), year=1800)

    def test_style_for_config(self) -> None:
        self.assertEqual(style_for_config("B"), "B")
        with self.assertRaises(IdError):
            style_for_config("E")

    def test_luhn_rejects_non_digits(self) -> None:
        with self.assertRaises(IdError):
            validate_luhn("12a45")

    def test_luhn_rejects_short(self) -> None:
        with self.assertRaises(IdError):
            validate_luhn("7")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
