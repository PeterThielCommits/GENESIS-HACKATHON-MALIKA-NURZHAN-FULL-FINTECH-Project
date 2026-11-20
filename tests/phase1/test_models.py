"""Phase 1 task 1.4: typed models are a faithful, validated mirror of the schemas."""

from __future__ import annotations

import dataclasses
import json
import unittest

from models import MODELS, ContractViolation, Finding
from tests.support import CONTRACTS, load_json
from tools import check_models


class ModelParityTests(unittest.TestCase):
    def test_every_schema_has_a_model(self) -> None:
        version = load_json(CONTRACTS / "version.json")
        schemas = {entry["file"] for entry in version["schemas"] if entry["kind"] != "definitions"}
        self.assertEqual(schemas, set(MODELS), "a schema has no typed model, or a model has no schema")

    def test_parity_tool_passes(self) -> None:
        result = check_models.run()
        self.assertEqual(result["status"], "PASS", result["problems"])
        self.assertEqual(result["models"], len(MODELS))

    def test_field_sets_match_schema_properties_exactly(self) -> None:
        for schema_name, model in MODELS.items():
            schema = load_json(CONTRACTS / schema_name)
            self.assertEqual(set(schema["properties"]), model.field_names(), schema_name)
            self.assertEqual(set(schema.get("required", [])), set(model.REQUIRED), schema_name)

    def test_models_are_dataclasses_with_type_hints(self) -> None:
        for model in MODELS.values():
            self.assertTrue(dataclasses.is_dataclass(model), model.__name__)
            hints = {name: field for name, field in model.__dataclass_fields__.items()
                     if field._field_type is dataclasses._FIELD}  # drop ClassVar entries
            self.assertEqual(set(hints), model.field_names())
            self.assertTrue(all(field.type for field in hints.values()), model.__name__)


class ModelBehaviourTests(unittest.TestCase):
    def load(self, name: str = "valid/finding_duplicate_payment.json") -> dict:
        return load_json(CONTRACTS / "fixtures" / name)

    def test_from_dict_validates_and_to_dict_round_trips(self) -> None:
        payload = self.load()
        finding = Finding.from_dict(payload)
        self.assertEqual(json.dumps(finding.to_dict(), sort_keys=True),
                         json.dumps(payload, sort_keys=True))
        self.assertIsInstance(finding.claimed_amount, int)
        self.assertIsInstance(finding.affected_ids, list)

    def test_invalid_payload_is_rejected_at_construction(self) -> None:
        payload = self.load()
        payload["type"] = "not_a_real_type"
        with self.assertRaises(ContractViolation):
            Finding.from_dict(payload)

    def test_unknown_field_is_rejected_rather_than_dropped(self) -> None:
        payload = self.load()
        payload["surprise"] = 1
        with self.assertRaises(ContractViolation):
            Finding.from_dict(payload)

    def test_extension_fields_survive_a_round_trip(self) -> None:
        payload = self.load("valid/finding_with_extension.json")
        finding = Finding.from_dict(payload)
        self.assertEqual(json.dumps(finding.to_dict(), sort_keys=True),
                         json.dumps(payload, sort_keys=True))

    def test_canonical_requires_a_valid_object(self) -> None:
        finding = Finding.from_dict(self.load())
        self.assertEqual(finding.canonical(), finding.to_dict())
        broken = Finding(type="fx_mismatch", affected_ids=["JE:1"], claimed_amount=1,
                         currency="USD", evidence_ids=[])
        broken.type = "nonsense"
        with self.assertRaises(ContractViolation):
            broken.canonical()

    def test_money_is_never_a_float(self) -> None:
        finding = Finding.from_dict(self.load())
        self.assertNotIsInstance(finding.claimed_amount, float)
        self.assertIsInstance(finding.claimed_amount, int)


if __name__ == "__main__":
    unittest.main()
