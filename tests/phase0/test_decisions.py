"""Phase 0 gate: the decision log is complete, machine-readable and internally consistent."""

from __future__ import annotations

import re
import unittest

from tests.support import DOCS, assumptions, load_json, read_text

DECISION_HEADING = re.compile(r"^## (D-\d{4}) — (.+)$", re.MULTILINE)
REQUIRED_FIELDS = ("Status", "Date", "Owner", "Refs", "Context", "Decision",
                   "Alternatives", "Consequences")
ALLOWED_STATUS = {"Accepted", "Proposed", "Superseded", "Rejected"}


def decisions() -> dict[str, dict]:
    """Split docs/DECISIONS.md into per-decision blocks with their bullet fields."""
    text = read_text(DOCS / "DECISIONS.md")
    matches = list(DECISION_HEADING.finditer(text))
    parsed: dict[str, dict] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.end():end]
        # The assumption register follows the last decision; stop a block at the next heading.
        block = block.split("\n## ")[0]
        fields = dict(re.findall(r"^- \*\*([A-Za-z]+):\*\*\s*(.+)$", block, re.MULTILINE))
        parsed[match.group(1)] = {"title": match.group(2).strip(), "fields": fields, "body": block}
    return parsed


class DecisionLogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.entries = decisions()

    def test_every_decision_has_every_required_field(self) -> None:
        self.assertGreaterEqual(len(self.entries), 15, "the decision log lost entries")
        for decision_id, entry in self.entries.items():
            for field_name in REQUIRED_FIELDS:
                self.assertIn(field_name, entry["fields"],
                              f"{decision_id} has no '{field_name}' field")

    def test_ids_are_sequential_and_unique(self) -> None:
        numbers = sorted(int(decision_id.split("-")[1]) for decision_id in self.entries)
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)),
                         "decision ids must be D-0001..D-00NN without gaps")
        self.assertEqual(len(numbers), len(set(numbers)))

    def test_status_and_date_are_valid(self) -> None:
        for decision_id, entry in self.entries.items():
            self.assertIn(entry["fields"]["Status"], ALLOWED_STATUS, decision_id)
            self.assertRegex(entry["fields"]["Date"], r"^\d{4}-\d{2}-\d{2}$", decision_id)

    def test_refs_point_at_real_records(self) -> None:
        known_requirements = set(load_json(DOCS / "REQUIREMENTS.json")["requirements"][0].keys())
        del known_requirements  # shape check only; ids are validated below
        requirement_ids = {item["id"] for item in load_json(DOCS / "REQUIREMENTS.json")["requirements"]}
        assumption_ids = set(assumptions())
        question_ids = set(re.findall(r"^## (Q-\d{3})", read_text(DOCS / "QUESTIONS.md"), re.MULTILINE))
        for decision_id, entry in self.entries.items():
            refs = entry["fields"]["Refs"]
            for req in re.findall(r"REQ-[A-Z]+-\d{3}", refs):
                self.assertIn(req, requirement_ids, f"{decision_id} cites unknown {req}")
            # (?<![A-Z]) so that REQ-DATA-022 is not mistaken for the assumption A-022.
            for assumption_id in re.findall(r"(?<![A-Z])A-\d{3}", refs):
                self.assertIn(assumption_id, assumption_ids,
                              f"{decision_id} cites unknown {assumption_id}")
            for question_id in re.findall(r"Q-\d{3}", refs):
                self.assertIn(question_id, question_ids, f"{decision_id} cites unknown {question_id}")

    def test_alternatives_are_actually_discussed(self) -> None:
        for decision_id, entry in self.entries.items():
            alternatives = entry["fields"]["Alternatives"]
            self.assertGreater(len(alternatives), 20,
                               f"{decision_id} does not record what was rejected")

    def test_key_phase0_decisions_exist(self) -> None:
        for decision_id in ("D-0001", "D-0002", "D-0008", "D-0015", "D-0016", "D-0019"):
            self.assertIn(decision_id, self.entries)

    def test_decisions_do_not_assert_organizer_confirmation(self) -> None:
        forbidden = (
            "official contract is available",
            "official contract is confirmed",
            "confirmed by the organizer",
            "the organizers confirmed",
            "official rubric is published",  # claim-detector-sample
            "официально подтвержд",
        )
        for decision_id, entry in self.entries.items():
            body = entry["body"].lower()
            for phrase in forbidden:
                self.assertNotIn(phrase, body,
                                 f"{decision_id} asserts organizer confirmation ({phrase!r})")


class AssumptionRegisterMirrorTests(unittest.TestCase):
    def test_register_lists_every_assumption(self) -> None:
        text = read_text(DOCS / "DECISIONS.md")
        register = text.split("## Assumption status register")[1]
        listed = set(re.findall(r"\|\s*(A-\d{3})\s*\|", register))
        self.assertEqual(listed, set(assumptions()),
                         "the register in DECISIONS.md disagrees with docs/ASSUMPTIONS.json")

    def test_register_marks_everything_unresolved(self) -> None:
        text = read_text(DOCS / "DECISIONS.md")
        register = text.split("## Assumption status register")[1]
        rows = [line for line in register.splitlines()
                if re.match(r"\|\s*A-\d{3}\s*\|", line)]
        self.assertTrue(rows)
        for row in rows:
            self.assertIn("UNRESOLVED", row, f"unexpected status in row: {row}")

    def test_statuses_match_the_json(self) -> None:
        text = read_text(DOCS / "DECISIONS.md")
        register = text.split("## Assumption status register")[1]
        for assumption_id, item in assumptions().items():
            row = next(line for line in register.splitlines()
                       if re.match(rf"\|\s*{assumption_id}\s*\|", line))
            self.assertIn(item["status"], row, assumption_id)


if __name__ == "__main__":
    unittest.main()
