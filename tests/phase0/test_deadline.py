"""Phase 0 task 0.8: the deadline is either confirmed by a human or explicitly unknown."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from tests.support import CONFIGS, DOCS, load_json, read_text

CONFIG = CONFIGS / "submission" / "submission.json"


class SubmissionConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_json(CONFIG)
        cls.values = cls.config["values"]
        cls.doc = read_text(DOCS / "official" / "SUBMISSION_DEADLINE.md")
        cls.questions = read_text(DOCS / "QUESTIONS.md")

    def test_config_is_declared_provisional(self) -> None:
        self.assertIs(self.config["provisional"], True)
        self.assertEqual(self.config["status"], "provisional")
        self.assertTrue(self.config["assumption_ids"])

    def test_local_timezone_is_the_team_timezone_and_has_no_dst(self) -> None:
        self.assertEqual(self.values["LOCAL_TIMEZONE"], "Asia/Almaty")
        self.assertEqual(self.values["LOCAL_UTC_OFFSET_HOURS"], 5)
        self.assertIs(self.values["LOCAL_DST_OBSERVED"], False)

    def test_asia_almaty_is_utc_plus_five_all_year(self) -> None:
        """Kazakhstan unified on UTC+5 in March 2024; no DST means no ambiguous deadlines."""
        if not hasattr(__import__("zoneinfo"), "ZoneInfo"):  # pragma: no cover
            self.skipTest("zoneinfo unavailable")
        from zoneinfo import ZoneInfo

        almaty = ZoneInfo("Asia/Almaty")
        for month in (1, 3, 6, 10, 12):
            moment = datetime(2027, month, 15, 12, tzinfo=almaty)
            self.assertEqual(moment.utcoffset(), timedelta(hours=5), f"offset changed in {month}")
            self.assertFalse(moment.dst(), f"DST observed in month {month}")

    def test_unknown_deadline_is_recorded_as_unknown_everywhere(self) -> None:
        if self.values["SUBMISSION_DEADLINE_UTC"] is None:
            self.assertIn("## OPEN-0", self.questions)
            self.assertIn("UNKNOWN", self.doc)
            self.assertIsNone(self.values["DEADLINE_CONFIRMED_BY"],
                              "an empty deadline must not carry a confirmation")
        else:
            self.assertIsNotNone(self.values["DEADLINE_CONFIRMED_BY"])
            self.assertIsNotNone(self.values["DEADLINE_CONFIRMED_AT"],
                                 "a confirmed deadline must say who confirmed it and when")

    def test_local_time_matches_the_utc_offset(self) -> None:
        utc = self.values["SUBMISSION_DEADLINE_UTC"]
        local = self.values["SUBMISSION_DEADLINE_LOCAL"]
        self.assertEqual(utc is None, local is None, "both deadlines must be set or both empty")
        if utc is None:
            return
        offset = self.values["LOCAL_UTC_OFFSET_HOURS"]
        parsed_utc = datetime.fromisoformat(utc.replace("Z", "+00:00"))
        parsed_local = datetime.fromisoformat(local)
        self.assertEqual(parsed_local.replace(tzinfo=None),
                         (parsed_utc + timedelta(hours=offset)).replace(tzinfo=None))

    def test_document_explains_the_freeze_plan(self) -> None:
        for token in ("72 hours", "UNKNOWN", "Asia/Almaty", "OPEN-0", "GOV-DEADLINE-01"):
            self.assertIn(token, self.doc, f"deadline document does not mention {token}")

    def test_no_invented_date_in_the_documents(self) -> None:
        for line in self.doc.splitlines():
            if "deadline" in line.lower() and "**UNKNOWN**" not in line:
                self.assertNotRegex(line, r"\b\d{4}-\d{2}-\d{2}\b",
                                    f"a concrete deadline date appears without confirmation: {line}")


if __name__ == "__main__":
    unittest.main()
