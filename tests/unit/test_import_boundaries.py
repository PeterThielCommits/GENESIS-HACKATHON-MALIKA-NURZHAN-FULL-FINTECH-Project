"""Import-boundary scanner tests (REQ-ARC-001..007)."""

import tempfile
import unittest
from pathlib import Path

from tools.check_import_boundaries import scan


class TestImportBoundaries(unittest.TestCase):
    def test_current_repo_is_clean(self):
        violations = scan(Path(__file__).resolve().parent.parent.parent)
        self.assertEqual(violations, [])

    def test_detects_env_importing_gen(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "env").mkdir()
            (root / "env" / "server.py").write_text("import gen\n", encoding="utf-8")
            violations = scan(root)
            self.assertTrue(any("env" in v and "gen" in v for v in violations))

    def test_detects_verifier_importing_gen(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "verifier").mkdir()
            (root / "verifier" / "discover.py").write_text("from gen.core import x\n", encoding="utf-8")
            violations = scan(root)
            self.assertTrue(any("verifier" in v for v in violations))

    def test_detects_policy_importing_scoring(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "arena" / "policies").mkdir(parents=True)
            (root / "arena" / "policies" / "p.py").write_text("import scoring\n", encoding="utf-8")
            violations = scan(root)
            self.assertTrue(any("policies" in v for v in violations))

    def test_detects_sealed_path_literal_in_env(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "env").mkdir()
            (root / "env" / "loader.py").write_text('p = "sealed/truth.json"\n', encoding="utf-8")
            violations = scan(root)
            self.assertTrue(any("sealed" in v for v in violations))

    def test_clean_code_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "env").mkdir()
            (root / "env" / "server.py").write_text("import json\nfrom contracts import canonical_json\n", encoding="utf-8")
            self.assertEqual(scan(root), [])

    def test_detects_verifier_importing_nlp_fuzzy_helper(self):
        # Phase 10 EXIT GATE: verifier must not rely on unsupported fuzzy matches.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "verifier").mkdir()
            (root / "verifier" / "discover.py").write_text("from nlp.matching import text_similarity_bps\n", encoding="utf-8")
            violations = scan(root)
            self.assertTrue(any("verifier" in v and "nlp" in v for v in violations))

    def test_detects_scoring_importing_nlp_fuzzy_helper_but_allows_hierarchy(self):
        # Phase 10: scoring may use only the strict nlp.hierarchy rule module.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "scoring").mkdir()
            bad = root / "scoring" / "bad.py"
            bad.write_text("from nlp.normalize import normalize_nfc\n", encoding="utf-8")
            violations = scan(root)
            self.assertTrue(any("nlp.normalize" in v for v in violations))
            bad.unlink()
            good = root / "scoring" / "good.py"
            good.write_text("from nlp.hierarchy import build_evidence_hierarchy_report\n", encoding="utf-8")
            self.assertEqual(scan(root), [])

    def test_detects_gen_importing_nlp(self):
        # Text layer optionality: generator core must not depend on the NLP package.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "gen").mkdir()
            (root / "gen" / "text.py").write_text("import nlp\n", encoding="utf-8")
            violations = scan(root)
            self.assertTrue(any("gen" in v and "nlp" in v for v in violations))


if __name__ == "__main__":
    unittest.main()
