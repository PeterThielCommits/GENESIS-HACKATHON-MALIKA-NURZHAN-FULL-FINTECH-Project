# CR-<NNNN> — <short title>

Copy this file to `docs/CR/CR-<NNNN>-<slug>.md` and fill every field. A CR is required for any
change to: frozen contracts, public schemas, reward semantics, ID semantics, process
boundaries, or the organizer adapter. It must be approved by the orchestrator (A0) **before**
the change is merged.

| Field | Value |
|-------|-------|
| CR id | `CR-0001` |
| Author | |
| Date | |
| Status | `DRAFT` / `APPROVED` / `REJECTED` / `WITHDRAWN` |
| Approved by (A0) | |
| Requirement ids | `REQ-…` |
| Conflict or defect | what is wrong today, with evidence (command/artifact) |
| Official basis | quoted organizer text + archived file hash, or `NONE (provisional)` |
| Proposed behaviour | precise, testable description |
| Compatibility | major / minor / patch + affected schemas and versions |
| Migration of episodes | what must be regenerated or re-sealed, and how |
| New or changed tests | ids and what they prove |
| Rollback plan | how to revert safely |
| Artifacts / PR | links or local paths |

## Why a CR and not a direct edit

1. Frozen contracts are the boundary between four zones; an unannounced change breaks another
   owner's tests and any sealed receipt that references the old shape.
2. A change without an official basis must be recorded as provisional, otherwise a later
   reader will mistake it for an organizer requirement (D-0001).
3. Weakening a test to make a build green is forbidden (REQ-TEST-002); the CR is the only
   legitimate path, and it must cite the specification.

## Checklist before approval

- [ ] The change cannot be expressed in `adapter/` or `configs/` instead.
- [ ] Contract digest change is included in the same commit.
- [ ] `make verify-core` passes with the new expectations.
- [ ] `docs/DECISIONS.md` has a new or superseded decision entry.
- [ ] No truth/seed/salt leakage introduced.
- [ ] Documentation updated (`contracts/CONTRACT.md`, `docs/DATA_DICTIONARY.md` if fields move).
