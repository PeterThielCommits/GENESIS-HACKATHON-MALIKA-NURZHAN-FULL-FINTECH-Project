# T-0-03 — Decisions, questions and adjudication path

| Field | Value |
|-------|-------|
| Phase | 0 (tasks 0.5, 0.6) |
| Human owner | A0 orchestrator |
| Status | DONE |
| Requirement ids | REQ-ORG-010..016, REQ-CONTRACT-004 |

## Goal
Turn every unresolved item into either a recorded decision or an owned question with a closure
condition, and define how change control works.

## What was done
* `docs/DECISIONS.md`: D-0001…D-0020 with Status/Date/Owner/Refs/Context/Decision/Alternatives/
  Consequences, plus an assumption status register mirroring the JSON.
* `docs/QUESTIONS.md`: Q-001…Q-014 plus `OPEN-0` (missing deadline), each with owner, asked-to,
  closure condition, impact if unanswered and current mitigation.
* `docs/CR/CR-TEMPLATE.md`: the only legitimate path to change a frozen contract.

## Acceptance evidence
| Check | Command | Result |
|-------|---------|--------|
| decisions complete | `python -m unittest tests.phase0.test_decisions` | PASS |
| questions complete | `python -m unittest tests.phase0.test_questions` | PASS |
| bidirectional links | same tests | PASS |

## Open items
Reviewer 2 signature and the deadline cannot be produced by an agent (D-0017).
