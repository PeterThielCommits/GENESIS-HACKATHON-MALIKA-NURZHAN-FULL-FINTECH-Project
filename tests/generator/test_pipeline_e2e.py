"""End-to-end integration tests for Phases 3, 4, 7, and 8.

Verifies:
  - Phase 3: deterministic Clean Twin generation across ID families A/B/C/D,
    currencies (KZT/USD/EUR/JPY/KWD), timezones, monthly/quarterly calendars,
    and clean distractors with 0 FP;
  - Phase 4 + 7: all 4 anomaly operators (reusing ``gen.errors.fx_cutoff``),
    structural diff, frozen-schema truth validation, salted truth commitment,
    anti-shortcut ID neutrality, and manifest SHA-256 verification;
  - Phase 8 EXIT GATE 8: 100% of generated episodes in ``episodes/dev`` and
    ``episodes/train`` pass manifest verification, Stage-1 public-only
    ``verifier.discover``, and Stage-2 ``scoring.crosscheck`` with
    ``release_blocked == False``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from contracts.loader import validate_instance
from contracts.models import TruthFinding
from gen.core.clean_twin import CleanTwinSpec, generate_clean_twin, verify_clean_invariants
from gen.pipeline import EpisodeRecipe, build_episode, default_dataset_recipes
from gen.serialize import verify_episode_manifest
from scoring.crosscheck import crosscheck
from tools.make_dataset import build_and_verify_split
from verifier import VerifierConfig, discover

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestGeneratorAndExitGate8(unittest.TestCase):
    def test_byte_determinism_across_repeated_builds(self):
        recipe = default_dataset_recipes("dev", master_seed=777)[5]  # compound all 4
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            e1 = build_episode(recipe, d1)
            e2 = build_episode(recipe, d2)
            self.assertEqual(e1.manifest, e2.manifest)
            self.assertEqual(e1.truths, e2.truths)
            for rel in sorted(p.relative_to(e1.episode_dir) for p in e1.episode_dir.rglob("*") if p.is_file()):
                self.assertEqual(
                    (e1.episode_dir / rel).read_bytes(),
                    (e2.episode_dir / rel).read_bytes(),
                    msg=f"byte mismatch on {rel}",
                )

    def test_salted_truth_commitment_hides_clean_status(self):
        r1 = EpisodeRecipe(CleanTwinSpec(episode_id="c1", master_seed=1, episode_index=1))
        r2 = EpisodeRecipe(CleanTwinSpec(episode_id="c2", master_seed=1, episode_index=2))
        with tempfile.TemporaryDirectory() as td:
            e1 = build_episode(r1, td)
            e2 = build_episode(r2, td)
            self.assertEqual(e1.truths, ())
            self.assertEqual(e2.truths, ())
            # Two clean books MUST have distinct commitments (no empty-truth oracle!)
            self.assertNotEqual(e1.manifest["truth_commitment"], e2.manifest["truth_commitment"])

    def test_anti_shortcut_ids_contain_no_anomaly_labels(self):
        recipe = default_dataset_recipes("dev", master_seed=2025)[5]
        with tempfile.TemporaryDirectory() as td:
            ep = build_episode(recipe, td)
            forbidden = ("DUP", "ERR", "MUT", "ANOM", "BUG", "FAKE", "DIST")
            for t in ep.truths:
                for tid in t["affected_ids"]:
                    raw = tid.split(":", 1)[1].upper()
                    for tok in forbidden:
                        self.assertNotIn(tok, raw, msg=f"shortcut token {tok} leaked in {tid}")

    def test_all_id_families_and_four_types_pass_stage1_and_stage2(self):
        for split, expected_count in (("dev", 6), ("train", 4)):
            with tempfile.TemporaryDirectory() as td:
                summary = build_and_verify_split(split, Path(td), master_seed=2025)
                self.assertEqual(summary["episode_count"], expected_count)
                self.assertEqual(summary["verified_count"], expected_count)
                self.assertTrue(summary["all_verified"])
                for rec in summary["episodes"]:
                    self.assertFalse(rec["release_blocked"])
                    self.assertEqual(rec["precision_exact"], "1")
                    self.assertEqual(rec["recall_exact"], "1")
                    self.assertEqual(rec["f1_exact"], "1")
                    self.assertEqual(rec["evidence_sufficiency_exact"], "1")
                    self.assertEqual(rec["evidence_minimality_exact"], "1")
                    self.assertEqual(rec["distractor_fp_rate_exact"], "0")
                    self.assertEqual(rec["unresolved_ambiguity_count"], 0)

    def test_clean_twin_with_all_compatible_distractors_zero_fp(self):
        spec = CleanTwinSpec(
            episode_id="clean_full",
            master_seed=42,
            allow_advances=True,
            distractor_classes=(
                "D-DUP-01", "D-DUP-02", "D-DUP-03", "D-DUP-04",
                "D-PART-01", "D-PART-02", "D-PART-03", "D-PART-04",
                "D-FX-01", "D-FX-02",
                "D-CUT-01", "D-CUT-02", "D-CUT-03", "D-CUT-04",
            ),
        )
        twin = generate_clean_twin(spec)
        self.assertEqual(verify_clean_invariants(twin), [])
        with tempfile.TemporaryDirectory() as td:
            ep = build_episode(EpisodeRecipe(spec), td)
            disc = discover(ep.episode_dir / "public", VerifierConfig(run_ablation=True))
            self.assertEqual(disc.report.findings, ())
            self.assertEqual(disc.report.unresolved_ambiguities, ())
            cc = crosscheck(
                disc.report.to_dict(),
                [],
                expected_report_digest=disc.report_digest,
                distractor_count=len(twin.distractor_log),
            )
            self.assertFalse(cc.release_blocked)
            self.assertEqual(cc.f1, Fraction(1))
            self.assertEqual(cc.distractor_false_positive_rate, Fraction(0))

    def test_checked_in_dev_and_train_episodes_100_percent_verified(self):
        dev_dirs = sorted(p for p in (REPO_ROOT / "episodes" / "dev").iterdir() if p.is_dir())
        train_dirs = sorted(p for p in (REPO_ROOT / "episodes" / "train").iterdir() if p.is_dir())
        all_dirs = dev_dirs + train_dirs
        self.assertGreaterEqual(len(dev_dirs), 6)
        self.assertGreaterEqual(len(train_dirs), 4)

        for ep_dir in all_dirs:
            # 1. Manifest SHA-256 verification
            self.assertEqual(verify_episode_manifest(ep_dir), [], msg=f"manifest failed for {ep_dir.name}")
            # 2. Independent Stage-1 discovery matches committed verifier_report.json
            disc = discover(ep_dir / "public", VerifierConfig(run_ablation=True))
            committed = json.loads((ep_dir / "verifier_report.json").read_text(encoding="utf-8"))
            self.assertEqual(validate_instance("verifier_report", committed), [])
            self.assertEqual(disc.report.to_dict(), committed)
            self.assertEqual(disc.report.unresolved_ambiguities, ())
            self.assertTrue(all(ab.all_minimal and ab.all_sufficient for ab in disc.ablation_results))

            # 3. If sealed/truth.json is present locally, verify Stage-2 crosscheck too
            truth_path = ep_dir / "sealed" / "truth.json"
            if truth_path.is_file():
                truths = [TruthFinding.from_dict(t) for t in json.loads(truth_path.read_text(encoding="utf-8"))]
                cc = crosscheck(committed, truths, expected_report_digest=disc.report_digest)
                self.assertFalse(cc.release_blocked, msg=f"{ep_dir.name}: {cc.blocking_reasons}")

    def test_verify_manifest_and_inspect_episode_clis(self):
        ep_dir = REPO_ROOT / "episodes" / "dev" / "ep_dev_006_compound_all4"
        p1 = subprocess.run(
            [sys.executable, "tools/verify_manifest.py", str(ep_dir)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(p1.returncode, 0, msg=p1.stderr + p1.stdout)
        p2 = subprocess.run(
            [sys.executable, "tools/inspect_episode.py", str(ep_dir)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(p2.returncode, 0, msg=p2.stderr + p2.stdout)
        inspected = json.loads(p2.stdout)
        self.assertTrue(inspected["manifest_valid"])


if __name__ == "__main__":
    unittest.main()
