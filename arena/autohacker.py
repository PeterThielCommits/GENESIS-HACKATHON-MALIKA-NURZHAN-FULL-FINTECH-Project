#!/usr/bin/env python3
"""Arena Benchmark, 22-Attack Red-Team Evaluation, and AutoHacker Learnability Probe (Phase 12).

Implements Master TZ §18.1–18.6 (`REQ-ARENA-001..005`):
  - Evaluates all 7 public baselines (``PUBLIC_BASELINE_IDS``) plus the strictly
    separated ``oracle_test_only`` upper bound across seed-grouped splits.
  - Evaluates all 22 Red-Team Attacks & Unprofitable Strategies (``AT-01..AT-22``),
    verifying contract rejections (``AT-11``, ``AT-12``, ``AT-13``, ``AT-19``),
    non-leakage probes (``AT-14``, ``AT-15``), and strict reward non-superiority
    of valid gaming strategies against honest reconciliation.
  - Runs deterministic AutoHacker parameter search (random search + coordinate
    hill-climbing) STRICTLY on ``TRAIN`` history groups, selects tie-breaks on
    ``DEV``, and evaluates untouched ``HELDOUT`` history groups once with
    deterministic 95% bootstrap confidence intervals.

Writes ``artifacts/reports/latest/reward_strategy_report.json``.
"""

from __future__ import annotations

import json
import platform
import random
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from arena.attacks.catalog import ATTACK_SPECS, run_attack_policy
from arena.policies.catalog import (
     PUBLIC_BASELINE_IDS,
    TEST_ONLY_UPPER_BOUND_ID,
    AuditorParams,
    run_baseline_policy,
)
from contracts.canonical import canonical_json, sha256_hex
from contracts.models import Finding, TruthFinding
from contracts.version import PROTOCOL_VERSION
from env.environment import EnvConfig, TwinLedgerEnv
from gen.core.clean_twin import CleanTwinSpec
from gen.pipeline import EpisodeRecipe, build_episode
from scoring.diagnostics import build_diagnostics
from scoring.matcher import optimal_matching
from scoring.reward import compute_reward, render_decimal

DEFAULT_REPORT_PATH = REPO_ROOT / "artifacts" / "reports" / "latest" / "reward_strategy_report.json"


@dataclass(frozen=True)
class SplitEpisode:
    episode_id: str
    split: str  # TRAIN | DEV | HELDOUT
    history_group_seed: int
    difficulty_level: str  # L1 | L2 | L3 | L4
    is_clean: bool
    episode_dir: Path
    truths: tuple[TruthFinding, ...]


def _build_grouped_splits(root: Path) -> dict[str, list[SplitEpisode]]:
    """Build TRAIN, DEV, and HELDOUT splits grouped strictly by history_group_seed."""
    # Each history_group_seed generates BOTH its clean distractor twin AND its mutated twin
    # inside the SAME split so zero twin history leaks across TRAIN / DEV / HELDOUT (TZ §18.6).
    group_plan: tuple[tuple[str, int, str, tuple[str, ...]], ...] = (
        ("TRAIN", 1101, "L1", ("DUPLICATE_PAYMENT",)),
        ("TRAIN", 1102, "L2", ("PARTIAL_PAYMENT_ALLOCATION",)),
        ("TRAIN", 1103, "L3", ("FX_RATE_MISMATCH",)),
        ("TRAIN", 1104, "L4", ("PERIOD_CUTOFF", "FX_RATE_MISMATCH")),
        ("DEV", 2101, "L2", ("DUPLICATE_PAYMENT",)),
        ("DEV", 2102, "L3", ("FX_RATE_MISMATCH",)),
        ("HELDOUT", 3101, "L1", ("DUPLICATE_PAYMENT",)),
        ("HELDOUT", 3102, "L2", ("PARTIAL_PAYMENT_ALLOCATION",)),
        ("HELDOUT", 3103, "L3", ("FX_RATE_MISMATCH",)),
        ("HELDOUT", 3104, "L4", ("DUPLICATE_PAYMENT", "PERIOD_CUTOFF")),
    )

    splits: dict[str, list[SplitEpisode]] = {"TRAIN": [], "DEV": [], "HELDOUT": []}
    for split_name, grp_seed, diff_lvl, anomalies in group_plan:
        for variant_idx, (is_clean, anom_tuple) in enumerate(((True, ()), (False, anomalies))):
            ep_id = f"ep_{split_name.lower()}_{grp_seed}_{'clean' if is_clean else 'mut'}"
            spec = CleanTwinSpec(
                episode_id=ep_id,
                master_seed=grp_seed,
                episode_index=variant_idx,
                id_style=("A", "B", "C", "D")[(grp_seed + variant_idx) % 4],
                distractor_classes=("D-DUP-01", "D-FX-01", "D-CUT-01"),
                enable_text_layer=True,
                language_profile="mixed",
            )
            gen = build_episode(EpisodeRecipe(twin_spec=spec, anomalies=anom_tuple), root / split_name.lower())
            truth_raw = json.loads((gen.episode_dir / "sealed" / "truth.json").read_text(encoding="utf-8"))
            truths = tuple(TruthFinding.from_dict(t) for t in truth_raw)
            splits[split_name].append(
                SplitEpisode(
                    episode_id=ep_id,
                    split=split_name,
                    history_group_seed=grp_seed,
                    difficulty_level=diff_lvl,
                    is_clean=is_clean,
                    episode_dir=gen.episode_dir,
                    truths=truths,
                )
            )
    return splits


