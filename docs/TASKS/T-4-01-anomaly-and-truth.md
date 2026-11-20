# T-4-01 — Anomaly operators, counterfactual twin and truth derivation

| Field | Value |
|-------|-------|
| Phase | 4 |
| Status | NOT STARTED |
| Blocked by | the Phase 3 gate in `docs/STATUS.md` |
| Requirement ids | see the matching `PHASE-04` entries in `judge/rubric_map.json` |

## Goal
Implement the anomaly catalogue deterministically, derive truth from the canonical diff of the clean and mutated books, and cross-check it with an independent verifier.

## Definition of done
Each operator is deterministic and confined to the affected records; every invariant has at least five positive and five negative vectors (DT-TRUTH-02); the verifier reproduces truth exactly.

## Constraints
Tolerance stays `rounding_ops * 1` minor unit per anomaly (A-014, RW-TOL-01); widening it after observing results is forbidden.

## Before you start
1. `make verify-core` is exit 0 and matches `docs/STATUS.md`.
2. Read the assumptions that touch this phase in `docs/ASSUMPTIONS.json`.
3. Open a CR for any schema change; never widen a contract to fit the code.
