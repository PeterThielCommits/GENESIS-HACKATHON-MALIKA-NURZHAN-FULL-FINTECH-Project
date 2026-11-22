#!/usr/bin/env python3
"""Reproducible 3-Minute Jury Demo Walkthrough CLI (Phase 15 — TZ §26.15).

Executes the six scripted segments of Master TZ §26.15 deterministically on a
locked seed (``master_seed=2025``). The segment table is not duplicated in the
prose: :data:`SEGMENTS` below is the single source, printed by :func:`main` and
compared against ``docs/DEMO.md`` by ``tools/verify_doc_claims.py::C-DEMO``.
That check exists because the narration previously claimed "five segments"
while the program printed six, with a clock that disagreed by up to 5 seconds.

Never reveals ``sealed/truth.json`` prior to post-finalize commit-reveal verification.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

#: ``(number, start, end, title)`` — printed by the demo and asserted against
#: ``docs/DEMO.md`` by the ``C-DEMO`` documentation gate. Editing the demo means
#: editing this tuple; the documentation then either matches or the gate fails.
SEGMENTS: tuple[tuple[str, str, str, str], ...] = (
    ("1", "0:00", "0:25", "Architecture & Contract Overview"),
    ("2", "0:25", "0:55", "Counterfactual Twins (Clean Distractor Twin vs Mutated Twin)"),
    ("3", "0:55", "1:25", "Independent Public-Only Verifier & ProofGraph"),
    ("4", "1:25", "1:55", "CLOSED_EVAL 3-Process Isolation, Commit-Reveal & Fresh Replay"),
    ("5", "1:55", "2:30", "Reward Stress Test (Official Formula, Internal Step Penalty)"),
    ("6", "2:30", "3:00", "Honest Limitations & Scope"),
)

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from arena.attacks.catalog import run_attack_policy
from arena.policies.catalog import run_baseline_policy
from contracts.models import Finding, TruthFinding
from contracts.version import PROTOCOL_VERSION
from env.environment import EnvConfig, TwinLedgerEnv
from gen.pipeline import default_dataset_recipes
from harness.replay import replay_episode
from harness.runner import run_closed_eval_episode
from scoring.reward import compute_reward, render_decimal
from tools.make_dataset import build_and_verify_split
from verifier import discover


def _segment(number: str) -> str:
    """Render the printed header for one segment from the single ``SEGMENTS`` table."""
    for num, start, end, title in SEGMENTS:
        if num == number:
            return f"\n[{start}\u2013{end}] {num}. {title}"
    raise KeyError(f"no segment {number!r} in SEGMENTS")


def main() -> int:
    print("=" * 76)
    print("TwinLedger v3.0 — Deterministic 3-Minute Jury Walkthrough (seed=2025)")
    print("=" * 76)

    print(_segment("1"))
    print("  - Pure Python 3.11 stdlib core | Offline | Exact integer minor-unit arithmetic")
    print("  - Frozen v1.0.0 JSON contracts | Strict Zone 1/2/3 AST import boundaries")

    with tempfile.TemporaryDirectory(prefix="tl_jury_demo_") as td:
        root = Path(td)
        recipes = default_dataset_recipes("dev", master_seed=2025)[:2]
        build_and_verify_split("dev", root / "eps", recipes=recipes)
        clean_ep = root / "eps" / "ep_dev_001_clean_distractors"
        mut_ep = root / "eps" / "ep_dev_002_duplicate"

        print(_segment("2"))
        # Counted from the manifest, never typed by hand: the narration said
        # "13 distractors" while the recipe generated 13 of the 16 catalogued
        # families, which is a true statement about that episode and a false
        # one about the catalogue. Deriving it keeps the sentence honest.
        clean_manifest = json.loads((clean_ep / "manifest.json").read_text(encoding="utf-8"))
        distractor_count = int(clean_manifest.get("profile", {}).get("distractor_count", 0))
        print(
            f"  - Clean Twin   : {clean_ep.name} "
            f"({distractor_count} clean accounting distractors, 0 anomalies)"
        )
        print(f"  - Mutated Twin : {mut_ep.name} (injected DUPLICATE_PAYMENT; truth sealed pre-run)")

        print(_segment("3"))
        d_clean = discover(clean_ep / "public")
        d_mut = discover(mut_ep / "public")
        print(f"  - Clean Twin Stage-1 Verifier findings   : {len(d_clean.report.findings)} (distractors excluded)")
        print(f"  - Mutated Twin Stage-1 Verifier findings : {len(d_mut.report.findings)} (digest={d_mut.report_digest[:16]}...)")
        if d_mut.report.findings:
            f0 = d_mut.report.findings[0]
            print(f"    Certificate: type={f0.type}, affected={list(f0.affected_ids)}, evidence={list(f0.evidence_sets[0])}")

        print(_segment("4"))
        run_res = run_closed_eval_episode(
            episode_dir=mut_ep,
            policy_argv=[sys.executable, "-m", "harness.reference_policies", "--policy", "rule_auditor_v1"],
            policy_id="rule_auditor_v1",
            artifacts_dir=root / "art",
        )
        rep_res = replay_episode(
            episode_dir=mut_ep,
            trajectory_path=run_res.trajectory_path,
            submission_path=run_res.submission_path,
            receipt_path=run_res.receipt_path,
            score_report_path=run_res.score_report_path,
        )
        print(f"  - Security profile     : {run_res.security_profile.profile_id} (full_os_sandbox={run_res.security_profile.is_full_os_sandbox})")
        print(f"  - Lifecycle ordering   : env_exited <= scorer_started = {run_res.lifecycle.strictly_ordered}")
        print(f"  - Commit-reveal & sem  : commit_verified={run_res.score_report['commit_reveal']['verified']}, semantic={run_res.score_report['semantic_truth_verification']['status']}")
        print(f"  - Fresh-process replay : matched={rep_res.matched}, head={rep_res.replayed_head[:16]}...")

        print(_segment("5"))
        truths = [TruthFinding.from_dict(t) for t in json.loads((mut_ep / "sealed" / "truth.json").read_text(encoding="utf-8"))]
        for label, kind, rid in (
            ("honest budget_aware", "baseline", "budget_aware"),
            ("AT-01 flag_all", "attack", "AT-01"),
            ("AT-04 duplicate_spam", "attack", "AT-04"),
            ("AT-09 silent", "attack", "AT-09"),
        ):
            env = TwinLedgerEnv(EnvConfig(mode="CLOSED_EVAL"))
            obs = env.reset(mut_ep / "public", cursor_seed=2025)
            seq = 0

            def _step(t: str, a: dict) -> dict:
                nonlocal seq
                seq += 1
                return env.step({"protocol_version": PROTOCOL_VERSION, "request_id": f"d-{seq}", "action": {"tool": t, "args": a}})

            if kind == "baseline":
                run_baseline_policy(rid, obs, _step, seed=2025)
            else:
                run_attack_policy(rid, obs, _step, seed=2025)
            fs = [Finding.from_dict(x) for x in (env.submitted_findings or [])]
            rb = compute_reward(fs, truths, env.steps_used)
            print(f"  - {label:22s}: F1={render_decimal(rb.f1)} | steps={env.steps_used:2d} | reward={render_decimal(rb.reward)} (TP={rb.tp}, FP={rb.fp}, FN={rb.fn})")

    print(_segment("6"))
    print("  - Internal verification pass rate is NOT an official organiser jury score.")
    print("  - Kernel namespace + seccomp-BPF sandbox requires Linux host or --network=none Docker.")
    print("  - Timing equivalence tests bound practical IPC differences, not microarchitectural side channels.")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
