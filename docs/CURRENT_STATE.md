# TwinLedger — current state

- Branch: `arena/bbc43571-genesis-hackathon-malika-nurzh`.
- Baseline: `62d7b9e` (Phase 7 PARTIAL merged line).
- Phase 8 PARTIAL: Tasks 8.1–8.7 DONE — independent public-only `verifier/`
  package (zero common-mode dependencies, never read `gen/`), frozen
  `spec/verifier_algorithm.md`, ProofGraph DAG, minimal-evidence ablation &
  reachability, all 16 minimum distractor exclusions, Stage-2
  `scoring/crosscheck.py` with pre-committed `report_digest`, and AST/runtime
  file-access boundary proofs.
- Verification: `make lint` CLEAN, `make test` PASS (197 tests: 137 baseline +
  60 Phase 8), `make test-property` PASS (3 tests), `make verify` PASS
  (`RC-001..003`), `make report` PASS. Docker check not run (unavailable).
- Blockers: `episodes/dev` and `episodes/train` have 0 generated episodes
  because Phases 3–5 are not integrated and issue #3 / draft CR-06-01 and
  official anomaly/affected-ID semantics `Q-004/Q-005/Q-006` remain open.
- Evidence: [Phase 8 report](PHASE_REPORTS/PHASE-08.md),
  [Phase 8 JSON](PHASE_REPORTS/PHASE-08.json),
  [Independence doc](INDEPENDENCE.md); previous
  [Phase 7 report](PHASE_REPORTS/PHASE-07.md).

Three priority next actions:
1. A0: approve the contract line (issue #3 / CR-06-01) and reconcile Phase 3–5
   + Phase 7 dependencies into `main`.
2. A0: obtain official anomaly/rubric/affected-ID semantics (`Q-004/Q-005/Q-006`).
3. Zone 1 + Zone 3: generate release episodes into `episodes/dev` &
   `episodes/train` and run Stage-1 `python3 -m verifier <ep>/public` + Stage-2
   `scoring.crosscheck.crosscheck()` across 100% of generated episodes to close
   EXIT GATE 8 (`DONE`), then proceed to Phase 9 (`seal/` & `harness/`).
