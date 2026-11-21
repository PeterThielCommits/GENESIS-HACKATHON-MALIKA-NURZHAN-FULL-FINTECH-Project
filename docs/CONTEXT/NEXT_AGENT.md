# Next Agent Handoff (Release v1.0.0 — Phases 0–17 Complete + Phase 10 Full Re-Audit)

## 1. Current Baseline

- **Branch:** `arena/794acafe-genesis-hackathon-malika-nurzh` from `main` @ `7f47638` (PR #11 merge). Phase 10 quality audit (`D-10-02`) complete on this branch.
- **Completed:** **All Master TZ v3.0.0 Phases 0–17 DONE (100%)**, Phase 9 Risk Remediations (`P-012`/`R-09`, `L4`, `L5`) **DONE**, Official 2026-11-20 FinTech checks **DONE**, and **Phase 10 re-executed end-to-end (tasks 10.1–10.6 + EXIT GATE 10 verified, `docs/PHASE_REPORTS/PHASE-10.md`)**.
- **Single-command full verification:**
  ```bash
  make verify && python3 tools/demo_walkthrough.py && python3 tools/freeze_release.py --verify
  ```
- **Expected baseline:**
  - `make lint` → `CLEAN (REQ-ARC-001..007)`
  - `python3 -m unittest discover -s tests -t .` → **343 tests OK**
  - `make verify` → `12/12` rubricator gates (`RC-001..RC-012`) `PASS`, `26/26` mutants killed, `7/7` metamorphic transforms, `macro_ROC_AUC <= 0.55`, `0` canary leaks.
  - `python3 tools/explanation_report.py --demo --output artifacts/reports/latest/explanation_consistency_report.json` → Phase 10 deliverable artifact (diagnostic-only).

## 2. Key Architectural Invariants (Do Not Break)

1. **Frozen contracts & release manifest (`configs/release_freeze.json`):** Never edit `contracts/*.schema.json` or frozen `configs/` without a formal CR (`docs/CR/`) and `python3 tools/freeze_release.py --write`.
2. **Strict AST import boundaries (`tools/check_import_boundaries.py`):**
   - `core/`, `invariants/`, `env/`, `gen/`, `seal/`, `harness/`, `verifier/` import **zero** `nlp` modules; `verifier/` additionally imports neither `gen/` (`REQ-VER-002`).
   - `nlp/` imports ONLY `contracts` + stdlib.
   - `scoring/` may import only `nlp.hierarchy` from `nlp` (strict TZ §17.3 rule module) — never `nlp.matching`/`nlp.normalize` fuzzy helpers (Phase 10 EXIT GATE, `D-10-02`).
   - `nlp/__init__.py` is a lazy PEP-562 facade: keep it lazy so importing `nlp.hierarchy` never loads the fuzzy helpers.
3. **Gitignore discipline:** Never stage `episodes/*/*/sealed/` or `artifacts/reports/latest/*.json`. Tests regenerate episodes deterministically in temporary workspaces.
4. **Preserve Official 2026-11-20 compatibility:** Keep `harness/isolated_runner.py`, `judge_adapter.py`, `adapter/official_env.py`, and `scoring/official_scorer.py` green.
5. **Diagnostics never feed reward (TZ §15.9):** `explanation_consistency` and `evidence_hierarchy` blocks are diagnostic-only (`D-06-05`, `D-10-02`).

## 3. What to Read First

1. `docs/PHASE_REPORTS/PHASE-10.md` + `docs/AGENT_REPORTS/2026-11-21/arena-phase-10-audit.md` (latest session).
2. `docs/DECISIONS.md` (`D-10-02` and predecessors).
3. `docs/CURRENT_STATE.md` (three priority next actions).

## 4. Exact Next Action

Run `make verify` on this branch (or a clean clone), then publish/merge the Phase 10 audit PR. If any gate regresses, bisect from `7f47638`; the audit session touched only `gen/core/text.py` (meta keys), `nlp/*`, `scoring/{scorer_cli,diagnostics}.py`, `tools/{check_import_boundaries,explanation_report}.py` and tests/docs. Do not change frozen schemas without a CR.
