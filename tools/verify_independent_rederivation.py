#!/usr/bin/env python3
"""Independent re-derivation harness (organisational zero-common-mode evidence).

Runs the *second*, from-scratch implementation in ``independent_verifier/``
against every publicly committed episode (dev + train) and against the 20
official D01..D20 scenarios re-built deterministically from the public recipe
matrix. Writes a machine-readable evidence artifact to ``docs/EVIDENCE/``.

This script is an experiment harness, NOT part of the verifier: it may import
the generator to materialise official episodes, exactly like
``tests/official/test_block2_episodes.py``. The verifier implementation under
test (``independent_verifier/``) never imports the generator; the import
boundary scanner enforces that.

Honesty note: both implementations were authored in one AI-agent-assisted
session. Agreement is *technical* zero-common-mode evidence (spec-only
re-derivation), not evidence of human organisational separation — see
``docs/QUESTIONS.md`` Q-ORG-01 (stays OPEN).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from contracts.models import TruthFinding  # noqa: E402
from scoring.crosscheck import crosscheck  # noqa: E402
from gen.pipeline import build_episode, official_d20_recipes  # noqa: E402

from independent_verifier.runner import compare_to_committed, run_episode  # noqa: E402

ON_DISK_EPISODES = [
    *(Path("episodes/dev") / d for d in sorted(p.name for p in (REPO_ROOT / "episodes" / "dev").iterdir() if p.is_dir())),
    *(Path("episodes/train") / d for d in sorted(p.name for p in (REPO_ROOT / "episodes" / "train").iterdir() if p.is_dir())),
]


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def _dev_train_results() -> list[dict]:
    out = []
    for ep_dir in ON_DISK_EPISODES:
        public = REPO_ROOT / ep_dir / "public"
        committed = REPO_ROOT / ep_dir / "verifier_report.json"
        if not public.is_dir() or not committed.is_file():
            continue
        result = run_episode(public)
        cmp = compare_to_committed(result.report, committed)
        out.append(
            {
                "episode": ep_dir.as_posix(),
                "public_hash_committed": json.loads(committed.read_text())["episode_public_hash"],
                "public_hash_independent": result.report["episode_public_hash"],
                "public_hash_match": cmp["episode_public_hash_match"],
                "independent_findings": cmp["independent_findings"],
                "committed_findings": cmp["committed_findings"],
                "matching": cmp["matching"],
                "only_independent": cmp["only_independent"],
                "only_committed": cmp["only_committed"],
                "unresolved_ambiguities": result.report["unresolved_ambiguities"],
                "evidence_enumeration_complete": result.report[
                    "deterministic_diagnostics"
                ]["evidence_enumeration_complete"],
                "proof_graph_invariant_errors": result.report["deterministic_diagnostics"][
                    "proof_graph_invariant_errors"
                ],
            }
        )
    return out


def _official_results() -> list[dict]:
    out = []
    recipes = official_d20_recipes(master_seed=2026)
    with tempfile.TemporaryDirectory(prefix="tl_independent_rederive_") as tmp:
        for rec in recipes:
            ge = build_episode(rec, tmp)
            ep_dir = Path(ge.episode_dir)
            result = run_episode(ep_dir / "public")
            truth_raw = json.loads((ep_dir / "sealed" / "truth.json").read_text(encoding="utf-8"))
            truths = [TruthFinding.from_dict(t) for t in truth_raw]
            cc = crosscheck(result.report, truths).to_dict()
            out.append(
                {
                    "episode": ep_dir.name,
                    "expected_anomalies": list(rec.anomalies),
                    "truth_findings": len(truths),
                    "independent_findings": len(result.report["findings"]),
                    "fp": cc["counts"]["fp"],
                    "fn": cc["counts"]["fn"],
                    "f1": cc["metrics"]["f1"]["exact"],
                    "unresolved_ambiguities": result.report["unresolved_ambiguities"],
                    "evidence_enumeration_complete": result.report[
                        "deterministic_diagnostics"
                    ]["evidence_enumeration_complete"],
                    "proof_graph_invariant_errors": result.report[
                        "deterministic_diagnostics"
                    ]["proof_graph_invariant_errors"],
                    "full_deletion_breaks_proof": all(
                        v.get("full_deletion_breaks_proof", False)
                        for v in result.report["deterministic_diagnostics"]["ablation"].values()
                    )
                    if truths
                    else True,
                }
            )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default="docs/EVIDENCE/independent-rederivation-2026-11-22.json",
        help="Path (relative to repo root) for the evidence artifact",
    )
    args = parser.parse_args()

    dev_train = _dev_train_results()
    official = _official_results()

    total_fp = sum(r["fp"] for r in official)
    total_fn = sum(r["fn"] for r in official)
    all_f1 = all(r["f1"] == "1" for r in official)
    dev_train_ok = all(
        r["matching"] == r["committed_findings"] == r["independent_findings"]
        and r["public_hash_match"]
        and not r["only_independent"]
        and not r["only_committed"]
        for r in dev_train
    )
    official_ok = all_f1 and total_fp == 0 and total_fn == 0
    graph_ok = all(
        not r.get("proof_graph_invariant_errors") for r in (*dev_train, *official)
    )
    evidence_ok = all(r.get("evidence_enumeration_complete") for r in (*dev_train, *official))

    artifact = {
        "artifact": "independent-rederivation",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": _git_sha(),
        "independent_verifier_version": "independent-1.0.0",
        "method": (
            "Second, from-scratch specification-only implementation in independent_verifier/ "
            "(money/time via Fraction+zoneinfo, discovery algorithms written from spec/verifier_algorithm.md, "
            "no imports of gen/verifier/scoring/seal/nlp/harness). On-disk committed episodes are compared "
            "signature-wise against their committed verifier_report.json; official D01..D20 are rebuilt via "
            "the public recipe matrix and cross-checked against sealed truth with scoring.crosscheck."
        ),
        "honesty_note": (
            "Both implementations were authored in a single AI-agent-assisted session (Q-ORG-01). "
            "Agreement is technical zero-common-mode re-derivation evidence; it does NOT constitute "
            "organisational independence and does not close Q-ORG-01, which stays OPEN."
        ),
        "summary": {
            "on_disk_episodes": len(dev_train),
            "on_disk_all_signatures_match": dev_train_ok,
            "on_disk_public_hashes_match": all(r["public_hash_match"] for r in dev_train),
            "official_scenarios": len(official),
            "official_total_fp": total_fp,
            "official_total_fn": total_fn,
            "official_all_f1_exact_1": all_f1,
            "proof_graph_invariant_errors_total": sum(
                len(r.get("proof_graph_invariant_errors", [])) for r in (*dev_train, *official)
            ),
            "evidence_enumeration_complete_all": evidence_ok,
            "pass": dev_train_ok and official_ok and graph_ok and evidence_ok,
        },
        "on_disk_episodes": dev_train,
        "official_d01_d20": official,
    }

    out_path = REPO_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact["summary"], indent=2, sort_keys=True))
    print(f"evidence artifact written to {out_path.relative_to(REPO_ROOT)}")
    return 0 if artifact["summary"]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
