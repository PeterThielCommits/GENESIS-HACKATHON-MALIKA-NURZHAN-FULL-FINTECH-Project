"""Phase 0 gate: sealed, hidden and generated data cannot be committed (D-0008)."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from tests.support import DOCS, ROOT, read_text

REQUIRED_PATTERNS = [
    "sealed/",
    "*.salt",
    "*.seed",
    "episodes/*/sealed/",
    "episodes/hidden/",
    "episodes/train/",
    "episodes/dev/",
    "artifacts/",
    "__pycache__/",
]

SEALED_TRACKED_PATTERNS = [
    ".salt",
    "sealed/",
    "episodes/hidden/",
    "/sealed/",
]


class GitIgnoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ignore = read_text(".gitignore")
        cls.policy = read_text(DOCS / "GIT_AND_DATA_POLICY.md")

    def test_every_required_pattern_is_present(self) -> None:
        for pattern in REQUIRED_PATTERNS:
            self.assertIn(pattern, self.ignore, f".gitignore lost the rule {pattern}")

    def test_manifests_are_not_accidentally_ignored(self) -> None:
        self.assertIn("!episodes/manifests/", self.ignore,
                      "hashes-only manifests must stay committable")

    def test_artifacts_are_ignored(self) -> None:
        self.assertIn("artifacts/", self.ignore)

    def test_policy_documents_the_essential_terms(self) -> None:
        lowered = self.policy.lower()
        for token in ("sealed", "hidden", "salt", "test_fixture", "held-out"):
            self.assertIn(token, lowered, f"policy does not explain {token}")

    def test_no_sealed_file_is_tracked(self) -> None:
        try:
            tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                                     text=True, check=True).stdout.splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError):  # pragma: no cover
            self.skipTest("git is not available in this environment")
        offenders = [path for path in tracked
                     if any(token in path for token in SEALED_TRACKED_PATTERNS)
                     or path.endswith((".salt", ".seed"))]
        # The policy document itself mentions the words, so exclude documentation paths.
        offenders = [path for path in offenders
                     if not path.startswith("docs/") and not path.startswith("tests/")]
        self.assertEqual(offenders, [], f"sealed material is tracked: {offenders}")

    def test_no_generated_report_is_tracked(self) -> None:
        try:
            tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                                     text=True, check=True).stdout.splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError):  # pragma: no cover
            self.skipTest("git is not available in this environment")
        self.assertEqual([p for p in tracked if p.startswith("artifacts/")], [])

    def test_repository_has_no_episode_directory_yet(self) -> None:
        # Phase 0 intentionally ships no episode data: generation is Phase 3.
        generated = [p for p in (ROOT / "episodes").rglob("*")] if (ROOT / "episodes").is_dir() else []
        self.assertEqual([p for p in generated if p.is_file() and "manifests" not in str(p)], [])


if __name__ == "__main__":
    unittest.main()
