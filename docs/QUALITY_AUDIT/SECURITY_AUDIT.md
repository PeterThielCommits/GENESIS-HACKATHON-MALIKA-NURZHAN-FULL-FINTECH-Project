# SECURITY_AUDIT — TwinLedger v3.0

No absolute security claims are made. Every statement below is a **measured
observation** with the command that produced it, or a **residual risk** that is
explicitly left open.

## S-1 Attack-surface inventory (runtime code, excluding tests/tools)

| Surface | Check | Result |
|---|---|---|
| Dynamic code execution | `grep -rn "\beval(\|\bexec(\|pickle\|marshal\|os.system\|shell=True"` over runtime tree | **0 hits** |
| Calculator | AST-only `Decimal` arithmetic; `__import__`, `open(...)`, `'; OR 1=1 --'` | `CALC_ERROR` for all, nothing executed |
| Arbitrary file read | `get_document('/etc/passwd')`, `get_document('../../../sealed/truth.json')` | `NOT_FOUND` both |
| SQL injection | calculator expression `' OR 1=1 --` | `CALC_ERROR`; no SQL engine in the tree |
| Network | no `socket`/`urllib`/`requests` in runtime path; Docker runs `--network=none` | no egress path in code |
| Hidden tables | `list_records(table='truth')`, `table='sealed'` | `BAD_ARGS` |
| Secrets in repo | `grep -rniE "aws_secret\|api_key\s*=\s*['\"]\|password\s*=\s*['\"]\|BEGIN RSA\|Bearer [A-Za-z0-9]{20}"` | 1 hit, a **test fixture string** in `tests/judge/test_release_audit.py` that builds a synthetic private-key marker to test the scanner |

## S-2 Truth / provenance containment (official C20)

The strongest requirement in the case is that the policy process must never
see truth, provenance, seeds or scorer answers. Verified at three levels:

**Behavioural (measured).** Across all records, documents, error paths and
`info`:

```
list_records / get_record / get_document over every table  -> no 'truth', 'provenance', 'issue_id', 'sealed' in any observation
closed-mode submit                                         -> reward == 0 (int) on every step incl. terminal
info keys in closed mode                                   -> ['mode', 'step'] only
train-mode terminal                                        -> reward returned (0.998) — by design, and only in train
```

**Structural.** `judge_adapter.score_episode` and
`generate_episode` live on the judge side; the policy receives only
`{"result","error","remaining_steps"}`. `sealed/` is never loaded by
`adapter/official_env.py` (it loads `public/` + `manifest.json` only).

**Packaging.** `.dockerignore` excludes `episodes/sealed/`,
`episodes/*/sealed/`, `episodes/*/*/sealed/`, `episodes/hidden/` (fixed in the
previous phase — `episodes/*/sealed/` alone did **not** match the real depth-2
layout). `make release-audit` FILELIST re-checks this: 498 tracked files, 0
forbidden paths.

## S-3 Cursor tamper evidence (BUG-TL-0003, fixed)

| Attack | Old behaviour | Now |
|---|---|---|
| Flip a signature byte | rejected | rejected (`BAD_CURSOR`) |
| Flip a payload byte | rejected | rejected |
| Reuse cursor on another table | rejected | rejected |
| Reuse cursor with different filters | rejected | rejected |
| Truncated / empty / non-string token | rejected | rejected |
| **Append `"x"` / `"xy"` / `"="` / `".."`** | **ACCEPTED** (decoded to original bytes) | rejected |
| **Non-canonical trailing base64 bits** | **ACCEPTED** | rejected |

Fix: decode requires the token to re-encode to itself byte for byte. This is
one rule that covers trailing garbage, alternate alphabets, stray padding and
non-canonical trailing bits. Round-trip proven for offsets 0–999 (1000/1000).

## S-4 Sandboxing of the policy process

`harness/sandbox.py` + `harness/ns_launcher.py` provide kernel-level isolation
(`wrap_argv_with_kernel_sandbox`), used by
`harness/isolated_runner.run_isolated_public_policy`. The README states
explicitly that Python-level field hiding is **not** treated as isolation.

Residual risk, stated openly: if the judge calls `make_env()` in-process and
runs the policy in the same interpreter, isolation is only as strong as the
process boundary the judge chooses. The official protocol puts the policy in a
separate restricted process; the repo documents the same requirement and
ships the launcher, but this audit did **not** measure the isolation strength
under a hostile kernel-level attacker.

## S-5 DoS / resource limits

| Limit | Value | Enforced in |
|---|---|---|
| Episode wall clock | 60 s | `adapter/official_env.py`, `harness/isolated_runner.py` |
| Step budget | 100 actions | `adapter/official_env.py` |
| Input file size | 16 MiB | `contracts/loader.py::read_text_bounded` |
| Input row cap | 100 000 | `contracts/loader.py::check_row_cap` |
| Page size | 1–50 | `env/cursors.py` + env |
| Calculator expression | length + AST node caps | calculator module |
| Submit findings | 30 | `scoring/official_scorer.py` |
| Evidence IDs per finding | 10 (pre-dedup) | `scoring/official_scorer.py` |
| Explanation | 1000 code points | `scoring/official_scorer.py` |

All caps were chosen against measured workloads (largest public file ~27 KiB,
largest table 292 rows) with 20×–500× headroom.

## S-6 Residual risks (open, not claimed solved)

1. **Kernel-level isolation strength not measured** (S-4).
2. **No penetration test** was performed; the attack list above is
   requirement-driven (what the official C20 asks) plus a secrets grep, not a
   general adversarial review.
3. **`canary_fuzz_report.json` PASS** covers 10 channels × 9 encodings ×
   17 variant patterns × 3 tokens = 0 hits. That is a measured negative, not a
   proof that no encoding can leak.
4. **Docker hardening unverified in this sandbox** — `make docker-check`
   cannot run (no `docker` binary); the Dockerfile's `--read-only`,
   `--cap-drop ALL`, `--network=none`, non-root `uid=10001` flags are reviewed
   but not executed here.
5. Frozen contracts still contain a now-unused `eta: 0.05` key (D-18-01). It
   is not a security issue but is a documented inconsistency.