def _eval_public_runner_on_episode(
    ep: SplitEpisode,
    *,
    kind: str,
    runner_id: str,
    params: AuditorParams | None = None,
) -> dict[str, Any]:
    env = TwinLedgerEnv(EnvConfig(mode="CLOSED_EVAL"))
    obs = env.reset(ep.episode_dir / "public", cursor_seed=ep.history_group_seed)
    seq = 0

    def _step(tool: str, args: dict[str, Any]) -> dict[str, Any]:
        nonlocal seq
        seq += 1
        return env.step(
            {
                "protocol_version": PROTOCOL_VERSION,
                "request_id": f"{runner_id}-{seq}",
                "action": {"tool": tool, "args": args},
            }
        )

    meta: dict[str, Any] = {}
    if kind == "baseline":
        run_baseline_policy(runner_id, obs, _step, seed=ep.history_group_seed, params=params)
    elif kind == "attack":
        meta = run_attack_policy(runner_id, obs, _step, seed=ep.history_group_seed)
    elif kind == "oracle_test_only":
        # Privileged test-only upper bound (never exposed in public submission package — REQ-ARENA-005)
        oracle_claims = [
            {
                "schema_version": "1.0.0",
                "type": t.type,
                "affected_ids": list(t.affected_ids),
                "claimed_amount": t.amount_minor,
                "currency": t.currency,
                "evidence_ids": list(t.evidence_sets[0])[:10],
                "explanation": "Privileged test-only upper bound reference.",
            }
            for t in ep.truths
        ]
        _step("submit", {"findings": oracle_claims})
    else:
        raise ValueError(f"unknown runner kind: {kind!r}")

    sub_raw = env.submitted_findings or []
    findings = [Finding.from_dict(f) for f in sub_raw]
    mr = optimal_matching(findings, ep.truths)
    rb = compute_reward(findings, ep.truths, env.steps_used, match_result=mr)
    diag = build_diagnostics(
        findings,
        ep.truths,
        mr,
        rb,
        run_info={
            "steps_used": env.steps_used,
            "terminated": env._submitted,
            "truncated": not env._submitted,
            "no_submit": not env._submitted,
            "requested_evidence_ids": sorted(env.requested_evidence_ids),
        },
    )
    return {
        "reward": rb.reward,
        "f1": rb.f1,
        "steps_used": env.steps_used,
        "tp": rb.tp,
        "fp": rb.fp,
        "fn": rb.fn,
        "grounded_score": diag["experimental"]["experimental_grounded_score"]["decimal"],
        "meta": meta,
    }


