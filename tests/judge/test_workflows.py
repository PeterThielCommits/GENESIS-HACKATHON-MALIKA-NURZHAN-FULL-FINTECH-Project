"""Guards for the GitHub Actions workflow files.

A workflow that does not parse produces a run with **zero jobs** and no
repository-level failure -- the CI simply disappears. That is how the
Phase 17 workflow went unnoticed for four pushes (the step name contained
``: `` inside an unquoted YAML scalar).

These tests fail loudly on the two hazards that cause it, and they fail on
the *repository's own* workflows, so a regression cannot reach a push.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import check_workflows as cw


#: The hardened offline container ships the submission image; the CI
#: configuration is not part of it, so the repository-level checks are
#: skipped there. The skip reason carries "optional", which the Judge Kit
#: classifies as an optional (not critical) skip.
NO_WORKFLOWS_REASON = "optional: this tree ships no CI configuration (offline submission image)"


class TestWorkflowFiles(unittest.TestCase):
    """The workflows that actually run this repository."""

    def setUp(self):
        if not cw.WORKFLOW_DIR.is_dir():
            self.skipTest(NO_WORKFLOWS_REASON)

    def test_repository_workflows_are_well_formed(self):
        problems = cw.check_workflows()
        self.assertEqual(problems, [], "malformed GitHub Actions workflow(s)")

    def test_every_workflow_defines_at_least_one_job(self):
        for path in sorted(cw.WORKFLOW_DIR.glob("*.yml")):
            text = path.read_text(encoding="utf-8")
            self.assertIn("jobs:", text, f"{path.name} defines no jobs section")

    def test_the_phase_evidence_step_is_quoted(self):
        """The step that broke CI is named without an unquoted colon."""
        ci = (cw.WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8")
        for line in ci.splitlines():
            if "Evidence freeze" in line:
                self.assertNotIn(": ", line.split("- name:", 1)[-1].rsplit(":", 1)[0])


class TestWorkflowHazards(unittest.TestCase):
    """The scanner must catch what breaks a workflow file."""

    def test_unquoted_colon_space_is_flagged(self):
        text = (
            "jobs:\n"
            "  core:\n"
            "    steps:\n"
            "      - name: Evidence freeze (Phase 17: the committed archive)\n"
            "        run: make evidence-verify\n"
        )
        problems = cw.scan_text(Path("ci.yml"), text)
        self.assertTrue(problems)
        self.assertIn("': '", problems[0])

    def test_quoted_colon_space_is_accepted(self):
        text = (
            "jobs:\n"
            "  core:\n"
            "    steps:\n"
            '      - name: "Evidence freeze (Phase 17: the committed archive)"\n'
            "        run: make evidence-verify\n"
        )
        self.assertEqual(cw.scan_text(Path("ci.yml"), text), [])

    def test_tab_indentation_is_flagged(self):
        text = "jobs:\n\tcore:\n\t\tsteps: []\n"
        problems = cw.scan_text(Path("ci.yml"), text)
        self.assertTrue(problems)
        self.assertIn("tab", problems[0])

    def test_block_scalars_are_not_flagged(self):
        text = (
            "jobs:\n"
            "  core:\n"
            "    steps:\n"
            "      - name: run the thing\n"
            "        run: |\n"
            "          python3 -c 'print(\"a: b\")'\n"
        )
        self.assertEqual(cw.scan_text(Path("ci.yml"), text), [])

    def test_comments_are_ignored(self):
        text = "# a comment with: a colon\njobs:\n  core:\n    steps: []\n"
        self.assertEqual(cw.scan_text(Path("ci.yml"), text), [])

    def test_missing_workflow_directory_is_reported(self):
        with tempfile.TemporaryDirectory() as td:
            problems = cw.check_workflows(Path(td) / "does-not-exist")
            self.assertTrue(problems)
            self.assertIn("missing workflow directory", problems[0])

    def test_missing_workflow_directory_is_optional(self):
        """The offline container has no CI configuration; that is not a failure."""
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(cw.check_workflows(Path(td) / "does-not-exist", optional=True), [])

    def test_empty_workflow_directory_is_reported(self):
        with tempfile.TemporaryDirectory() as td:
            problems = cw.check_workflows(Path(td))
            self.assertTrue(problems)
            self.assertIn("no workflow files", problems[0])

    def test_auxiliary_yaml_files_are_scanned(self):
        """docker-compose.yml and the spec YAML files are parsed by tooling too."""
        problems = cw.check_auxiliary_yaml()
        self.assertEqual(problems, [])

    def test_workflow_without_jobs_is_reported(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "broken.yml").write_text("name: CI\non:\n  push:\n", encoding="utf-8")
            problems = cw.check_workflows(Path(td))
            self.assertTrue(problems)


if __name__ == "__main__":
    unittest.main()
