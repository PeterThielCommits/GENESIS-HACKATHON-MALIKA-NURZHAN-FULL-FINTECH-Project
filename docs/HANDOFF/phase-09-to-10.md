# Phase 9 → Phase 10

Phase 9 (`ПРОЦЕССЫ, SEALED EVALUATION И RECEIPTS`, Zone 2) is **DONE** and
**EXIT GATE 9** is **PASS** on a clean workspace:
- `seal/` (`commitment.py`, `hashchain.py`, `merkle.py`, `receipt.py`, `cli.py`)
- `harness/` (`sandbox.py`, `protocol.py`, `trajectory.py`, `env_process.py`,
  `policy_process.py`, `scorer_process.py`, `runner.py`, `reference_policies.py`,
  `replay.py`, plus `isolated_runner.py`)
- `env/jsonl_server.py` (`--require-closed-eval`, `export_state`, `shutdown`)
- `scoring/scorer_cli.py` (`score`, `seal-batch`)

Run `make setup && make lint && make test-property && make replay && make verify && make report`
first; expect 295 unit/integration tests, 5 property suites, `RC-001..RC-005`
all green, and `5/5` byte-identical fresh-process trajectory replays.

Next: **Phase 10 (`PERTURBATION, METAMORPHIC, ANTI-CHEAT, CANARY`)**. Extend
perturbation/metamorphic suites, explanation-consistency diagnostics
(`scoring/diagnostics.py` currently marks `explanation_consistency` as
`NOT_AVAILABLE`), and canary/shortcut checks without breaking frozen v1.0.0
schemas or Zone 1/2/3 AST import boundaries.
