# Next Agent — Exact Task

## Read first (in order)

1. `TwinLedger_v3_Master_TZ_AI_Agents.txt` (master spec)
2. `AGENTS.md`
3. `docs/PROJECT_CONTEXT.md`
4. `docs/CURRENT_STATE.md`
5. `docs/DECISIONS.md`
6. `docs/STATUS.md`
7. `docs/TASKS/T-02-01.md` (your task card)
8. `docs/PHASE_REPORTS/PHASE-01.md` + `docs/HANDOFF/A0-to-A1-phase-01.md`

## Task

**T-02-01 (Phase 2): money, time, IDs, invariants.**
Implement `core/money.py` (exponents, Decimal-from-string conversion,
rounding policies), `core/time_rules.py` (zoneinfo periods, DST
boundaries), `core/ids.py` (4 ID families), `invariants/` checks for
INV-01…INV-17, and hand-authored fixtures in `tests/fixtures/manual/`.
Zone: Orchestrator + Owner A (primitives). Do not touch `verifier/`
(Owner C) or `env/`/`scoring/` (Owner B) without a CR.

## Commands

```bash
git status && git log --oneline -3
make setup && make lint && make test
```

## Acceptance

- Hand-authored tests for KZT/USD/JPY/KWD, half-even/half-up boundaries,
  DST spring-forward/fall-back, JE balance, allocation conservation,
  duplicate ID, dangling reference.
- `make test` + `make lint` green; update `docs/CURRENT_STATE.md`,
  `docs/STATUS.md`, task report + handoff.

## Forbidden

Do not invent official contract values; do not weaken Phase 1 tests;
do not import `gen` from `verifier` (or vice versa); do not claim PASS
without running commands.
