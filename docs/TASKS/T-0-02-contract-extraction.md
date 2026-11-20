# T-0-02 — Contract extraction and assumption matrix

| Field | Value |
|-------|-------|
| Phase | 0 (tasks 0.3, 0.4) |
| Human owner | A0 orchestrator |
| Status | DONE |
| Requirement ids | REQ-CONTRACT-001..004, A-001..A-016 |

## Goal
Write out the exact tools, schemas, reward, budget, limits, submission format and runtime
restrictions, and map each official/provisional item onto the assumptions of the master
specification.

## What was done
* `docs/official/CONTRACT_SUMMARY.md`: seven sections, every row tagged
  `PROVISIONAL`/`UNKNOWN`/`DERIVED`.
* `docs/REQUIREMENTS.json`: 186 requirements extracted by tool from the archived text (plus 3
  mention-only identifiers listed separately).
* `docs/ASSUMPTIONS.json`: A-001…A-016, all `UNRESOLVED`, each with an isolation point, a
  question id, decision ids, an impact statement and a covering test.

## Acceptance evidence
| Check | Command | Result |
|-------|---------|--------|
| registry freshness | `python -m tools.extract_requirements --check` | PASS (186) |
| assumptions complete | `python -m unittest tests.phase0.test_assumption_registry` | PASS |
| values match configs | same test (A-004…A-016 cross-checks) | PASS |

## Note
Extraction is mechanical; the *interpretation* of each requirement remains provisional and is
tracked per assumption. Nothing here is an organizer confirmation.
