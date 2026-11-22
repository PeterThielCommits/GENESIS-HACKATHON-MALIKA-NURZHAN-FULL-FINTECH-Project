# TwinLedger — Changelog

## 1.0.1 — Release-blocking image fix and post-release hardening (2026-11-22)

- **Submission image no longer ships sealed truth (`D-16-02`, release blocker):** `.dockerignore` matched only depth-1 `episodes/*/sealed/`; the real depth-2 layout (`episodes/dev/ep_x/sealed/`) entered the build context. Both depths now excluded; locked by `TestDockerIgnore`. Fixes a `REQ-ARENA-005` violation that affected tag `v1.0.0`.
- **Forensic audit vs the official 2026-11-20 check definitions (PR #24):** BUG-TL-0001 (P0, two competing reward implementations — the jury formula is now the only one), BUG-TL-0002 (P0, cursor HMAC `rsplit` defect stalling C05 at 150/214 rows), BUG-TL-0003 (P1, trailing base64 accepted), BUG-TL-0004 (P1, C05 mirror test never walked the broken `ledger` fixture); mutants MUT-07/08/13 re-armed (26/26 again).
- **Post-release mandatory-target audit (PR #23, `D-16-02`):** all 19 TZ §23.2 `make` targets executed in sequence; fixed `verify-core`-after-`build-episodes` (filesystem walk now honours ignore rules), relocated `official_eval_summary.json` out of the frozen evidence dir, and pinned the published gate count to the frozen rubric map.
- **Documentation gate hardened (PR #25, `D-15-04..D-15-07`):** structural detectors `C-PATHS`, `C-DATADICT`, `C-DEMO`, `C-WORKBENCH-API`, `C-COMMANDS`, `C-REWARD`, `C-COUNTS` (each failure-proven); phantom workbench route implemented; two order-dependency bugs (`D-15-06`); ASCII-locale console crash fixed (`D-15-07`); `docs/INDEPENDENCE.md` honestly marks organisational verifier independence as unevidenced (`Q-ORG-01`, `Q-ORG-02`, OPEN).
- **Package metadata aligned:** `pyproject.toml` `version` 0.1.0 → 1.0.1. Nothing frozen changed; `schema_version` remains `1.0.0`; frozen surface still 30 files, `0747baf0…`.
- **`v1.0.1` tagged and released after re-verification** (clean clone, tarball without `.git`, CI `docker-offline` green on the release commit). See `docs/PHASE_REPORTS/PHASE-16.md` (v1.0.1 addendum) and `docs/RELEASE_NOTES.md`.

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
