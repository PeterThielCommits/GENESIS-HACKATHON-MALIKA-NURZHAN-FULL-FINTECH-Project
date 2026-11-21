# TwinLedger — Status (evidence-linked, not subjective %)

| Gate | Status | Evidence |
|---|---|---|
| Phase 0 Discovery | PARTIAL (external official TZ/rubric unpublished) | `docs/DECISIONS.md` D-00-01, `docs/QUESTIONS.md` (`Q-003..Q-006`) |
| Phase 1 Foundation + freeze | DONE | `docs/PHASE_REPORTS/PHASE-01.md`, `make verify` PASS |
| Phase 2 Money/time/IDs/invariants | DONE (local gate PASS) | `docs/PHASE_REPORTS/PHASE-02.md` |
| Phase 3 Clean generator | DONE (integrated on frozen v1.0.0) | `gen/core/{rng,clean_twin}.py`, `gen/distractors/catalog.py`, `tests/generator/test_pipeline_e2e.py` |
| Phase 4 Operators + diff truth | DONE (integrated on frozen v1.0.0) | `gen/errors/operators.py`, `gen/truth.py`, `gen/serialize.py`, `gen/pipeline.py`, `tests/generator/test_pipeline_e2e.py` |
| Phase 5 Env reset/step + calc + JSONL | DONE (provisional adapter pending Q-003..Q-006) | `env/*.py`, `adapter/organizer.py`, `tests/env/test_environment.py`, `CR-06-01` RESOLVED |
| Phase 6 Matcher + reward | DONE (provisional rubric per EXIT GATE 6; P1..P5 PASS) | `docs/PHASE_REPORTS/PHASE-06.md`, `PHASE-06-reward-matrix.json`, `make verify` PASS |
| Phase 7 FX + cutoff | DONE (all 4 types integrated end-to-end) | `gen/errors/{fx_cutoff,operators}.py`, `tests/generator/{test_phase07,test_pipeline_e2e}.py` |
| Phase 8 Verifier + ProofGraph | DONE (EXIT GATE 8 PASS: 10/10 generated episodes verified) | `docs/PHASE_REPORTS/PHASE-08.md`, `PHASE-08.json`, `episodes/{dev,train}/verification_summary.json`, `docs/INDEPENDENCE.md` |
| Phase 9 Processes + seal + receipts | READY TO START | All upstream Phases 1–8 gates closed |
| Phase 10 NLP layer | NOT STARTED | — |
| Phase 11 Injection track | NOT STARTED | — |
| Phase 12 Arena + shortcut audit | NOT STARTED | — |
| Phase 13 Metamorphic/mutation | NOT STARTED | — |
| Phase 14 Judge kit + report | PARTIAL (verify CLI + report index) | `judge/verify.py`, `judge/report.py` |
| Phase 15 Docs + demo | PARTIAL (Phase 1–8 docs) | `docs/` |
| Phase 16 Release candidate | NOT STARTED | — |
| Phase 17 Evidence freeze | NOT STARTED | — |

Test statuses: PASS = run and succeeded; FAIL = run and failed;
SKIPPED = intentionally not run (reason recorded); BLOCKED = could not
run; FLAKY = unstable. Never mark unverified work DONE.

Latest verified checks (2026-11-21): make lint PASS (scan CLEAN),
python3 tools/make_dataset.py --split all PASS (10/10 verified,
release_blocked=False), make test PASS (214), make test-property PASS (3),
make verify PASS (RC-001..003), make report PASS; make docker-check NOT RUN
(no Docker in session sandbox); pytest/hypothesis/jsonschema SKIPPED
(optional extras absent).
