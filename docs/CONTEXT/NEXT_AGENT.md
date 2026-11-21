# Next Agent — Exact Task

## Read first (in order)

1. `docs/reference/TwinLedger_v3_Master_TZ_AI_Agents.txt` (master spec, section 24 = phase plan)
2. `AGENTS.md`
3. `docs/PROJECT_CONTEXT.md`
4. `docs/CURRENT_STATE.md`
5. `docs/DECISIONS.md` (incl. D-06-00..D-06-05)
6. `docs/STATUS.md`
7. `docs/PHASE_REPORTS/PHASE-06.md` + `docs/HANDOFF/phase-06-to-07.md`
8. `docs/TASKS/T-06-0*.md` (what scoring guarantees)

## Task

**Default next: Phase 7 — FX_RATE_MISMATCH / PERIOD_CUTOFF operators
(Zone 1).** Produce mutation operators whose truth output conforms to
`contracts/truth.schema.json` v1.0.0; the Phase 6 scorer scores it
unchanged. Alternative (Zone 2): reconcile Phase 5 env with the chosen
contract line after A0 resolves issue #3 / draft CR-06-01.

## Commands

```bash
git status && git log --oneline -5
make setup && make lint && make test        # expect 131 tests OK
make verify-core                            # expect RC-001..003 PASS
```

## Acceptance

- New work keeps `make test` green (do not weaken scoring tests in
  `tests/scoring/` — 91 tests encode TZ 15.2-15.9).
- Truth records carry `amount_minor`, `tolerance_minor`, `evidence_sets`
  and `minimal_evidence_size`; matcher semantics stay per D-06-04/D-06-05.
- Update docs/CURRENT_STATE.md, STATUS.md, task report + handoff with
  real command output.

## Forbidden

Do not modify frozen `contracts/*` without an approved CR (issue #3 is
open); do not import `gen` into `scoring` (import lint enforces it); do
not present the provisional reward formula as the official rubric; do
not claim PASS without running commands.
