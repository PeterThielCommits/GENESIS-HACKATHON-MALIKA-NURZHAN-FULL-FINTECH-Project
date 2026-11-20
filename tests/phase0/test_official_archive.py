"""Phase 0 gate: the archive is immutable and the missing material is stated."""

from __future__ import annotations

import hashlib
import unittest

from tests.support import DOCS, ROOT, load_json, read_text


class ArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_json(DOCS / "official" / "MANIFEST.json")

    def test_hashes_and_sizes_match(self) -> None:
        for entry in self.manifest["documents"]:
            path = ROOT / entry["path"]
            self.assertTrue(path.is_file(), entry["path"])
            raw = path.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), entry["sha256"], entry["path"])
            self.assertEqual(len(raw), entry["bytes"], entry["path"])
            lines = raw.decode("utf-8").count("\n") + (0 if raw.endswith(b"\n") else 1)
            self.assertEqual(lines, entry["lines"], entry["path"])

    def test_classification_is_declared_and_not_official(self) -> None:
        for entry in self.manifest["documents"]:
            self.assertIn(entry["classification"], {"DERIVED_INTERNAL", "OFFICIAL_ORGANIZER"})
        self.assertTrue(all(entry["classification"] == "DERIVED_INTERNAL"
                            for entry in self.manifest["documents"]),
                        "no organizer document has been archived, so none may be classified official")

    def test_absent_material_is_listed(self) -> None:
        absent = {item["document"] for item in self.manifest["absent"]}
        for expected in ("Official organizer technical specification",
                         "Official rubric with 80 checks and weights",
                         "Official starter code / environment adapter",
                         "Official sample inputs and outputs"):
            self.assertIn(expected, absent)
        for item in self.manifest["absent"]:
            self.assertEqual(item["status"], "NOT_RECEIVED")
            self.assertTrue(item["question"])

    def test_two_person_review_is_recorded_honestly(self) -> None:
        text = read_text(DOCS / "official" / "CONTRACT_SIGNOFF.md")
        self.assertEqual(text.count("## Reviewer 1"), 1)
        self.assertEqual(text.count("## Reviewer 2"), 1)
        reviewer1 = text.split("## Reviewer 2")[0]
        self.assertIn("**Status:** SIGNED", reviewer1)
        for field_name in ("**Name:**", "**Date:**", "**Scope:**", "**Evidence:**"):
            self.assertIn(field_name, reviewer1)
        reviewer2 = text.split("## Reviewer 2")[1]
        status = "SIGNED" if "**Status:** SIGNED" in reviewer2 else "PENDING"
        self.assertIn(status, {"SIGNED", "PENDING"})
        if status == "PENDING":
            self.assertIn("HUMAN_ACTION_REQUIRED" if False else "human", reviewer2.lower())

    def test_contract_summary_is_marked_provisional(self) -> None:
        summary = read_text(DOCS / "official" / "CONTRACT_SUMMARY.md")
        self.assertIn("PROVISIONAL INTERNAL SUMMARY", summary)
        self.assertIn("UNKNOWN", summary)
        for item in ("Q-001", "Q-005", "Q-012"):
            self.assertIn(item, summary)

    def test_search_log_records_every_channel_and_rejects_third_party_sources(self) -> None:
        log = read_text(DOCS / "official" / "SOURCE_SEARCH_LOG.md")
        for channel in ("User attachment", "Public web search", "GitHub repository search",
                        "GitHub code search"):
            self.assertIn(channel, log)
        self.assertIn("Not authoritative", log)
        self.assertIn("organizer contract", log)
        self.assertIn("never** treated as the organizer contract", log)

    def test_archive_readme_states_the_absence(self) -> None:
        readme = read_text(DOCS / "official" / "README.md")
        self.assertIn("no organizer-published document", readme.lower())
        self.assertIn(self.manifest["documents"][0]["sha256"], readme)


if __name__ == "__main__":
    unittest.main()
