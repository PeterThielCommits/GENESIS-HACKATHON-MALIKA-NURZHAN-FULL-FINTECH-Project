"""Schemas are versioned, mutually consistent and stay inside the supported subset."""

from __future__ import annotations

import json
import re
import unittest

from tests.support import CONTRACTS, load_json
from tools.jsonschema_lite import SUPPORTED_KEYWORDS, ContractValidator, SchemaError

SCHEMA_KEYWORDS = {"$schema", "$id", "title", "description"}


def walk_keywords(node: object, tokens: tuple[str, ...] = ()) -> list[tuple[str, tuple[str, ...]]]:
    """Yield (keyword, token path) for every schema keyword, not descending into maps."""
    found: list[tuple[str, tuple[str, ...]]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"properties", "patternProperties", "$defs"} and isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    found.extend(walk_keywords(sub_value, tokens + (key, sub_key)))
                continue
            found.append((key, tokens))
            found.extend(walk_keywords(value, tokens + (key,)))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(walk_keywords(item, tokens + (str(index),)))
    return found


class SchemaSelfConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.version = load_json(CONTRACTS / "version.json")
        cls.validator = ContractValidator(CONTRACTS)

    def test_every_declared_schema_exists_and_parses(self) -> None:
        for entry in self.version["schemas"]:
            path = CONTRACTS / entry["file"]
            self.assertTrue(path.is_file(), entry["file"])
            json.loads(path.read_text(encoding="utf-8"))

    def test_no_undeclared_schema_file(self) -> None:
        declared = {entry["file"] for entry in self.version["schemas"]}
        present = {p.name for p in CONTRACTS.glob("*.json") if p.name.endswith(".schema.json")} | {"common.defs.json"}
        self.assertEqual(declared, present, "every contract json must be declared in version.json")

    def test_headers_are_present_and_consistent(self) -> None:
        payload_version = self.version["schema_payload_version"]
        for entry in self.version["schemas"]:
            schema = load_json(CONTRACTS / entry["file"])
            self.assertTrue(schema.get("$id"), entry["file"])
            self.assertEqual(schema.get("schema_version"), payload_version, entry["file"])
            self.assertEqual(entry["schema_version"], payload_version, entry["file"])
            self.assertEqual(schema.get("status"), "provisional", entry["file"])
            self.assertTrue(schema.get("description"), entry["file"])
            if entry["file"].endswith(".schema.json"):
                self.assertIn("provisional_reason", schema, entry["file"])
            for keyword in SCHEMA_KEYWORDS:
                self.assertIn(keyword, schema, f"{entry['file']} lacks {keyword}")

    def test_only_supported_keywords_are_used(self) -> None:
        allowed = set(SUPPORTED_KEYWORDS)
        for entry in self.version["schemas"]:
            schema = load_json(CONTRACTS / entry["file"])
            for keyword, tokens in walk_keywords(schema):
                where = "/".join(tokens) or "<root>"
                self.assertIn(keyword, allowed, f"{entry['file']} {where} uses unsupported keyword {keyword!r}")

    def test_every_ref_resolves(self) -> None:
        for entry in self.version["schemas"]:
            schema = load_json(CONTRACTS / entry["file"])
            for keyword, tokens in walk_keywords(schema):
                if keyword != "$ref":
                    continue
                ref = self._ref_at(schema, tokens)
                # Resolve through the validator; a broken ref raises SchemaError.
                try:
                    resolved, _ = self.validator._resolve_ref(ref, CONTRACTS / entry["file"])
                except SchemaError as exc:  # pragma: no cover - failure path
                    self.fail(f"{entry['file']} {tokens}: {exc}")
                self.assertIsInstance(resolved, dict)

    @staticmethod
    def _ref_at(document: object, tokens: tuple[str, ...]) -> str:
        node = document
        for token in tokens:
            node = node[int(token)] if isinstance(node, list) else node[token]
        return node["$ref"]

    def test_no_remote_refs(self) -> None:
        for entry in self.version["schemas"]:
            text = (CONTRACTS / entry["file"]).read_text(encoding="utf-8")
            self.assertNotIn('"$ref": "http', text, entry["file"])

    def test_versioning_rules_are_documented(self) -> None:
        for key in ("major", "minor", "patch", "change_control"):
            self.assertIn(key, self.version["versioning_rules"])
        self.assertEqual(self.version["unknown_field_policy"]["extension_namespace"], "x_twinledger_*")

    def test_currency_registry(self) -> None:
        registry = load_json(CONTRACTS / "currency.json")
        currencies = registry["currencies"]
        for code in ("KZT", "USD", "JPY", "KWD"):
            self.assertIn(code, currencies, f"{code} is required by the money tests")
        for code, entry in currencies.items():
            self.assertRegex(code, r"^[A-Z]{3}$")
            self.assertIsInstance(entry["exponent"], int)
            self.assertIn(entry["exponent"], (0, 2, 3), f"{code} exponent is not a reviewed value")
        self.assertEqual(currencies["JPY"]["exponent"], 0)
        self.assertEqual(currencies["KWD"]["exponent"], 3)
        self.assertIn(registry["default_rounding_mode"], registry["allowed_rounding_modes"])

    def test_anomaly_taxonomy_is_consistent_everywhere(self) -> None:
        definitions = load_json(CONTRACTS / "common.defs.json")["$defs"]["anomaly_type"]["enum"]
        catalog = load_json("spec/anomaly_catalog.json")
        catalog_types = [item["type"] for item in catalog["types"]]
        self.assertEqual(sorted(definitions), sorted(catalog_types))
        self.assertEqual(len(definitions), 4)
        for item in catalog["types"]:
            self.assertEqual(len(item["distractors"]), 4, item["type"])
            self.assertTrue(item["affected_ids_rule_candidate"])
            self.assertTrue(item["definition"])
            self.assertEqual(item["status"], "NOT_IMPLEMENTED_PHASE_4")
        distractor_ids = [d for item in catalog["types"] for d in item["distractors"]]
        self.assertEqual(len(distractor_ids), len(set(distractor_ids)), "distractor ids must be unique")

    def test_invariant_catalog_is_consistent(self) -> None:
        catalog = load_json("spec/invariants.json")
        ids = [item["id"] for item in catalog["invariants"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 17)
        self.assertEqual(ids, [f"INV-{n:02d}" for n in range(1, 18)])
        anomaly_catalog = load_json("spec/anomaly_catalog.json")
        referenced = {inv for item in anomaly_catalog["types"] for inv in item["intended_invariants"]}
        self.assertTrue(referenced <= set(ids), f"catalog references unknown invariants: {referenced - set(ids)}")
        for item in catalog["invariants"]:
            self.assertIn("grouping_key", item)
            self.assertIn("metric", item)
            self.assertIn("tolerance_minor", item)
            self.assertIn("exceptions", item)

    def test_manifest_cannot_express_a_finding_count(self) -> None:
        schema = load_json(CONTRACTS / "episode_manifest.schema.json")
        self.assertIn("findings_count", json.dumps(schema["not"]))
        forbidden = {"findings", "truth", "mutation_count", "is_clean", "anomaly_type"}
        self.assertEqual(forbidden & set(schema["properties"]), set())

    def test_rubric_check_can_never_be_official(self) -> None:
        schema = load_json(CONTRACTS / "rubric_check.schema.json")
        self.assertEqual(schema["properties"]["official"]["const"], False)

    def test_id_namespaces_match_the_documented_set(self) -> None:
        namespaces = load_json(CONTRACTS / "common.defs.json")["$defs"]["id_namespace"]["enum"]
        self.assertEqual(namespaces, ["JE", "INV", "CN", "PAY", "BANK", "FX", "CP"])
        pattern = load_json(CONTRACTS / "common.defs.json")["$defs"]["namespaced_id"]["pattern"]
        for namespace in namespaces:
            self.assertRegex(f"{namespace}:abc-123", pattern)
        self.assertIsNone(re.match(pattern, "XX:abc"))

    def test_manifest_hash_fields_are_sha256(self) -> None:
        pattern = load_json(CONTRACTS / "common.defs.json")["$defs"]["sha256_hex"]["pattern"]
        self.assertRegex("a" * 64, pattern)
        self.assertIsNone(re.fullmatch(pattern, "A" * 64), "hashes must be lower-case hex")


if __name__ == "__main__":
    unittest.main()
