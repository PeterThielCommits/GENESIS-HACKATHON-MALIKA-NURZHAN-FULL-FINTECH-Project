"""Phase 17 evidence-freeze tests (Master TZ section 24, tasks 17.1-17.3).

The evidence freeze pins the whole tracked release surface plus the Judge
Kit report verdicts. These tests pin the tool itself: determinism,
tamper detection, missing-manifest handling, self-exclusion, and the
verdict-vs-bytes distinction (a re-run that only changes timestamps or
run-ids must still verify).
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools import evidence_freeze


def _make_tree(tmp: Path) -> tuple[Path, Path]:
    """Create a minimal repo tree + manifest path inside tmp."""
    repo = tmp / "repo"
    (repo / "configs").mkdir(parents=True)
    (repo / "docs" / "EVIDENCE").mkdir(parents=True)
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "configs" / "c.json").write_text('{"k": 1}\n', encoding="utf-8")
    manifest = repo / "docs" / "EVIDENCE" / "evidence_freeze.json"
    return repo, manifest


def _write_report(repo: Path, rel: str, payload: dict) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestEvidenceFreezeManifest(unittest.TestCase):
    def test_manifest_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo, _ = _make_tree(Path(td))
            first = evidence_freeze.compute_manifest(repo)
            second = evidence_freeze.compute_manifest(repo)
            self.assertEqual(first["aggregate_sha256"], second["aggregate_sha256"])
            self.assertEqual(first["files"], second["files"])
            paths = [e["path"] for e in first["files"]]
            self.assertEqual(paths, sorted(paths))
            self.assertEqual(first["official_score_claimed"], False)
            self.assertEqual(first["code_version"], "twinledger@1.0.0")

    def test_manifest_excludes_itself(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo, manifest = _make_tree(Path(td))
            manifest.write_text('{"self": true}\n', encoding="utf-8")
            doc = evidence_freeze.compute_manifest(repo)
            paths = [e["path"] for e in doc["files"]]
            self.assertNotIn("docs/EVIDENCE/evidence_freeze.json", paths)

    def test_file_hash_matches_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo, _ = _make_tree(Path(td))
            doc = evidence_freeze.compute_manifest(repo)
            entry = next(e for e in doc["files"] if e["path"] == "src/a.py")
            raw = (repo / "src" / "a.py").read_bytes()
            self.assertEqual(entry["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(entry["bytes"], len(raw))


class TestEvidenceFreezeVerify(unittest.TestCase):
    def test_verify_passes_on_fresh_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo, manifest = _make_tree(Path(td))
            doc = evidence_freeze.compute_manifest(repo)
            manifest.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            ok, errs = evidence_freeze.verify_manifest(manifest, repo)
            self.assertTrue(ok, errs)

    def test_verify_detects_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo, manifest = _make_tree(Path(td))
            doc = evidence_freeze.compute_manifest(repo)
            manifest.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            (repo / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
            ok, errs = evidence_freeze.verify_manifest(manifest, repo)
            self.assertFalse(ok)
            self.assertTrue(any("src/a.py" in e for e in errs))

    def test_verify_detects_new_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo, manifest = _make_tree(Path(td))
            doc = evidence_freeze.compute_manifest(repo)
            manifest.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            (repo / "src" / "b.py").write_text("y = 1\n", encoding="utf-8")
            ok, errs = evidence_freeze.verify_manifest(manifest, repo)
            self.assertFalse(ok)
            self.assertTrue(any("src/b.py" in e for e in errs))

    def test_verify_missing_manifest_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo, manifest = _make_tree(Path(td))
            ok, errs = evidence_freeze.verify_manifest(manifest, repo)
            self.assertFalse(ok)
            self.assertTrue(any("missing evidence manifest" in e for e in errs))


class TestEvidenceFreezeVerdicts(unittest.TestCase):
    """The verdict is the archived fact; the bytes are informational."""

    def test_verdict_ignores_timestamps_and_run_ids(self) -> None:
        rel = "artifacts/reports/latest/verify_summary.json"
        base = {
            "status": "PASS",
            "run_id": "a",
            "generated_at_utc": "2026-01-01T00:00:00Z",
            "official_score_claimed": False,
            "required_checks": {"total": 12, "passed": 12},
        }
        first = evidence_freeze._extract_verdict("verify_summary", dict(base, run_id="a"))
        second = evidence_freeze._extract_verdict("verify_summary", dict(base, run_id="b"))
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "PASS")

    def test_verdict_excludes_volatile_check_details(self) -> None:
        """`duration_s` / `output_tail` must not enter the archived verdict."""
        doc = {
            "status": "PASS",
            "checks": [
                {
                    "check_id": "RC-001",
                    "status": "PASS",
                    "required": True,
                    "release_blocker": False,
                    "duration_s": 63.7,
                    "output_tail": "....ok",
                }
            ],
        }
        verdict = evidence_freeze._extract_verdict("verify_summary", doc)
        self.assertNotIn("duration_s", json.dumps(verdict))
        self.assertNotIn("output_tail", json.dumps(verdict))
        self.assertEqual(verdict["gates"][0]["check_id"], "RC-001")

    def test_verdict_detects_a_failing_gate(self) -> None:
        good = evidence_freeze._extract_verdict(
            "verify_summary", {"status": "PASS", "checks": [{"check_id": "RC-001", "status": "PASS"}]}
        )
        bad = evidence_freeze._extract_verdict(
            "verify_summary", {"status": "FAIL", "checks": [{"check_id": "RC-001", "status": "FAIL"}]}
        )
        self.assertNotEqual(good, bad)

    def test_required_report_missing_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo, manifest = _make_tree(Path(td))
            doc = evidence_freeze.compute_manifest(repo)
            # Pretend the archive recorded a required report as present.
            doc["reports"]["verify_summary"] = {
                "path": evidence_freeze.REQUIRED_REPORTS["verify_summary"],
                "required": True,
                "present": True,
                "sha256": "0" * 64,
                "verdict": {"status": "PASS"},
            }
            manifest.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            ok, errs = evidence_freeze.verify_manifest(manifest, repo)
            self.assertFalse(ok)
            self.assertTrue(any("report missing" in e for e in errs))

    def test_optional_report_absent_is_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo, manifest = _make_tree(Path(td))
            doc = evidence_freeze.compute_manifest(repo)
            doc["reports"]["release_audit"] = {
                "path": evidence_freeze.OPTIONAL_REPORTS["release_audit"],
                "required": False,
                "present": True,
                "sha256": "0" * 64,
                "verdict": {"status": "PASS"},
            }
            manifest.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            ok, errs = evidence_freeze.verify_manifest(manifest, repo)
            # The optional report is absent from the tree: skipped, not failed.
            self.assertTrue(ok, errs)


if __name__ == "__main__":
    unittest.main()
