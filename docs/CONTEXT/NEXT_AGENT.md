# NEXT_AGENT — exact starting point

Written: 2026-11-20, end of Phase 0. Read `AGENTS.md` first, then
`docs/PROJECT_CONTEXT.md`, `docs/CURRENT_STATE.md`, `docs/STATUS.md`.

## Repository state

| Field | Value |
|-------|-------|
| Branch | `arena/6e3d45bc-genesis-hackathon-malika-nurzh` |
| Base commit | `c961a009611e1711463f5116b2df926bb4726de8` (branch point, only `README.md` existed) |
| Phase | `PHASE-00` and `PHASE-01` closed as `PASS_WITH_OPEN_ITEMS` (see `docs/PHASE_REPORTS/`) |
| Last verified command | `make verify-core` → exit `0`, `PASS_WITH_PLANNED_CHECKS_BLOCKED`, 231 tests |
| Working tree | committed, see `git status` |
| Blockers | none technical; two human items (second signature, deadline) |

## Your first action (exact)

1. `git status && git log --oneline -3`
2. `make verify-core` and confirm the same statuses as `docs/STATUS.md`.
3. Open `docs/TASKS/T-1-01-contracts-hardening.md` and execute it.

## What exists (do not rebuild)

* `contracts/` — 11 typed schemas + shared definitions, 35 fixtures, frozen by `GOLDEN.json`, `CONTRACT.md`, `version.json`, `currency.json`.
  Changing any schema needs a CR plus a decision.
* `tools/` — canonical JSON, stdlib schema validator, contract validator, requirement
  extractor, import-boundary scan, governance check, verify runner, setup check.
* `adapter/` — unbound compatibility profile that fails closed. Do not "temporarily" bind it
  to a guessed contract.
* `configs/`, `spec/`, `judge/`, `docs/`, `tests/`.

## What was added in Phase 1 (do not rebuild)

* `models/` — 11 dataclasses mirroring the schemas, checked by `tools/check_models.py`.
* `contracts/GOLDEN.json` — per-file freeze; refresh only via a CR.
* `.github/` — workflow, PR template, 4 issue forms, CODEOWNERS (placeholders).
* `docs/BRANCH_PROTECTION.md`, `docs/PHASE0_CHECKLIST.md`, `docs/PHASE_REPORTS/PHASE-01.md`.
* `configs/submission/` — deadline (null, honest) and starter-probe configuration.

## What does not exist yet (build in this order)

| Phase | Deliverable | Suggested first ticket |
|-------|-------------|-----------------------|
| 1 | foundation hardening: CI, typed models, golden freeze — **DONE** | `docs/PHASE_REPORTS/PHASE-01.md` |
| 2 | money, time, ID factory, invariant checks | `T-2-01-money-primitives` |
| 3 | deterministic clean generator | `T-3-01-rng-service` |
| 4 | mutation operators + diff truth | `T-4-01-duplicate-payment-operator` |
| 5 | environment reset/step + tools | `T-5-01-env-contract` |

## Do not do

* Do not claim official compatibility, an official score, or a guaranteed result.
* Do not commit `episodes/**/sealed/`, salts, `artifacts/` or hidden episodes (D-0008).
* Do not bind `adapter/` to anything that is not an archived organizer document.
* Do not weaken or delete a failing test (REQ-TEST-002).
* Do not sign Reviewer 2 of `docs/official/CONTRACT_SIGNOFF.md` — only a human can.
