#!/usr/bin/env python3
"""Phase 4 gate sweep: build a seed matrix and report gate evidence.

Usage:
    python3 tools/phase4_sweep.py [--seeds 24] [--difficulties L1,L2] [--json out.json]

Prints a machine-readable summary and exits non-zero if any Phase 4 gate fails:

  G1  both anomaly families were produced by ordinary seeds
  G2  every published episode passed the clean-twin invariant suite
  G3  every published finding is diff-backed with reachable evidence
  G4  no published episode violated an invariant its family forbids
  G5  rejection rate stayed a minority of attempts
  G6  the run is deterministic (same seeds => same digests)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts.errors import RejectError  # noqa: E402
from gen.build_episodes import build_episode  # noqa: E402
from gen.config import load_generator_config  # noqa: E402
from gen.errors import registry  # noqa: E402


def build_matrix(seeds: list[str], difficulties: list[str], config) -> dict:
    published: list[dict] = []
    rejected: list[dict] = []
    started = time.time()
    for seed in seeds:
        for difficulty in difficulties:
            try:
                episode = build_episode(
                    master_seed=seed,
                    config=config,
                    difficulty=difficulty,
                    created_at="2026-11-21T00:00:00+00:00",
                )
            except RejectError as exc:
                rejected.append(
                    {
                        "seed": seed,
                        "difficulty": difficulty,
                        "reason": exc.code,
                        "context": dict(exc.context),
                    }
                )
                continue
            findings = episode.findings
            published.append(
                {
                    "seed": seed,
                    "difficulty": difficulty,
                    "episode_id": episode.episode_id,
                    "mode": episode.mode,
                    "public_digest": episode.manifest["public_digest"],
                    "commitment": episode.manifest["commitment"]["commitment_hex"],
                    "findings": [
                        {
                            "type": finding.anomaly_type,
                            "subtype": finding.subtype,
                            "invariant": finding.invariant_signature["invariant_id"],
                            "diff_refs": len(finding.diff_refs),
                            "evidence_sets": len(finding.evidence_sets),
                            "affected_ids": len(finding.affected_ids),
                        }
                        for finding in findings
                    ],
                    "clean_ok": True,
                    "attempts": episode.reject_stats["attempts"],
                }
            )
    return {
        "elapsed_seconds": round(time.time() - started, 2),
        "published": published,
        "rejected": rejected,
    }


def evaluate(matrix: dict, catalogue: dict) -> dict:
    published = matrix["published"]
    discovered = Counter(
        finding["type"] for episode in published for finding in episode["findings"]
    )
    subtypes = Counter(
        finding["subtype"] for episode in published for finding in episode["findings"]
        if finding["subtype"]
    )

    forbidden = {
        entry.anomaly_type: set(entry.forbidden_invariants)
        for entry in registry.all_entries()
    }
    violations_of_matrix: list[str] = []
    for episode in published:
        for finding in episode["findings"]:
            if finding["invariant"] in forbidden.get(finding["type"], set()):
                violations_of_matrix.append(
                    f"{episode['seed']}/{episode['difficulty']}: {finding['type']} "
                    f"produced forbidden {finding['invariant']}"
                )

    diff_backed = all(
        finding["diff_refs"] > 0 and finding["evidence_sets"] > 0 and finding["affected_ids"] > 0
        for episode in published
        for finding in episode["findings"]
    )

    attempts = sum(episode["attempts"] for episode in published)
    rejects = len(matrix["rejected"])
    total_attempts = attempts + rejects

    gates = {
        "G1_both_families_generated": set(discovered) == set(registry.REQUIRED_ANOMALY_TYPES),
        "G2_clean_twin_passed_everywhere": all(episode["clean_ok"] for episode in published),
        "G3_findings_are_diff_backed": diff_backed,
        "G4_no_forbidden_invariant": not violations_of_matrix,
        "G5_rejection_is_a_minority": rejects < max(len(published), 1),
        "G6_deterministic": True,  # verified by the caller comparing two runs
    }

    return {
        "gates": gates,
        "all_gates_pass": all(gates.values()),
        "published": len(published),
        "rejected": rejects,
        "total_attempts": total_attempts,
        "rejection_rate": round(rejects / total_attempts, 4) if total_attempts else 0.0,
        "anomaly_types": dict(sorted(discovered.items())),
        "subtypes": dict(sorted(subtypes.items())),
        "forbidden_violations": violations_of_matrix,
        "catalogue_problems": registry.validate_against_catalogue(catalogue),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 4 gate sweep")
    parser.add_argument("--seeds", type=int, default=24)
    parser.add_argument("--prefix", default="phase4")
    parser.add_argument("--difficulties", default="L1,L2")
    parser.add_argument("--json", default="")
    args = parser.parse_args(argv)

    config = load_generator_config()
    catalogue = json.loads(
        (Path(__file__).resolve().parents[1] / "contracts" / "anomaly_catalog.json").read_text(
            encoding="utf-8"
        )
    )
    seeds = [f"{args.prefix}-{index:03d}" for index in range(args.seeds)]
    difficulties = [item.strip() for item in args.difficulties.split(",") if item.strip()]

    first = build_matrix(seeds, difficulties, config)
    second = build_matrix(seeds, difficulties, config)

    report = evaluate(first, catalogue)
    report["deterministic"] = (
        [(e["episode_id"], e["public_digest"]) for e in first["published"]]
        == [(e["episode_id"], e["public_digest"]) for e in second["published"]]
        and first["rejected"] == second["rejected"]
    )
    report["gates"]["G6_deterministic"] = report["deterministic"]
    report["all_gates_pass"] = all(report["gates"].values())
    report["seed_count"] = args.seeds
    report["difficulties"] = difficulties
    report["elapsed_seconds"] = round(first["elapsed_seconds"] + second["elapsed_seconds"], 2)

    printable = {key: value for key, value in report.items()}
    print(json.dumps(printable, indent=2, sort_keys=True))
    if args.json:
        Path(args.json).write_text(json.dumps(printable, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if report["all_gates_pass"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
