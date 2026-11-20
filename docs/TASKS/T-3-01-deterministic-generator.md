# T-3-01 — Deterministic clean-book generator

| Field | Value |
|-------|-------|
| Phase | 3 |
| Status | NOT STARTED |
| Blocked by | the Phase 2 gate in `docs/STATUS.md` |
| Requirement ids | see the matching `PHASE-03` entries in `judge/rubric_map.json` |

## Goal
Generate a clean company (COA, journals, invoices, payments, bank lines, FX, policy) from a seed and a locked config; publish `public/` and a manifest with hashes only.

## Definition of done
Same seed and config produce byte-identical public data (DT-GEN-01); RNG streams are namespaced so adding a mutation cannot shift an earlier stream (DT-GEN-02); invariants hold on 100 seeds.

## Constraints
Never write `sealed/` from this module; truth derivation is Phase 4.

## Before you start
1. `make verify-core` is exit 0 and matches `docs/STATUS.md`.
2. Read the assumptions that touch this phase in `docs/ASSUMPTIONS.json`.
3. Open a CR for any schema change; never widen a contract to fit the code.
