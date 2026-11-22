#!/usr/bin/env python3
"""Run the complete official Genesis FinTech (2026-11-20) baseline evaluation.

Generates all 20 closed scenarios D01..D20 in an ephemeral working directory
(never committing sealed files), executes all 4 baseline policies
(``random``, ``simple_reconciliation``, ``mass_flagging`` in isolated OS
subprocesses + ``oracle`` on the judge side), verifies zero truth leakage in
observations, and writes:
  - ``artifacts/trajectories/trajectories.jsonl``
  - ``artifacts/reports/evaluation/official_eval_summary.json``
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import judge_adapter
from gen.pipeline import build_episode, official_d20_recipes
from harness.isolated_runner import run_inprocess_judge_policy, run_isolated_public_policy
from judge.oracle_policy import JudgeOraclePolicy

FORBIDDEN_LEAK_TOKENS = ("truth.json", "provenance.json", "sealed/", "truth_commitment")


def _assert_no_obs_leakage(traj: dict[str, Any]) -> None:
    """Verify neither initial_observation nor any step observation/info leaks sealed data."""
    blob = json.dumps(
        {
            "initial_observation": traj["initial_observation"],
            "steps": [
                {"observation": s["observation"], "info": s["info"], "reward": s["reward"]}
                for s in traj["steps"]
            ],
        },
        ensure_ascii=False,
    )
    for tok in FORBIDDEN_LEAK_TOKENS:
        if tok in blob:
            raise AssertionError(f"leakage token {tok!r} found in trajectory for {traj['episode_id']}")
    for s in traj["steps"]:
        if traj["mode"] == "closed" and s["reward"] != 0:
            raise AssertionError(f"non-zero closed-mode reward {s['reward']} in {traj['episode_id']}")


def run_evaluation(
    *,
    master_seed: int = 2026,
    trajectories_path: Path | None = None,
    summary_path: Path | None = None,
) -> dict[str, Any]:
    traj_out = trajectories_path or (REPO_ROOT / "artifacts" / "trajectories" / "trajectories.jsonl")
    # Deliberately NOT inside artifacts/reports/latest/: that directory is the
    # frozen Judge Kit evidence set (TZ §23.5, 20 files). Writing a 21st file
    # there made the documented artifact count false after a legitimate
    # `make official-eval` (found during the mandatory-target sweep, D-16-02).
    sum_out = summary_path or (REPO_ROOT / "artifacts" / "reports" / "evaluation" / "official_eval_summary.json")
    traj_out.parent.mkdir(parents=True, exist_ok=True)
    sum_out.parent.mkdir(parents=True, exist_ok=True)

    recipes = official_d20_recipes(master_seed=master_seed)
    public_policies = ("random", "simple_reconciliation", "mass_flagging")
    all_policies = (*public_policies, "oracle")

    per_policy_runs: dict[str, list[dict[str, Any]]] = {p: [] for p in all_policies}
    trajectories: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="twinledger_d20_") as tmp:
        for idx, recipe in enumerate(recipes):
            ge = build_episode(recipe, tmp)
            ep_dir = str(ge.episode_dir)
            ep_seed = master_seed + idx

            for pname in public_policies:
                env = judge_adapter.make_env()
                res = run_isolated_public_policy(
                    env,
                    policy_name=pname,
                    episode_dir=ep_dir,
                    seed=ep_seed,
                    mode="closed",
                    time_limit_s=60.0,
                    score_fn=judge_adapter.score_episode,
                )
                rec = res.to_trajectory_record()
                _assert_no_obs_leakage(rec)
                trajectories.append(rec)
                per_policy_runs[pname].append(
                    {
                        "episode_id": rec["episode_id"],
                        "inspection_steps": rec["inspection_steps"],
                        "duration_s": rec["duration_s"],
                        "terminated": rec["terminated"],
                        "truncated": rec["truncated"],
                        "metrics": rec["metrics"],
                    }
                )

            # Judge-side Oracle policy
            env = judge_adapter.make_env()
            oracle = JudgeOraclePolicy(ep_dir, inspection_steps=4)
            res_oracle = run_inprocess_judge_policy(
                env,
                oracle,
                episode_dir=ep_dir,
                seed=ep_seed,
                mode="closed",
                time_limit_s=60.0,
                score_fn=judge_adapter.score_episode,
            )
            rec_o = res_oracle.to_trajectory_record()
            _assert_no_obs_leakage(rec_o)
            trajectories.append(rec_o)
            per_policy_runs["oracle"].append(
                {
                    "episode_id": rec_o["episode_id"],
                    "inspection_steps": rec_o["inspection_steps"],
                    "duration_s": rec_o["duration_s"],
                    "terminated": rec_o["terminated"],
                    "truncated": rec_o["truncated"],
                    "metrics": rec_o["metrics"],
                }
            )

    with traj_out.open("w", encoding="utf-8") as fh:
        for rec in trajectories:
            fh.write(json.dumps(rec, separators=(",", ":"), ensure_ascii=False) + "\n")

    policy_summary: dict[str, Any] = {}
    for pname, runs in per_policy_runs.items():
        returns = [float(r["metrics"]["return"]) for r in runs if r["metrics"] is not None]
        f1s = [float(r["metrics"]["f1"]) for r in runs if r["metrics"] and r["metrics"]["f1"] is not None]
        steps = [int(r["inspection_steps"]) for r in runs]
        durs = [float(r["duration_s"]) for r in runs]
        policy_summary[pname] = {
            "episodes": len(runs),
            "mean_f1": round(statistics.mean(f1s), 6) if f1s else None,
            "mean_return": round(statistics.mean(returns), 6) if returns else None,
            "min_return": round(min(returns), 6) if returns else None,
            "max_return": round(max(returns), 6) if returns else None,
            "mean_inspection_steps": round(statistics.mean(steps), 3) if steps else 0.0,
            "mean_duration_s": round(statistics.mean(durs), 4) if durs else 0.0,
            "max_duration_s": round(max(durs), 4) if durs else 0.0,
            "runs": runs,
        }

    try:
        traj_rel = str(traj_out.relative_to(REPO_ROOT))
    except ValueError:
        traj_rel = str(traj_out)

    summary = {
        "schema_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "master_seed": master_seed,
        "episodes_evaluated": len(recipes),
        "trajectories_count": len(trajectories),
        "trajectories_file": traj_rel,
        "policies": policy_summary,
    }
    sum_out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run official D01..D20 baseline evaluation")
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args(argv)
    summary = run_evaluation(master_seed=args.seed)
    print(f"Official D01..D20 evaluation complete ({summary['trajectories_count']} trajectories):")
    for pname, stats in summary["policies"].items():
        print(
            f"  {pname:24s} mean_F1={stats['mean_f1']:.4f} "
            f"mean_return={stats['mean_return']:+.4f} "
            f"mean_steps={stats['mean_inspection_steps']:.1f} "
            f"max_dur={stats['max_duration_s']:.3f}s"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
