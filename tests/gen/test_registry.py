"""Operator registry tests (Phase 4.3, 12.x error matrix).

The registry is the contract between an operator implementation and the frozen
anomaly catalogue. These tests fail if the two drift apart — the failure mode that
would otherwise only surface as a wrong ground-truth label much later.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from contracts.errors import OperatorError
from gen.errors import registry

CATALOGUE_PATH = Path(__file__).resolve().parents[2] / "contracts" / "anomaly_catalog.json"


class RegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalogue = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))

    def test_both_phase_four_families_are_registered(self) -> None:
        self.assertTrue(registry.required_anomaly_types_present())
        self.assertEqual(
            set(registry.anomaly_types()),
            {"DUPLICATE_PAYMENT", "PARTIAL_PAYMENT_ALLOCATION"},
        )

    def test_registry_matches_the_frozen_catalogue(self) -> None:
        self.assertEqual(registry.validate_against_catalogue(self.catalogue), [])

    def test_catalogue_drift_is_detected(self) -> None:
        tampered = json.loads(json.dumps(self.catalogue))
        entry = next(t for t in tampered["types"] if t["type"] == "DUPLICATE_PAYMENT")
        entry["intended_invariants"] = ["INV-99"]
        problems = registry.validate_against_catalogue(tampered)
        self.assertTrue(any("intended mismatch" in problem for problem in problems), problems)

    def test_missing_family_is_detected(self) -> None:
        tampered = json.loads(json.dumps(self.catalogue))
        tampered["types"] = [t for t in tampered["types"] if t["type"] != "DUPLICATE_PAYMENT"]
        problems = registry.validate_against_catalogue(tampered)
        self.assertTrue(any("missing from anomaly catalogue" in p for p in problems), problems)

    def test_forbidden_and_intended_never_overlap(self) -> None:
        for entry in registry.all_entries():
            with self.subTest(operator=entry.operator_id):
                self.assertEqual(
                    set(entry.intended_invariants) & set(entry.forbidden_invariants), set()
                )

    def test_unknown_operator_raises(self) -> None:
        with self.assertRaises(OperatorError):
            registry.get("OP-NOT-REAL")
        with self.assertRaises(OperatorError):
            registry.factory_for("OP-NOT-REAL")

    def test_every_entry_builds_an_operator(self) -> None:
        for entry in registry.all_entries():
            with self.subTest(operator=entry.operator_id):
                operator = entry.factory()
                self.assertEqual(operator.spec.operator_id, entry.operator_id)
                self.assertEqual(operator.spec.anomaly_type, entry.anomaly_type)
                self.assertTrue(operator.spec.intended_invariants)

    def test_describe_is_json_safe(self) -> None:
        for entry in registry.all_entries():
            payload = entry.describe()
            json.dumps(payload)
            self.assertEqual(payload["operator_id"], entry.operator_id)

    def test_partial_family_declares_its_subtypes(self) -> None:
        entry = registry.get("OP-PARTIAL_PAYMENT_ALLOCATION")
        self.assertGreaterEqual(len(entry.subtypes), 3)
        self.assertIn("OVER_ALLOCATE_TO_ONE_INVOICE", entry.subtypes)

    def test_operator_ids_are_sorted_and_unique(self) -> None:
        ids = registry.operator_ids()
        self.assertEqual(list(ids), sorted(set(ids)))

    def test_build_episodes_uses_the_registry(self) -> None:
        from gen import build_episodes

        self.assertEqual(set(build_episodes.OPERATORS), set(registry.operator_ids()))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