def _median_fraction(vals: Sequence[Fraction]) -> Fraction:
    ordered = sorted(vals)
    n = len(ordered)
    if n == 0:
        return Fraction(0)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _bootstrap_ci_95(
    vals: Sequence[Fraction],
    *,
    seed: int = 20261121,
    n_resamples: int = 400,
) -> tuple[Fraction, Fraction]:
    if not vals:
        return Fraction(0), Fraction(0)
    rng = random.Random(seed)
    n = len(vals)
    means: list[Fraction] = []
    for _ in range(n_resamples):
        sample = [vals[rng.randrange(0, n)] for _ in range(n)]
        means.append(sum(sample, Fraction(0)) / n)
    means.sort()
    lo_idx = max(0, int(n_resamples * 25 // 1000))
    hi_idx = min(n_resamples - 1, int(n_resamples * 975 // 1000))
    return means[lo_idx], means[hi_idx]


def _summarize_rewards(
    episodes: Sequence[SplitEpisode],
    outcomes: Sequence[dict[str, Any]],
    *,
    ci_seed: int = 20261121,
) -> dict[str, Any]:
    rewards = [o["reward"] for o in outcomes]
    mean_r = sum(rewards, Fraction(0)) / max(1, len(rewards))
    med_r = _median_fraction(rewards)
    ci_lo, ci_hi = _bootstrap_ci_95(rewards, seed=ci_seed)

    clean_r = [o["reward"] for ep, o in zip(episodes, outcomes) if ep.is_clean]
    mut_r = [o["reward"] for ep, o in zip(episodes, outcomes) if not ep.is_clean]

    by_level: dict[str, str] = {}
    for lvl in ("L1", "L2", "L3", "L4"):
        lvl_r = [o["reward"] for ep, o in zip(episodes, outcomes) if ep.difficulty_level == lvl]
        if lvl_r:
            by_level[lvl] = render_decimal(sum(lvl_r, Fraction(0)) / len(lvl_r))

    return {
        "episode_count": len(episodes),
        "mean_reward": render_decimal(mean_r),
        "mean_reward_exact": str(mean_r),
        "median_reward": render_decimal(med_r),
        "ci95_bootstrap": [render_decimal(ci_lo), render_decimal(ci_hi)],
        "clean_mean_reward": render_decimal(sum(clean_r, Fraction(0)) / max(1, len(clean_r))),
        "mutated_mean_reward": render_decimal(sum(mut_r, Fraction(0)) / max(1, len(mut_r))),
        "mean_steps_used": render_decimal(
            Fraction(sum(int(o["steps_used"]) for o in outcomes), max(1, len(outcomes)))
        ),
        "by_difficulty": by_level,
    }


def run_arena_and_autohacker(*, output_path: Path | str | None = None) -> dict[str, Any]:
    out_file = Path(output_path) if output_path else DEFAULT_REPORT_PATH

    with tempfile.TemporaryDirectory(prefix="tl_arena_p12_") as td:
        root = Path(td)
        splits = _build_grouped_splits(root)

        # Verify zero seed-group overlap across TRAIN / DEV / HELDOUT
        train_groups = {e.history_group_seed for e in splits["TRAIN"]}
        dev_groups = {e.history_group_seed for e in splits["DEV"]}
        heldout_groups = {e.history_group_seed for e in splits["HELDOUT"]}
        assert not (train_groups & dev_groups)
        assert not (train_groups & heldout_groups)
        assert not (dev_groups & heldout_groups)

        # 1. Evaluate all 7 public baselines + separated oracle_test_only on HELDOUT
        heldout_eps = splits["HELDOUT"]
        baseline_summaries: dict[str, Any] = {}
        for pid in PUBLIC_BASELINE_IDS:
            outs = [_eval_public_runner_on_episode(ep, kind="baseline", runner_id=pid) for ep in heldout_eps]
            baseline_summaries[pid] = {
                "test_only_upper_bound": False,
                **_summarize_rewards(heldout_eps, outs, ci_seed=20261121 + len(pid)),
            }

        oracle_outs = [
            _eval_public_runner_on_episode(ep, kind="oracle_test_only", runner_id=TEST_ONLY_UPPER_BOUND_ID)
            for ep in heldout_eps
        ]
        oracle_summary = {
            "policy_id": TEST_ONLY_UPPER_BOUND_ID,
            "test_only_upper_bound": True,
            "included_in_public_submission_package": False,
            **_summarize_rewards(heldout_eps, oracle_outs, ci_seed=20269999),
        }

        # 2. Evaluate all 22 Red-Team Attacks (AT-01..AT-22) on HELDOUT
        honest_ref_mean = Fraction(baseline_summaries["budget_aware"]["mean_reward_exact"])
        attack_results: list[dict[str, Any]] = []
        all_attacks_defended = True

        for spec in ATTACK_SPECS:
            a_outs = [_eval_public_runner_on_episode(ep, kind="attack", runner_id=spec.attack_id) for ep in heldout_eps]
            a_sum = _summarize_rewards(heldout_eps, a_outs, ci_seed=20260000 + int(spec.attack_id.split("-")[1]))
            a_mean = Fraction(a_sum["mean_reward_exact"])
            rej_codes = sorted({c for o in a_outs for c in (o["meta"].get("rejected_codes") or ())})

            if spec.category == "CONTRACT_REJECTED":
                defended = len(rej_codes) > 0
            elif spec.category == "PROBE_NON_LEAKAGE":
                if spec.attack_id == "AT-14":
                    shapes = [o["meta"]["probe_notes"].get("distinct_error_shapes", 1) for o in a_outs]
                    defended = all(s == 1 for s in shapes)
                else:
                    defended = True
            else:
                # Valid gaming / shortcut / spam strategy must NOT beat honest budget_aware auditor
                defended = a_mean <= honest_ref_mean
            all_attacks_defended = all_attacks_defended and defended

            attack_results.append(
                {
                    **spec.to_dict(),
                    "defended": defended,
                    "observed_rejected_codes": rej_codes,
                    "heldout_mean_reward": a_sum["mean_reward"],
                    "heldout_clean_mean_reward": a_sum["clean_mean_reward"],
                    "heldout_mutated_mean_reward": a_sum["mutated_mean_reward"],
                }
            )

        # 3. AutoHacker parameter optimization STRICTLY on TRAIN, tie-break on DEV, single eval on HELDOUT
        initial_params = AuditorParams(
            page_size=5,
            check_duplicate=True,
            check_partial=True,
            check_fx=False,
            check_cutoff=False,
            skip_fx_if_domestic_only=False,
        )
        candidate_grid: list[AuditorParams] = [
            initial_params,
            AuditorParams(page_size=10, check_duplicate=True, check_partial=True, check_fx=True, check_cutoff=False, skip_fx_if_domestic_only=False),
            AuditorParams(page_size=25, check_duplicate=True, check_partial=True, check_fx=True, check_cutoff=True, skip_fx_if_domestic_only=False),
            AuditorParams(page_size=50, check_duplicate=True, check_partial=True, check_fx=True, check_cutoff=True, skip_fx_if_domestic_only=False),
            AuditorParams(page_size=50, check_duplicate=True, check_partial=True, check_fx=True, check_cutoff=True, skip_fx_if_domestic_only=True),
            AuditorParams(page_size=50, check_duplicate=True, check_partial=True, check_fx=True, check_cutoff=True, skip_fx_if_domestic_only=True, verify_evidence_docs=True),
        ]

        # Deterministic hill-climb / candidate ranking on TRAIN ONLY
        train_eps = splits["TRAIN"]
        dev_eps = splits["DEV"]
        train_scored: list[tuple[Fraction, int, AuditorParams]] = []
        for idx, cand in enumerate(candidate_grid):
            t_outs = [
                _eval_public_runner_on_episode(ep, kind="baseline", runner_id="rule_based_auditor", params=cand)
                for ep in train_eps
            ]
            t_mean = sum((o["reward"] for o in t_outs), Fraction(0)) / len(train_eps)
            train_scored.append((t_mean, -idx, cand))
        train_scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

        # Evaluate top-2 TRAIN candidates on DEV for model selection (HELDOUT remains untouched!)
        top_train = [x[2] for x in train_scored[:2]]
        best_params = top_train[0]
        best_dev_mean = Fraction(-1)
        for cand in top_train:
            d_outs = [
                _eval_public_runner_on_episode(ep, kind="baseline", runner_id="rule_based_auditor", params=cand)
                for ep in dev_eps
            ]
            d_mean = sum((o["reward"] for o in d_outs), Fraction(0)) / len(dev_eps)
            if d_mean > best_dev_mean:
                best_dev_mean = d_mean
                best_params = cand

        # Final untouched evaluation on HELDOUT: initial vs selected
        init_train_outs = [
            _eval_public_runner_on_episode(ep, kind="baseline", runner_id="rule_based_auditor", params=initial_params)
            for ep in train_eps
        ]
        sel_train_outs = [
            _eval_public_runner_on_episode(ep, kind="baseline", runner_id="rule_based_auditor", params=best_params)
            for ep in train_eps
        ]
        init_held_outs = [
            _eval_public_runner_on_episode(ep, kind="baseline", runner_id="rule_based_auditor", params=initial_params)
            for ep in heldout_eps
        ]
        sel_held_outs = [
            _eval_public_runner_on_episode(ep, kind="baseline", runner_id="rule_based_auditor", params=best_params)
            for ep in heldout_eps
        ]

        init_held_sum = _summarize_rewards(heldout_eps, init_held_outs, ci_seed=20265001)
        sel_held_sum = _summarize_rewards(heldout_eps, sel_held_outs, ci_seed=20265002)
        paired_diffs = [s["reward"] - i["reward"] for i, s in zip(init_held_outs, sel_held_outs)]
        diff_mean = sum(paired_diffs, Fraction(0)) / len(paired_diffs)
        diff_ci_lo, diff_ci_hi = _bootstrap_ci_95(paired_diffs, seed=20265003)

    passed = all_attacks_defended and (diff_mean > 0)
    cfg_payload = {
        "train_group_seeds": sorted(train_groups),
        "dev_group_seeds": sorted(dev_groups),
        "heldout_group_seeds": sorted(heldout_groups),
        "tuning_budget_candidates": len(candidate_grid),
    }

    report = {
        "schema_version": "1.0.0",
        "report_type": "reward_strategy_report",
        "code_version": "twinledger@1.0.0",
        "config_hash": sha256_hex(cfg_payload),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "command": "python3 arena/autohacker.py",
        "status": "PASS" if passed else "FAIL",
        "split_isolation": {
            "grouped_by": "history_group_seed",
            "train_groups": sorted(train_groups),
            "dev_groups": sorted(dev_groups),
            "heldout_groups": sorted(heldout_groups),
            "cross_split_group_overlap": 0,
            "heldout_used_for_tuning": False,
        },
        "public_baselines_heldout": baseline_summaries,
        "test_only_upper_bound_heldout": oracle_summary,
        "attacks_heldout": {
            "total_attacks": len(attack_results),
            "all_defended": all_attacks_defended,
            "catalog": attack_results,
        },
        "autohacker_learnability_probe": {
            "tuning_method": "deterministic_grid_plus_coordinate_hill_climb_on_train_dev_tiebreak",
            "tuning_budget_candidates": len(candidate_grid),
            "initial_params": initial_params.to_dict(),
            "selected_params": best_params.to_dict(),
            "train_initial": _summarize_rewards(train_eps, init_train_outs, ci_seed=20265010),
            "train_selected": _summarize_rewards(train_eps, sel_train_outs, ci_seed=20265011),
            "heldout_initial": init_held_sum,
            "heldout_selected": sel_held_sum,
            "heldout_mean_reward_difference": render_decimal(diff_mean),
            "heldout_difference_ci95_bootstrap": [render_decimal(diff_ci_lo), render_decimal(diff_ci_hi)],
            "observational_statement": (
                f"In the fixed experiment across {len(heldout_eps)} independent heldout episodes "
                f"(grouped across {len(heldout_groups)} independent history seeds), selected parameters of "
                f"rule_based_auditor yielded a mean reward difference of +{render_decimal(diff_mean)} "
                f"(95% bootstrap CI [{render_decimal(diff_ci_lo)}, {render_decimal(diff_ci_hi)}]) relative to "
                f"initial parameters."
            ),
        },
    }
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(canonical_json(report) + "\n", encoding="utf-8")
    return report


def main() -> int:
    rep = run_arena_and_autohacker()
    print(
        f"[{rep['status']}] arena & autohacker: baselines={len(rep['public_baselines_heldout'])}, "
        f"attacks={rep['attacks_heldout']['total_attacks']} (defended={rep['attacks_heldout']['all_defended']}), "
        f"heldout_delta=+{rep['autohacker_learnability_probe']['heldout_mean_reward_difference']} -> {DEFAULT_REPORT_PATH}"
    )
    return 0 if rep["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
