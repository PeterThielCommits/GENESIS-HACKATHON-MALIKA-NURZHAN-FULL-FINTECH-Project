# FINAL_QUALITY_REPORT — TwinLedger v3.0 forensic audit

Branch `arena/45dc3a73-genesis-hackathon-malika-nurzh`, base `3a3988e`.
`official_score_claimed: false`.

> **Correct statement of what was achieved:** every defect found in this audit
> is handled, each with a regression test that fails on the old code.
> This is **not** a claim that no bugs remain.

---

## 1. Scope actually covered

| Area | Method | Outcome |
|---|---|---|
| Input files | hashed, diffed, read in full | official checks were already vendored (byte-identical) |
| Official Block 1 (C01–C20) | executed the contract directly, not just the tests | **1 P0 defect** (C05) |
| Official Block 2 (D01–D20) | 20 episodes, independent verifier + oracle submit | no defect |
| Official Block 3 (vectors + M01–M12) | recomputed 11 reward vectors and all 12 examples by hand | **1 P0 defect** (formula) |
| Official Block 4 (P01–P20) | paired transform matrix, 25 assertions | no defect |
| Adapter interface | direct calls: 3 exports, invalid submit, train/closed split | no defect |
| Matcher conventions | normalisation 1–8, τ, max-cardinality, tie-break | no defect |
| Step accounting | C14/C16/C17, 99+submit, 100 without submit | no defect |
| Time limit | 59.9 / 60.0 / 61.0 s with a deterministic clock | no defect |
| Isolation / leakage | 7 attack vectors + 20-fixture scan + code review | no direct leak; 1 tamper-evidence weakness |
| Security | eval/exec/secrets scans, resource caps | no critical finding |
| Dependencies | 109 modules, 0 external | no defect |
| Determinism | 80/80 replay, artifact regeneration diff | no defect |
| Reproducibility | clean `git archive`, no git, empty artifacts | PASS |
| Performance | same harness before/after | no regression |

## 2. Defects found and their status

| ID | Sev | Summary | Status |
|---|---|---|---|
| BUG-TL-0001 | P0 | Two competing reward implementations; the internal one used the superseded provisional formula and failed 10/11 published vectors | **VERIFIED FIXED** |
| BUG-TL-0002 | P0 | Pagination cursors unusable for ~6.5% of offsets; L-fixture ledger stalled at 150/214 rows (official C05) | **VERIFIED FIXED** |
| BUG-TL-0003 | P1 | Trailing base64 garbage accepted; a valid token plus `"x"` passed signature verification | **VERIFIED FIXED** |
| BUG-TL-0004 | P1 | Official C05 test walked only `invoices`, so it could not see BUG-TL-0002 | **VERIFIED FIXED** |

Plus one process defect recorded rather than hidden: three mutation mutants
were silently disarmed by the reward refactor (23/26 → 26/26 after re-arming).

## 3. Release gates A–I

| Gate | Command | Result |
|---|---|---|
| A. Compliance | Block 1–4 suites + manual probes | VERIFIED (`RUBRIC_COMPLIANCE.md`) |
| B. Core correctness | 502 tests + 55 official + mutation 26/26 | PASS |
| C. Security | `SECURITY_AUDIT.md`, RC-009 canary 0 hits, 7 attack vectors bounded | PASS with 5 documented residual risks |
| D. Determinism | `make replay-all` 80/80, 567 steps | PASS |
| E. Quality | `make lint` CLEAN, `make verify` 12/12 | PASS |
| F. Performance | p99 0.125 ms (target <5), RSS 22.4 MB (<300) | PASS |
| G. Infrastructure | `make release-audit` 6/6; **`make docker-check` UNVERIFIED** | PARTIAL |
| H. Documentation | `make docs-verify` PASS (22 facts, 11 checks) | PASS |
| I. GitHub | branch pushed; CI result recorded in `FINAL_GITHUB_REPORT.md` | see that file |

Gate G is **PARTIAL**, not PASS: the Docker binary is absent in this
environment, so the offline hardened image was not executed here.

## 4. Measured state at end of audit

```
tests            502 (18 documented bootstrap skips)
official tests   55
mutation         26/26 killed
metamorphic      7/7 transforms, 28 episode pairs
replay           80/80 runs, 567 steps byte-identical
judge kit        12/12 RC gates PASS (~72 s)
clean extract    12/12 RC gates PASS in 65.8 s (no git, empty artifacts)
release audit    6/6, 498 files, 5,530,451 bytes, 0 external imports
freeze           30 files intact, aggregate_sha256 0747baf0...
baselines        oracle 1.0000/+0.9920/4.0 · simple 1.0000/+0.9853/7.3
                 random 0.2500/−0.5060/12.0 · mass_flagging 0.0000/−1.0000/1.0
```

## 5. Remaining limitations (explicit, not hidden)

1. **Docker verification not executed here** — no `docker` binary. The
   hardening flags are reviewed, not run. UNVERIFIED.
2. **Kernel-level isolation strength not measured.** The repo ships
   `harness/sandbox.py` and documents that Python-level hiding is not
   isolation, but no hostile-escape test was performed.
3. **No penetration test.** The security attack list is requirement-driven.
4. **`canary_fuzz` PASS is a measured negative**, not a proof of no leakage
   across all encodings.
5. **Property tests are seeded**, not exhaustive. Hypothesis is optional and
   skipped.
6. **Frozen config still carries `eta: 0.05`** (D-18-01). It no longer
   influences the reward, but it is a stale key in a frozen file.
7. **`scoring/reward.py` remains as a compatibility shim.** Callers in
   `arena/`, `judge/mutation_suite.py`, `judge/robustness_audit.py` could move
   to `official_scorer` directly; not done because it exceeds this audit's
   safe scope.
8. **tzdata drift** across machines could move a period boundary. Not
   measured.
9. **Jury hardware timing** is not ours to measure; the harness caveat stands.
10. **Phase 17 not started** (not authorised).

## 6. What would have happened without this audit

- Official Block 3 would have been scored against the published formula by
  `official_scorer` (correct) — so the *jury-facing* score was never wrong.
- Official **C05 would have failed** on the shipped L fixture: 64 of 214
  ledger rows unreachable with `BAD_CURSOR`. That is 1 of 20 contract tests
  (worth up to 1.25 of 25 points) plus the credibility of the pagination
  claim.
- Internal artifacts would have kept publishing a reward scale that does not
  exist in the rubric.
- A tamper-evidence weakness would have remained, protected by a test that
  passed by luck.

The C05 defect is the one that would have cost points directly.
