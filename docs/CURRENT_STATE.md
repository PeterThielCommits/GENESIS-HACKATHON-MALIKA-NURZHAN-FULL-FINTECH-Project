# Current State

- **Active branch:** `arena/3a99279e-genesis-hackathon-malika-nurzh` (branched from `main` @ `da42d26`).
- **Completed Master TZ phases:** **Phases 1–9 DONE** (`EXIT GATE 8` DONE, **`EXIT GATE 9` DONE**).
- **Official 2026-11-20 FinTech compliance:** **100% GREEN** across all 5 blocks (`C01..C20`, `S01..S25`, `Q01..Q20`, `P01..P20`, `A01..A15`).
- **Phase 9 (`ПРОЦЕССЫ, SEALED EVALUATION И RECEIPTS`) summary:**
  - `seal/` (`commitment.py`, `hashchain.py`, `merkle.py`, `receipt.py`, `cli.py`): salted truth commitment + constant-time `verify_reveal`, wall-clock-free `TrajectoryEvent` hash chain, size-bound RFC-6962 Merkle tree (`0x00`/`0x01`/`0x02`), batch receipt sealing, and offline `python3 -m seal.cli verify-receipt`.
  - `env/jsonl_server.py` & `scoring/scorer_cli.py`: hardened JSONL stdio server (`--require-closed-eval`) and post-termination isolated scorer CLI (`score` + `seal-batch`).
  - `harness/` (`sandbox.py`, `protocol.py`, `trajectory.py`, `env_process.py`, `policy_process.py`, `scorer_process.py`, `runner.py`, `reference_policies.py`, `replay.py`): 3-subprocess `CLOSED_EVAL` coordinator, staged read-only `public/` (`0o444`/`0o555`, zero `sealed/`), empty `0o555` `policy` scratch `cwd`, `ScorerPrematureStartError` barrier + monotonic nanosecond `ProcessLifecycleProof`, honest `SecurityProfile` (`is_full_os_sandbox: false`), and fresh-process replay (`make replay`, `RC-005`).
- **Verification baseline (clean workspace, `rm -rf episodes/*/*/sealed`):**
  - `make lint` -> `CLEAN (REQ-ARC-001..007)`
  - `make test` -> `295/295 PASS`
  - `make test-property` -> `5/5 PASS`
  - `make replay` -> `5/5 byte-identical` (`replay_report.json`) + `P01..P20 PASS`
  - `make verify` -> `PASS` (`RC-001..RC-005`)
  - `make report` -> `PASS` (`artifacts/reports/latest/report_index.json`)
- **Next phase:** **Phase 10** (`PERTURBATION, METAMORPHIC, ANTI-CHEAT, CANARY`).
- **Open external items:** `Q-003`..`Q-006` (`docs/QUESTIONS.md`) and `make docker-check` (Docker unavailable in sandbox).
