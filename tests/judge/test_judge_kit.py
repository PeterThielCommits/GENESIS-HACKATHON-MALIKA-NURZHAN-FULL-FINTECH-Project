"""Judge Kit tests (Phase 14 — Master TZ §23).

Covers the previously untested Judge Kit surface: exit-code classification,
skip accounting, rubric-map consistency, artifact completeness, offline HTML
guarantee, and artifact schemas. All tests are stdlib-only and deterministic.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from judge import report as report_mod
from judge import schemas as schemas_mod
from judge import verify as verify_mod

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestParseSkippedCounts(unittest.TestCase):
    def test_hypothesis_skip_is_optional(self):
        out = (
            "test_optional_dependency (tests.unit.test_property.TestHypothesisProperties."
            "test_optional_dependency) ... skipped 'hypothesis extra not installed'\n"
            "OK (skipped=1)\n"
        )
        self.assertEqual(verify_mod.parse_skipped_counts(out), (1, 0))

    def test_unknown_skip_is_critical(self):
        out = "test_x (tests.foo.TestX.test_x) ... skipped 'not ready'\nOK (skipped=1)\n"
        self.assertEqual(verify_mod.parse_skipped_counts(out), (0, 1))

    def test_no_skips(self):
        self.assertEqual(verify_mod.parse_skipped_counts("Ran 5 tests\nOK\n"), (0, 0))

    def test_unattributed_skipped_count_is_critical(self):
        # Non-verbose runner: skipped=N with no per-test lines must not hide.
        self.assertEqual(verify_mod.parse_skipped_counts("Ran 5 tests\nOK (skipped=2)\n"), (0, 2))


class TestClassifyCheck(unittest.TestCase):
    def test_pass_clean(self):
        status, reason, blocked, resource, incomplete = verify_mod.classify_check(0, False, 0, 0)
        self.assertEqual(status, "PASS")
        self.assertEqual(reason, "")
        self.assertFalse(blocked or resource or incomplete)

    def test_pass_with_optional_skip_stays_pass(self):
        status, _, _, _, incomplete = verify_mod.classify_check(0, False, 1, 0)
        self.assertEqual(status, "PASS")
        self.assertFalse(incomplete)

    def test_pass_with_critical_skip_is_skipped_and_incomplete(self):
        status, reason, _, _, incomplete = verify_mod.classify_check(0, False, 0, 2)
        self.assertEqual(status, "SKIPPED")
        self.assertIn("2", reason)
        self.assertTrue(incomplete)

    def test_exit_4_is_blocked_release_blocker(self):
        status, _, blocked, _, _ = verify_mod.classify_check(4, False, 0, 0)
        self.assertEqual(status, "BLOCKED")
        self.assertTrue(blocked)

    def test_exit_2_is_config_error(self):
        status, reason, _, _, _ = verify_mod.classify_check(2, False, 0, 0)
        self.assertEqual(status, "FAIL")
        self.assertIn("configuration", reason)

    def test_exit_5_is_incomplete(self):
        status, _, _, _, incomplete = verify_mod.classify_check(5, False, 0, 0)
        self.assertEqual(status, "BLOCKED")
        self.assertTrue(incomplete)

    def test_exit_3_is_resource_error(self):
        status, _, _, resource, _ = verify_mod.classify_check(3, False, 0, 0)
        self.assertEqual(status, "FAIL")
        self.assertTrue(resource)

    def test_blocker_failure_escalates(self):
        status, _, blocked, _, _ = verify_mod.classify_check(1, True, 0, 0)
        self.assertEqual(status, "FAIL")
        self.assertTrue(blocked)

    def test_non_blocker_failure_does_not_escalate(self):
        status, _, blocked, _, _ = verify_mod.classify_check(1, False, 0, 0)
        self.assertEqual(status, "FAIL")
        self.assertFalse(blocked)


class TestRubricMapConsistency(unittest.TestCase):
    def test_rubric_map_matches_verify_checks(self):
        data, err = verify_mod.load_rubric_map()
        self.assertIsNone(err, err)
        assert data is not None
        rubric_ids = {c["check_id"] for c in data["checks"]}
        verify_ids = {c[0] for c in verify_mod.ALL_CHECKS}
        self.assertEqual(rubric_ids, verify_ids)

    def test_rubric_commands_match_verify(self):
        import sys

        data, err = verify_mod.load_rubric_map()
        self.assertIsNone(err, err)
        assert data is not None
        by_id = {c["check_id"]: c for c in data["checks"]}
        for check_id, _req, cmd, _req_flag, _core, _blocker, _art in verify_mod.ALL_CHECKS:
            # rubric_map uses the portable `python3`; verify uses sys.executable.
            expected = " ".join(cmd).replace(sys.executable, "python3")
            self.assertEqual(by_id[check_id]["command"], expected, check_id)

    def test_rubric_test_ids_resolve(self):
        data, err = verify_mod.load_rubric_map()
        self.assertIsNone(err, err)
        assert data is not None
        for check in data["checks"]:
            test_id = check["test_id"]
            if "*" in test_id:
                # Glob like tests/* or tests/official/*: parent dir must exist.
                parent = REPO_ROOT / test_id.split("*")[0].rstrip("/")
                self.assertTrue(parent.is_dir(), f"{check['check_id']} test_id parent missing: {parent}")
            elif test_id.endswith(".py"):
                self.assertTrue((REPO_ROOT / test_id).is_file(), f"{check['check_id']} test_id missing: {test_id}")
            else:
                # Module path like tests.unit.test_property: resolve to file.
                parts = test_id.split(".")
                candidate = REPO_ROOT.joinpath(*parts).with_suffix(".py")
                self.assertTrue(candidate.is_file(), f"{check['check_id']} test_id module missing: {test_id}")

    def test_rubric_map_validates(self):
        data, err = verify_mod.load_rubric_map()
        self.assertIsNone(err, err)
        self.assertEqual(schemas_mod.validate_rubric_map(data), [])

    def test_load_rubric_map_malformed_is_config_error(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "rubric_map.json"
            bad.write_text("{not json", encoding="utf-8")
            data, err = verify_mod.load_rubric_map(bad)
            self.assertIsNone(data)
            self.assertIsNotNone(err)

    def test_load_rubric_map_missing_is_config_error(self):
        with tempfile.TemporaryDirectory() as td:
            data, err = verify_mod.load_rubric_map(Path(td) / "nope.json")
            self.assertIsNone(data)
            self.assertIsNotNone(err)


class TestArtifactCompleteness(unittest.TestCase):
    def test_required_artifacts_cover_tz_23_5(self):
        required = set(verify_mod.REQUIRED_FULL_ARTIFACTS)
        for name in (
            "verify_summary.json",
            "verify_summary.txt",
            "rubric_matrix.csv",
            "episode_matrix.csv",
            "generator_report.json",
            "invariants_report.json",
            "verifier_report_index.json",
            "reward_strategy_report.json",
            "shortcut_audit.json",
            "canary_fuzz_report.json",
            "mutation_test_report.json",
            "metamorphic_report.json",
            "replay_report.json",
            "performance_report.json",
            "dependency_report.json",
            "limitations_snapshot.md",
            "report.html",
        ):
            self.assertIn(name, required)

    def test_missing_artifacts_detected(self):
        with tempfile.TemporaryDirectory() as td:
            missing = verify_mod.check_artifact_completeness(Path(td))
            self.assertEqual(set(missing), set(verify_mod.REQUIRED_FULL_ARTIFACTS))

    def test_present_artifacts_not_reported_missing(self):
        with tempfile.TemporaryDirectory() as td:
            for name in verify_mod.REQUIRED_FULL_ARTIFACTS:
                (Path(td) / name).write_text("x", encoding="utf-8")
            self.assertEqual(verify_mod.check_artifact_completeness(Path(td)), [])


class TestArtifactPlaceholders(unittest.TestCase):
    """Bookkeeping dotfiles must never be counted as evidence.

    `.gitkeep` exists so Git can track an empty directory. Counting it made the
    reported artifact count environment-dependent -- 21 in a checkout versus 20
    in the offline image -- which surfaced as a real `docker-offline` failure
    (DRIFT: committed 20 != measured 21). Regression for D-15-03.
    """

    def test_dotfile_is_not_an_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            placeholder = Path(td) / ".gitkeep"
            placeholder.write_text("", encoding="utf-8")
            self.assertFalse(report_mod._is_artifact(placeholder))

    def test_regular_report_is_an_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            real = Path(td) / "verify_summary.json"
            real.write_text("{}", encoding="utf-8")
            self.assertTrue(report_mod._is_artifact(real))

    def test_directory_is_not_an_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertFalse(report_mod._is_artifact(Path(td)))

    def test_evidence_count_is_environment_independent(self):
        """The published count must not change between a checkout and the image."""
        from tools import verify_doc_claims as vdc

        if not (vdc.REPORT_DIR / "report_index.json").is_file():
            self.skipTest("evidence artifacts not generated yet")
        indexed = json.loads((vdc.REPORT_DIR / "report_index.json").read_text(encoding="utf-8"))["artifacts"]
        self.assertFalse([a for a in indexed if a.startswith(".")], "placeholder counted as evidence")
        on_disk = sorted(p.name for p in vdc.REPORT_DIR.iterdir() if report_mod._is_artifact(p))
        self.assertEqual(sorted(indexed), on_disk, "index disagrees with the evidence files on disk")


class TestOfflineHtmlGuarantee(unittest.TestCase):
    def test_clean_html_has_no_violations(self):
        self.assertEqual(report_mod.audit_html_offline("<html><body>ok</body></html>"), [])

    def test_http_url_is_violation(self):
        self.assertTrue(report_mod.audit_html_offline('<a href="http://x.test/">x</a>'))

    def test_https_url_is_violation(self):
        self.assertTrue(report_mod.audit_html_offline('<script src="https://cdn.test/x.js"></script>'))

    def test_css_external_url_is_violation(self):
        self.assertTrue(report_mod.audit_html_offline("<style>@import url(https://x.test/a.css);</style>"))

    def test_built_report_is_offline_and_disclaimed(self):
        summary = {
            "run_id": "test-run",
            "status": "PASS",
            "internal_pass_rate_pct": 100.0,
            "platform": "test",
            "python_version": "3.11.2",
            "required_checks": {"passed": 12, "total": 12},
            "checks": [
                {
                    "check_id": "RC-001",
                    "req_id": "REQ-CONTRACT-001",
                    "status": "PASS",
                    "duration_s": 0.1,
                    "artifact": "artifacts/reports/latest/verify_summary.json",
                }
            ],
        }
        html_doc = report_mod._build_html_report(summary, ["verify_summary.json"])
        self.assertEqual(report_mod.audit_html_offline(html_doc), [])
        self.assertIn("does not claim an official organiser jury score", html_doc)
        self.assertIn("zero external network requests", html_doc)

    def test_build_report_survives_empty_artifact_dir(self):
        """Clean checkout: no optional reports present.

        Regression for an f-string bug where `x or {{}}` inside a replacement
        field parses as `{ {} }` and raises TypeError: unhashable type 'dict'
        only when the left operand is falsy — i.e. exactly on a clean clone,
        which is the EXIT GATE 14 scenario.
        """
        import tempfile
        from pathlib import Path as _Path

        summary = {
            "run_id": "clean-run",
            "status": "PASS",
            "internal_pass_rate_pct": 100.0,
            "platform": "test",
            "python_version": "3.11.2",
            # Deliberately omitted: required_checks → exercises the falsy path.
            "checks": [],
        }
        saved = report_mod.REPORT_DIR
        with tempfile.TemporaryDirectory() as td:
            report_mod.REPORT_DIR = _Path(td)
            try:
                html_doc = report_mod._build_html_report(summary, [])
            finally:
                report_mod.REPORT_DIR = saved
        self.assertEqual(report_mod.audit_html_offline(html_doc), [])
        self.assertIn("0/0", html_doc)

    def test_proof_samples_only_public_keys(self):
        allowed = {
            "episode_id",
            "type",
            "affected_ids",
            "claimed_amount_minor",
            "currency",
            "evidence_sets",
            "invariant_id",
            "explanation_code",
        }
        for sample in report_mod._collect_public_proof_samples():
            self.assertTrue(set(sample.keys()) <= allowed, sample.keys())


class TestSchemas(unittest.TestCase):
    def test_valid_verify_summary_passes(self):
        summary = {
            "schema_version": "1.0.0",
            "report_type": "verify_summary",
            "status": "PASS",
            "official_score_claimed": False,
            "checks": [
                {
                    "check_id": "RC-001",
                    "req_id": "REQ-CONTRACT-001",
                    "rubric_item": "x",
                    "status": "PASS",
                    "reason": "",
                    "required": True,
                    "exit_code": 0,
                    "duration_s": 0.1,
                    "artifact": "a",
                }
            ],
        }
        self.assertEqual(schemas_mod.validate_verify_summary(summary), [])

    def test_verify_summary_rejects_official_score_claim(self):
        summary = {
            "schema_version": "1.0.0",
            "report_type": "verify_summary",
            "status": "PASS",
            "official_score_claimed": True,
            "checks": [
                {
                    "check_id": "RC-001",
                    "req_id": "REQ-CONTRACT-001",
                    "rubric_item": "x",
                    "status": "PASS",
                    "reason": "",
                    "required": True,
                    "exit_code": 0,
                    "duration_s": 0.1,
                    "artifact": "a",
                }
            ],
        }
        self.assertTrue(schemas_mod.validate_verify_summary(summary))

    def test_report_envelope_accepts_complete_report(self):
        report = {
            "code_version": "twinledger@1.0.0",
            "config_hash": "0" * 64,
            "generated_at_utc": "2026-11-21T00:00:00Z",
            "platform": "Linux-6.1.0-x86_64-with-glibc2.36",
            "python_version": "3.11.2",
            "command": "python3 judge/verify.py --full",
        }
        self.assertEqual(schemas_mod.validate_report_envelope(report, "r.json"), [])

    def test_report_envelope_rejects_missing_and_malformed_fields(self):
        errors = schemas_mod.validate_report_envelope({"code_version": "x"}, "r.json")
        self.assertTrue(any("config_hash" in e for e in errors))
        bad = {
            "code_version": "twinledger@1.0.0",
            "config_hash": "not-a-digest",
            "generated_at_utc": "2026-11-21 00:00:00",
            "platform": "p",
            "python_version": "3.11.2",
            "command": "c",
        }
        malformed = schemas_mod.validate_report_envelope(bad, "r.json")
        self.assertTrue(any("config_hash" in e for e in malformed))
        self.assertTrue(any("generated_at_utc" in e for e in malformed))

    def test_report_dir_envelopes_flags_unparseable_json(self):
        import tempfile
        from pathlib import Path as _Path

        with tempfile.TemporaryDirectory() as td:
            root = _Path(td)
            (root / "broken.json").write_text("{nope", encoding="utf-8")
            errors = schemas_mod.validate_report_dir_envelopes(root)
        self.assertTrue(any("broken.json" in e for e in errors))

    def test_valid_report_index_passes(self):
        index = {
            "schema_version": "1.0.0",
            "report_type": "report_index",
            "offline_self_contained_html": True,
            "artifacts": ["report.html"],
        }
        self.assertEqual(schemas_mod.validate_report_index(index), [])

    def test_rubric_map_rejects_bad_weights(self):
        data = {
            "provisional": True,
            "blocks": [{"provisional_weight": 10}],
            "checks": [
                {
                    "schema_version": "1.0.0",
                    "check_id": "RC-001",
                    "rubric_item": "x",
                    "req_id": "REQ-X",
                    "test_id": "tests/x.py",
                    "command": "true",
                    "evidence_artifact": "a",
                    "provisional": True,
                }
            ],
        }
        self.assertTrue(schemas_mod.validate_rubric_map(data))


class TestPerformanceGuards(unittest.TestCase):
    def test_invariant_catalog_matches_tz_12_1(self):
        from judge.performance_and_deps import INVARIANT_IDS

        self.assertEqual(len(INVARIANT_IDS), 17)
        self.assertEqual(INVARIANT_IDS[0], "INV-01")
        self.assertEqual(INVARIANT_IDS[-1], "INV-17")

    def test_measure_performance_handles_missing_episodes(self):
        # With episodes/dev present this returns a normal report; the guard
        # path (empty metrics + error) must never raise IndexError.
        from judge.performance_and_deps import _measure_performance

        result = _measure_performance()
        self.assertIn(result["status"], ("PASS", "FAIL"))
        if result["status"] == "FAIL":
            self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
