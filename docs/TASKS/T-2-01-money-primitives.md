# T-2-01 — Money, FX, time and identifiers

| Field | Value |
|-------|-------|
| Phase | 2 |
| Status | NOT STARTED |
| Blocked by | the Phase 1 gate in `docs/STATUS.md` |
| Requirement ids | see the matching `PHASE-02` entries in `judge/rubric_map.json` |

## Goal
Implement exact minor-unit arithmetic (Decimal only for parsing), currency exponent handling (JPY, KWD, BHD), FX conversion with a recorded rate id, period cut-off with an explicit timezone, and the seven ID namespaces.

## Definition of done
Property tests over exponents 0..3; no float anywhere (a lint test asserts `float(` never appears in `core/money*`); DST and month-end cases pass.

## Constraints
The FX source of truth is provisional (A-006): keep it behind `configs/fx/` and never hardcode a rate pair in code.

## Before you start
1. `make verify-core` is exit 0 and matches `docs/STATUS.md`.
2. Read the assumptions that touch this phase in `docs/ASSUMPTIONS.json`.
3. Open a CR for any schema change; never widen a contract to fit the code.
