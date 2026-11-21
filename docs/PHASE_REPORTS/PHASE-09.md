# Phase 9 Report — ПРОЦЕССЫ, SEALED EVALUATION И RECEIPTS

- **Phase:** 9 (`ФАЗА 9. ПРОЦЕССЫ, SEALED EVALUATION И RECEIPTS`)
- **Outcome:** **DONE** (Tasks 9.1–9.8 DONE; EXIT GATE 9 PASS on clean workspace)
- **Date:** 2026-11-21
- **Branch:** `arena/3a99279e-genesis-hackathon-malika-nurzh`
- **Base commit:** `da42d26008f948c294920ae8b02a30b08f541732`
- **Master TZ SHA-256:** `a46cdb63bb4b41aabb95a842406f5a4fff91e218ead1e4f97b22b60d1c748e36`

## 1. Scope & Architecture Summary

Phase 9 closes all runtime channels to the scorer during `CLOSED_EVAL` and implements offline-verifiable cryptographic commitments, trajectory hash chains, batch Merkle receipts, fresh-process replay, and an honest platform isolation profile without modifying any frozen Phase 1 v1.0.0 schema:

1. **Zone 2 `seal/` (`contracts` + stdlib only):**
   - `seal/commitment.py` — CSPRNG salt (`secrets.token_hex`), explicit `TEST_FIXTURE` salt mode, salted `truth_commitment` byte-identical with `gen/truth.py`, and constant-time `verify_reveal` (`hmac.compare_digest`).
   - `seal/hashchain.py` — Domain-separated wall-clock-free `TrajectoryEvent` chain (`h_0 = SHA256("twinledger:h0:v1|" + truth_commitment + "|" + episode_id)`, `h_{i+1} = SHA256(b"twinledger:event:v1|" + h_i + b"|" + canonical_bytes(event_i))`).
   - `seal/merkle.py` — Domain-separated binary Merkle tree (`0x00` leaf, `0x01` internal node, `0x02 || uint64_be(leaf_count) || top_node` size-bound root, RFC-6962 odd-leaf promotion without self-duplication).
   - `seal/receipt.py` & `seal/cli.py` — `receipt.schema.json`-valid receipt construction, batch Merkle sealing (`seal_receipt_batch`), and offline CLI (`python3 -m seal.cli verify-receipt`).

2. **Isolated `env` & post-termination `scorer` CLIs:**
   - `env/jsonl_server.py` — Canonical JSONL stdio server supporting `reset`, `step`, `export_state`, `shutdown`, and `--require-closed-eval` (preserving backward-compatible `serve_stream`).
   - `scoring/scorer_cli.py` — Dedicated post-termination subprocess (`score` and `seal-batch`) verifying public manifest SHA-256 digests, commit-reveal, trajectory hash chain, Official 2026-11-20 F1/return, and frozen v1.0.0 rational reward/diagnostics.

3. **Zone 2 `harness/` (`contracts` + stdlib only):**
   - `harness/sandbox.py` — `StagedPublicWorkspace` (`0o444`/`0o555`, 12 allowlisted `public/` files only, zero `sealed/`, rejects symlinks/dotfiles/`index_hints.json`), `IsolatedPolicyWorkspace` (empty `0o555` temp `cwd`), `build_sanitized_env`, POSIX soft `rlimit`s, and explicit `SecurityProfile` (`is_full_os_sandbox = False`).
   - `harness/protocol.py`, `harness/trajectory.py`, `harness/env_process.py`, `harness/policy_process.py`, `harness/scorer_process.py`, `harness/runner.py` — Full 3-subprocess `CLOSED_EVAL` coordinator with outbound leakage guard and hard `ScorerPrematureStartError` + monotonic nanosecond `ProcessLifecycleProof`.
   - `harness/reference_policies.py` — JSONL v1.0 `silent_v1`, `rule_auditor_v1`, `truncate_exhaust_v1`, and `malicious_probe_v1`.
   - `harness/replay.py` — Fresh-process clean-workspace replay CLI (`--episode-dir` / `--verify-suite`), wired into `make replay` and `judge/verify.py` (`RC-005`).

## 2. Task Completion Matrix

| Task | Description | Status | Evidence |
| --- | --- | --- | --- |
| 9.1 | Implement policy JSONL protocol | DONE | `harness/protocol.py`, `harness/policy_process.py`, `harness/reference_policies.py`, `docs/TASKS/T-09-01.md` |
| 9.2 | Implement harness and env subprocess | DONE | `harness/env_process.py`, `harness/runner.py`, `env/jsonl_server.py`, `docs/TASKS/T-09-02.md` |
| 9.3 | Implement scorer subprocess after termination | DONE | `harness/scorer_process.py`, `scoring/scorer_cli.py`, `docs/TASKS/T-09-03.md` |
| 9.4 | Add commit-reveal | DONE | `seal/commitment.py`, `tests/seal/test_commitment.py`, `docs/TASKS/T-09-04.md` |
| 9.5 | Add trajectory hash chain | DONE | `seal/hashchain.py`, `harness/trajectory.py`, `tests/seal/test_hashchain.py`, `docs/TASKS/T-09-05.md` |
| 9.6 | Add Merkle tree and receipt | DONE | `seal/merkle.py`, `seal/receipt.py`, `seal/cli.py`, `tests/seal/test_merkle_and_receipt.py`, `docs/TASKS/T-09-06.md` |
| 9.7 | Add replay command | DONE | `harness/replay.py`, `Makefile`, `judge/verify.py`, `tests/harness/test_replay.py`, `docs/TASKS/T-09-07.md` |
| 9.8 | Add platform-specific isolation profile | DONE | `harness/sandbox.py`, `tests/security/test_phase09_isolation.py`, `docs/TASKS/T-09-08.md` |

## 3. Mandatory Phase 9 Tests & Verification Gates

- `policy cannot read sealed` — PASS (`tests/security/test_phase09_isolation.py::test_malicious_policy_probe_blocked_and_zero_canary_leakage`)
- `env cannot read sealed` — PASS (`tests/security/test_phase09_isolation.py::test_staged_public_workspace_readonly_and_rejects_bad_entries` + `tests/env/test_environment.py::test_runtime_file_access_spy_never_touches_sealed_sibling`)
- `scorer only starts after environment ends` — PASS (`tests/harness/test_protocol_and_processes.py::test_scorer_premature_start_rejected` + `lifecycle.strictly_ordered == True`)
- `commitment verifies` — PASS (`tests/seal/test_commitment.py`)
- `trajectory mutation changes hash` — PASS (`tests/seal/test_hashchain.py` + `tests/unit/test_property.py::test_hashchain_single_event_mutation_always_detected`)
- `replay is byte-identical` — PASS (`tests/harness/test_replay.py` + `python3 -m harness.replay --verify-suite`: 5/5 byte-identical)
- Clean-workspace EXIT GATE 9 (`rm -rf episodes/*/*/sealed && make lint && make test-property && make replay && make verify && make report`) — **PASS** (`exit 0`, 295 unit/integration tests + 5 property suites + `RC-001..RC-005` PASS).
- `make docker-check` — **NOT RUN** (Docker daemon/CLI not installed in sandbox).
