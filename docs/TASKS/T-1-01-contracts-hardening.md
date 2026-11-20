# T-1-01 — Foundation hardening: CI, golden hashes, contract ergonomics

| Field | Value |
|-------|-------|
| Phase | 1 |
| Status | NOT STARTED |
| Blocked by | the Phase 0 gate in `docs/STATUS.md` |
| Requirement ids | see the matching `PHASE-01` entries in `judge/rubric_map.json` |

## Goal
Add a GitHub Actions workflow that runs `make lint`, `make test` and `make verify-core` on every push; add golden hashes for the contract set; add typed dataclass mirrors of the core schemas only where a real Phase 1 code path needs them.

## Definition of done
`make verify-core` still exit 0 on a clean checkout; the workflow uploads `artifacts/reports/latest/`; adding a schema field without a fixture fails the build.

## Constraints
Do not widen any schema to make Phase 1 easier: open a CR (`docs/CR/CR-TEMPLATE.md`) first.

## Before you start
1. `make verify-core` is exit 0 and matches `docs/STATUS.md`.
2. Read the assumptions that touch this phase in `docs/ASSUMPTIONS.json`.
3. Open a CR for any schema change; never widen a contract to fit the code.
