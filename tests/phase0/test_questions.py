"""Phase 0 gate: questions are numbered, owned, closed with evidence and never fabricate answers."""

from __future__ import annotations

import re
import unittest

from tests.support import DOCS, assumptions, read_text
from tests.support import markdown_sections


class QuestionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = read_text(DOCS / "QUESTIONS.md")
        all_sections = markdown_sections(cls.text)
        cls.sections = {k: v for k, v in all_sections.items()
                        if re.fullmatch(r"(Q-[0-9]{3}|OPEN-0)", k)}

    def test_all_fourteen_questions_exist_plus_the_deadline_finding(self) -> None:
        expected = [f"Q-{n:03d}" for n in range(1, 15)]
        for qid in expected:
            self.assertIn(qid, self.sections, f"{qid} is missing")
        self.assertIn("OPEN-0", self.sections, "the missing deadline must be recorded as a finding")

    def test_question_order_and_numbering(self) -> None:
        numbers = [int(qid.split("-")[1]) for qid in self.sections if qid.startswith("Q-")]
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)), "question numbers must be contiguous")

    def test_each_question_has_the_required_fields(self) -> None:
        for qid, body in self.sections.items():
            status = re.search(r"\*\*Status:\*\*\s*([A-Z_]+)", body)
            self.assertIsNotNone(status, f"{qid} has no status")
            self.assertIn(status.group(1), {"OPEN", "ANSWERED", "WITHDRAWN", "PROVISIONAL_VERBAL"}, qid)
            for field_name in ("Asked to", "Date asked", "Owner", "Close condition",
                               "Impact if unanswered", "Current mitigation"):
                self.assertIn(f"**{field_name}:**", body, f"{qid} lacks {field_name}")

    def test_open_questions_have_mitigation_and_impact(self) -> None:
        for qid, body in self.sections.items():
            status = re.search(r"\*\*Status:\*\*\s*([A-Z_]+)", body).group(1)
            if status in {"OPEN", "PROVISIONAL_VERBAL"}:
                mitigation = body.split("**Current mitigation:**")[1].strip()
                self.assertGreater(len(mitigation), 10, f"{qid} has an empty mitigation")
                impact = body.split("**Impact if unanswered:**")[1].split("**")[0].strip()
                self.assertGreater(len(impact), 10, f"{qid} has an empty impact statement")

    def test_answered_questions_quote_a_source(self) -> None:
        for qid, body in self.sections.items():
            if "**Status:** ANSWERED" in body:
                self.assertIn("**Answer source:**", body, f"{qid} is ANSWERED without a source")

    def test_every_assumption_question_is_open_until_an_answer_exists(self) -> None:
        referenced = {item["question_id"] for item in assumptions().values()}
        for qid in referenced:
            body = self.sections[qid]
            status = re.search(r"\*\*Status:\*\*\s*([A-Z_]+)", body).group(1)
            if status == "ANSWERED":
                self.assertIn("**Answer source:**", body)
            self.assertIn("**Related assumptions:**", body, qid)

    def test_assumption_links_are_bidirectional(self) -> None:
        items = assumptions()
        for aid, item in items.items():
            body = self.sections[item["question_id"]]
            self.assertIn(aid, body, f"{aid} is not listed under {item['question_id']}")
        for qid, body in self.sections.items():
            if not qid.startswith("Q-"):
                continue
            related = body.split("**Related assumptions:**")[1].split("**")[0]
            for aid in re.findall(r"A-[0-9]{3}", related):
                self.assertIn(aid, items, f"{qid} references unknown assumption {aid}")

    def test_deadline_is_not_claimed_anywhere(self) -> None:
        body = self.sections["OPEN-0"]
        self.assertIn("**Status:** OPEN", body)
        without_asked = body.replace("**Date asked:** 2026-11-20", "")
        self.assertNotRegex(without_asked, r"\b\d{4}-\d{2}-\d{2}\b", "no deadline date may be invented")


if __name__ == "__main__":
    unittest.main()
