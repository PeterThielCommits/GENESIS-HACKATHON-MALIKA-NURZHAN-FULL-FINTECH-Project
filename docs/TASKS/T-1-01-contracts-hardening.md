# T-1-01 — Foundation hardening: CI, golden hashes, contract ergonomics

| Field | Value |
|-------|-------|
| Phase | 1 |
| Status | DONE (2026-11-20) |
| Blocked by | — (Phase 0 gate passed) |
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

## Outcome

Delivered in one pass together with the Phase 1 gate:

* CI: `.github/workflows/verify.yml`, linted locally by `python3 -m tools.check_ci` (every `run:`
  command resolved against the Makefile; actions pinned; artifacts uploaded).
* Golden hashes: `contracts/GOLDEN.json` + `python3 -m tools.check_golden` (per-file, payload and
  fixture digests; refresh requires a CR).
* Typed models: `models/` (11 dataclasses) + `python3 -m tools.check_models` (parity both ways,
  fixture round-trip, unknown field rejected).
* Process files: PR template, 4 issue forms, CODEOWNERS, `docs/BRANCH_PROTECTION.md`.
* Generated traceability: `make traceability`, `GOV-RUBRIC-01` fails on staleness.

Evidence: `docs/PHASE_REPORTS/PHASE-01.md` and `artifacts/reports/latest/`.
