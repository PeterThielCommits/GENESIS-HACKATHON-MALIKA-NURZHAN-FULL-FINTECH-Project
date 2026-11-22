"""Phase 17 release-evidence archive tests (TZ section 24, tasks 17.2/17.3/17.6).

The archive is the file that makes EXIT GATE 17 ("the release can be
restored and checked without oral explanations from the team") a fact rather
than a claim. These tests pin it: it must exist, stay honest, quote the
frozen digest, archive the rubric map and the decisions, and carry a
reconstruct command list whose scripts actually exist.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import release_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestReleaseEvidenceArchive(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.archive = json.loads(release_evidence.ARTIFACT_PATH.read_text(encoding="utf-8"))

    def test_archive_exists_and_verifies(self) -> None:
        ok, errors = release_evidence.verify_archive()
        self.assertTrue(ok, errors)

    def test_builder_is_deterministic(self) -> None:
        """The archive is generated, not hand-written: two builds must agree."""
        first = release_evidence.build_archive()
        second = release_evidence.build_archive()
        self.assertEqual(
            release_evidence._comparable(first), release_evidence._comparable(second)
        )

    def test_archive_is_honest(self) -> None:
        self.assertIs(self.archive["official_score_claimed"], False)
        self.assertEqual(self.archive["exit_gate_17"], "PASS")
        self.assertRegex(str(self.archive["git_sha"]), r"^[0-9a-f]{40}$")

    def test_all_six_tasks_are_recorded(self) -> None:
        tasks = self.archive["tasks"]
        self.assertEqual(sorted(tasks), ["17.1", "17.2", "17.3", "17.4", "17.5", "17.6"])
        for task_id, entry in tasks.items():
            with self.subTest(task=task_id):
                self.assertEqual(entry["status"], "DONE")
                self.assertTrue(str(entry["evidence"]).strip())

    def test_archived_gate_verdicts_match_the_archive_status(self) -> None:
        """FINAL archives record a passing run; DRAFT archives say why not.

        The archive is a *snapshot* of a release run, so the invariant is not
        "the current run passed" but "the archive states, honestly, what the
        run it records was". A DRAFT archive names the verdict that was not
        PASS; the release-time gate (``release_evidence --verify --strict``)
        refuses to ship one.
        """
        gates = self.archive["gates"]
        status = self.archive["status"]
        self.assertIn(status, ("FINAL", "DRAFT"))
        if status == "FINAL":
            self.assertEqual(gates["verify"]["status"], "PASS")
            self.assertEqual(gates["verify"]["gates_passed"], gates["verify"]["gates_total"])
            self.assertEqual(gates["replay_all"]["status"], "PASS")
            self.assertEqual(gates["replay_all"]["runs_matched"], gates["replay_all"]["runs_replayed"])
            self.assertEqual(gates["release_audit"]["status"], "PASS")
            self.assertEqual(self.archive["draft_reason"], "")
        else:
            self.assertTrue(str(self.archive.get("draft_reason", "")).strip())

    def test_archived_rubric_map_has_all_twelve_gates(self) -> None:
        self.assertEqual(
            self.archive["rubric_map"]["gates"], [f"RC-{i:03d}" for i in range(1, 13)]
        )

    def test_archived_decisions_exist_in_the_register(self) -> None:
        decisions = (REPO_ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
        for decision_id in self.archive["decisions"]["ids"]:
            with self.subTest(decision=decision_id):
                self.assertIn(f"## {decision_id}", decisions)

    def test_reconstruct_commands_name_existing_scripts(self) -> None:
        commands = self.archive["reconstruct"]["commands"]
        self.assertTrue(commands)
        for command in commands:
            parts = command.split()
            if len(parts) >= 2 and parts[0] == "python3" and not parts[1].startswith("-"):
                with self.subTest(command=command):
                    self.assertTrue((REPO_ROOT / parts[1]).is_file())

    def test_tampered_archive_fails_verification(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tampered = Path(td) / "archive.json"
            doc = json.loads(release_evidence.ARTIFACT_PATH.read_text(encoding="utf-8"))
            doc["official_score_claimed"] = True
            tampered.write_text(json.dumps(doc), encoding="utf-8")
            ok, errors = release_evidence.verify_archive(tampered)
            self.assertFalse(ok)
            self.assertTrue(any("official_score_claimed" in e for e in errors))

    def test_missing_archive_fails_verification(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ok, errors = release_evidence.verify_archive(Path(td) / "nope.json")
            self.assertFalse(ok)
            self.assertTrue(any("missing release-evidence archive" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
