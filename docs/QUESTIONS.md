# Questions Log (Master TZ v3.0.0 — Resolved against 2026-11-20 Official Spec)

All previously open protocol/rubric questions (`Q-001..Q-014`) were resolved
upon publication of the official Genesis FinTech check definitions on
2026-11-20 (`spec/official_fintech_checks_2026-11-20.md`).

| ID | Topic | Resolution (2026-11-20 Spec) | Implementation | Status |
|---|---|---|---|---|
| Q-001 | Official submission packaging & container | Offline Docker container, single verification command, non-root, no new mandatory base image | `Dockerfile`, `Makefile` (`make verify`, `make docker-check`) | RESOLVED |
| Q-002 | Required adapter entrypoints | `judge_adapter.py` exposing `generate_episode`, `make_env`, `score_episode` | `judge_adapter.py` | RESOLVED |
| Q-003 | Action envelope & names | `{"name": ..., "args": ...}` with `list_records`, `get_record`, `get_document`, `calculator`, `submit` | `adapter/official_env.py` | RESOLVED |
| Q-004 | Canonical table names & cursor pagination | `ledger`, `invoices`, `payments`, `fx`; `cursor=null` page 1, `limit<=50`, repeatable cursors | `adapter/official_env.py`, `env/cursors.py` | RESOLVED |
| Q-005 | Official reward formula & clean-book rule | `clip([-1,1], 2*F1 - 1 - 0.2*inspection_steps/100)`; empty truth + empty findings -> `P=0, R=0, F1=1` | `scoring/official_scorer.py` | RESOLVED |
| Q-006 | Submit budget & step counting | `submit` counts in 100-action cap (99+submit=100 accepted), NOT in `inspection_steps`; errored steps count in `inspection_steps` | `adapter/official_env.py` | RESOLVED |
| Q-007 | Pre-dedup structural limits & invalid return | Max 30 findings, max 10 `evidence_ids` pre-dedup (M05), max 1000 Unicode code points `explanation`; invalid -> `return=-1`, other metrics `null` | `scoring/official_scorer.py`, `adapter/official_env.py` | RESOLVED |
| Q-008 | Matcher tie-breaking & evidence reachability | Max-cardinality bipartite matching; sort `issue_id` by Unicode code points, pick lex-smallest `(issue_id, finding_idx)`; absent `evidence_id` -> FP (M04) | `scoring/official_scorer.py` | RESOLVED |
| Q-009 | Default amount tolerance | `tau = 0` (`abs(claimed - expected) <= tau`), configurable per truth fixture (M07/M08) | `scoring/official_scorer.py` | RESOLVED |
| Q-010 | Closed vs. train mode reward | `closed`: numeric `0` on every step including terminal; `train`: terminal reward returned | `adapter/official_env.py`, `judge_adapter.py` | RESOLVED |
| Q-011 | 20 closed scenarios D01..D20 & 2 interactions | 5 clean, 3 dup, 3 missing/partial alloc, 2 FX, 2 cutoff, 3 Interaction #1, 2 Interaction #2 | `gen/pipeline.py::official_d20_recipes` | RESOLVED |
| Q-012 | 20 paired invariance checks P01..P20 | 5 row perm, 5 bijective ID remap, 10 both via `episode_dir`; preserve row order, arbitrary IDs, FX semantic key | `adapter/official_env.py`, `metamorphic/paired_transform.py` | RESOLVED |
| Q-013 | 4 baseline policies & process isolation | `random`, `simple_reconciliation`, `mass_flagging` in OS subprocess + judge-side `oracle` | `arena/policies/`, `judge/oracle_policy.py`, `harness/isolated_runner.py` | RESOLVED |
| Q-014 | Trajectories, failure analysis, limitations | `artifacts/trajectories/trajectories.jsonl` (80 runs, zero obs leaks), measured failure report, honest limitations | `tools/run_official_eval.py`, `docs/FAILURE_ANALYSIS.md`, `docs/LIMITATIONS.md` | RESOLVED |
