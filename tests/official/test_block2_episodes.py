"""Block 2 mirror tests: 20 closed scenarios D01..D20 (Genesis FinTech 2026-11-20)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import judge_adapter
from contracts.models import TruthFinding
from gen.pipeline import build_episode, official_d20_recipes
from scoring.crosscheck import crosscheck
from scoring.official_scorer import collect_accessible_ids_from_episode_dir
from verifier.discover import discover


class TestBlock2ClosedEpisodesD01ToD20(unittest.TestCase):
    """Verify every scenario D01..D20 satisfies all 6 Block 2 pass criteria."""

    def test_all_20_scenarios_independent_verifier_and_evidence_reachability(self) -> None:
        recipes = official_d20_recipes(master_seed=2026)
        self.assertEqual(len(recipes), 20)

        # Verify scenario matrix counts: 5 clean, 3 dup, 3 partial/missing, 2 fx, 2 cutoff, 3 int#1, 2 int#2
        self.assertEqual(sum(1 for r in recipes[:5] if len(r.anomalies) == 0), 5)
        self.assertEqual([r.anomalies for r in recipes[5:8]], [("DUPLICATE_PAYMENT",)] * 3)
        self.assertEqual([r.anomalies for r in recipes[8:11]], [("PARTIAL_PAYMENT_ALLOCATION",)] * 3)
        self.assertIn("missing_allocation", [r.partial_subcase for r in recipes[8:11]])
        self.assertIn("premature_paid", [r.partial_subcase for r in recipes[8:11]])
        self.assertEqual([r.anomalies for r in recipes[11:13]], [("FX_RATE_MISMATCH",)] * 2)
        self.assertEqual([r.anomalies for r in recipes[13:15]], [("PERIOD_CUTOFF",)] * 2)
        self.assertEqual([r.anomalies for r in recipes[15:18]], [("FX_RATE_MISMATCH", "PERIOD_CUTOFF")] * 3)
        self.assertEqual([r.anomalies for r in recipes[18:20]], [("DUPLICATE_PAYMENT", "PARTIAL_PAYMENT_ALLOCATION")] * 2)

        with tempfile.TemporaryDirectory(prefix="tl_block2_") as tmp:
            for rec in recipes:
                ge = build_episode(rec, tmp)
                ep_dir = ge.episode_dir

                # Criterion 1 & 2 & 3: provenance + independent zero-common-mode verifier F1=1.0
                prov = json.loads((ep_dir / "sealed" / "provenance.json").read_text(encoding="utf-8"))
                self.assertIn("structural_diff", prov)
                if rec.anomalies:
                    self.assertTrue(prov["structural_diff"], f"empty diff for {rec.twin_spec.episode_id}")
                else:
                    self.assertEqual(prov["structural_diff"], {}, f"non-empty diff for clean {rec.twin_spec.episode_id}")

                v = discover(ep_dir / "public")
                truth_raw = json.loads((ep_dir / "sealed" / "truth.json").read_text(encoding="utf-8"))
                truths = [TruthFinding.from_dict(t) for t in truth_raw]
                cc = crosscheck(v.report.to_dict(), truths)
                d = cc.to_dict()
                self.assertEqual(d["counts"]["fp"], 0, f"FP on {rec.twin_spec.episode_id}")
                self.assertEqual(d["counts"]["fn"], 0, f"FN on {rec.twin_spec.episode_id}")
                self.assertEqual(d["metrics"]["f1"]["exact"], "1", f"F1!=1 on {rec.twin_spec.episode_id}")

                # Criterion 4: every evidence ID in at least one valid evidence set is reachable via public tools
                accessible = collect_accessible_ids_from_episode_dir(ep_dir)
                for t in truth_raw:
                    self.assertTrue(
                        any(set(es).issubset(accessible) for es in t["evidence_sets"]),
                        f"unreachable evidence set on {rec.twin_spec.episode_id}: {t['evidence_sets']}",
                    )

                # Verify oracle submission via judge_adapter achieves F1=1.0 on every episode
                oracle_findings = {
                    "findings": [
                        {
                            "type": t["type"],
                            "affected_ids": t["affected_ids"],
                            "claimed_amount_minor": t["amount_minor"],
                            "currency": t["currency"],
                            "evidence_ids": t["evidence_sets"][0],
                            "explanation": "verified",
                        }
                        for t in truth_raw
                    ]
                }
                scored = judge_adapter.score_episode(str(ep_dir), oracle_findings, inspection_steps=10)
                self.assertAlmostEqual(scored["f1"], 1.0, delta=1e-9)
                self.assertAlmostEqual(scored["return"], 0.98, delta=1e-9)


if __name__ == "__main__":
    unittest.main()
