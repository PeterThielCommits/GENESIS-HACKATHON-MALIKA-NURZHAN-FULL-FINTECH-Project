# CURRENT STATE

One-screen orientation for the next agent or human. Update at the end of every phase.
Length limit: this file stays under two screens; detail belongs in the linked documents.

**Phase:** 0 and 1 complete (`PASS_WITH_OPEN_ITEMS`); Phase 2 not started.
**Branch:** `arena/6e3d45bc-genesis-hackathon-malika-nurzh` (base `c961a00`).
**Date:** 2026-11-20.

## What exists and works

| Area | State | Where |
|------|-------|-------|
| Archived specification | byte-identical copy + SHA-256 | `docs/official/master_tz/`, `docs/official/MANIFEST.json` |
| Contract summary | 7 sections, every row tagged PROVISIONAL/UNKNOWN/DERIVED | `docs/official/CONTRACT_SUMMARY.md` |
| Requirement registry | 186 requirements extracted by tool, freshness enforced | `docs/REQUIREMENTS.json`, `tools/extract_requirements.py` |
| Assumptions | 16, all `UNRESOLVED`, each isolated | `docs/ASSUMPTIONS.json`, `adapter/`, `configs/` |
| Decisions / questions | 20 decisions, 14 questions + `OPEN-0` | `docs/DECISIONS.md`, `docs/QUESTIONS.md` |
| Contracts v0.1 | 11 schemas + definitions, 35 fixtures, digest published | `contracts/` |
| Configurations | limits, mode, cursor, resources, reward, match, tolerance, generator, rubric, arena | `configs/` |
| Verification | 1 command, 45 mapped checks, 12 artifacts, exit codes 0–5 | `tools/verify.py`, `artifacts/reports/latest/` |
| Typed models | 11 dataclasses + parity tool | `models/`, `tools/check_models.py` |
| Contract freeze | per-file golden hashes | `contracts/GOLDEN.json`, `tools/check_golden.py` |
| CI + repo process | workflow, PR/issue templates, CODEOWNERS | `.github/`, `docs/BRANCH_PROTECTION.md` |
| Tests | 231 stdlib tests, 0 failures | `tests/` |

## What does not exist yet (deliberately)

* No episode data, no generator, no scorer, no environment, no verifier implementation — all
  Phase 1+.
* No bound organizer protocol: `adapter/compatibility.py` is `UNBOUND` and fails closed.
* No runtime sandbox: socket blocking, cgroups and process isolation are Phase 16 work
  (stated as "NOT ENABLED" in `docs/THREAT_MODEL.md`).
* No official rubric: `judge/rubric_map.json` is internal, `official: false`.
* Branch protection is not enabled and `.github/CODEOWNERS` holds placeholder handles — both are
  human actions (`docs/BRANCH_PROTECTION.md`).

## Read in this order

1. `AGENTS.md` — hard rules and zones.
2. `docs/CURRENT_STATE.md` (this file) → `docs/STATUS.md` (gates).
3. `docs/official/CONTRACT_SUMMARY.md` — what we believe the contract is, and how sure we are.
4. `docs/ASSUMPTIONS.json` — what is unknown and where it is isolated.
5. `docs/DECISIONS.md`, `docs/QUESTIONS.md` — why, and what is still open.
6. `contracts/CONTRACT.md` — the interfaces you must implement.
7. `docs/CONTEXT/NEXT_AGENT.md`, `docs/HANDOFF/orchestrator-to-phase1.md` — the exact next step.

## The only three open items that block a claim of "done"

1. Reviewer 2 signature (`docs/official/CONTRACT_SIGNOFF.md`) — human.
2. Submission deadline (`docs/QUESTIONS.md` `OPEN-0`) — human.
3. Organizer contract missing (`Q-001`) — external; the isolation strategy is the answer until
   it arrives.

## Commands you will actually use

```bash
python3 -m unittest discover -s tests -t . -p 'test_*.py'   # 231 tests
python3 -m tools.verify --profile core                     # phase gate, exit 0-5
python3 -m tools.validate_contracts                        # 35 fixtures
python3 -m tools.check_governance                          # 16 consistency checks
python3 -m tools.check_import_boundaries                   # zone enforcement
python3 -m tools.extract_requirements --check               # registry freshness
make setup; make verify-core; make phase0                  # the same, wrapped
```
