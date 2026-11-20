# T-5-01 — Environment contract: reset/step, tools, budget

| Field | Value |
|-------|-------|
| Phase | 5 |
| Status | NOT STARTED |
| Blocked by | the Phase 4 gate in `docs/STATUS.md` |
| Requirement ids | see the matching `PHASE-05` entries in `judge/rubric_map.json` |

## Goal
Implement the JSON reset/step protocol per `contracts/` with the six read-only tools, page size 50, budget 100 steps, 64 KiB request cap and the `info` projection `[steps_used, steps_remaining]`.

## Definition of done
Lifecycle and budget accounting are exact; a failed call costs a step; submit does not; a closed run never exposes reward or truth (CT-ENV-01..CT-SEAL-02).

## Constraints
The adapter is still `UNBOUND`; the environment must work against the internal contract and must not assume an official transport (Q-005).

## Before you start
1. `make verify-core` is exit 0 and matches `docs/STATUS.md`.
2. Read the assumptions that touch this phase in `docs/ASSUMPTIONS.json`.
3. Open a CR for any schema change; never widen a contract to fit the code.
