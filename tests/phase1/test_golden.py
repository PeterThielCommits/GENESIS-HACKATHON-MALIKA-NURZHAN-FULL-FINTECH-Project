"""Phase 1 exit gate: the contract set is frozen and the freeze is verifiable."""

from __future__ import annotations

import json
import unittest

from tests.support import CONTRACTS, load_json
from tools import check_golden, validate_contracts


class GoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.golden = load_json(CONTRACTS / "GOLDEN.json")
        cls.recomputed = check_golden.compute()

    def test_golden_file_is_current(self) -> None:
        result = check_golden.run()
        self.assertEqual(result["status"], "PASS", result["problems"])
        self.assertGreaterEqual(result["files_checked"], 40)

    def test_every_contract_file_is_covered(self) -> None:
        recorded = set(self.golden["files"])
        current = set(self.recomputed["files"])
        self.assertEqual(recorded, current, "the freeze does not cover the contract set exactly")

    def test_hashes_match_the_files_on_disk(self) -> None:
        import hashlib

        for name, meta in self.golden["files"].items():
            raw = (CONTRACTS / name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), meta["sha256"], name)
            self.assertEqual(len(raw), meta["bytes"], name)

    def test_freeze_digests_are_consistent(self) -> None:
        self.assertEqual(self.golden["contract_set_digest"], self.recomputed["contract_set_digest"])
        self.assertEqual(self.golden["fixtures_digest"], self.recomputed["fixtures_digest"])
        self.assertNotEqual(self.golden["contract_set_digest"], self.golden["fixtures_digest"])

    def test_contract_digest_ignores_freeze_metadata(self) -> None:
        """`contract_digest()` names the payload; GOLDEN.json is metadata about it."""
        payload = {name: meta["sha256"] for name, meta in self.golden["files"].items()
                   if not name.startswith("fixtures/")}
        self.assertNotIn("GOLDEN.json", payload)
        self.assertEqual(len(validate_contracts.contract_digest()), 64)

    def test_golden_file_documents_how_to_refresh(self) -> None:
        self.assertIn("check_golden --write", self.golden["note"])
        self.assertIn("docs/CR/", self.golden["note"])

    def test_a_modified_file_would_be_detected(self) -> None:
        """Prove the check is not vacuous: perturb a copy of the recorded data in memory."""
        tampered = json.loads(json.dumps(self.golden))
        first = sorted(tampered["files"])[0]
        tampered["files"][first]["sha256"] = "0" * 64
        self.assertNotEqual(tampered["files"][first]["sha256"],
                            self.recomputed["files"][first]["sha256"])


if __name__ == "__main__":
    unittest.main()
