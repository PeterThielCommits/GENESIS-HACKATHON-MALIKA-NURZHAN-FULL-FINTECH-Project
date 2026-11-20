# PHASE-00 REPORT — official sources, contract, isolation, governance

**Date:** 2026-11-20 · **Status:** `PASS_WITH_OPEN_ITEMS` · **Owner:** A0 orchestrator
**Machine companion:** `docs/PHASE_REPORTS/PHASE-00.json` (same numbers, generated from
`artifacts/reports/latest/verify_summary.json`).

## Outcome

Gate 0 is satisfied with two human actions outstanding. The repository now contains a frozen
archive of the only specification that exists, a 186-requirement registry extracted from it by
tool, 16 explicitly unresolved assumptions each isolated behind `adapter/` and `configs/`,
`contracts/` v0.1 with 35 executable fixtures, a 40-entry internal check map, and one command
(`python3 -m tools.verify --profile core`) that proves all of it and writes artifacts.

What the gate asks for and where the evidence is:

| Exit-gate criterion (§24) | Evidence | Result |
|---|---|---|
| mandatory interfaces known | `docs/official/CONTRACT_SUMMARY.md`, `contracts/` (11 schemas) | known **provisionally**, every row tagged |
| unknowns isolated | `adapter/` (`UNBOUND`, fails closed) + `configs/` (9 files) | done, `CT-ADAPTER-01` + `CT-BOUNDARY-01` |
| blocking risks resolved or documented | `docs/RISK_REGISTER.md`, `docs/THREAT_MODEL.md`, `docs/LIMITATIONS.md` | documented; 3 boundaries honestly "NOT ENABLED" |
| deliverables produced | `docs/official/`, `contracts/`, `docs/RUBRIC_TRACEABILITY.md`, `docs/STATUS.md` | all four present |

Why the status is not plain `PASS`: the organizer contract does not exist in any channel we can
reach, one of the two required signatures is human, and the deadline is unknown. None of these
can be closed by an agent, and none is hidden behind a green check.

## Objectives

| Task | Requirement | Result | Where |
|------|-------------|--------|-------|
| 0.1 find and archive official sources | REQ-ADAPTER-001 | 6 channels searched, absence recorded | `docs/official/SOURCE_SEARCH_LOG.md` |
| 0.2 freeze archive + hash | REQ-CONTRACT-001 | sha256 `a46cdb63…c748e36`, 4062 lines | `docs/official/MANIFEST.json` |
| 0.3 exact tools, schemas, reward, budget, limits, format, env | REQ-CONTRACT-002 | 7-section summary + `configs/` | `docs/official/CONTRACT_SUMMARY.md` |
| 0.4 map every point to assumptions | REQ-CONTRACT-003 | 16 assumptions, 186 requirements | `docs/ASSUMPTIONS.json`, `docs/REQUIREMENTS.json` |
| 0.5 decisions CONFIRMED/CHANGED/OPEN | REQ-ORG-013 | 20 decisions, 0 CONFIRMED (nothing can be) | `docs/DECISIONS.md` |
| 0.6 questions with owners | REQ-ORG-014 | 14 questions + `OPEN-0` | `docs/QUESTIONS.md` |
| starter smoke test | §24 task 0.5 | `SKIPPED` — no starter code exists | `docs/official/MANIFEST.json` `absent[]` |
| deadline + local timezone | §24 task 0.6 | `NOT RUN` — unknown | `docs/QUESTIONS.md` `OPEN-0` |
| rubric traceability | REQ-JUDGE-001 | 118/186 mapped, 40 checks | `docs/RUBRIC_TRACEABILITY.md` |
| status/gate table | REQ-GH-006 | 13-row gate table | `docs/STATUS.md` |

## Verification

Every number below is copied from a run performed while writing this report.

| Command | Result |
|---------|--------|
| `python3 -m unittest discover -s tests -t . -p 'test_*.py'` | **188 tests, 0 FAIL, 0 ERROR, 0 SKIPPED** (0.1 s) |
| `python3 -m tools.validate_contracts` | **35/35** fixtures; every invalid case asserts its JSON pointer + keyword |
| `python3 -m tools.validate_contracts --hash` | `d9b438cc58bdbb40317ee49024cdfa1fe1ccf56e4ab09cdc752093155f0016bc` |
| `python3 -m tools.check_governance` | **13/13** checks pass |
| `python3 -m tools.check_import_boundaries` | PASS — 34 files, 0 third-party imports, 0 forbidden edges |
| `python3 -m tools.extract_requirements --check` | PASS — 186 requirements reproduce byte-identically |
| `python3 -m tools.verify --profile core` | 40 checks: **12 executed** (12 pass) + **28 `BLOCKED`** with reasons; exit code **0**, status `PASS_WITH_PLANNED_CHECKS_BLOCKED` |
| `make setup` | PASS — Python 3.11.2; optional extras absent → `SKIPPED` |

Check map state: 40 internal checks, `official: false` on every one; 12 `IMPLEMENTED`, 28
`PLANNED` and reported as `BLOCKED` with the phase that will implement them — never as `PASS`.

## Risks

Top risks carried into Phase 1 (full register: `docs/RISK_REGISTER.md`):

| Id | Risk | Status | Control |
|----|------|--------|---------|
| R-01 | provisional reward formula is wrong | `ACCEPTED` | only `configs/scoring/reward.json`; one-line change on Q-012 |
| R-02 | schema drift between teams | `MITIGATED` | frozen contract digest + fixture suite + `tests/contracts/` |
| R-03 | truth leaks into the policy process | `OPEN` | Phase 2/16 work; boundary recorded as "NOT ENABLED" |
| R-24 | claiming an official score | `MITIGATED` | `GOV-CLAIMS-01` blocker + `official: false` const in schema |
| P0-1 | no organizer contract at all | `ACCEPTED` | isolation + CR path; nothing else is possible today |

## Owner sign-off

| Role | Name | Status | Date |
|------|------|--------|------|
| A0 orchestrator (agent) | Arena coding agent, session `phase-0-orchestrator` | SIGNED for internal consistency | 2026-11-20 |
| Owner B — human zone owner | — | **PENDING** (`HUMAN_ACTION_REQUIRED`) | — |

The agent signature covers: every command above was executed, every number is reproducible,
and no item is described as official. It does **not** certify any organizer fact.

## Next phase entry conditions (all met except where noted)

1. `contracts/` v0.1 frozen at digest `d9b438cc…`; changes only via `docs/CR/CR-TEMPLATE.md`.
2. Phase 1 may implement the generator against `contracts/company.schema.json` and
   `configs/generator/default.json` without waiting for the organizer contract.
3. Phase 1 must not read `sealed/`, must not add third-party dependencies to the mandatory
   path, and must emit `DT-GEN-01`-style reproducibility evidence.
4. Reviewer 2 must sign before Phase 5 consumes the contract summary as if reviewed.
