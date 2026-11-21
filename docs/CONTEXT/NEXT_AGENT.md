# Next Agent Handoff (Phase 10)

## 1. Current Baseline

- **Completed:** Phases 1–9 **DONE** (`EXIT GATE 8` DONE, **`EXIT GATE 9` DONE**) + Official 2026-11-20 FinTech checks (`C01..A15`) GREEN.
- **Quick startup verification (run first):**
  ```bash
  make setup && make lint && make test-property && make replay && make verify && make report
  ```
- **Expected baseline:** `make lint` CLEAN, `295` unit/integration tests PASS, `5` stdlib property tests PASS, `make replay` (`5/5` byte-identical + `P01..P20`) PASS, `make verify` (`RC-001..RC-005`) PASS.

## 2. Key Architectural Invariants (Do Not Break)

1. **Frozen Phase 1 v1.0.0 schemas (`contracts/*.schema.json`):** Do NOT edit without a formal CR (`docs/CR/`).
2. **Strict AST import boundaries (`tools/check_import_boundaries.py`):**
   - `seal/` imports ONLY `contracts` + stdlib.
   - `harness/` imports ONLY `contracts` + stdlib.
   - `env/` imports ONLY `contracts` + stdlib (zero `sealed` path literals).
   - `verifier/` imports ONLY `contracts` + stdlib (zero `gen`/`scoring` imports).
3. **Gitignore discipline:** Never stage `episodes/*/*/sealed/` or `artifacts/reports/latest/*.json`. Tests and replay must work on a fresh clone even when `episodes/*/*/sealed/` is absent (use `gen.pipeline.build_episode` in temp dirs or regenerate deterministically).
4. **Preserve Official 2026-11-20 compatibility:** Keep `harness/isolated_runner.py`, `judge_adapter.py`, `adapter/official_env.py`, and `scoring/official_scorer.py` green.

## 3. Target for Next Session — Phase 10 (`PERTURBATION, METAMORPHIC, ANTI-CHEAT, CANARY`)

- Implement Master TZ §17 / §24 Phase 10 perturbation & metamorphic invariants on top of frozen v1.0.0 episodes and `CLOSED_EVAL` harness.
- Implement explanation-consistency diagnostics (`scoring/diagnostics.py` currently marks `explanation_consistency` as `NOT_AVAILABLE` per `D-06-05`) without letting `explanation` alter official F1/reward unless explicitly gated.
- Expand canary, shortcut-resistance, and adversarial policy probes across all 4 anomaly classes (`DUPLICATE_PAYMENT`, `PARTIAL_PAYMENT_ALLOCATION`, `FX_RATE_MISMATCH`, `PERIOD_CUTOFF`).
- See `docs/PHASE_REPORTS/PHASE-09.md` and `docs/HANDOFF/phase-09-to-10.md` for full Phase 9 details.
