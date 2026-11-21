# Phase 2 → Phase 3

Start with `make setup verify-core`. Build a small clean ledger and map rows to
catalog groups (namespace for IDs, explicit nullable references, one currency per
monetary group). Run all group checks before publication. Keep the manual
fixtures independent of generator output; do not reuse generator FX selection
in the verifier. See `docs/PHASE_REPORTS/PHASE-02.md` and decision D-02-01.
