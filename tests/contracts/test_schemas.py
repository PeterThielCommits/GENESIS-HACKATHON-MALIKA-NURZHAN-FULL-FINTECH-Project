"""Frozen-schema tests: valid fixtures pass, malformed fixtures fail (Phase 1/7.1).

Covers REQ-CONTRACT-001..005, REQ-CONTRACT-010..012 and the executable contract
requirement that a schema can never be silently permissive.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from contracts.canonical import canonical_json, digest_of
from contracts.errors import ContractError
from contracts.jsonschema_subset import SchemaValidator

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"


def validator(name: str) -> SchemaValidator:
    return SchemaValidator.from_file(CONTRACTS / name)


class SchemaInventoryTests(unittest.TestCase):
    def test_every_declared_schema_exists(self) -> None:
        version = json.loads((CONTRACTS / "version.json").read_text(encoding="utf-8"))
        for name in version["schemas"]:
            with self.subTest(schema=name):
                self.assertTrue((CONTRACTS / name).exists(), f"missing {name}")

    def test_every_schema_file_is_declared(self) -> None:
        version = json.loads((CONTRACTS / "version.json").read_text(encoding="utf-8"))
        declared = set(version["schemas"])
        on_disk = {path.name for path in CONTRACTS.glob("*.schema.json")}
        self.assertEqual(on_disk - declared, set(), "undeclared schema files")

    def test_contract_is_frozen(self) -> None:
        version = json.loads((CONTRACTS / "version.json").read_text(encoding="utf-8"))
        self.assertEqual(version["status"], "FROZEN_FOR_MVP")
        self.assertEqual(version["contract_version"], "1.0.0")


class SchemaRejectsUnknownKeywordsTests(unittest.TestCase):
    def test_unsupported_keyword_raises(self) -> None:
        schema = {"type": "object", "unevaluatedProperties": False}
        with self.assertRaises(ContractError):
            SchemaValidator(schema).validate({})

    def test_ignored_annotations_are_allowed(self) -> None:
        schema = {"type": "string", "title": "x", "description": "y", "$comment": "z"}
        SchemaValidator(schema).validate("ok")


class FindingSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.v = validator("finding.schema.json")

    def test_valid_finding_passes(self) -> None:
        self.v.validate(
            {
                "type": "DUPLICATE_PAYMENT",
                "affected_ids": ["PAY-0001", "JE-0002"],
                "amount_minor": 12345,
                "currency": "KZT",
                "evidence_ids": ["INV-1"],
            }
        )

    def test_missing_field_fails(self) -> None:
        with self.assertRaises(ContractError):
            self.v.validate({"type": "DUPLICATE_PAYMENT", "affected_ids": ["A1"]})

    def test_unknown_field_fails(self) -> None:
        with self.assertRaises(ContractError):
            self.v.validate(
                {
                    "type": "DUPLICATE_PAYMENT",
                    "affected_ids": ["PAY-1"],
                    "amount_minor": 1,
                    "currency": "KZT",
                    "evidence_ids": ["INV-1"],
                    "surprise": True,
                }
            )

    def test_float_amount_fails(self) -> None:
        with self.assertRaises(ContractError):
            self.v.validate(
                {
                    "type": "DUPLICATE_PAYMENT",
                    "affected_ids": ["PAY-1"],
                    "amount_minor": 1.5,
                    "currency": "KZT",
                    "evidence_ids": ["INV-1"],
                }
            )

    def test_unknown_type_fails(self) -> None:
        with self.assertRaises(ContractError):
            self.v.validate(
                {
                    "type": "ROUNDING_FRAUD",
                    "affected_ids": ["PAY-1"],
                    "amount_minor": 1,
                    "currency": "KZT",
                    "evidence_ids": ["INV-1"],
                }
            )

    def test_empty_affected_ids_fails(self) -> None:
        with self.assertRaises(ContractError):
            self.v.validate(
                {
                    "type": "DUPLICATE_PAYMENT",
                    "affected_ids": [],
                    "amount_minor": 1,
                    "currency": "KZT",
                    "evidence_ids": ["INV-1"],
                }
            )


class TruthAndManifestSchemaTests(unittest.TestCase):
    def test_manifest_rejects_truth_leak_fields(self) -> None:
        v = validator("episode_manifest.schema.json")
        payload = {
            "manifest_version": "1.0.0",
            "episode_id": "EP-L1-ABCDEF123456",
            "difficulty": "L1",
            "contract_version": "1.0.0",
            "generator_version": "1.0.0",
            "config_hash": "a" * 64,
            "schema_versions": {},
            "public_files": [
                {"name": "company.json", "sha256": "b" * 64, "bytes": 10, "rows": 1}
            ],
            "public_digest": "c" * 64,
            "commitment": {"algorithm": "sha256(salt||truth_digest)", "commitment_hex": "d" * 64},
            "table_counts": {},
            "timezone": "UTC",
            "functional_currency": "KZT",
            "created_at_utc": "2026-11-21T00:00:00+00:00",
            "canary_scan": {"scan_version": "v1", "public_hits": 0},
        }
        v.validate(payload)
        leaked = dict(payload)
        leaked["finding_count"] = 2
        with self.assertRaises(ContractError):
            v.validate(leaked)

    def test_manifest_canary_hits_must_be_zero(self) -> None:
        v = validator("episode_manifest.schema.json")
        with self.assertRaises(ContractError):
            v.validate(
                {
                    "manifest_version": "1.0.0",
                    "episode_id": "EP-L1-ABCDEF123456",
                    "difficulty": "L1",
                    "contract_version": "1.0.0",
                    "generator_version": "1.0.0",
                    "config_hash": "a" * 64,
                    "schema_versions": {},
                    "public_files": [
                        {"name": "company.json", "sha256": "b" * 64, "bytes": 10, "rows": 1}
                    ],
                    "public_digest": "c" * 64,
                    "commitment": {
                        "algorithm": "sha256(salt||truth_digest)",
                        "commitment_hex": "d" * 64,
                    },
                    "table_counts": {},
                    "timezone": "UTC",
                    "functional_currency": "KZT",
                    "created_at_utc": "2026-11-21T00:00:00+00:00",
                    "canary_scan": {"scan_version": "v1", "public_hits": 3},
                }
            )

    def test_truth_requires_signature_and_evidence(self) -> None:
        v = validator("truth.schema.json")
        finding = {
            "truth_id": "TR-001",
            "type": "DUPLICATE_PAYMENT",
            "affected_ids": ["PAY-1"],
            "amount_minor": 10,
            "currency": "KZT",
            "tolerance_minor": 0,
            "evidence_sets": [["INV-1"]],
            "minimal_evidence_size": 1,
            "invariant_signature": {
                "invariant_id": "INV-04",
                "entity_key": "invoices:INV-1",
                "expected_delta_minor": 10,
                "currency": "KZT",
                "direction": "over",
                "tolerance_minor": 0,
                "side_effect_class": "intended",
            },
            "operator_version": "1.0.0",
            "depends_on": [],
            "optimal_steps_model_id": "query_plan_v1",
            "optimal_steps": None,
        }
        document = {
            "truth_version": "1.0.0",
            "episode_id": "EP-L1-ABCDEF123456",
            "mode": "ANOMALOUS",
            "findings": [finding],
            "diff_summary": {
                "added": 1,
                "removed": 0,
                "modified": 1,
                "unchanged_tables_digest": "e" * 64,
            },
            "distractors": [],
        }
        v.validate(document)
        broken = json.loads(json.dumps(document))
        broken["findings"][0]["evidence_sets"] = []
        with self.assertRaises(ContractError):
            v.validate(broken)


class CanonicalJsonTests(unittest.TestCase):
    def test_key_order_independence(self) -> None:
        left = {"b": 1, "a": {"y": 2, "x": [3, {"k": 4, "j": 5}]}}
        right = {"a": {"x": [3, {"j": 5, "k": 4}], "y": 2}, "b": 1}
        self.assertEqual(canonical_json(left), canonical_json(right))
        self.assertEqual(digest_of(left), digest_of(right))

    def test_utf8_not_escaped(self) -> None:
        self.assertIn("Алматы", canonical_json({"city": "Алматы"}))

    def test_float_rejected(self) -> None:
        with self.assertRaises(ContractError):
            canonical_json({"rate": 0.5})

    def test_decimal_rejected(self) -> None:
        from decimal import Decimal

        with self.assertRaises(ContractError):
            canonical_json({"rate": Decimal("0.5")})

    def test_nan_rejected(self) -> None:
        with self.assertRaises(ContractError):
            canonical_json({"x": float("nan")})

    def test_cr_rejected(self) -> None:
        with self.assertRaises(ContractError):
            canonical_json({"x": "a\rb"})

    def test_non_string_key_rejected(self) -> None:
        with self.assertRaises(ContractError):
            canonical_json({1: "a"})

    def test_set_is_sorted(self) -> None:
        self.assertEqual(canonical_json({"s": {"b", "a"}}), '{"s":["a","b"]}')

    def test_separators_are_compact(self) -> None:
        self.assertEqual(canonical_json({"a": 1, "b": 2}), '{"a":1,"b":2}')

    def test_bool_and_none_supported(self) -> None:
        self.assertEqual(canonical_json({"a": True, "b": None}), '{"a":true,"b":null}')


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
