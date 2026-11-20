# T-0-07 — Verification harness and exit codes

| Field | Value |
|-------|-------|
| Phase | 0 (enables §23) |
| Human owner | A0 orchestrator |
| Status | DONE |
| Requirement ids | REQ-JUDGE-001..005, REQ-TEST-004 |

## Goal
One command that proves the Phase 0 gate, emits machine-readable artifacts and uses the
documented exit codes.

## What was done
* `tools/verify.py`: executes contract validation, schema self-consistency, governance,
  import-boundary scan and the unittest suite; emits `verify_summary.json`, `verify_summary.txt`
  and `rubric_matrix.csv`; validates each emitted result against
  `contracts/rubric_check.schema.json`.
* Exit codes `0/1/2/3/4/5` per §23.3; release blockers (leak, false official claim) exit `4`.
* `make verify-core` / `make verify` / `make phase0`, plus honest stubs (`exit 5`) for targets
  of later phases.

## Acceptance evidence
| Check | Command | Result |
|-------|---------|--------|
| gate | `make verify-core` | see `docs/PHASE_REPORTS/PHASE-00.md` |
| artifacts | `artifacts/reports/latest/` | summary + csv present |
| no silent skip | planned checks reported `BLOCKED` | verified in the summary |

## Note
The full rubricator arrives in Phase 14; it extends this runner instead of adding a parallel
script, so the exit-code semantics cannot drift.
