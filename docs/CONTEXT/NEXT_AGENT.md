# Next agent — Phase 7 continuation

First, A0: resolve issue #3 / CR-06-01 and identify approved Phase 3–5
commits compatible with the pinned contracts. Read `CURRENT_STATE.md`,
`PHASE_REPORTS/PHASE-07.md` and `HANDOFF/phase-06-to-07.md` in `docs/`.
Run `make verify` before integration. The implementation and hand fixtures
are `gen/errors/fx_cutoff.py` and `tests/generator/test_phase07.py`.
Do not change frozen schemas, treat journal signatures as sealed truth, or
claim discoverability based on these direct fixture calls. After the upstream
inputs are approved, run clean/mutated episode and tool-reachability tests
for all four types, including aggregate period checks and official IDs.
