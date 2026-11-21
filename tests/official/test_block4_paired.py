"""Block 4 mirror tests: All 20 paired invariance checks P01..P20 (Genesis FinTech 2026-11-20).

Matrix:
  - P01..P05 on D01..D05: Row permutation only (order preserved by env, values identical)
  - P06..P10 on D06..D10: Bijective ID remap only (order preserved, IDs remapped consistently)
  - P11..P20 on D11..D20: Row permutation + bijective ID remap together

Verifies all 4 pass/fail pair criteria:
  1. Exact determinism on original episode repeat (records, transitions, rewards, reset cleanliness);
  2. Oracle findings on transformed variant match original after inverse ID mapping;
  3. Exact equality of TP, FP, FN, P, R, F1, and terminal return at equal inspection_steps;
  4. Zero new leakage channels, all remapped evidence reachable, FX semantic key intact.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import judge_adapter
from gen.pipeline import build_episode, official_d20_recipes
from harness.isolated_runner import run_inprocess_judge_policy
from judge.oracle_policy import JudgeOraclePolicy
from metamorphic.paired_transform import invert_findings_ids, transform_episode_copy


class TestBlock4PairedInvarianceP01ToP20(unittest.TestCase):
    """Exact verification of paired order/ID invariance checks P01..P20."""

    def test_P01_to_P20_paired_invariance_matrix(self) -> None:
        recipes = official_d20_recipes(master_seed=2026)
        self.assertEqual(len(recipes), 20)

        with tempfile.TemporaryDirectory(prefix="tl_block4_") as tmp:
            root = Path(tmp)
            for idx, recipe in enumerate(recipes, start=1):
                orig_dir = build_episode(recipe, root / "orig").episode_dir
                permute = (1 <= idx <= 5) or (11 <= idx <= 20)
                remap = 6 <= idx <= 20

                # Criterion 1: Repeated reset + identical actions reproduce exact records & rewards
                env_rep = judge_adapter.make_env()
                obs_a, _ = env_rep.reset(seed=2026, config={"mode": "closed", "episode_dir": str(orig_dir)})
                s_a1, r_a1, _, _, _ = env_rep.step({"name": "list_records", "args": {"table": "invoices", "cursor": None, "limit": 50}})
                obs_b, _ = env_rep.reset(seed=2026, config={"mode": "closed", "episode_dir": str(orig_dir)})
                s_b1, r_b1, _, _, _ = env_rep.step({"name": "list_records", "args": {"table": "invoices", "cursor": None, "limit": 50}})
                self.assertEqual(obs_a, obs_b)
                self.assertEqual(s_a1, s_b1)
                self.assertEqual(r_a1, r_b1)

                # Build transformed copy without touching original
                tr_dir = root / "transformed" / f"P{idx:02d}_{recipe.twin_spec.episode_id}"
                tr = transform_episode_copy(
                    orig_dir,
                    tr_dir,
                    permute_rows=permute,
                    remap_ids=remap,
                    seed=7000 + idx,
                )

                # Verify env preserves file row order when permuted (P01..P05, P11..P20)
                if permute:
                    env_o = judge_adapter.make_env()
                    env_o.reset(seed=2026, config={"mode": "closed", "episode_dir": str(orig_dir)})
                    o_rows = env_o.step({"name": "list_records", "args": {"table": "ledger", "cursor": None, "limit": 50}})[0]["result"]["records"]

                    env_t = judge_adapter.make_env()
                    env_t.reset(seed=2026, config={"mode": "closed", "episode_dir": str(tr.transformed_dir)})
                    t_rows = env_t.step({"name": "list_records", "args": {"table": "ledger", "cursor": None, "limit": 50}})[0]["result"]["records"]

                    self.assertEqual(len(o_rows), len(t_rows))
                    if not remap and len(o_rows) > 1:
                        self.assertNotEqual(
                            [r["je_id"] for r in o_rows],
                            [r["je_id"] for r in t_rows],
                            f"P{idx:02d}: env re-sorted permuted rows instead of preserving file order",
                        )

                # Verify FX semantic key lookup works identically on transformed copy
                env_fx = judge_adapter.make_env()
                env_fx.reset(seed=2026, config={"mode": "closed", "episode_dir": str(tr.transformed_dir)})
                fx_page = env_fx.step({"name": "list_records", "args": {"table": "fx", "cursor": None, "limit": 1}})[0]["result"]["records"]
                if fx_page:
                    fx0 = fx_page[0]
                    src_c, dst_c = fx0["pair"].split("/", 1)
                    sem_key = f"{fx0['effective_date']}:{src_c}:{dst_c}:{fx0['source_code']}"
                    got_fx = env_fx.step({"name": "get_record", "args": {"table": "fx", "id": sem_key}})[0]["result"]
                    self.assertIsNotNone(got_fx)
                    self.assertEqual(got_fx["rate_decimal"], fx0["rate_decimal"])

                # Criterion 2 & 3: Oracle on original vs transformed with IDENTICAL inspection_steps=6
                oracle_orig = JudgeOraclePolicy(orig_dir, inspection_steps=6)
                res_orig = run_inprocess_judge_policy(
                    judge_adapter.make_env(),
                    oracle_orig,
                    episode_dir=str(orig_dir),
                    seed=2026,
                    mode="closed",
                    score_fn=judge_adapter.score_episode,
                )

                oracle_tr = JudgeOraclePolicy(tr.transformed_dir, inspection_steps=6)
                res_tr = run_inprocess_judge_policy(
                    judge_adapter.make_env(),
                    oracle_tr,
                    episode_dir=str(tr.transformed_dir),
                    seed=2026,
                    mode="closed",
                    score_fn=judge_adapter.score_episode,
                )

                # Identical inspection_steps and exact metrics/return match
                self.assertEqual(res_orig.inspection_steps, 6)
                self.assertEqual(res_tr.inspection_steps, 6)
                self.assertEqual(res_orig.metrics["tp"], res_tr.metrics["tp"])
                self.assertEqual(res_orig.metrics["fp"], res_tr.metrics["fp"])
                self.assertEqual(res_orig.metrics["fn"], res_tr.metrics["fn"])
                self.assertAlmostEqual(res_orig.metrics["precision"], res_tr.metrics["precision"], delta=1e-9)
                self.assertAlmostEqual(res_orig.metrics["recall"], res_tr.metrics["recall"], delta=1e-9)
                self.assertAlmostEqual(res_orig.metrics["f1"], res_tr.metrics["f1"], delta=1e-9)
                self.assertAlmostEqual(res_orig.metrics["return"], res_tr.metrics["return"], delta=1e-9)
                self.assertAlmostEqual(res_tr.metrics["f1"], 1.0, delta=1e-9)

                # Inverse ID mapping matches original findings (type, affected_ids, amount, currency, evidence_ids)
                inv_orig = invert_findings_ids(res_orig.final_findings, {})
                inv_tr = invert_findings_ids(res_tr.final_findings, tr.inverse_map)
                self.assertEqual(len(inv_orig["findings"]), len(inv_tr["findings"]))
                for fo, ft in zip(inv_orig["findings"], inv_tr["findings"]):
                    self.assertEqual(fo["type"], ft["type"])
                    self.assertEqual(fo["affected_ids"], ft["affected_ids"])
                    self.assertEqual(fo["claimed_amount_minor"], ft["claimed_amount_minor"])
                    self.assertEqual(fo["currency"], ft["currency"])
                    self.assertEqual(fo["evidence_ids"], ft["evidence_ids"])

                # Criterion 4: Zero leakage in transformed observations
                tr_obs_blob = json.dumps(
                    [res_tr.initial_observation, [s["observation"] for s in res_tr.steps]],
                    ensure_ascii=False,
                )
                for bad in ("truth.json", "provenance.json", "sealed/"):
                    self.assertNotIn(bad, tr_obs_blob)


if __name__ == "__main__":
    unittest.main()
