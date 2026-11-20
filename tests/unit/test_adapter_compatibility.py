"""Adapter boundary (REQ-ADAPTER-001..003, D-0006): fail closed while unbound."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.support import CONFIGS, ROOT, load_json
from adapter.compatibility import (
    AdapterError,
    AdapterNotBound,
    InvalidExternalPayload,
    UnsupportedProfileVersion,
    load_profile,
)
from adapter import organizer


class UnboundProfileTests(unittest.TestCase):
    def test_shipped_profile_is_unbound(self) -> None:
        profile = load_profile()
        self.assertEqual(profile.status, "UNBOUND")
        self.assertFalse(profile.bound)
        self.assertEqual(profile.profile_id, "twinledger-internal-v0")

    def test_require_bound_raises_a_bounded_error(self) -> None:
        with self.assertRaises(AdapterNotBound) as caught:
            load_profile().require_bound("normalize_request")
        self.assertEqual(caught.exception.code, "ADAPTER_NOT_BOUND")
        message = str(caught.exception)
        for absolute in ("/home", "/tmp", "C:\\", "Traceback"):
            self.assertNotIn(absolute, message, "adapter errors must not leak filesystem paths or traces")
        self.assertIn("Q-001", message)

    def test_every_entry_point_fails_closed(self) -> None:
        cases = [
            lambda: organizer.normalize_request({"action": {"tool": "list_records", "args": {}}}),
            lambda: organizer.serialize_observation({"ok": True, "result": {}}),
            lambda: organizer.normalize_finding({"type": "DUPLICATE_PAYMENT"}),
            lambda: organizer.serialize_submission([]),
        ]
        for index, call in enumerate(cases):
            with self.assertRaises(AdapterNotBound, msg=f"entry point {index} did not fail closed"):
                call()

    def test_tool_mapping_requires_a_bound_profile(self) -> None:
        with self.assertRaises(AdapterNotBound):
            load_profile().internal_tool("list_records")


class ProfileValidationTests(unittest.TestCase):
    def _write(self, profile: dict) -> Path:
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(profile, handle)
        handle.close()
        self.addCleanup(Path(handle.name).unlink)
        return Path(handle.name)

    def test_unknown_profile_version_is_rejected(self) -> None:
        raw = load_json(CONFIGS / "adapter" / "compatibility.json")
        raw["profile_version"] = "9.9.9"
        with self.assertRaises(UnsupportedProfileVersion):
            load_profile(self._write(raw))

    def test_missing_required_field_is_rejected(self) -> None:
        raw = load_json(CONFIGS / "adapter" / "compatibility.json")
        raw.pop("supported_profile_versions")
        with self.assertRaises(AdapterError):
            load_profile(self._write(raw))

    def test_invalid_status_is_rejected(self) -> None:
        raw = load_json(CONFIGS / "adapter" / "compatibility.json")
        raw["profile_status"] = "MAYBE"
        with self.assertRaises(AdapterError):
            load_profile(self._write(raw))

    def test_bound_profile_translates_and_still_rejects_unknown_fields(self) -> None:
        raw = load_json(CONFIGS / "adapter" / "compatibility.json")
        raw["profile_status"] = "BOUND"
        profile = load_profile(self._write(raw))
        self.assertTrue(profile.bound)
        self.assertEqual(profile.internal_tool("list_records"), "list_records")
        finding = {"type": "DUPLICATE_PAYMENT", "affected_ids": ["PAY:x"], "claimed_amount": 1,
                   "currency": "KZT", "evidence_ids": ["PAY:x"]}
        self.assertEqual(organizer.normalize_finding(finding, profile), finding)
        with self.assertRaises(InvalidExternalPayload):
            organizer.normalize_finding(dict(finding, unexpected=1), profile)
        with self.assertRaises(InvalidExternalPayload):
            profile.internal_tool("get_balance")

    def test_bound_request_normalization(self) -> None:
        raw = load_json(CONFIGS / "adapter" / "compatibility.json")
        raw["profile_status"] = "BOUND"
        profile = load_profile(self._write(raw))
        internal = organizer.normalize_request(
            {"request_id": "r1", "action": {"tool": "list_records", "args": {"table": "payments"}}}, profile)
        self.assertEqual(internal["action"]["tool"], "list_records")
        self.assertEqual(internal["schema_version"], "1.0.0")


class AdapterBoundaryTests(unittest.TestCase):
    def test_adapter_imports_no_internal_zone(self) -> None:
        forbidden = ("gen", "verifier", "scoring", "seal", "env", "harness", "arena")
        for path in sorted((ROOT / "adapter").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for zone in forbidden:
                self.assertNotRegex(text, rf"^\s*(?:from|import)\s+{zone}\b",
                                    f"{path.name} imports forbidden zone {zone}")

    def test_documented_candidate_mapping_covers_every_tool(self) -> None:
        raw = load_json(CONFIGS / "adapter" / "compatibility.json")
        schema = load_json("contracts/tool_request.schema.json")
        tools = set()
        for variant in schema["oneOf"]:
            tools.add(variant["properties"]["action"]["properties"]["tool"]["const"])
        self.assertEqual(set(raw["candidate_tool_aliases"]), tools)


if __name__ == "__main__":
    unittest.main()
