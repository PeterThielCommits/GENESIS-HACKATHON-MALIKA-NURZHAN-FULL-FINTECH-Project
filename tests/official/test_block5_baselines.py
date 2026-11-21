"""Block 5 mirror tests: 4 baseline policies, process isolation, and trajectories.jsonl."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.run_official_eval import run_evaluation


class TestBlock5BaselinesAndTrajectories(unittest.TestCase):
    """Verify all 4 baseline policies, OS isolation, trajectories.jsonl, and score separation."""

    def test_four_baselines_isolated_and_trajectories_clean(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tl_block5_") as tmp:
            root = Path(tmp)
            traj_file = root / "trajectories.jsonl"
            sum_file = root / "summary.json"
            summary = run_evaluation(
                master_seed=2026,
                trajectories_path=traj_file,
                summary_path=sum_file,
            )

            self.assertEqual(summary["episodes_evaluated"], 20)
            self.assertEqual(summary["trajectories_count"], 80)
            self.assertTrue(traj_file.is_file())

            # Validate every line of trajectories.jsonl
            lines = [ln for ln in traj_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
            self.assertEqual(len(lines), 80)
            policies_seen: set[str] = set()
            for ln in lines:
                rec = json.loads(ln)
                policies_seen.add(rec["policy"])
                self.assertIn("initial_observation", rec)
                self.assertIn("steps", rec)
                self.assertIn("metrics", rec)
                self.assertEqual(rec["mode"], "closed")
                # Zero truth leakage in observations
                obs_blob = json.dumps([rec["initial_observation"], [s["observation"] for s in rec["steps"]]])
                for tok in ("truth.json", "provenance.json", "sealed/", "truth_commitment"):
                    self.assertNotIn(tok, obs_blob)

            self.assertEqual(policies_seen, {"random", "simple_reconciliation", "mass_flagging", "oracle"})

            # Meaningful separation of baselines: oracle >= simple > random > mass_flagging
            pols = summary["policies"]
            self.assertGreaterEqual(pols["oracle"]["mean_return"], pols["simple_reconciliation"]["mean_return"])
            self.assertGreater(pols["simple_reconciliation"]["mean_return"], pols["random"]["mean_return"])
            self.assertGreater(pols["random"]["mean_return"], pols["mass_flagging"]["mean_return"])
            self.assertLess(pols["mass_flagging"]["mean_return"], -0.5)
            self.assertAlmostEqual(pols["oracle"]["mean_f1"], 1.0, delta=1e-9)


if __name__ == "__main__":
    unittest.main()
