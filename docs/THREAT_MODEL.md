# Threat Model (Release v1.0.1 — Kernel-Sandboxed Sealed Evaluation & Anti-Leakage)

## 1. Assets Protected
- **Sealed Ground Truth & Salts:** `episodes/*/*/sealed/truth.json`, `provenance.json`, and 256-bit `PRODUCTION_SECRET` commitment salts (`seal/rekey.py`).
- **Scoring & Lifecycle Integrity:** Official matcher/reward (`scoring/`), trajectory hash chains (`seal/hashchain.py`), and size-bound RFC-6962 Merkle batch receipts (`seal/merkle.py`).
- **Evaluation Fairness:** Prevention of metadata shortcuts (`AUC <= 0.55`), prompt-injection hijacking, and post-submission tampering.

## 2. Trust Boundaries & Enforced Controls

| Boundary | Trusted Side | Untrusted / Restricted Side | Enforced Controls |
| --- | --- | --- | --- |
| `POLICY` ↔ `ENV` | `env.jsonl_server` | External `policy` process | Separate OS process; JSONL v1.0 over stdin/stdout only; Linux `unshare --user --map-root-user --net --mount` + `harness.ns_launcher` masking `episodes/`, `episode_dir`, and staged `env` dir with read-only `tmpfs`; read-only `tmpfs` `cwd` (`EROFS`); `PR_SET_NO_NEW_PRIVS` + `seccomp-BPF` blocking `socket`/`mount`/`umount2`/`pivot_root`/`ptrace`/`process_vm_*`; sanitized env allowlist; `close_fds=True` |
| `ENV` ↔ `sealed/` | Post-episode `scorer` (`scoring.scorer_cli`) | `env` & `policy` processes | `StagedPublicWorkspace` copies ONLY the 12 allowlisted `public/` files (`0o444`/`0o555`) with zero `sealed/`, symlinks, or dotfiles; kernel mount namespace masks repository `episodes/`; `ScorerPrematureStartError` + monotonic nanosecond `ProcessLifecycleProof` (`env_exited_ns <= scorer_started_ns`) |
| `gen/` ↔ `verifier/` | Independent Stage-1 discovery | Common-mode generator bug | Disjoint AST import zones (`tools/check_import_boundaries.py`: `verifier` imports neither `gen` nor `nlp`); Stage-2 `scoring/crosscheck.py` attestation (`semantic_truth_verification: VERIFIED`) |
| Untrusted Document Text ↔ Policy | Structured accounting tables | Free-text descriptions/memos | `nlp/injection_guard.py` + 4-tier evidence hierarchy (`nlp/hierarchy.py` rejecting Tier-4 text-only proof); paired prompt-injection twin audit (`judge/robustness_audit.py`) |
| Container Host ↔ Evaluation Run | Judge host | Containerized run | `Dockerfile` (`python:3.11-slim-bookworm`, non-root UID `10001`), `docker-compose.yml` (`network_mode: none`, `read_only: true`, `cap_drop: [ALL]`, `no-new-privileges:true`), CI `docker-offline` job |

## 3. Red-Team & Fuzzing Verification Evidence
- **Live Malicious Policy Probe (`tests/security/test_phase09_isolation.py`):** Even when handed the exact host path to `sealed/truth.json`, `malicious_probe_v1` observes `cwd_empty=True`, `cwd_writable=False`, `env_leaks=0`, `sealed_found=False`, `net_blk=True`, `umnt_blk=True`, `trav_blk=True`, `calc_blk=True`.
- **10-Channel Canary & API Fuzzer (`judge/canary_fuzzer.py`):** 0 canary hits across 10 policy-visible channels and 9 encoding transforms. The channel and transform lists are read directly from source and asserted against this page by `tools/verify_doc_claims.py` (`C-CANARY-CHANNELS`, `C-ENCODING-TRANSFORMS`); measured hit counts live in `canary_fuzz_report.json`.
- **22-Attack Red-Team Catalog (`arena/attacks/catalog.py`):** `AT-01..AT-22` all defended (`reward_strategy_report.json`).
