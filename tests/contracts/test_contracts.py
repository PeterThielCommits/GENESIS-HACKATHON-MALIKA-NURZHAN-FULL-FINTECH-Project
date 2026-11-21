"""Contract schema tests (REQ-CONTRACT-001..005, Phase 1 exit gate)."""

import json
import unittest
from pathlib import Path

from contracts.loader import SCHEMA_FILES, load_schema, validate_instance
from contracts.version import CONTRACT_VERSION

FIX_VALID = Path(__file__).resolve().parent.parent / "fixtures" / "valid"
FIX_INVALID = Path(__file__).resolve().parent.parent / "fixtures" / "invalid"

# fixture file -> contract name
VALID_MAP = {
    "finding.json": "finding",
    "company.json": "company",
    "policy.json": "policy",
    "tool_request.json": "tool_request",
    "tool_response.json": "tool_response",
    "truth.json": "truth",
    "trajectory_event.json": "trajectory_event",
    "receipt.json": "receipt",
    "verifier_report.json": "verifier_report",
    "rubric_check.json": "rubric_check",
    "episode_manifest.json": "episode_manifest",
}

INVALID_MAP = {
    "finding_unknown_type.json": "finding",
    "finding_untyped_id.json": "finding",
    "finding_missing_evidence.json": "finding",
    "finding_extra_field.json": "finding",
    "tool_request_unknown_tool.json": "tool_request",
    "policy_bad_page_size.json": "policy",
}


class TestContracts(unittest.TestCase):
    def test_all_schemas_load_and_have_version(self):
        for name in SCHEMA_FILES:
            schema = load_schema(name)
            self.assertIn("title", schema, name)
            self.assertIn("type", schema, name)

    def test_valid_fixtures_pass(self):
        for fname, contract in VALID_MAP.items():
            data = json.loads((FIX_VALID / fname).read_text(encoding="utf-8"))
            errors = validate_instance(contract, data)
            self.assertEqual(errors, [], f"{fname} should be valid: {errors}")

    def test_invalid_fixtures_rejected(self):
        for fname, contract in INVALID_MAP.items():
            data = json.loads((FIX_INVALID / fname).read_text(encoding="utf-8"))
            errors = validate_instance(contract, data)
            self.assertNotEqual(errors, [], f"{fname} should be rejected")

    def test_unknown_schema_is_bounded_error(self):
        with self.assertRaises(KeyError):
            load_schema("nonexistent")

    def test_version_consistency(self):
        version = json.loads(
            (Path(__file__).resolve().parent.parent.parent / "contracts" / "version.json").read_text(encoding="utf-8")
        )
        self.assertEqual(version["contract_version"], CONTRACT_VERSION)
        self.assertEqual(version["schema_version"], "1.0.0")

    def test_x_extension_allowed_but_unknown_rejected(self):
        data = json.loads((FIX_VALID / "finding.json").read_text(encoding="utf-8"))
        data["x_twinledger_debug"] = "ok"
        self.assertEqual(validate_instance("finding", data), [])
        data["unknown_field"] = "nope"
        self.assertNotEqual(validate_instance("finding", data), [])


if __name__ == "__main__":
    unittest.main()
