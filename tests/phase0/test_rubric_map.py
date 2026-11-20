"""Phase 0 gate: the rubric map is internal, traceable and complete (REQ-JUDGE-001..005)."""

from __future__ import annotations

import re
import unittest

from tests.support import CONFIGS, ROOT, load_json, requirements

BLOCKS = {"contract_isolation", "data_truth", "reward_robustness", "reproducibility", "engineering"}
CHECK_ID = re.compile(r"[A-Z]{2,8}-[A-Z0-9]{1,16}-[0-9]{2}")


class RubricMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.map = load_json("judge/rubric_map.json")
        cls.config = load_json(CONFIGS / "rubric" / "provisional.json")
        cls.reqs = requirements()

    def test_official_rubric_is_declared_unavailable(self) -> None:
        self.assertFalse(self.map["official_rubric_available"])
        self.assertFalse(self.config["official_rubric_available"])
        self.assertTrue(self.map["provisional"])

    def test_no_check_is_presented_as_official(self) -> None:
        offenders = [c["check_id"] for c in self.map["internal_checks"] if c.get("official") is not False]
        self.assertEqual(offenders, [], "internal checks must never be marked official (D-0002)")

    def test_blocks_and_weights(self) -> None:
        blocks = {b["block"] for b in self.map["blocks"]}
        self.assertEqual(blocks, BLOCKS)
        self.assertEqual(sum(b["provisional_points"] for b in self.map["blocks"]), 100)
        scored = [b for b in self.map["blocks"] if b["block"] != "engineering"]
        self.assertEqual(len(scored), 4)
        self.assertEqual(sum(b["assumed_official_checks"] for b in scored), 80)
        self.assertEqual(next(b for b in self.map["blocks"] if b["block"] == "engineering")["assumed_official_checks"], 5)

    def test_every_check_is_well_formed(self) -> None:
        ids = [c["check_id"] for c in self.map["internal_checks"]]
        self.assertEqual(len(ids), len(set(ids)), "check ids must be unique")
        for check in self.map["internal_checks"]:
            self.assertRegex(check["check_id"], CHECK_ID)
            self.assertIn(check["block"], BLOCKS)
            self.assertTrue(check["title"])
            self.assertTrue(check["req_ids"])
            self.assertIn(check["declared_state"], {"IMPLEMENTED", "PLANNED"})
            self.assertRegex(check["phase"], r"^PHASE-[0-9]{2}$")
            self.assertTrue(check["artifact"].startswith(("artifacts/", "docs/")))
            self.assertTrue(check["command"])

    def test_every_check_cites_existing_requirements(self) -> None:
        for check in self.map["internal_checks"]:
            for req_id in check["req_ids"]:
                self.assertIn(req_id, self.reqs, f"{check['check_id']} cites unknown {req_id}")

    def test_implemented_checks_have_resolvable_commands(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        targets = set(re.findall(r"^([A-Za-z0-9_.-]+):(?!=)", makefile, re.MULTILINE))
        for check in self.map["internal_checks"]:
            if check["declared_state"] != "IMPLEMENTED":
                continue
            command = check["command"]
            make_targets = [token for token in command.split() if token in targets]
            module_match = re.search(r"python -m ([\w.]+)", command)
            self.assertTrue(make_targets or module_match, f"{check['check_id']}: {command}")
            if module_match:
                path = ROOT / (module_match.group(1).replace(".", "/") + ".py")
                self.assertTrue(path.is_file() or (ROOT / "tests").is_dir(), f"{check['check_id']}: {path}")

    def test_planned_checks_are_explicitly_blocked_not_hidden(self) -> None:
        planned = [c for c in self.map["internal_checks"] if c["declared_state"] == "PLANNED"]
        self.assertGreater(len(planned), 20, "most of the suite is still planned and must be visible")
        for check in planned:
            self.assertIn("PHASE", check["phase"])

    def test_all_five_blocks_have_checks(self) -> None:
        covered = {c["block"] for c in self.map["internal_checks"]}
        self.assertEqual(covered, BLOCKS)

    def test_rules_forbid_an_official_score_claim(self) -> None:
        self.assertIn("no_official_score_claim", self.map["rules"])
        rule = self.map["rules"]["internal_checks_are_not_official"].lower()
        self.assertTrue("never" in rule or "not" in rule, rule)

    def test_traceability_document_covers_every_check(self) -> None:
        doc = (ROOT / "docs" / "RUBRIC_TRACEABILITY.md").read_text(encoding="utf-8")
        for check in self.map["internal_checks"]:
            self.assertIn(check["check_id"], doc, f"{check['check_id']} is missing from RUBRIC_TRACEABILITY.md")

    def test_requirement_coverage_is_reported_honestly(self) -> None:
        # Not every requirement can be covered in Phase 0; the document must state the number.
        doc = (ROOT / "docs" / "RUBRIC_TRACEABILITY.md").read_text(encoding="utf-8")
        covered = {rid for c in self.map["internal_checks"] for rid in c["req_ids"]}
        self.assertIn(f"{len(covered)} / {len(self.reqs)}", doc,
                      "RUBRIC_TRACEABILITY.md must state how many requirements are mapped")


if __name__ == "__main__":
    unittest.main()
