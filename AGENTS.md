# AGENTS.md — TwinLedger universal agent instructions

## Context loading order (mandatory before any code change)

1. `docs/reference/TwinLedger_v3_Master_TZ_AI_Agents.txt` (Master TZ v3.0.0 reference; do not confuse with organizer TZ)
2. `AGENTS.md` (this file)
3. `docs/PROJECT_CONTEXT.md`
4. `docs/CURRENT_STATE.md`
5. `docs/DECISIONS.md`
6. `docs/STATUS.md`
7. `docs/QUESTIONS.md`
8. Relevant `contracts/` schemas
9. Your task card in `docs/TASKS/`
10. Latest phase report in `docs/PHASE_REPORTS/` and handoff in `docs/HANDOFF/`

Missing files must be named explicitly, never invented.

## Ownership (one owner per zone, TZ 4)

| Zone | Directories | Owner |
|---|---|---|
| 1 Generator/Data | `gen/`, `episodes/` | A |
| 2 Env/Evaluator | `env/`, `adapter/`, `harness/`, `scoring/`, `seal/` | B |
| 3 Verification/Red team | `verifier/`, `arena/` | C |
| 4 Docs/QA/Judge | `judge/`, `docs/`, cross-zone tests | D |
| Contracts/spec | `contracts/`, `spec/`, `invariants/`, `configs/` | Orchestrator (A0) |

Change only your zone without permission. Frozen-contract changes require
an approved CR in `docs/CR/`.

## Forbidden operations

- Never put truth/provenance/seed in public observation or policy logs.
- Never let policy import scorer/verifier/generator internals.
- Never use real accounting records or personal data.
- Never add a network dependency, paid API or model download to core.
- Never weaken a test just to get a green build (needs CR + QA approval).
- Never claim PASS without running the command and recording output.
- Never claim OS-level sandbox when only process separation exists.

## Money / time rules

- Money: integer minor units; Decimal from strings only; rounding mode
  from `policy.json` (REQ-MONEY-001…006).
- Time: ISO-8601 with offset; period in company timezone (REQ-TIME-001…005).

## Work cycle

1. Read context + ticket. 2. Inspect repo. 3. Smallest correct slice.
4. Add tests. 5. Run scoped tests. 6. Run cross-module tests.
7. Review diff (secrets, drift, forbidden imports). 8. Update docs/report.
9. Commit with REQ-ID + ticket. 10. Handoff.

## Report format (end of every session)

```
STATUS: DONE / PARTIAL / BLOCKED
SCOPE: ...
IMPLEMENTED: ...
REQUIREMENTS: REQ IDs closed
TESTS RUN: exact commands
TEST RESULTS: PASS/FAIL/SKIPPED with counts
COMMIT: hash or NOT COMMITTED
RISKS: ...
DECISIONS: new decision IDs
NEXT ACTION: single exact next step
```

Full templates: Master TZ Appendices A–C, `docs/TASKS/`, `docs/HANDOFF/`.
