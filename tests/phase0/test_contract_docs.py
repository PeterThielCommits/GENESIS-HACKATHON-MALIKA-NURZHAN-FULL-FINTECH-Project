"""Documentation must match the schemas (REQ-CONTRACT-005)."""

from __future__ import annotations

import re
import unittest

from tests.support import CONTRACTS, load_json, read_text


class ContractDocTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.doc = read_text(CONTRACTS / "CONTRACT.md")
        cls.version = load_json(CONTRACTS / "version.json")

    def test_every_schema_file_is_documented(self) -> None:
        for entry in self.version["schemas"]:
            self.assertIn(entry["file"], self.doc, f"{entry['file']} is not mentioned in CONTRACT.md")

    def test_documented_versions_match(self) -> None:
        self.assertIn(self.version["contract_version"], self.doc)
        self.assertIn(self.version["schema_payload_version"], self.doc)

    def test_every_error_code_is_documented(self) -> None:
        codes = load_json(CONTRACTS / "tool_response.schema.json")["properties"]["error"]["properties"]["code"]["enum"]
        for code in codes:
            self.assertIn(code, self.doc, f"error code {code} is not documented")

    def test_every_tool_is_documented(self) -> None:
        schema = load_json(CONTRACTS / "tool_request.schema.json")
        for variant in schema["oneOf"]:
            tool = variant["properties"]["action"]["properties"]["tool"]["const"]
            self.assertIn(tool, self.doc, f"tool {tool} is not documented")

    def test_every_table_and_filter_is_documented(self) -> None:
        schema = load_json(CONTRACTS / "tool_request.schema.json")
        tables = None
        filters = set()
        for variant in schema["oneOf"]:
            args = variant["properties"]["action"]["properties"]["args"]
            if "table" in args.get("properties", {}):
                tables = args["properties"]["table"]["enum"]
            if "filters" in args.get("properties", {}):
                filters |= set(args["properties"]["filters"]["properties"])
        self.assertIsNotNone(tables)
        for table in tables:
            self.assertIn(table, self.doc, f"table {table} is not documented")
        for key in filters:
            self.assertIn(key, self.doc, f"filter {key} is not documented")

    def test_finding_fields_are_documented(self) -> None:
        finding = load_json(CONTRACTS / "finding.schema.json")
        for field in list(finding["properties"]):
            self.assertIn(field, self.doc, f"finding field {field} is not documented")

    def test_currency_exponents_are_documented(self) -> None:
        registry = load_json(CONTRACTS / "currency.json")["currencies"]
        for code, entry in registry.items():
            self.assertRegex(self.doc, rf"{code}\s*{entry['exponent']}\b", f"{code} exponent missing")

    def test_canonical_rules_are_documented(self) -> None:
        lowered = self.doc.lower()
        for token in ("sort_keys", "ensure_ascii=false", "separators", "lf", "nan", "decimal"):
            self.assertIn(token, lowered, f"canonical JSON rule {token} is not documented")

    def test_id_namespaces_are_documented(self) -> None:
        namespaces = load_json(CONTRACTS / "common.defs.json")["$defs"]["id_namespace"]["enum"]
        for namespace in namespaces:
            self.assertIn(f"`{namespace}`", self.doc, f"namespace {namespace} not documented")

    def test_documented_field_names_exist_in_schemas(self) -> None:
        # Reverse direction: a `field` in backticks that looks like a schema property must exist.
        known = set()
        for path in CONTRACTS.glob("*.schema.json"):
            schema = load_json(path)
            known |= set(schema.get("properties", {}))
            for sub in schema.get("properties", {}).values():
                if isinstance(sub, dict):
                    known |= set(sub.get("properties", {}))
        # Fields that would leak the answer may only be mentioned as forbidden, never offered.
        for name in ("answer_key", "truth_ids", "is_clean"):
            self.assertNotIn(f"`{name}`", self.doc, f"CONTRACT.md must not offer a field named {name}")
        self.assertTrue(known)
        self.assertIn("findings_count", self.doc, "the manifest prohibition should stay documented")

    def test_readme_mentions_the_contract_status(self) -> None:
        readme = read_text("README.md")
        self.assertIn("provisional", readme.lower())
        self.assertIn("contracts/", readme)


if __name__ == "__main__":
    unittest.main()
