"""Phase 0 gate: no provisional item is presented as official, and no secret is committed.

The detector is a guard, not a proof-reader: the tests below pin its behaviour on synthetic
lines so that a future refactor cannot silently make it always-pass.
"""

from __future__ import annotations

import re
import unittest

from tests.support import ROOT, read_text
from tools import check_governance


class ClaimDetectorBehaviourTests(unittest.TestCase):
    def _violations(self, line: str) -> list[str]:
        hits = []
        for pattern, description in check_governance.FORBIDDEN_CLAIMS:
            if pattern.search(line) and not check_governance.NEGATIONS.search(line):
                hits.append(description)
        return hits

    # Lines below are detector samples, not documentation: they are exempt from the repository
    # scan through the explicit marker checked by test_samples_are_marked.
    def test_plain_claims_are_flagged(self) -> None:
        self.assertTrue(self._violations("Our official score is 100/100."))  # claim-detector-sample
        self.assertTrue(self._violations("The official rubric is known and complete."))  # claim-detector-sample
        self.assertTrue(self._violations("We guarantee victory in this hackathon."))  # claim-detector-sample

    def test_discussion_of_claims_is_not_flagged(self) -> None:
        self.assertEqual(self._violations("No report may claim 100/100 or an official score."), [])
        self.assertEqual(self._violations("The scan blocks \"100/100\" and official score claims."), [])
        self.assertEqual(self._violations("It is forbidden to announce an official score."), [])
        self.assertEqual(self._violations("Никогда нельзя заявлять 100/100."), [])
        self.assertEqual(self._violations("A false claim of 100/100 is a release blocker."), [])

    def test_provisional_context_is_not_flagged(self) -> None:
        self.assertEqual(self._violations("Provisional: the official rubric is not published."), [])

    def test_secret_patterns(self) -> None:
        self.assertTrue(any(p.search('"salt": "a1b2c3d4e5f60718"')  # claim-detector-sample
                            for p, _ in check_governance.LEAK_PATTERNS))
        self.assertFalse(any(p.search('"salt_ref": "sealed/salt.hex"')
                             for p, _ in check_governance.LEAK_PATTERNS))


class RepositoryClaimScanTests(unittest.TestCase):
    def test_repository_contains_no_forbidden_claim(self) -> None:
        check = check_governance.check_no_official_claims()
        self.assertEqual(check.status, "PASS", check.reason)
        self.assertFalse(check.blocker)

    def test_repository_contains_no_committed_secret_literal(self) -> None:
        check = check_governance.check_no_official_claims()
        self.assertNotIn("literal salt/seed value committed", check.reason)

    def test_rubric_map_never_becomes_official(self) -> None:
        text = read_text("judge/rubric_map.json")
        self.assertNotIn('"official": true', text)
        self.assertIn('"official_rubric_available": false', text)

    def test_exemptions_are_explicit_and_limited_to_this_test_module(self) -> None:
        marker = check_governance.DETECTOR_SAMPLE_MARKER
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file() or path.suffix not in {".md", ".py", ".json", ".txt"}:
                continue
            if ".git" in path.parts or "artifacts" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if marker in text:
                in_detector_tests = path.parent == ROOT / "tests" / "phase0"
                self.assertTrue(path == ROOT / "tools" / "check_governance.py" or in_detector_tests,
                                f"{path} uses the detector exemption marker outside tests/")
                self.assertNotIn("docs", path.parts,
                                 f"documentation may never be exempted: {path}")

    def test_no_document_claims_a_guaranteed_win(self) -> None:
        for path in sorted((ROOT / "docs").rglob("*.md")):
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"(?i)\bwe (?:will|are going to) win\b", text),
                              f"{path.name} promises a win")


if __name__ == "__main__":
    unittest.main()
