# Threat Model (Phase 9 — Process Separation, Sealed Evaluation & Receipts)

## Trust boundaries

| Boundary | Trusted side | Untrusted / restricted side | Enforced control |
| --- | --- | --- | --- |
| Policy ↔ Environment | `env` subprocess (`env.jsonl_server`) | `policy` subprocess | Separate OS processes; JSONL v1.0 pipe only; empty `0o555` scratch `cwd`; sanitized env allowlist; `close_fds=True` (REQ-ARC-004, REQ-SEAL-002, REQ-SEAL-004) |
| Environment ↔ Sealed truth | Post-episode `scorer` subprocess (`scoring.scorer_cli`) | `env` & `policy` subprocesses | `StagedPublicWorkspace` copies ONLY the 12 allowlisted `public/` files (`0o444`/`0o555`) with zero `sealed/`, `manifest.json`, symlinks, or dotfiles; `scorer` starts strictly after `policy` + `env` exit (`ScorerPrematureStartError`, REQ-ARC-005, REQ-SEAL-001, REQ-SEAL-003) |
| Generator ↔ Verifier | Independent audit | Common-mode bug | Separate modules (`gen/` vs `verifier/`), AST import check, Stage-2 `scoring/crosscheck.py` (REQ-ARC-001..002) |
| Benchmark ↔ Post-hoc tampering | Offline auditor (`seal.cli`) | Operator / runner | Salted truth commitment (`seal/commitment.py`), wall-clock-free trajectory hash chain (`seal/hashchain.py`), size-bound RFC-6962 Merkle receipt (`seal/merkle.py`, `seal/receipt.py`), fresh-process replay (`harness/replay.py`) |

## Threats & mitigations

- **T1 Direct file read of `sealed/truth.json` or `provenance.json`:** Mitigated by `StagedPublicWorkspace` (never stages `sealed/`) and `IsolatedPolicyWorkspace` (empty `0o555` temp `cwd` outside repository tree) plus AST import-boundary scan (`tools/check_import_boundaries.py`). Verified in `tests/security/test_phase09_isolation.py`.
- **T2 Environment variable or open FD leakage:** Mitigated by `build_sanitized_env` (strict minimal allowlist; strips `SECRET`, `TOKEN`, `SALT`, `CANARY`, `SEED`, `TRUTH`) and `subprocess.Popen(..., close_fds=True)`.
- **T3 Premature scorer execution or reward oracle in `CLOSED_EVAL`:** Mitigated by `--require-closed-eval` (`reward: null` on `submit`) and `ScorerPrematureStartError` barrier + monotonic nanosecond `ProcessLifecycleProof` (`env_exited_ns <= scorer_started_ns`).
- **T4 Path traversal via `get_document` / `get_record`:** Mitigated by typed-ID lookup against pre-loaded allowlisted public tables and outbound leakage guard (`assert_policy_outbound_clean`).
- **T5 Code injection via `calc`:** Mitigated by safe AST whitelist + length/depth caps (`env/calc.py`, REQ-ENV-013) + no `eval`.
- **T6 Resource exhaustion / oversized JSONL frames:** Mitigated by `MAX_JSONL_LINE_BYTES = 65_536`, `max_steps`, `max_page_size`, monotonic episode timeout, and best-effort POSIX soft `RLIMIT_CPU` / `RLIMIT_FSIZE` / `RLIMIT_NOFILE`.
- **T7 Shortcut exploitation on clean/anomalous episodes:** Mitigated by clean twins (`REQ-DATA-020`), salted `truth_commitment` (`REQ-SEAL-010`), opaque HMAC cursors, and hash-derived entity IDs without anomaly labels.
- **T8 Post-hoc tampering of truth, trajectory, public snapshot, or batch receipts:** Mitigated by `verify_reveal` (`hmac.compare_digest`), SHA-256 manifest verification, `verify_hash_chain`, size-bound Merkle inclusion proofs (`0x00`/`0x01`/`0x02`), and `python3 -m harness.replay`.

## Residual limits (honesty note — Master TZ P-012 / Risk R-09)

Plain POSIX subprocess isolation (`SecurityProfile.is_full_os_sandbox == False`) is **not** a kernel mandatory-access-control (MAC) sandbox against arbitrary native code execution if a hostile binary knows absolute host paths outside its scratch `cwd`. Full filesystem mount-namespace hiding, `--network=none`, and syscall filtering require outer containerization (`Dockerfile` / `docker-compose.yml`, Phase 13 `make docker-check`).
