# Rubric Traceability (Genesis FinTech 2026-11-20)

Authoritative rubric weights (100 points total) from `spec/official_fintech_checks_2026-11-20.md`:

| Block | Weight | Scope | Implementation | Automated Verification |
|---|---:|---|---|---|
| Block 1 | 25 pts | 20 Contract Tests (`C01..C20`) | `judge_adapter.py`, `adapter/official_env.py`, `env/calc.py`, `env/cursors.py`, `harness/isolated_runner.py` | `tests/official/test_block1_contracts.py` (20/20 PASS) |
| Block 2 | 25 pts | 20 Closed Episodes (`D01..D20`) | `gen/pipeline.py`, `gen/core/clean_twin.py`, `gen/errors/operators.py`, `verifier/discover.py` | `tests/official/test_block2_episodes.py` (20/20 verifier F1=1.0 PASS) |
| Block 3 | 25 pts | 20 Matcher/Reward Vectors + `M01..M12` | `scoring/official_scorer.py` | `tests/official/test_block3_scorer.py` (32/32 PASS within `1e-9`) |
| Block 4 | 15 pts | 20 Paired Order/ID Invariance Checks (`P01..P20`) | `adapter/official_env.py`, `scoring/official_scorer.py`, `metamorphic/paired_transform.py`, `judge/oracle_policy.py` | `tests/official/test_block4_paired.py` (20/20 PASS) |
| Block 5 | 10 pts | Engineering Anchors (Single cmd, Pinned config, Trajectories, Measured Failures, Honest Limits) + 4 Baselines | `Makefile`, `Dockerfile` (base image pinned by digest), `configs/official_eval_manifest.json`, `arena/policies/`, `tools/run_official_eval.py`, `artifacts/trajectories/trajectories.jsonl`, `docs/FAILURE_ANALYSIS.md`, `docs/LIMITATIONS.md` | `tests/official/test_block5_baselines.py` + `make verify` (PASS) |

Note: Internal verification runs report `official_score_claimed: false` in `artifacts/reports/latest/verify_summary.json`; final scoring is always executed by the organizers' judge harness.
