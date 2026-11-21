# Next agent — Phase 8 → Phase 9 / Integration continuation

First, A0: resolve issue #3 / draft CR-06-01 and merge approved Phase 3–5 +
Phase 7 commits compatible with the pinned v1.0.0 contracts. Read
`docs/CURRENT_STATE.md`, `docs/PHASE_REPORTS/PHASE-08.md`,
`docs/INDEPENDENCE.md`, and `spec/verifier_algorithm.md`.

Run `make verify` before any edits.

Once generated episodes exist in `episodes/dev` and `episodes/train`:
1. Run Stage-1 independent discovery on every generated episode's `public/`
   directory (`python3 -m verifier <ep>/public --out <ep>/verifier_report.json`)
   and Stage-2 `scoring.crosscheck.crosscheck()` against sealed truth to close
   EXIT GATE 8 (`100%` generated release episodes verified).
2. Reconcile any official organiser clarifications for `Q-004/Q-005/Q-006`
   without weakening `verifier/` independence (`verifier/` must never import
   `gen/`, `core/`, `invariants/`, or `scoring/`).
3. Proceed to Phase 9 (`seal/` commit-reveal/Merkle/receipts & `harness/`
   process isolation).
