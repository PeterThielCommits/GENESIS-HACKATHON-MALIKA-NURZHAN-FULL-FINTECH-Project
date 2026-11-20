"""Phase 1 task 1.5/1.6: CI runs the same gate, and repository process files exist."""

from __future__ import annotations

import re
import unittest

from tests.support import ROOT, read_text
from tools import check_ci

WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.commands = check_ci.flatten(check_ci.run_commands(cls.text))

    def test_lint_passes(self) -> None:
        result = check_ci.run()
        self.assertEqual(result["status"], "PASS", result["problems"])

    def test_workflow_runs_the_same_gate_as_a_human(self) -> None:
        for required in ("make setup", "make lint", "make test", "make verify-core"):
            self.assertTrue(any(command == required or command.startswith(required + " ")
                                for command in self.commands), f"CI does not run `{required}`")

    def test_actions_are_pinned_to_tags(self) -> None:
        for repo, ref in re.findall(r"uses:\s*([\w./-]+)@([\w.\-]+)", self.text):
            self.assertRegex(ref, r"^v\d+(\.\d+)*$", f"{repo}@{ref} is not a version tag")

    def test_permissions_are_minimal(self) -> None:
        self.assertIn("permissions:", self.text)
        self.assertIn("contents: read", self.text)

    def test_artifacts_are_uploaded_even_on_failure(self) -> None:
        self.assertIn("if: always()", self.text)
        self.assertIn("artifacts/reports/latest/", self.text)

    def test_workflow_never_claims_success_without_the_gate(self) -> None:
        self.assertNotIn("continue-on-error: true", self.text)
        self.assertNotIn("|| true", self.text)
        self.assertNotIn("exit 0", self.text)

    def test_no_network_install_creeps_in(self) -> None:
        for forbidden in ("pip install", "apt-get", "npm install"):
            self.assertNotIn(forbidden, self.text,
                             f"CI installs packages at runtime ({forbidden}); the core is stdlib-only")


class RepositoryProcessTests(unittest.TestCase):
    def test_pull_request_template_requires_evidence(self) -> None:
        template = read_text(ROOT / ".github" / "pull_request_template.md")
        for token in ("Evidence", "Exit code", "Honesty checklist", "Contract impact"):
            self.assertIn(token, template)

    def test_issue_forms_cover_bug_contract_and_question(self) -> None:
        names = {path.name for path in (ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml")}
        for expected in ("bug.yml", "contract-change.yml", "question.yml", "config.yml"):
            self.assertIn(expected, names)

    def test_codeowners_covers_the_frozen_zones(self) -> None:
        owners = read_text(ROOT / ".github" / "CODEOWNERS")
        for path in ("/contracts/", "/adapter/", "/configs/", "/tests/", "/.github/"):
            self.assertIn(path, owners)
        self.assertIn("placeholder", read_text(ROOT / "docs" / "BRANCH_PROTECTION.md").lower())

    def test_branch_protection_gap_is_documented_not_hidden(self) -> None:
        doc = read_text(ROOT / "docs" / "BRANCH_PROTECTION.md").lower()
        for token in ("require a pull request", "status checks", "human", "placeholders",
                      "not an oversight"):
            self.assertIn(token, doc)


if __name__ == "__main__":
    unittest.main()
