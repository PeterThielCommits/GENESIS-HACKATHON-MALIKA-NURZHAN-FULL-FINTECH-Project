"""Release audit tests (Phase 16, tasks 16.5 and 16.6; TZ §16).

Two kinds of test:

* **mechanism tests** over synthetic input — they always run, and prove each
  detector actually fires. A gate that cannot fail is not a gate.
* **integration tests** against the real repository — they need a Git checkout
  and the generated evidence, and skip explicitly otherwise (never silently).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import release_audit as ra

# Integration checks depend on the generated evidence (and on a Git checkout),
# NOT on the audit report itself: artifacts/reports/release/ is gitignored, so
# gating on it made every integration test skip on a clean clone, which turned
# RC-001 into SKIPPED and failed the suite (23 skips). Gate on the input.
AUDIT_READY = (ra.REPO_ROOT / "artifacts" / "reports" / "latest" / "verify_summary.json").is_file()


def setUpModule() -> None:
    if AUDIT_READY:
        print("release-audit: report present - integration checks are active in this run")
    else:
        print("release-audit: report absent - integration checks skip explicitly (bootstrap position)")


class TestSecretDetectors(unittest.TestCase):
    """Each credential shape must be recognised, and prose must not trip it."""

    # Assembled at runtime on purpose: writing a complete credential shape as a
    # source literal makes the repository fail its own secrets audit (the audit
    # found these exact four lines). The shapes are still exact.
    SAMPLES = {
        "private key block": "-" * 5 + "BEGIN RSA " + "PRIVATE KEY" + "-" * 5,
        "aws access key id": "AKIA" + "IOSFODNN7EXAMPLE",
        "github token": "ghp" + "_" + "a" * 36,
        "github pat": "github" + "_pat_" + "b" * 40,
        "openai-style key": "sk" + "-" + "c" * 32,
        "slack token": "xoxb" + "-" + "1234567890" + "-" + "abcdefghij",
        "google api key": "AIza" + "d" * 35,
        "jwt": "eyJhbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0" + "." + "abcdefghijklmnop",
    }

    def test_every_documented_shape_is_detected(self):
        for label, sample in self.SAMPLES.items():
            with self.subTest(label=label):
                hits = [name for name, pattern in ra.SECRET_PATTERNS if pattern.search(sample)]
                self.assertIn(label, hits)

    def test_prose_is_not_a_false_positive(self):
        prose = (
            "The secret salt is never logged. Tokens are not accepted. "
            "A password field is rejected. Secrets live in sealed truth only."
        )
        for label, pattern in ra.SECRET_PATTERNS:
            with self.subTest(label=label):
                self.assertIsNone(pattern.search(prose), f"{label} false-positived on prose")

    def test_audit_secrets_passes_clean_tree(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "clean.py").write_text("VALUE = 1\n", encoding="utf-8")
            saved = ra.REPO_ROOT
            ra.REPO_ROOT = Path(td)
            try:
                result = ra.audit_secrets(["clean.py"])
            finally:
                ra.REPO_ROOT = saved
        self.assertEqual(result["status"], "PASS")

    def test_audit_secrets_flags_a_real_leak(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "leaky.py").write_text('KEY = "' + "AKIA" + "Z" * 16 + '"\n', encoding="utf-8")
            saved = ra.REPO_ROOT
            ra.REPO_ROOT = Path(td)
            try:
                result = ra.audit_secrets(["leaky.py"])
            finally:
                ra.REPO_ROOT = saved
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["findings"][0]["kind"], "aws access key id")


class TestForbiddenPaths(unittest.TestCase):
    """Sealed truth must never reach the package, at any directory depth."""

    def test_real_episode_sealed_layout_is_forbidden(self):
        # The actual repository layout: episodes/<split>/<episode>/sealed/...
        result = ra.audit_forbidden_files(["episodes/dev/ep_dev_001_clean_distractors/sealed/truth.json"])
        self.assertEqual(result["status"], "FAIL")

    def test_split_level_sealed_is_forbidden(self):
        result = ra.audit_forbidden_files(["episodes/dev/sealed/truth.json"])
        self.assertEqual(result["status"], "FAIL")

    def test_hidden_split_is_forbidden(self):
        result = ra.audit_forbidden_files(["episodes/hidden/ep_x/truth.json"])
        self.assertEqual(result["status"], "FAIL")

    def test_credential_files_are_forbidden(self):
        for rel in (".env", "deploy/id_rsa", "certs/server.pem", "certs/key.key", "aws/credentials"):
            with self.subTest(rel=rel):
                self.assertEqual(ra.audit_forbidden_files([rel])["status"], "FAIL")

    def test_public_episode_files_are_allowed(self):
        allowed = [
            "episodes/dev/ep_dev_001_clean_distractors/public/accounts.json",
            "episodes/dev/ep_dev_001_clean_distractors/manifest.json",
            "docs/DESIGN.md",
            ".gitignore",
        ]
        self.assertEqual(ra.audit_forbidden_files(allowed)["status"], "PASS")


class TestFileListWithoutGit(unittest.TestCase):
    """The offline image excludes .git, so the audit must work without it.

    Found by running `make verify` from a release tarball: the audit returned an
    ERROR report with no `official_score_claimed` key, which failed the report
    contract. The image is a submission artefact, so this is not an edge case.
    """

    def test_filesystem_walk_finds_files_without_git(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "pkg").mkdir()
            (root / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
            saved = ra.REPO_ROOT
            ra.REPO_ROOT = root
            try:
                files = ra._walk_fallback()
            finally:
                ra.REPO_ROOT = saved
        self.assertEqual(files, ["pkg/mod.py"])

    def test_walk_excludes_ignored_directories_and_bytecode(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for rel in ("__pycache__/x.pyc", ".git/config", "build/out.bin", "keep.json"):
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
            saved = ra.REPO_ROOT
            ra.REPO_ROOT = root
            try:
                files = ra._walk_fallback()
            finally:
                ra.REPO_ROOT = saved
        self.assertEqual(files, ["keep.json"])

    def test_error_report_still_carries_the_envelope(self):
        with tempfile.TemporaryDirectory() as td:
            saved = ra.REPO_ROOT
            ra.REPO_ROOT = Path(td)
            try:
                report = ra.run_audit()
            finally:
                ra.REPO_ROOT = saved
        self.assertEqual(report["status"], "ERROR")
        self.assertEqual(report["exit_code"], 2)
        self.assertIn("official_score_claimed", report)
        self.assertFalse(report["official_score_claimed"])
        self.assertIn("schema_version", report)


class TestSizeBudget(unittest.TestCase):
    def test_budget_constants_are_sane(self):
        self.assertLessEqual(ra.MAX_SINGLE_FILE_BYTES, ra.MAX_PACKAGE_BYTES)
        self.assertGreater(ra.MAX_TRACKED_FILES, 0)

    def test_oversized_file_fails(self):
        with tempfile.TemporaryDirectory() as td:
            big = Path(td) / "big.bin"
            big.write_bytes(b"\0" * (ra.MAX_SINGLE_FILE_BYTES + 1))
            saved = ra.REPO_ROOT
            ra.REPO_ROOT = Path(td)
            try:
                result = ra.audit_size(["big.bin"])
            finally:
                ra.REPO_ROOT = saved
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["findings"][0]["file"], "big.bin")

    def test_small_file_passes(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "small.txt").write_text("x", encoding="utf-8")
            saved = ra.REPO_ROOT
            ra.REPO_ROOT = Path(td)
            try:
                result = ra.audit_size(["small.txt"])
            finally:
                ra.REPO_ROOT = saved
        self.assertEqual(result["status"], "PASS")


class TestDependencyAudit(unittest.TestCase):
    def test_local_imports_are_not_external(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "mod.py").write_text("import json\nimport core.ids\nfrom . import x\n", encoding="utf-8")
            saved = ra.REPO_ROOT
            ra.REPO_ROOT = Path(td)
            try:
                result = ra.audit_dependencies(["mod.py"])
            finally:
                ra.REPO_ROOT = saved
        self.assertEqual(result["status"], "PASS")

    def test_third_party_import_fails(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "mod.py").write_text("import requests\n", encoding="utf-8")
            saved = ra.REPO_ROOT
            ra.REPO_ROOT = Path(td)
            try:
                result = ra.audit_dependencies(["mod.py"])
            finally:
                ra.REPO_ROOT = saved
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["findings"][0]["module"], "requests")

    def test_tests_and_tools_are_out_of_scope(self):
        """The product is the runtime package; dev tooling may use extras."""
        self.assertNotIn("tests/x.py", ra._runtime_sources(["tests/x.py"]))
        self.assertNotIn("tools/y.py", ra._runtime_sources(["tools/y.py"]))


class TestEntrypointContract(unittest.TestCase):
    @unittest.skipUnless(AUDIT_READY, "evidence artifacts not generated yet")
    def test_entrypoint_passes_in_real_repo(self):
        result = ra.audit_entrypoint()
        self.assertEqual(result["status"], "PASS", json.dumps(result, indent=2))
        self.assertEqual(result["metrics"]["step_tuple_len"], 5)
        self.assertEqual(result["metrics"]["reset_tuple_len"], 2)

    @unittest.skipUnless(AUDIT_READY, "evidence artifacts not generated yet")
    def test_every_adapter_tool_is_accepted(self):
        tools = ra.audit_entrypoint()["metrics"]["tools"]
        for name in ra.ADAPTER_TOOL_NAMES:
            with self.subTest(tool=name):
                self.assertTrue(tools[name]["accepted"], f"{name} rejected by the adapter")

    def test_missing_entrypoint_fails(self):
        saved = ra.REPO_ROOT
        with tempfile.TemporaryDirectory() as td:
            ra.REPO_ROOT = Path(td)
            try:
                result = ra.audit_entrypoint()
            finally:
                ra.REPO_ROOT = saved
        self.assertEqual(result["status"], "FAIL")


class TestSubmissionFormat(unittest.TestCase):
    @unittest.skipUnless(AUDIT_READY, "evidence artifacts not generated yet")
    def test_submission_format_passes_in_real_repo(self):
        self.assertEqual(ra.audit_submission_format()["status"], "PASS")

    def test_documentation_vocabulary_matches_the_adapter(self):
        """The docs must name exactly the tools the adapter accepts (D-15-02)."""
        text = (REPO_ROOT / "docs" / "API_USAGE.md").read_text(encoding="utf-8")
        for name in ra.ADAPTER_TOOL_NAMES:
            with self.subTest(tool=name):
                self.assertIn(name, text)
        # The core protocol spelling must never leak into the adapter contract.
        adapter_source = (REPO_ROOT / "adapter" / "official_env.py").read_text(encoding="utf-8")
        self.assertNotIn('"calc"', adapter_source)


class TestReportContract(unittest.TestCase):
    @unittest.skipUnless(AUDIT_READY, "evidence artifacts not generated yet")
    def test_report_shape(self):
        """Produce the report through the real CLI into a temp dir, then inspect it.

        Never read ra.OUTPUT_PATH: it is gitignored, so on a clean clone it does
        not exist and RC-001 would error instead of passing.
        """
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "release_audit.json"
            saved = ra.OUTPUT_PATH
            ra.OUTPUT_PATH = out
            try:
                exit_code = ra.main([])
            finally:
                ra.OUTPUT_PATH = saved
            self.assertEqual(exit_code, 0)
            report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "PASS")
        self.assertFalse(report["official_score_claimed"])
        self.assertEqual(report["exit_code"], 0)
        self.assertEqual(len(report["checks"]), 6)
        self.assertEqual(report["failed"], [])

    def test_report_never_claims_an_official_score(self):
        report = ra.run_audit()
        self.assertFalse(report["official_score_claimed"])

    def test_audit_is_not_in_the_frozen_evidence_set(self):
        """artifacts/reports/latest is the 20-file Judge Kit set (D-15-03)."""
        self.assertNotIn("reports/latest", str(ra.OUTPUT_PATH))
        self.assertIn("release", str(ra.OUTPUT_PATH))

    def test_ascii_only_console_output(self):
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertIsNone(ra._say("a \u2014 b -> c \u00a7 d"))
        self.assertEqual(buffer.getvalue(), "a - b -> c S d\n")
        result = subprocess.run(
            [sys.executable, "-c", "import sys; sys.path.insert(0, %r); from tools import release_audit as ra; ra._say('x \u2014 y')" % str(REPO_ROOT)],
            capture_output=True,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C", "PYTHONIOENCODING": "ascii"},
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertRegex(result.stdout.decode("ascii"), r"^x - y\n$")


if __name__ == "__main__":
    unittest.main()
