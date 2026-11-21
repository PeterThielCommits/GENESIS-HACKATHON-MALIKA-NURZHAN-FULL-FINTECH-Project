#!/usr/bin/env python3
"""Deterministic TwinLedger dataset builder with mandatory Stage-1/Stage-2
independent verification gate (EXIT GATE 8 — REQ-VER-020..022).

Pipeline per episode:
  1. Generate clean twin + apply mutation operators + write public/manifest/sealed (`gen.pipeline`).
  2. Verify manifest schema & every public file SHA-256 (`gen.serialize.verify_episode_manifest`).
  3. Stage-1 public-only discovery (`verifier.discover(ep_dir / "public")`).
  4. Write `<ep_dir>/verifier_report.json` (schema-validated).
  5. Stage-2 post-discovery crosscheck (`scoring.crosscheck.crosscheck`) locking pre-committed
     `report_digest` against `sealed/truth.json`; reject/fail immediately if `release_blocked=True`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from contracts.canonical import canonical_bytes
from contracts.models import TruthFinding
from gen.pipeline import EpisodeRecipe, build_episode, default_dataset_recipes
from gen.serialize import verify_episode_manifest
from scoring.crosscheck import crosscheck
from verifier import VerifierConfig, discover


def build_and_verify_split(
    split: str,
    out_dir: Path,
    *,
    master_seed: int = 2025,
    recipes: list[EpisodeRecipe] | None = None,
) -> dict[str, Any]:
    """Generate and 100%-verify all episodes for one split."""
    out_dir.mkdir(parents=True, exist_ok=True)
    plan = recipes if recipes is not None else default_dataset_recipes(split, master_seed=master_seed)
    records: list[dict[str, Any]] = []

    for recipe in plan:
        gen_ep = build_episode(recipe, out_dir)
        m_errs = verify_episode_manifest(gen_ep.episode_dir)
        if m_errs:
            raise RuntimeError(f"manifest failed for {gen_ep.episode_id}: {m_errs}")

        # Stage-1: strictly public-only independent discovery
        disc = discover(gen_ep.episode_dir / "public", VerifierConfig(run_ablation=True))
        rep_dict = disc.report.to_dict()
        (gen_ep.episode_dir / "verifier_report.json").write_bytes(canonical_bytes(rep_dict) + b"\n")

        # Stage-2: strictly post-discovery crosscheck against sealed truth
        sealed_truth_raw = json.loads(
            (gen_ep.episode_dir / "sealed" / "truth.json").read_text(encoding="utf-8")
        )
        truth_models = [TruthFinding.from_dict(t) for t in sealed_truth_raw]
        distractor_count = int(gen_ep.manifest.get("profile", {}).get("distractor_count", 0))
        cc = crosscheck(
            rep_dict,
            truth_models,
            expected_report_digest=disc.report_digest,
            distractor_count=distractor_count,
        )
        if cc.release_blocked:
            raise RuntimeError(
                f"EXIT GATE 8 REJECTED {gen_ep.episode_id}: {cc.blocking_reasons} "
                f"(tp={cc.tp}, fp={cc.fp}, fn={cc.fn})"
            )

        records.append(
            {
                "episode_id": gen_ep.episode_id,
                "attempts": gen_ep.attempts,
                "episode_public_hash": rep_dict["episode_public_hash"],
                "report_digest": disc.report_digest,
                "crosscheck_hash": cc.crosscheck_hash,
                "release_blocked": cc.release_blocked,
                "precision_exact": str(cc.precision),
                "recall_exact": str(cc.recall),
                "f1_exact": str(cc.f1),
                "evidence_sufficiency_exact": str(cc.evidence_sufficiency_rate),
                "evidence_minimality_exact": str(cc.evidence_minimality_rate),
                "distractor_fp_rate_exact": str(cc.distractor_false_positive_rate),
                "unresolved_ambiguity_count": cc.unresolved_ambiguity_count,
            }
        )

    summary = {
        "schema_version": "1.0.0",
        "split": split,
        "master_seed": master_seed,
        "episode_count": len(records),
        "verified_count": sum(1 for r in records if not r["release_blocked"]),
        "all_verified": all(not r["release_blocked"] for r in records),
        "episodes": records,
    }
    (out_dir / "verification_summary.json").write_bytes(canonical_bytes(summary) + b"\n")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and independently verify TwinLedger episodes")
    parser.add_argument("--split", choices=["dev", "train", "all"], default="all")
    parser.add_argument("--out", default=None, help="Output directory (used when --split is dev or train)")
    parser.add_argument("--seed", type=int, default=2025)
    args = parser.parse_args(argv)

    splits = [("dev", REPO_ROOT / "episodes" / "dev"), ("train", REPO_ROOT / "episodes" / "train")]
    if args.split != "all":
        target = Path(args.out) if args.out else (REPO_ROOT / "episodes" / args.split)
        splits = [(args.split, target)]

    total = 0
    for split, out_dir in splits:
        summary = build_and_verify_split(split, out_dir, master_seed=args.seed)
        total += summary["verified_count"]
        print(
            f"make_dataset[{split}]: {summary['verified_count']}/{summary['episode_count']} "
            f"episodes generated and independently verified -> {out_dir}"
        )
    print(f"make_dataset: ALL {total} episodes verified with release_blocked=False (EXIT GATE 8 PASS)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
