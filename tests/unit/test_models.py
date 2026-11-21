"""Typed model round-trip tests (REQ-CONTRACT-001)."""

import json
import unittest
from pathlib import Path

from contracts.models import (
    Finding,
    Receipt,
    ToolRequest,
    ToolResponse,
    TrajectoryEvent,
    TruthFinding,
    canonical_ids,
)

FIX = Path(__file__).resolve().parent.parent / "fixtures" / "valid"


def _load(name: str):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


class TestModels(unittest.TestCase):
    def test_finding_roundtrip(self):
        data = _load("finding.json")
        f = Finding.from_dict(data)
        self.assertEqual(f.to_dict(), data)
        f.validate()

    def test_tool_request_roundtrip(self):
        data = _load("tool_request.json")
        r = ToolRequest.from_dict(data)
        self.assertEqual(r.tool, "list_records")
        self.assertEqual(r.to_dict(), data)

    def test_tool_response_ok_and_error(self):
        ok = ToolResponse.from_dict(_load("tool_response.json"))
        self.assertTrue(ok.ok)
        err = ToolResponse(request_id="r1", ok=False, error_code="NOT_FOUND", error_message="not found")
        self.assertEqual(err.to_dict()["error"]["code"], "NOT_FOUND")
        ToolResponse.from_dict(err.to_dict())

    def test_trajectory_event_roundtrip(self):
        data = _load("trajectory_event.json")
        e = TrajectoryEvent.from_dict(data)
        self.assertEqual(e.to_dict(), data)

    def test_receipt_roundtrip(self):
        data = _load("receipt.json")
        r = Receipt.from_dict(data)
        self.assertEqual(r.to_dict(), data)

    def test_truth_roundtrip(self):
        data = _load("truth.json")
        t = TruthFinding.from_dict(data)
        self.assertEqual(t.to_dict(), data)

    def test_canonical_ids_sorted_deduped(self):
        self.assertEqual(
            canonical_ids(["JE:b", "JE:a", "JE:b", "PAY:x"]),
            ("JE:a", "JE:b", "PAY:x"),
        )

    def test_invalid_finding_raises(self):
        with self.assertRaises(ValueError):
            Finding.from_dict({"type": "NOPE"})


if __name__ == "__main__":
    unittest.main()
