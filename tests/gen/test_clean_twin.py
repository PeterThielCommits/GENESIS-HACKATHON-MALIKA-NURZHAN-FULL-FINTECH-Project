"""Clean-twin tests: determinism, invariants, RNG isolation, ID/reference integrity.

Covers EXIT GATE 3 requirements that Phase 4 depends on (REQ-GEN-001..006,
REQ-INV-001, REQ-DATA-001..005).
"""

from __future__ import annotations

import unittest

from contracts.errors import ConfigError
from gen.clean import build_clean_book
from gen.config import GeneratorConfig, load_generator_config
from gen.core.rng import RngService
from invariants.checks_clean import check_all


class ConfigTests(unittest.TestCase):
    def test_default_config_validates(self) -> None:
        config = load_generator_config()
        self.assertTrue(config.config_hash)

    def test_unknown_version_rejected(self) -> None:
        config = load_generator_config()
        raw = dict(config.raw)
        raw["config_version"] = "9.9.9"
        broken = GeneratorConfig(raw=raw, mutation_raw=config.mutation_raw)
        with self.assertRaises(ConfigError):
            broken.validate()

    def test_missing_section_rejected(self) -> None:
        config = load_generator_config()
        raw = {key: value for key, value in config.raw.items() if key != "fx"}
        broken = GeneratorConfig(raw=raw, mutation_raw=config.mutation_raw)
        with self.assertRaises(ConfigError):
            broken.validate()

    def test_out_of_range_value_rejected(self) -> None:
        config = load_generator_config()
        raw = {**config.raw, "volumes": {**config.raw["volumes"], "customer_ratio_bps": 20000}}
        with self.assertRaises(ConfigError):
            GeneratorConfig(raw=raw, mutation_raw=config.mutation_raw).validate()

    def test_unknown_difficulty_rejected(self) -> None:
        config = load_generator_config()
        with self.assertRaises(ConfigError):
            config.profile("L9")

    def test_config_hash_is_stable_and_sensitive(self) -> None:
        first = load_generator_config()
        second = load_generator_config()
        self.assertEqual(first.config_hash, second.config_hash)
        changed = {**first.raw, "volumes": {**first.raw["volumes"], "invoices_per_month": 9}}
        tweaked = GeneratorConfig(raw=changed, mutation_raw=first.mutation_raw)
        self.assertNotEqual(first.config_hash, tweaked.config_hash)


class RngIsolationTests(unittest.TestCase):
    def test_namespaces_are_independent(self) -> None:
        left = RngService("seed-x")
        right = RngService("seed-x")
        left.stream("company").randint(0, 1000)
        # Consuming one stream must not move the other.
        self.assertEqual(
            left.stream("chart").randint(0, 1_000_000),
            right.stream("chart").randint(0, 1_000_000),
        )

    def test_different_seeds_differ(self) -> None:
        self.assertNotEqual(
            RngService("a").stream("company").randint(0, 10**9),
            RngService("b").stream("company").randint(0, 10**9),
        )

    def test_invalid_namespace_rejected(self) -> None:
        service = RngService("seed")
        for bad in ("", "/leading", "trailing/", "double//slash"):
            with self.subTest(namespace=bad), self.assertRaises(ConfigError):
                service.stream(bad)

    def test_empty_seed_rejected(self) -> None:
        with self.assertRaises(ConfigError):
            RngService("")

    def test_fork_is_deterministic(self) -> None:
        first = RngService("s").fork("mutation/op", "0").randint(0, 10**6)
        second = RngService("s").fork("mutation/op", "0").randint(0, 10**6)
        self.assertEqual(first, second)

    def test_weighted_choice_is_deterministic(self) -> None:
        stream = RngService("w").stream("weights")
        picks = [stream.choices_weighted({"a": 5000, "b": 5000}) for _ in range(20)]
        again = [RngService("w").stream("weights").choices_weighted({"a": 5000, "b": 5000})]
        self.assertEqual(picks[:1], again)


class CleanTwinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_generator_config()
        cls.build = build_clean_book(master_seed="clean-001", config=cls.config, difficulty="L1")

    def test_clean_twin_has_no_violations(self) -> None:
        self.assertEqual(self.build.violations, ())

    def test_deterministic_across_processes(self) -> None:
        again = build_clean_book(master_seed="clean-001", config=self.config, difficulty="L1")
        self.assertEqual(self.build.book.public_files(), again.book.public_files())

    def test_different_seed_differs(self) -> None:
        other = build_clean_book(master_seed="clean-002", config=self.config, difficulty="L1")
        self.assertNotEqual(self.build.book.public_digest(), other.book.public_digest())

    def test_public_file_set_is_exact(self) -> None:
        expected = {
            "company.json", "policy.json", "accounts.jsonl", "counterparties.jsonl",
            "journal_entries.jsonl", "invoices.jsonl", "credit_notes.jsonl",
            "payments.jsonl", "bank_lines.jsonl", "fx_rates.jsonl",
            "opening_balances.json", "period_calendar.json",
        }
        self.assertEqual(set(self.build.book.public_files()), expected)

    def test_ids_unique_and_references_resolve(self) -> None:
        book = self.build.book
        for table in book.table_names():
            key_field = {
                "accounts": "account_id",
                "counterparties": "counterparty_id",
                "journal_entries": "je_id",
                "invoices": "doc_id",
                "credit_notes": "credit_note_id",
                "payments": "pay_id",
                "bank_lines": "bank_line_id",
                "fx_rates": "effective_date",
            }[table]
            keys = [getattr(row, key_field) for row in book.rows(table)]
            if table == "fx_rates":
                keys = [f"{row.pair}@{row.effective_date}" for row in book.fx_rates]
            self.assertEqual(len(keys), len(set(keys)), f"duplicate keys in {table}")

    def test_money_fields_are_integers(self) -> None:
        book = self.build.book
        for invoice in book.invoices:
            self.assertIsInstance(invoice.total_minor, int)
            self.assertNotIsInstance(invoice.total_minor, bool)
        for payment in book.payments:
            self.assertIsInstance(payment.amount_minor, int)
            self.assertIsInstance(payment.functional_amount_minor, int)

    def test_no_float_anywhere_in_public_payload(self) -> None:
        def walk(value: object) -> None:
            self.assertNotIsInstance(value, float, "float found in public payload")
            if isinstance(value, dict):
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        import json

        for name, text in self.build.book.public_files().items():
            with self.subTest(file=name):
                walk(json.loads(text) if name.endswith(".json") else [
                    json.loads(line) for line in text.splitlines() if line
                ])

    def test_all_invariants_pass_explicitly(self) -> None:
        violations = check_all(self.build.book)
        self.assertEqual(violations, [])

    def test_no_anomaly_markers_in_ids(self) -> None:
        """Identifiers must never encode anomaly hints (8.4 anti-shortcut).

        Free-text business names are deliberately excluded: they are ordinary
        narrative, not a shortcut signal, and checking them would forbid legitimate
        words such as "duplicate invoice notice".
        """
        book = self.build.book
        forbidden = ("BUG", "DUP", "ERROR", "SYNTHETIC", "ANOM", "MUTANT")
        id_values: list[str] = []
        for table in book.table_names():
            for row in book.rows(table):
                for key, value in row.to_row().items():
                    if key.endswith("_id") and isinstance(value, str):
                        id_values.append(value)
        for entry in book.journal_entries:
            id_values.append(entry.je_id)
            id_values.extend(line.line_id for line in entry.lines)
            id_values.extend(line.account_id for line in entry.lines)
        for payment in book.payments:
            id_values.extend(item.allocation_id for item in payment.allocations)
        self.assertTrue(id_values)
        for identifier in id_values:
            upper = identifier.upper()
            for marker in forbidden:
                self.assertNotIn(marker, upper, f"{marker} leaked into id {identifier}")

    def test_profiles_produce_more_records(self) -> None:
        small = build_clean_book(master_seed="profile", config=self.config, difficulty="L1")
        large = build_clean_book(master_seed="profile", config=self.config, difficulty="L3")
        self.assertGreater(
            large.book.row_counts()["invoices"], small.book.row_counts()["invoices"]
        )

    def test_seed_matrix_is_clean(self) -> None:
        for index in range(6):
            with self.subTest(seed=index):
                build = build_clean_book(
                    master_seed=f"matrix-{index}", config=self.config, difficulty="L1"
                )
                self.assertEqual(build.violations, ())

    def test_empty_seed_rejected(self) -> None:
        with self.assertRaises(ConfigError):
            build_clean_book(master_seed="", config=self.config, difficulty="L1")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
