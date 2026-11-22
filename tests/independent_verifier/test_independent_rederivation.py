"""Regression lock for the independent re-derivation verifier (2026-11-22).

These tests pin the *second* implementation's agreement with the committed
evidence, and its freedom from generator/verifier imports. They exist because
documentation alone cannot prove re-derivation; CI can.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from contracts.loader import validate_instance  # noqa: E402
from contracts.models import TruthFinding  # noqa: E402

from independent_verifier.runner import compare_to_committed, run_episode  # noqa: E402
from scoring.crosscheck import crosscheck  # noqa: E402

DEV_TRAIN_DIRS = [
    *(REPO_ROOT / "episodes" / "dev").iterdir(),
    *(REPO_ROOT / "episodes" / "train").iterdir(),
]
ON_DISK_EPISODES = sorted(
    d for d in DEV_TRAIN_DIRS if d.is_dir() and (d / "public").is_dir() and (d / "verifier_report.json").is_file()
)
FORBIDDEN_TOP_LEVEL = {
    "gen",
    "verifier",
    "scoring",
    "seal",
    "nlp",
    "harness",
    "env",
    "arena",
    "judge",
}


def _signatures(report: dict) -> set[tuple[str, tuple[str, ...], int, str]]:
    return {
        (f["type"], tuple(sorted(f["affected_ids"])), int(f["claimed_amount_minor"]), f["currency"])
        for f in report["findings"]
    }


def _committed_signatures(path: Path) -> set[tuple[str, tuple[str, ...], int, str]]:
    return _signatures(json.loads(path.read_text(encoding="utf-8")))


class TestIndependentReDerivation(unittest.TestCase):
    def test_on_disk_episodes_match_committed_signatures(self) -> None:
        self.assertEqual(len(ON_DISK_EPISODES), 10, "expected 6 dev + 4 train committed episodes")
        for ep_dir in ON_DISK_EPISODES:
            with self.subTest(episode=ep_dir.name):
                result = run_episode(ep_dir / "public")
                errors = validate_instance("verifier_report", result.report)
                self.assertEqual(errors, [], f"schema errors: {errors}")
                committed = json.loads((ep_dir / "verifier_report.json").read_text(encoding="utf-8"))
                self.assertEqual(
                    result.report["episode_public_hash"], committed["episode_public_hash"]
                )
                self.assertEqual(
                    _signatures(result.report), _committed_signatures(ep_dir / "verifier_report.json")
                )
                self.assertEqual(
                    result.report["deterministic_diagnostics"]["proof_graph_invariant_errors"], []
                )
                self.assertTrue(
                    result.report["deterministic_diagnostics"]["evidence_enumeration_complete"]
                )

    def test_official_d20_rederived_f1_exact_1(self) -> None:
        from gen.pipeline import build_episode, official_d20_recipes

        recipes = official_d20_recipes(master_seed=2026)
        self.assertEqual(len(recipes), 20)
        with tempfile.TemporaryDirectory(prefix="tl_independent_test_") as tmp:
            for recipe in recipes:
                episode_dir = Path(build_episode(recipe, tmp).episode_dir)
                with self.subTest(episode=episode_dir.name):
                    result = run_episode(episode_dir / "public")
                    truths = [
                        TruthFinding.from_dict(t)
                        for t in json.loads(
                            (episode_dir / "sealed" / "truth.json").read_text(encoding="utf-8")
                        )
                    ]
                    cc = crosscheck(result.report, truths).to_dict()
                    self.assertEqual(cc["counts"]["fp"], 0)
                    self.assertEqual(cc["counts"]["fn"], 0)
                    self.assertEqual(cc["metrics"]["f1"]["exact"], "1")
                    self.assertEqual(result.report["unresolved_ambiguities"], [])

    def test_independent_package_imports_stay_zero_common_mode(self) -> None:
        package = REPO_ROOT / "independent_verifier"
        for path in sorted(package.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    tops = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    tops = [] if node.level else [(node.module or "").split(".")[0]]
                else:
                    continue
                for top in tops:
                    if not top:
                        continue
                    self.assertNotIn(
                        top,
                        FORBIDDEN_TOP_LEVEL,
                        f"{path.name}: forbidden import {top!r} breaks zero-common-mode re-derivation",
                    )

    def test_currency_exponents_come_from_registry(self) -> None:
        from independent_verifier.money import currency_exponents

        self.assertEqual(
            currency_exponents(),
            {"KZT": 2, "USD": 2, "EUR": 2, "JPY": 0, "KWD": 3},
        )

    def test_repo_import_boundary_scanner_is_clean(self) -> None:
        from tools.check_import_boundaries import scan as repo_boundary_scan

        self.assertEqual(repo_boundary_scan(REPO_ROOT), [])

    def test_fresh_process_importing_independent_verifier_loads_nothing_forbidden(self) -> None:
        code = (
            "import sys, independent_verifier; "
            "bad = [m for m in sys.modules if m.split('.')[0] in "
            "{'gen','verifier','scoring','seal','nlp','harness','env','arena','judge'}]; "
            "assert not bad, f'unexpected loaded modules: {bad}'"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr + proc.stdout)

    def test_runtime_file_access_spy_never_leaves_public_dir(self) -> None:
        import io
        from unittest import mock

        src = REPO_ROOT / "episodes" / "dev" / "ep_dev_006_compound_all4" / "public"
        with tempfile.TemporaryDirectory() as td:
            ep_root = Path(td)
            pub_dir = ep_root / "public"
            priv_dir = ep_root / "sealed"
            pub_dir.mkdir()
            for name in os.listdir(src):
                (pub_dir / name).write_bytes((src / name).read_bytes())
            priv_dir.mkdir()
            (priv_dir / "truth.json").write_text('{"canary": "DO_NOT_READ"}\n', encoding="utf-8")
            (priv_dir / "provenance.json").write_text('{"canary": "DO_NOT_READ"}\n', encoding="utf-8")
            (ep_root / "manifest.json").write_text('{"canary": "DO_NOT_READ"}\n', encoding="utf-8")

            pub_resolved = pub_dir.resolve()
            opened_paths: list[Path] = []
            real_io_open = io.open
            real_path_open = Path.open

            def spy_io_open(file, *args, **kwargs):
                if isinstance(file, (str, os.PathLike)):
                    opened_paths.append(Path(file).resolve())
                return real_io_open(file, *args, **kwargs)

            def spy_path_open(self_path, *args, **kwargs):
                opened_paths.append(self_path.resolve())
                return real_path_open(self_path, *args, **kwargs)

            with (
                mock.patch("io.open", side_effect=spy_io_open),
                mock.patch.object(Path, "open", spy_path_open),
            ):
                result = run_episode(pub_dir)

            self.assertEqual(len(result.report["findings"]), 4)
            self.assertGreater(len(opened_paths), 0)
            for p in opened_paths:
                if ep_root.resolve() in p.parents or p == ep_root.resolve():
                    self.assertTrue(
                        p.is_relative_to(pub_resolved) or p == pub_resolved,
                        msg=f"independent verifier accessed path outside public/: {p}",
                    )
                    self.assertNotIn("sealed", p.parts)

    def test_rejects_hidden_extra_index_hints_and_symlink_escape(self) -> None:
        from independent_verifier.loader import PublicDataError, load_public_dir

        src = REPO_ROOT / "episodes" / "dev" / "ep_dev_001_clean_distractors" / "public"

        def fresh_public() -> Path:
            td = tempfile.mkdtemp(prefix="tl_indep_bound_")
            pub = Path(td) / "public"
            pub.mkdir()
            for name in os.listdir(src):
                (pub / name).write_bytes((src / name).read_bytes())
            self.addCleanup(lambda: shutil.rmtree(td, ignore_errors=True))
            return pub

        pub = fresh_public()
        (pub / ".hidden").write_text("x", encoding="utf-8")
        self.assertRaises(PublicDataError, load_public_dir, pub)

        pub = fresh_public()
        (pub / "index_hints.json").write_text("{}", encoding="utf-8")
        self.assertRaises(PublicDataError, load_public_dir, pub)

        pub = fresh_public()
        (pub / "extra.json").write_text("{}", encoding="utf-8")
        self.assertRaises(PublicDataError, load_public_dir, pub)

        pub = fresh_public()
        os.remove(pub / "fx_rates.jsonl")
        os.symlink("/etc/passwd", pub / "fx_rates.jsonl")
        self.assertRaises(PublicDataError, load_public_dir, pub)


if __name__ == "__main__":
    unittest.main()
