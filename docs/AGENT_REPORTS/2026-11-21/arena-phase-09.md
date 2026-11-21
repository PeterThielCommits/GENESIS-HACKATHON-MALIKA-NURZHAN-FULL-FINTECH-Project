# Arena agent — Phase 9 session (2026-11-21)

DONE (Tasks 9.1–9.8 DONE; EXIT GATE 9 PASS on a clean workspace). See
[Phase 9 report](../../PHASE_REPORTS/PHASE-09.md) and
[Phase 9 JSON](../../PHASE_REPORTS/PHASE-09.json) for Master TZ hash,
branch, baseline, task matrix, command/exit-code results, requirements, and
gate evidence. Owner: Zone 2 (`seal/`, `harness/`, `scoring/scorer_cli.py`,
`env/jsonl_server.py`).

Started cleanly from `da42d26`. Implemented Zone-2 `seal/` (commit-reveal
`seal/commitment.py`, wall-clock-free trajectory hash chain `seal/hashchain.py`,
size-bound RFC-6962 Merkle tree `seal/merkle.py`, offline receipt builder and
verifier `seal/receipt.py` + `seal/cli.py`), hardened `env/jsonl_server.py`
with `--require-closed-eval`, added isolated post-termination
`scoring/scorer_cli.py`, and implemented the full 3-subprocess `CLOSED_EVAL`
harness (`harness/sandbox.py`, `protocol.py`, `trajectory.py`, `env_process.py`,
`policy_process.py`, `scorer_process.py`, `runner.py`, `reference_policies.py`,
`replay.py`) while preserving `harness/isolated_runner.py` and zero frozen
schema edits. Added 24 new Phase 9 unit/integration/security tests plus 2
stdlib property suites (295 total tests, 5 property suites). Verified on a
clean workspace (`rm -rf episodes/*/*/sealed`): `make lint`, `make test`,
`make test-property`, `make replay`, `make verify` (`RC-001..005`), and
`make report` all exited 0.
