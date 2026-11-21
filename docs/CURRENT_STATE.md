# TwinLedger — current state

- Branch: `arena/7a1327ee-genesis-hackathon-malika-nurzh` (from `be114f0`).
- **Phases 1–8 integrated & verified on frozen v1.0.0 contracts** (`CR-06-01` resolved):
  - Phase 3–4 & 7 (`gen/`): deterministic Clean Twin + 16-class clean distractors + all 4 anomaly operators (reusing `gen/errors/fx_cutoff.py`) + structural diff + salted `truth_commitment` + canonical manifest serializer.
  - Phase 5 (`env/`, `adapter/`): frozen-contract public-only environment (`list_records`, `get_record`, `get_document`, safe AST `calc`, `submit`), opaque HMAC cursors, `CLOSED_EVAL`, JSONL stdio server, provisional organiser adapter.
  - Phase 6 (`scoring/`): matcher, exact rational reward, diagnostics, exhaustive oracle, plus Stage-2 `scoring/crosscheck.py`.
  - Phase 8 (`verifier/`): **EXIT GATE 8 DONE** — 10/10 generated release episodes (`episodes/dev`: 6/6, `episodes/train`: 4/4) verified with `release_blocked=False`, `F1=1`, `evidence_minimality=1`, `distractor_FP=0`.
- Verification: `make lint` CLEAN, `make test` PASS (214 tests), `make test-property` PASS (3 tests), `make verify` PASS (`RC-001..003`), `make report` PASS, `python3 tools/make_dataset.py --split all` PASS (10/10).
- Remaining external/non-local items: official organiser clarifications `Q-003..Q-006` (provisional adapter/rubric isolated); `make docker-check` NOT RUN (no Docker in sandbox).
- Evidence: [Phase 8 report](PHASE_REPORTS/PHASE-08.md), [CR-06-01 (resolved)](CR/CR-06-01.md), [Independence doc](INDEPENDENCE.md).

Three priority next actions:
1. Zone 2 (Phase 9): implement `seal/` (commit-reveal, Merkle tree, signed receipts) and `harness/` (process-isolated JSONL runner, trajectory recorder, deterministic replay).
2. Zone 3 (Phase 10–12): implement NLP layer, injection track, and `arena/` baselines + shortcut audit on the verified `episodes/dev` & `episodes/train` corpus.
3. A0: reconcile official organiser protocol/rubric (`Q-003..Q-006`) inside `adapter/` & `configs/rubric/` once published, and run `make docker-check` in a Docker-enabled runner.
