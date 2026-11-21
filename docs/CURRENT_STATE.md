# Current State

- **Active branch:** `arena/3a99279e-genesis-hackathon-malika-nurzh` (PR #11 open against `main` @ `da42d26`).
- **Completed Master TZ phases:** **Phases 0–17 COMPLETE (100%)**.
- **Phase 9 Risk Remediation (`P-012`/`R-09`, `L4`, `L5`):** **COMPLETE**:
  - Linux kernel `user + mount + net` namespace + `seccomp-BPF` sandbox (`harness/ns_launcher.py`, `harness/sandbox.py`, `profile_id = "linux-kernel-ns-seccomp-v1"`, `is_full_os_sandbox = True` on Linux) + hardened offline `Dockerfile` (`UID 10001`, `util-linux`) + `docker-compose.yml` + GitHub Actions `docker-offline` job (`--network=none`).
  - CSPRNG `PRODUCTION_SECRET` salt re-keying (`seal/rekey.py`, `python3 -m seal.cli rekey-production`) + Stage-2 `semantic_truth_verification` (`scoring/scorer_cli.py` running `scoring/crosscheck.py` against `verifier_report.json`).
  - Diagnostic `explanation_consistency` linter (`scoring/explanation_linter.py`) + `verifier_quality` integrated into `scoring/diagnostics.py` and `scoring/scorer_cli.py`.
- **Phases 10–17 Summary:**
  - **Phase 10–11:** `gen/core/text.py` (`ru`/`kk`/`en`/`mixed` under isolated `"text_layer"` & `"injection_layer"` RNG streams), `nlp/` (`normalize.py`, `matching.py`, `hierarchy.py`, `injection_guard.py`), `configs/robustness/default.json`, `judge/robustness_audit.py` (`robustness_report.json`).
  - **Phase 12:** 7 public baselines (`arena/policies/catalog.py`) + separated `oracle_test_only` (`REQ-ARENA-005`), all 22 attacks `AT-01..AT-22` (`arena/attacks/catalog.py`), seed-grouped `TRAIN`/`DEV`/`HELDOUT` AutoHacker with 95% bootstrap CIs (`arena/autohacker.py`), within-table L2 Logistic Regression shortcut auditor (`macro_ROC_AUC = 0.5389 <= 0.55`, `judge/shortcut_audit.py`), and 10-channel canary & API fuzzer (`judge/canary_fuzzer.py`).
  - **Phase 13:** Metamorphic suite `M-01..M-07` (`7/7 PASS`, `metamorphic/suite.py`), 26-mutant scoring suite (`26/26 = 100% killed`, `judge/mutation_suite.py`), RNG isolation (`tests/generator/test_rng_isolation.py`), and interleaved multi-env isolation (`tests/env/test_interleaved_isolation.py`).
  - **Phases 14–17:** 12-gate Judge Kit (`judge/verify.py`, `RC-001..RC-012`), performance & offline dependency auditor (`judge/performance_and_deps.py`, `step p99 = 0.13ms`, `peak RSS = 22MB`), self-contained offline `report.html` (`judge/report.py`), 3-minute deterministic jury demo (`tools/demo_walkthrough.py`), and cryptographic release freeze (`tools/freeze_release.py`, `configs/release_freeze.json`).
- **Active blockers:** None. Ready for clean-clone check, remote CI (`core` + `docker-offline`), and PR #11 merge.
