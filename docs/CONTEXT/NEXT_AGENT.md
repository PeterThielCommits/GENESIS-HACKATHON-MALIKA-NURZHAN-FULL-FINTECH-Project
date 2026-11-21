# Next Agent Handoff (Release v1.0.0 — Phases 0–17 Complete)

## 1. Current Baseline

- **Completed:** **All Master TZ v3.0.0 Phases 0–17 DONE (100%)**, Phase 9 Risk Remediations (`P-012`/`R-09`, `L4`, `L5`) **DONE**, and Official 2026-11-20 FinTech checks (`C01..A15`) **DONE**.
- **Single-command full verification:**
  ```bash
  make verify && python3 tools/demo_walkthrough.py && python3 tools/freeze_release.py --verify
  ```
- **Expected baseline:**
  - `make lint` → `CLEAN (REQ-ARC-001..007)`
  - `make verify` → `12/12` rubricator gates (`RC-001..RC-012`) `PASS`, `317` unit/integration/security/official tests `PASS`, `7/7` property suites `PASS`, `26/26` mutants killed (`100%`), `7/7` metamorphic transforms `PASS`, `macro_ROC_AUC <= 0.55`, `0` canary leaks across 10 channels, `21` artifacts synthesized in `artifacts/reports/latest/` including self-contained offline `report.html`.
  - `python3 tools/demo_walkthrough.py` → deterministic 5-segment jury walkthrough `PASS` (`master_seed=2025`).
  - `python3 tools/freeze_release.py --verify` → `PASS` (`30` frozen contract/config/spec files verified).

## 2. Key Architectural Invariants (Do Not Break)

1. **Frozen contracts & release manifest (`configs/release_freeze.json`):** Never edit `contracts/*.schema.json` or frozen `configs/` without a formal CR (`docs/CR/`) and `python3 tools/freeze_release.py --write`.
2. **Strict AST import boundaries (`tools/check_import_boundaries.py`):**
   - `seal/`, `harness/`, `env/`, `verifier/`, and `nlp/` import ONLY `contracts` (or stdlib for `nlp/`) + Python 3.11 stdlib.
   - `verifier/` imports neither `gen/` nor `nlp/` (`REQ-NLP-005`).
3. **Gitignore discipline:** Never stage `episodes/*/*/sealed/` or `artifacts/reports/latest/*.json`. Every test and CLI regenerates episodes deterministically in temporary workspaces when gitignored `sealed/` directories are absent.
4. **Preserve Official 2026-11-20 compatibility:** Keep `harness/isolated_runner.py`, `judge_adapter.py`, `adapter/official_env.py`, and `scoring/official_scorer.py` green.
