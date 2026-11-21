# Project Status Matrix (Release v1.0.0)

| Phase / Track | Title | Status | Gate / Primary Evidence |
| --- | --- | --- | --- |
| Phase 0–1 | Contracts, Schemas & Architecture Boundaries | DONE | Frozen v1.0.0 schemas, `tools/check_import_boundaries.py`, `docs/PHASE_REPORTS/PHASE-01.md` |
| Phase 2 | Canonical JSON, Money, Decimal, Time & ID Primitives | DONE | `core/money.py`, `core/time_rules.py`, `core/ids.py`, `docs/PHASE_REPORTS/PHASE-02.md` |
| Phase 3 | Clean Twin Accounting Generator & 16 Distractors | DONE | `gen/core/clean_twin.py`, `gen/distractors/`, `invariants/checks.py` |
| Phase 4 | Mutation Operators (Duplicate & Partial) & Truth Diff | DONE | `gen/errors/operators.py`, `gen/truth.py`, `gen/serialize.py` |
| Phase 5 | Public-Only Interactive Environment & Safe Calc | DONE | `env/environment.py`, `env/calc.py`, `env/cursors.py`, `env/jsonl_server.py` |
| Phase 6 | Optimal Matcher, Rational Reward & Diagnostics | DONE | `scoring/matcher.py`, `scoring/reward.py`, `scoring/diagnostics.py`, `docs/PHASE_REPORTS/PHASE-06.md` |
| Phase 7 | FX Rate Mismatch & Period Cutoff Operators | DONE | `gen/errors/fx_cutoff.py`, `docs/PHASE_REPORTS/PHASE-07.md` |
| Phase 8 | Independent Verifier, ProofGraph & Release Gate | DONE | `verifier/`, `scoring/crosscheck.py`, `docs/PHASE_REPORTS/PHASE-08.md` |
| Phase 9 | Kernel-Isolated Sealed Evaluation, CSPRNG Rekey & Receipts | DONE | `harness/ns_launcher.py`, `harness/sandbox.py`, `seal/`, `docs/PHASE_REPORTS/PHASE-09.md` |
| Phase 10 | Multilingual (`ru`/`kk`/`en`) Text, NLP & Evidence Hierarchy | DONE | `gen/core/text.py`, `nlp/`, `scoring/explanation_linter.py`, `docs/PHASE_REPORTS/PHASE-10.md` |
| Phase 11 | Prompt-Injection Robustness Twin Evaluation | DONE | `configs/robustness/default.json`, `judge/robustness_audit.py`, `docs/PHASE_REPORTS/PHASE-11.md` |
| Phase 12 | Arena (8 Baselines, 22 Attacks), AutoHacker & Shortcut/Canary Audits | DONE | `arena/`, `judge/shortcut_audit.py`, `judge/canary_fuzzer.py`, `docs/PHASE_REPORTS/PHASE-12.md` |
| Phase 13 | Property, Metamorphic (`M-01..M-07`), RNG & 26-Mutant Suites | DONE | `metamorphic/suite.py`, `judge/mutation_suite.py`, `docs/PHASE_REPORTS/PHASE-13.md` |
| Phase 14 | 12-Gate Judge Kit & Self-Contained Offline HTML Report | DONE | `judge/verify.py`, `judge/report.py`, `judge/performance_and_deps.py`, `docs/PHASE_REPORTS/PHASE-14.md` |
| Phase 15 | Complete Documentation & 3-Minute Reproducible Jury Demo | DONE | `tools/demo_walkthrough.py`, `README.md`, `docs/*`, `docs/PHASE_REPORTS/PHASE-15.md` |
| Phase 16 | Hardened Offline Docker, Compose & CI Gate Verification | DONE | `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`, `docs/PHASE_REPORTS/PHASE-16.md` |
| Phase 17 | Post-Release Cryptographic Evidence Freeze | DONE | `tools/freeze_release.py`, `configs/release_freeze.json`, `docs/PHASE_REPORTS/PHASE-17.md` |
| Official 2026-11-20 | FinTech Checks (`C01..C20`, `D01..D20`, `Block 3`, `P01..P20`, `Baselines`) | DONE | `judge_adapter.py`, `adapter/official_env.py`, `scoring/official_scorer.py`, `tests/official/` |
