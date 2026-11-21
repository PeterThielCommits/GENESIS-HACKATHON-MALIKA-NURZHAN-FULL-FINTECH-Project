# TwinLedger — Changelog

## 1.0.0 — Full Master TZ v3.0 & Phase 9 Risk Remediation Release (2026-11-21)

- **Kernel Sandbox & Container Hardening (`P-012` / `R-09`):** Added stdlib Linux `unshare` + `MS_REC|MS_PRIVATE` `tmpfs` path masking + `PR_SET_NO_NEW_PRIVS` + `x86_64`/`aarch64` `seccomp-BPF` syscall filter (`harness/ns_launcher.py`, `harness/sandbox.py`), non-root `UID 10001` `Dockerfile`, offline `docker-compose.yml`, and CI `docker-offline` job (`--network=none`).
- **CSPRNG Production Sealing & Semantic Truth Attestation (`L4`):** Added `seal/rekey.py` (`python3 -m seal.cli rekey-production`) and Stage-2 `scoring/crosscheck.py` `semantic_truth_verification` inside `scoring/scorer_cli.py`.
- **Multilingual (`ru`/`kk`/`en`) & NLP Layer (Phase 10 + `L5`):** Added isolated `"text_layer"` generator (`gen/core/text.py`), `nlp/` (`normalize.py`, `matching.py`, 4-tier `hierarchy.py`, `injection_guard.py`), and diagnostic `scoring/explanation_linter.py`.
- **Prompt-Injection Robustness Track (Phase 11):** Added `configs/robustness/default.json` and paired Clean vs Injected twin evaluator (`judge/robustness_audit.py`).
- **Arena, 22 Attacks, AutoHacker, Shortcut & Canary Audits (Phase 12):** Added 7 public baselines (`arena/policies/catalog.py`) + separated `oracle_test_only`, 22 red-team attacks `AT-01..AT-22` (`arena/attacks/catalog.py`), seed-grouped `TRAIN`/`DEV`/`HELDOUT` AutoHacker with 95% bootstrap CIs (`arena/autohacker.py`), within-table L2 Logistic Regression shortcut auditor (`macro_ROC_AUC <= 0.55`, `judge/shortcut_audit.py`), and 10-channel canary & API fuzzer (`judge/canary_fuzzer.py`).
- **Metamorphic, RNG Isolation, Interleaved Env & 26-Mutant Suites (Phase 13):** Added `metamorphic/suite.py` (`M-01..M-07`), `judge/mutation_suite.py` (`26/26` mutants killed), `tests/generator/test_rng_isolation.py`, and `tests/env/test_interleaved_isolation.py`.
- **Judge Kit, Offline HTML Report, Jury Demo & Release Freeze (Phases 14–17):** Upgraded `judge/verify.py` (`RC-001..RC-012`), `judge/performance_and_deps.py`, `judge/report.py` (offline `report.html`), `tools/demo_walkthrough.py`, and `tools/freeze_release.py` (`configs/release_freeze.json`).

## 0.9.0 — Phases 2–9 & Official 2026-11-20 Compliance (2026-11-21)

- Exact integer/rational money, timezone, anti-shortcut ID, and 15-invariant primitives (`core/`, `invariants/`).
- Clean Twin accounting generator, 16 clean distractors, and 4 anomaly operators (`gen/`).
- Independent public-only verifier with ProofGraph DAG and minimal-evidence ablation (`verifier/`, `scoring/crosscheck.py`).
- Official Genesis FinTech 2026-11-20 adapter & mirror suite (`judge_adapter.py`, `tests/official/`).
- 3-process `CLOSED_EVAL` harness, commit-reveal, hashchain, size-bound Merkle receipts, and fresh-process replay (`seal/`, `harness/`).

## 0.1.0 — Phase 1 (2026-11-20)

- Repository skeleton per Master TZ 6; frozen v1.0.0 JSON schemas; canonical JSON; AST import-boundary scanner.
