"""Every declared contract fixture behaves exactly as declared (REQ-CONTRACT-002/004)."""

from __future__ import annotations

import unittest

from tests.support import CONTRACTS, load_json
from tools.jsonschema_lite import ContractValidator, SchemaError
from tools.validate_contracts import run


class FixtureSuiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run()
        cls.validator = ContractValidator(CONTRACTS)

    def test_all_declared_cases_behave_as_declared(self) -> None:
        failures = [f"{case['case_id']}: {msg}" for case in self.result.cases
                    for msg in case["failures"]]
        self.assertEqual(failures, [], f"{len(failures)} fixture(s) disagreed with their declaration")
        self.assertTrue(self.result.ok)

    def test_every_schema_has_valid_and_invalid_case(self) -> None:
        index = load_json(CONTRACTS / "fixtures" / "index.json")
        version = load_json(CONTRACTS / "version.json")
        required = {entry["file"] for entry in version["schemas"] if entry.get("kind") != "definitions"}
        for schema in required:
            kinds = {case["expect"] for case in index["cases"] if case["schema"] == schema}
            self.assertEqual(kinds, {"valid", "invalid"}, f"{schema} lacks valid/invalid coverage")

    def test_invalid_cases_are_rejected_for_the_declared_reason(self) -> None:
        index = load_json(CONTRACTS / "fixtures" / "index.json")
        for case in index["cases"]:
            if case["expect"] != "invalid":
                continue
            errors = self.validator.validate_file(CONTRACTS / "fixtures" / case["file"], case["schema"])
            self.assertTrue(errors, f"{case['case_id']} unexpectedly validated")
            for expected in case.get("expect_errors", []):
                self.assertTrue(
                    any(e.path == expected["path"] and e.keyword == expected["keyword"] for e in errors),
                    f"{case['case_id']} did not fail at {expected['path']} [{expected['keyword']}]: {errors}",
                )

    def test_unknown_fields_are_rejected_but_extensions_allowed(self) -> None:
        base = load_json(CONTRACTS / "fixtures" / "valid" / "finding_duplicate_payment.json")
        extended = dict(base, x_twinledger_policy={"budget": 100})
        self.assertEqual(self.validator.validate(extended, "finding.schema.json"), [])
        unknown = dict(base, reviewer_note="look here")
        paths = {error.path for error in self.validator.validate(unknown, "finding.schema.json")}
        self.assertIn("$/reviewer_note", paths)

    def test_ambiguous_tool_request_is_rejected(self) -> None:
        request = {
            "schema_version": "1.0.0",
            "request_id": "req-amb",
            "action": {"tool": "get_record", "args": {"table": "payments", "id": "PAY:x", "doc_id": "INV:y"}},
        }
        errors = self.validator.validate(request, "tool_request.schema.json")
        self.assertTrue(errors, "an ambiguous request must not validate")

    def test_success_response_cannot_carry_an_error(self) -> None:
        response = {
            "schema_version": "1.0.0", "protocol_version": "1.0.0", "request_id": "req-1",
            "ok": True, "result": {"accepted": True},
            "error": {"code": "INTERNAL", "message": "boom"},
        }
        keywords = {error.keyword for error in self.validator.validate(response, "tool_response.schema.json")}
        self.assertIn("not", keywords)

    def test_validator_rejects_an_unsupported_schema_keyword(self) -> None:
        with self.assertRaises(SchemaError):
            self.validator.validate({"a": 1}, "common.defs.json#/$defs/nonexistent")

    def test_fixture_index_declares_only_known_schemas(self) -> None:
        index = load_json(CONTRACTS / "fixtures" / "index.json")
        declared = {entry["file"] for entry in load_json(CONTRACTS / "version.json")["schemas"]}
        for case in index["cases"]:
            self.assertIn(case["schema"], declared, case["case_id"])


if __name__ == "__main__":
    unittest.main()
