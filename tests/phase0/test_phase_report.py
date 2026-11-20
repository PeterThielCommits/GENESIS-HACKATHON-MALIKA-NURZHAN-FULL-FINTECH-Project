"""Phase 0 gate: the phase report is honest, complete and matches the artifacts it cites."""

from __future__ import annotations

import json
import unittest

from tests.support import DOCS, ROOT, load_json, read_text

REPORT_MD = DOCS / "PHASE_REPORTS" / "PHASE-00.md"
REPORT_JSON = DOCS / "PHASE_REPORTS" / "PHASE-00.json"
SUMMARY = ROOT / "artifacts" / "reports" / "latest" / "verify_summary.json"

REQUIRED_HEADINGS = ("## Outcome", "## Objectives", "## Verification", "## Risks", "## Owner sign-off")
REQUIRED_KEYS = ("phase", "status", "requirements", "verification", "artifacts", "known_limitations")


class PhaseReportStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.md = REPORT_MD.read_text(encoding="utf-8")
        cls.payload = load_json(REPORT_JSON)

    def test_both_files_exist(self) -> None:
        self.assertTrue(REPORT_MD.is_file())
        self.assertTrue(REPORT_JSON.is_file())

    def test_human_report_has_every_required_section(self) -> None:
        for heading in REQUIRED_HEADINGS:
            self.assertIn(heading, self.md, f"phase report lost the '{heading}' section")

    def test_machine_report_has_every_required_key(self) -> None:
        for key in REQUIRED_KEYS:
            self.assertIn(key, self.payload, f"phase report json lost '{key}'")

    def test_json_is_valid_and_internally_consistent(self) -> None:
        json.dumps(self.payload)  # parses
        self.assertEqual(self.payload["phase"], "PHASE-00")
        self.assertIn(self.payload["status"],
                      {"PASS", "PASS_WITH_OPEN_ITEMS", "FAIL", "BLOCKED", "INCOMPLETE"})
        self.assertEqual(self.payload["requirements"]["assumptions_unresolved"],
                         self.payload["requirements"]["assumptions_total"],
                         "Phase 0 requires every assumption to still be unresolved")

    def test_status_vocabulary_is_honest(self) -> None:
        # PASS_WITH_OPEN_ITEMS is only legitimate when open items are actually listed.
        if self.payload["status"] == "PASS_WITH_OPEN_ITEMS":
            self.assertTrue(self.payload["human_actions_required"])
            self.assertIn("PENDING", self.md)
            self.assertIn("human", self.md.lower())


class PhaseReportMatchesArtifactTests(unittest.TestCase):
    """REQ-JUDGE-002: if a report and an artifact disagree, the report is the bug."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = load_json(REPORT_JSON)
        if not SUMMARY.is_file():
            raise unittest.SkipTest("no artifacts yet: run `python3 -m tools.verify --profile core`")
        cls.summary = json.loads(SUMMARY.read_text(encoding="utf-8"))

    def test_counts_come_from_the_verification_summary(self) -> None:
        verification = self.payload["verification"]
        self.assertEqual(verification["checks_total"], self.summary["counts"]["checks_total"])
        self.assertEqual(verification["planned_blocked"], self.summary["counts"]["planned_blocked"])
        self.assertEqual(verification["tests_run"], self.summary["tests"]["tests_run"])
        self.assertEqual(verification["tests_failed"], self.summary["tests"]["failed"])
        self.assertEqual(verification["contract_digest"], self.summary["digests"]["contracts"])

    def test_no_failure_is_reported_as_a_pass(self) -> None:
        if self.summary["counts"]["failed"]:
            self.assertNotEqual(self.payload["status"], "PASS")
            self.assertNotEqual(self.payload["status"], "PASS_WITH_OPEN_ITEMS")

    def test_every_cited_artifact_exists_or_is_declared_generated(self) -> None:
        for relative in self.payload["artifacts"]:
            path = ROOT / relative
            self.assertTrue(path.is_file(), f"phase report cites a missing artifact: {relative}")

    def test_contract_digest_matches_the_frozen_contract_set(self) -> None:
        from tools import validate_contracts
        self.assertEqual(self.payload["verification"]["contract_digest"],
                         validate_contracts.contract_digest(),
                         "the phase report froze a digest that is no longer current")

    def test_known_limitations_are_specific(self) -> None:
        limitations = self.payload["known_limitations"]
        self.assertGreaterEqual(len(limitations), 5)
        for item in limitations:
            self.assertGreater(len(item), 40, f"limitation is too vague: {item!r}")
        joined = " ".join(limitations)
        for topic in ("organizer contract", "adapter", "signature", "deadline"):
            self.assertIn(topic, joined, f"limitations do not mention {topic}")

    def test_report_does_not_present_the_internal_suite_as_a_score(self) -> None:
        lowered = json.dumps(self.payload, ensure_ascii=False).lower()
        self.assertNotIn("jury score:", lowered)
        self.assertIn("not a jury score", lowered)


class StatusDocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = read_text(DOCS / "STATUS.md")

    def test_status_uses_the_documented_vocabulary(self) -> None:
        for token in ("PASS", "FAIL", "SKIPPED", "BLOCKED", "NOT RUN", "PASS_WITH_OPEN_ITEMS"):
            self.assertIn(token, self.text, f"STATUS.md does not use {token!r}")

    def test_gate_table_covers_phase_zero_rows(self) -> None:
        self.assertIn("| Gate |", self.text)
        for gate in ("Archive official sources", "contracts/", "Two-person review", "Submission deadline"):
            self.assertIn(gate, self.text, f"gate table lost the row {gate!r}")

    def test_human_actions_are_listed(self) -> None:
        self.assertIn("Human actions required", self.text)
        self.assertIn("Reviewer 2", self.text)
        self.assertIn("OPEN-0", self.text)

    def test_no_gate_is_reported_green_without_evidence(self) -> None:
        for line in self.text.splitlines():
            if line.startswith("|") and "`PASS`" in line and "PHASE-00" in line:
                evidence = ("docs/", "contracts/", "artifacts/", "tools/", "tests/",
                            "adapter/", "configs/", "judge/")
                self.assertTrue(any(token in line for token in evidence),
                                f"gate row has no evidence path: {line}")

    def test_current_state_exists_and_stays_short(self) -> None:
        current = read_text(DOCS / "CURRENT_STATE.md")
        self.assertLessEqual(len(current.splitlines()), 120,
                             "CURRENT_STATE.md must stay under two screens")
        for token in ("Read in this order", "What exists", "does not exist"):
            self.assertIn(token, current)


if __name__ == "__main__":
    unittest.main()
