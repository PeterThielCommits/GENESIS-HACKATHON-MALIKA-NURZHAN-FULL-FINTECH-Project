# T-0-04 — contracts/ v0.1

| Field | Value |
|-------|-------|
| Phase | 0 (deliverable "contracts/ v0.1") |
| Human owner | A0 orchestrator (owner B reviews before Phase 5) |
| Status | DONE |
| Requirement ids | REQ-CONTRACT-001..022, REQ-ADAPTER-001..004 |

## Goal
Describe every public structure *before* implementation, with executable schemas rather than
prose.

## What was done
* 11 typed schemas + shared definitions: manifest, company, policy, finding, truth, tool
  request/response, trajectory event, receipt, verifier report, rubric check.
* `version.json` (set `0.1.0`, payload `1.0.0`, semver rules, unknown-field policy) and
  `currency.json` (10 currencies, JPY 0 / KWD 3 boundary cases).
* 35 fixtures (valid + invalid) with the exact expected JSON pointer and keyword per invalid case.
* `contracts/CONTRACT.md` as the human-readable agreement, cross-checked against the schemas by
  `tests/phase0/test_contract_docs.py`.
* `tools/jsonschema_lite.py`: stdlib validator over a fixed keyword subset that fails the build
  if a schema leaves the subset (no silent ignoring).

## Acceptance evidence
| Check | Command | Result |
|-------|---------|--------|
| fixtures | `python -m tools.validate_contracts` | PASS (35/35) |
| self-consistency | `python -m unittest tests.contracts.test_schema_self_consistency` | PASS |
| docs vs schemas | `python -m unittest tests.phase0.test_contract_docs` | PASS |
| digest | `python -m tools.validate_contracts --hash` | printed by `make verify` |

## Note
Every schema carries `"status": "provisional"` and a `provisional_reason`, so a reader of the
file alone cannot mistake it for an organizer contract.
