# Project Status Matrix

| Phase / Track | Title | Status | Gate / Evidence |
| --- | --- | --- | --- |
| Phase 1 | Contracts, Schemas & Architecture Boundaries | DONE | Frozen v1.0.0 schemas (`D-01-01`), `docs/PHASE_REPORTS/PHASE-01.md` |
| Phase 2 | Canonical JSON, Money, Decimal, Time Primitives | DONE | `contracts/canonical.py`, `money.py`, `rounding.py`, `time_utils.py`, `docs/PHASE_REPORTS/PHASE-02.md` |
| Phase 3 | Clean Twin Accounting Generator & 16 Distractors | DONE | `gen/core/`, `gen/distractors/`, `episodes/dev` & `episodes/train` |
| Phase 4 | Mutation Operators (Duplicate & Partial) & Truth Diff | DONE | `gen/errors/operators.py`, `gen/truth.py`, `gen/serialize.py` |
| Phase 5 | Public-Only Interactive Environment & Safe Calc | DONE | `env/environment.py`, `env/calc.py`, `env/cursors.py`, `env/jsonl_server.py` |
| Phase 6 | Matcher, Rational Reward & Diagnostics | DONE | `scoring/matcher.py`, `scoring/reward.py`, `scoring/diagnostics.py`, `docs/PHASE_REPORTS/PHASE-06.md` |
| Phase 7 | FX Rate Mismatch & Period Cutoff Operators | DONE | `gen/errors/fx_cutoff.py`, `docs/PHASE_REPORTS/PHASE-07.md` |
| Phase 8 | Independent Verifier, ProofGraph & Release Gate | DONE | **EXIT GATE 8 DONE** (`10/10` episodes verified), `docs/PHASE_REPORTS/PHASE-08.md` |
| Official 2026-11-20 | FinTech Checks (`C01..C20`, `S01..S25`, `Q01..Q20`, `P01..P20`, `A01..A15`) | DONE | `judge_adapter.py`, `adapter/official_env.py`, `scoring/official_scorer.py`, `tests/official/` |
| **Phase 9** | **Processes, Sealed Evaluation & Receipts** | **DONE** | **EXIT GATE 9 DONE** (`seal/`, `harness/`, `scoring/scorer_cli.py`, `docs/PHASE_REPORTS/PHASE-09.md`) |
| Phase 10 | Perturbation, Metamorphic, Anti-Cheat & Canary | TODO | Partial foundation in `tests/official/test_block4_paired.py` & `test_block5_anticheat.py` |
| Phase 11 | Baseline Agents & Benchmark Analytics | TODO | Partial baselines in `arena/policies/` & `harness/reference_policies.py` |
| Phase 12 | Judge Packaging, Reports & Final Rubric Matrix | TODO | `judge/verify.py` (`RC-001..005`), `judge/report.py` |
| Phase 13 | Docker Hardening, Hypothesis Extras & Final Release | TODO | `Dockerfile`, `docker-compose.yml` (`make docker-check` pending Docker host) |
