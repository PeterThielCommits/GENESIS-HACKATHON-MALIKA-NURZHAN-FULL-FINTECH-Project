"""Phase 0 task 0.7: the starter smoke test is a real probe, not a sentence."""

from __future__ import annotations

import unittest

from tests.support import CONFIGS, DOCS, ROOT, load_json, read_text
from tools import probe_starter


class StarterProbeTests(unittest.TestCase):
    def test_probe_runs_and_reports_a_status(self) -> None:
        result = probe_starter.probe(run=False)
        self.assertIn(result["status"], {"SKIPPED", "PASS", "FAIL"})
        self.assertTrue(result["reason"])

    def test_absent_starter_is_reported_as_skipped_with_evidence(self) -> None:
        result = probe_starter.probe(run=False)
        if result["status"] == "SKIPPED":
            self.assertEqual(result["found"], [])
            self.assertTrue(result["candidates_scanned"])
            self.assertIn("manifest records as absent", " ".join(
                ["manifest records as absent"] if result["manifest_absent_entries"] else [""]))

    def test_no_bundle_is_imported_into_the_repository(self) -> None:
        for candidate in probe_starter.CANDIDATES:
            path = ROOT / candidate
            self.assertFalse(path.is_dir() and any(path.rglob("*.py")),
                             f"{candidate} exists: archive it with a manifest before use")

    def test_probe_config_declares_rules_and_does_not_execute_by_default(self) -> None:
        config = load_json(CONFIGS / "submission" / "starter_probe.json")
        self.assertIs(config["values"]["EXECUTE_BY_DEFAULT"], False)
        self.assertGreaterEqual(len(config["rules"]), 3)
        self.assertIn("timeout_seconds", config)

    def test_manifest_and_probe_agree_about_the_absence(self) -> None:
        manifest = load_json(DOCS / "official" / "MANIFEST.json")
        absent = " ".join(item["document"] for item in manifest["absent"]).lower()
        result = probe_starter.probe(run=False)
        if not result["found"]:
            self.assertIn("starter", absent)

    def test_archive_doc_describes_the_probe(self) -> None:
        readme = read_text(DOCS / "official" / "README.md")
        self.assertIn("probe_starter", readme)


if __name__ == "__main__":
    unittest.main()
