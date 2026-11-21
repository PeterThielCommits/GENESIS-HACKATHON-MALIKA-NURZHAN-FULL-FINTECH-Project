# Phase 6 → Phase 7

Scorer (Zone 2) is complete for the frozen v1.0.0 contracts:
`scoring/matcher.py` (predicate + deterministic matching),
`scoring/reward.py` (exact F1/reward), `scoring/diagnostics.py`,
`scoring/exhaustive.py`. Run `make setup lint test verify-core` first;
expect 131 tests green.

Next: Phase 7 (FX_RATE_MISMATCH / PERIOD_CUTOFF mutation operators,
Zone 1). Produce truth records in `contracts/truth.schema.json` v1.0.0
(`amount_minor`, `tolerance_minor`, `evidence_sets`, `minimal_evidence_size`)
and the scorer will consume them unchanged. Do not alter frozen schemas
without an approved CR — the parallel-branch freeze conflict is open
(issue #3, draft CR-06-01). Keep operator fixtures independent from
matcher tests (D-02-01). See `docs/PHASE_REPORTS/PHASE-06.md` and
`docs/TASKS/T-06-0*.md` for acceptance evidence.
