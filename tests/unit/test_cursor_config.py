"""Cursor configuration (A-009, §14.5) is honest about what it does not protect."""

from __future__ import annotations

import unittest

from tests.support import CONFIGS, load_json


class CursorConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_json(CONFIGS / "environment" / "cursor.json")
        cls.token = cls.config["token"]

    def test_cursor_is_not_claimed_to_be_authenticated(self) -> None:
        self.assertFalse(self.token["authenticated"])
        self.assertEqual(self.token["integrity"], "checksum_only")
        self.assertIn("not a forgery-proof token", self.token["honest_description"])

    def test_payload_is_snapshot_bound_and_table_bound(self) -> None:
        self.assertEqual(self.token["payload_fields"],
                         ["cursor_version", "table", "snapshot_digest", "last_sort_key"])

    def test_reject_rules_use_contract_error_codes(self) -> None:
        codes = set(load_json("contracts/tool_response.schema.json")["properties"]["error"]
                    ["properties"]["code"]["enum"])
        for rule, code in self.config["reject_rules"].items():
            self.assertIn(code, codes, f"{rule} uses an undeclared error code {code}")

    def test_cursor_cannot_encode_anomaly_information(self) -> None:
        forbidden = self.config["leakage_rules"]["must_not_encode"]
        for token in ("seed", "mutation_index", "operator_name", "anomaly_position"):
            self.assertIn(token, forbidden)
        self.assertTrue(self.config["leakage_rules"]["same_structure_for_mutated_and_clean_rows"])

    def test_secret_source_is_sealed(self) -> None:
        self.assertIn("sealed", self.token["secret_source_if_authenticated"])


if __name__ == "__main__":
    unittest.main()
