# TwinLedger — Status (evidence-linked, not subjective %)

| Gate | Status | Evidence |
|---|---|---|
| Phase 0 Discovery | PARTIAL (official TZ missing) | `docs/DECISIONS.md` D-00-01, `docs/QUESTIONS.md` |
| Phase 1 Foundation + freeze | DONE (Exit Gate 1 PASS; remote branch protection follow-up) | `docs/PHASE_REPORTS/PHASE-01.md`, `make verify-core` + `make verify` PASS |
| Phase 2 Money/time/IDs/invariants | Local gate PASS | `docs/PHASE_REPORTS/PHASE-02.md` |
| Phase 3 Clean generator | NOT STARTED | — |
| Phase 4 Operators + diff truth | NOT STARTED | — |
| Phase 5 Env reset/step | NOT STARTED | — |
| Phase 6 Matcher + reward | NOT STARTED | — |
| Phase 7 FX + cutoff | NOT STARTED | — |
| Phase 8 Verifier + ProofGraph | NOT STARTED | — |
| Phase 9 Processes + seal + receipts | NOT STARTED | — |
| Phase 10 NLP layer | NOT STARTED | — |
| Phase 11 Injection track | NOT STARTED | — |
| Phase 12 Arena + shortcut audit | NOT STARTED | — |
| Phase 13 Metamorphic/mutation | NOT STARTED | — |
| Phase 14 Judge kit + report | PARTIAL (verify CLI skeleton) | `judge/verify.py`, `judge/report.py` |
| Phase 15 Docs + demo | PARTIAL (Phase 1 docs) | `docs/` |
| Phase 16 Release candidate | NOT STARTED | — |
| Phase 17 Evidence freeze | NOT STARTED | — |

Test statuses: PASS = run and succeeded; FAIL = run and failed;
SKIPPED = intentionally not run (reason recorded); BLOCKED = could not
run; FLAKY = unstable. Never mark unverified work DONE.
