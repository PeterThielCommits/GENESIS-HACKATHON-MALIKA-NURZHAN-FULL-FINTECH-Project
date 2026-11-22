# Measured Failure Analysis & Re-Verification

This document records concrete, reproducible failures measured during the
integration of TwinLedger with the Genesis FinTech 2026-11-20 verification
suite, their root causes, and re-verification measurements after fixing (or
explicitly bounded limits where intentional).

---

## Failure Case 1 — Cross-Check Divergence on `D13_fx_inverse_operation_date` (Fixed & Re-Verified)

### Measured Failure (Before Fix)
When generating the 20 closed scenarios `D01..D20` (`master_seed=2026`) and
running the independent zero-common-mode verifier (`verifier/discover.py`) +
crosscheck (`scoring/crosscheck.py`):

- `D01..D12`: `12/12 PASS` (`FP=0, FN=0, F1=1.0000000`)
- **`D13_fx_inverse_operation_date` (`rate_date_rule="operation_date"`, `quote_convention="foreign_per_functional"`, `rounding_mode="half_up"`):**
  - **Measured result:** `TP=0, FP=5, FN=1, precision=0.0000000, recall=0.0000000, F1=0.0000000`, `release_blocked=True`.

### Root Cause
1. Per `spec/policy_semantics.md` and `verifier/fx_mismatch.py:52`, when
   `fx_policy.rate_date_rule == "operation_date"`, the permitted FX rate date is
   the journal entry operation timestamp (`je["timestamp"]` converted to company
   timezone), and the minimal evidence set is `{FX:<fx_id>, JE:<je_id>}`.
2. In `gen/core/clean_twin.py` and `gen/errors/operators.py`, the generator
   erroneously mapped `"operation_date"` to `inv["service_start"]` instead of
   `je["timestamp"]`, causing all 5 clean foreign-currency journal entries in
   `D13` to be converted with the `service_start` date rate rather than the
   journal operation date rate (5 false positives in verifier) and causing the
   injected truth evidence/delta to disagree with the verifier (1 false negative).

### Fix & Re-Verification (After Fix)
- Updated `gen/core/clean_twin.py` (`fx_target` for `operation_date` uses `je_ts`)
  and `gen/errors/operators.py` (`events["operation_date"] = je["timestamp"]` and
  minimal evidence set `[FX:<id>, JE:<id>]`).
- **Re-verification measurement (`tests/official/test_block2_episodes.py`):**
  - `D13_fx_inverse_operation_date`: `TP=1, FP=0, FN=0, F1=1.0000000` (`PASS`).
  - Full `D01..D20` matrix: **`20/20 PASS` (`FP=0, FN=0, F1=1.0000000`)**.

---

## Failure Case 2 — Baseline Policy Failure Modes on `D01..D20` (Measured)

All four baseline policies were evaluated across the identical 20 closed
scenarios (`master_seed=2026`, 80 total episodes, OS-isolated subprocesses for
public policies, logged in `artifacts/trajectories/trajectories.jsonl`):

| Policy | Clean (`D01..D05`) Mean Return | Single-Error (`D06..D15`) Mean Return | Interaction (`D16..D20`) Mean Return | Overall Mean F1 | Overall Mean Return |
|---|---:|---:|---:|---:|---:|
| `oracle` | `+0.9920` | `+0.9920` | `+0.9920` | `1.0000` | `+0.9920` |
| `simple_reconciliation` | `+0.9860` | `+0.9854` | `+0.9844` | `1.0000` | `+0.9853` |
| `random` | `+0.9760` | `-1.0000` | `-1.0000` | `0.2500` | `-0.5060` |
| `mass_flagging` | `-1.0000` | `-1.0000` | `-1.0000` | `0.0000` | `-1.0000` |

### Failure Analysis by Policy
1. **`random` (`mean_F1=0.2500`, `mean_return=-0.5060`):**
   - Succeeds only on the 5 clean episodes (`D01..D05`) because submitting empty
     findings satisfies the clean-book rule (`TP=FP=FN=0 -> F1=1`, return
     `1 - 0.2 * 12 / 100 = +0.9760`).
   - Fails completely on all 15 anomalous episodes (`D06..D20`, `FN >= 1 -> F1=0`,
     clipped `return=-1.0`).
2. **`mass_flagging` (`mean_F1=0.0000`, `mean_return=-1.0000`):**
   - Submits 28 structurally valid findings across the first 7 ledger entries
     (all 4 anomaly types). Even when an entry coincides with a true anomaly,
     missing required evidence sets (e.g. `INV`, `FX`, `PAY`) plus 27+ false
     positives drive `F1` near `0` and clip `return` to `-1.0`.
   - Independently corroborated by Block 3 vector #12 (`TP=1, FP=19, FN=0 ->
     F1=2/21, return=-871/1050 ≈ -0.8295`), proving reward resistance to shotgun
     flagging.

---

## Failure Case 3 — Reproducible Structural & Budget Limits (Verified Bounds)

The following reproducible failure boundaries were measured and locked via unit
tests in `tests/official/test_block1_contracts.py` and `test_block3_scorer.py`:

1. **Step-budget boundary (`C16` vs `C17`):** 99 inspection calls + `submit` on
   action 100 is accepted (`terminated=True, inspection_steps=99`); 100
   inspection calls without `submit` truncates with frozen empty findings
   (`truncated=True`, late `submit` rejected with `ALREADY_TERMINATED`).
2. **Pre-deduplication structural caps (`Block 3 #18..20`, `M05`, `M09`):**
   31 findings, 11 `evidence_ids` (even when 10 are duplicates of `D1`),
   1001-code-point `explanation`, or string/boolean `claimed_amount_minor` all
   deterministically return `{"tp": None, "fp": None, "fn": None, "precision":
   None, "recall": None, "f1": None, "return": -1.0}`.
3. **Unreachable evidence injection (`M04`):** Appending a single non-existent
   `evidence_id` `U` alongside a valid evidence set `{D1, D2}` deterministically
   prevents matching (`TP=0, FP=1, FN=1, return=-1.0`).
4. **Pagination budget ceiling for `simple_reconciliation` (unremediated design
   limit):** Because `simple_reconciliation` performs full sequential table scans
   at `limit=50`, on synthetic books whose combined rows across the 6 scanned
   tables exceed `99 * 50 = 4,950` rows, it exhausts its inspection budget before
   reading all records and submits partial findings at `remaining_steps == 1`.

---

## Failure Case 4 — Container Hardening Failures Found by Measuring the Real Build Context (Phase 18, Fixed & Re-Verified)

This case is *measured failure analysis in the strict sense*: the failures were
reproduced with a measurement, the cause was identified, the fix was applied,
and the same measurement was repeated afterwards.

### Measured failure (before the fix)

| # | Failure | Measurement | Consequence |
|---|---|---|---|
| F1 | `.dockerignore` rules are root-anchored in Docker | effective build context = **750 files**, of which **197** were stale `.pyc` files from nested `__pycache__` directories | the image was not reproducible; stale bytecode shipped; nested `*.pem`/`.env` would ship too |
| F2 | the base image was a floating tag | `FROM python:3.11-slim-bookworm` - no digest anywhere in the repository | TZ 22.4 ("pin the base image digest") unmet; the Python patch version inside the image was undefined |
| F3 | the Compose profile had no process/file-size limits and one unwritten path | no `pids_limit`, no `ulimits`, no `/app/artifacts/reports/doc_claims` tmpfs; **nothing in the repository parsed the file** | TZ 16.2 resource limits unenforced; a judge starting the profile would hit a read-only write |
| F4 | the dependency audit matched the Dockerfile with a literal substring | `RC-012 FAIL` while the measured facts were inside their targets (`step_p99=0.09ms < 5ms`, `peak_rss=22.4MB < 300MB`) | a release gate that measured a *spelling* instead of the property |

The reproduction of F1 is deterministic and is now a test:
`tools/docker_context.py` computes the effective context with Docker's own
path semantics, so the "before" number (750 files / 197 `.pyc`) can be
re-derived from the old rules at any time.

### Root cause

The container artifacts (`.dockerignore`, `Dockerfile`, `docker-compose.yml`)
were the only parts of the repository that **nothing executed**. CI ran
`docker build` and `docker run` (so the Dockerfile was exercised), but the
build-context rules and the Compose profile were only ever read by eye - and
the two tools that *did* parse files (`tools/check_workflows.py` for the
workflows, `judge/performance_and_deps.py` for the Dockerfile) used literal
substring matches that no longer described the intent.

### Fix & re-verification (after the fix)

| # | Measurement before | Measurement after | Test that locks it |
|---|---|---|---|
| F1 | 750 context files, 197 stale `.pyc` | **556 context files, 0 stale `.pyc`**, no sealed path, no key material | `tests/judge/test_docker_hardening.py` (7 context tests) |
| F2 | no digest | `python:3.11-slim-bookworm@sha256:a36c24f9...` pinned in the Dockerfile, recorded in `docs/EVIDENCE/docker-build-info.json`, reported by the CI job `base-image` | `test_dockerfile_pins_the_base_image_by_digest`, `tools/release_audit.py` |
| F3 | no limits, unparsed file | every service declares `pids_limit` + `fsize` ulimit; `tools/check_compose_profile.py` fails on any violation and runs in `make lint` | `TestComposeProfile` (6 tests) |
| F4 | `RC-012 FAIL` (false negative) | `RC-012 PASS`, `dockerfile_base_image_digest_pinned: true` | `judge/performance_and_deps.py` + `test_static_verify_passes_for_the_committed_state` |

### The measurement that could not be taken locally — and what replaced it

The strongest measurement of the container contract is `docker build` +
`docker run` on a host with a container runtime and a registry. The execution
host has neither (`docker`, `podman`, `buildah`, `nerdctl`, `ctr`, `runc`,
`containerd` absent; `registry-1.docker.io`, `ghcr.io`, `quay.io` unreachable
- probed 2026-11-22), so that measurement is taken by the CI job
`docker-offline`, and **only** by it.

What replaced it locally is the container-equivalent run
(`tools/container_local_check.py`, `make container-local-check`): the image is
materialised from the build context and `make verify` runs as uid 10001 with
no capabilities, `no_new_privs`, a read-only tree and tmpfs over the writable
paths. Measured: PASS, 12/12 gates inside the sandbox, 20 artifacts
identical in name to the host run. It is explicitly **not** a Docker build,
and `docs/LIMITATIONS.md` (L9) says so.

## Failure Case 5 — A Green CI Run That Hid a Failed Step (Phase 18 close-out, Fixed & Re-Verified)

### Measured failure (before the fix)

The `docker-offline` job of every successful CI run carried a
`Process completed with exit code 1` annotation while the job's conclusion was
`success`. The step timings showed the failing step: the container-equivalent
step's start and completion timestamps were identical (zero seconds), while a
genuine execution takes 87–154 seconds.

| Measurement | Result |
|---|---|
| CI step duration (successful jobs `137280266858`, `137282565423`, `137290242282`) | **0 s** |
| Genuine local run of the same tool | **156.9 s** (`make verify` inside the sandbox: 153.6 s, 12/12 gates) |
| Same tool with the namespace refused | **1.2 s**, exit 1 |

### Root cause

Three defects compounded (`BUG-TL-0015..0017`, `D-18-04`):

1. the tool classified a host that forbids unprivileged user namespaces as a
   generic **FAIL** — the same class of error as "the image is broken", when
   in fact the host had proven nothing about the image;
2. the workflow masked the exit status twice (`continue-on-error: true` and
   `|| true`), so the failure was visible only as an annotation on a green
   job;
3. the `publish` subcommand of the provenance tool was unreachable dead code
   and crashed with an `AttributeError`; the step named "Publish the image
   build provenance" had never published anything, and its drift comparison
   never ran.

The trigger is Ubuntu 24.04's AppArmor policy
`kernel.apparmor_restrict_unprivileged_userns=1`, which refuses
`unshare --map-root-user --mount --net` with `Operation not permitted`.

### Fix & re-verification (after the fix)

* a capability probe distinguishes an environmental refusal (an explicit skip,
  exit code 2, with the reason recorded) from a real failure (exit code 1);
* the CI step has no mask: `0` = PASS, `2` = SKIPPED with a `::notice::`
  annotation and a job-summary line, anything else = `::error::` **and a
  failed step**;
* `tools/check_workflows.py` enforces the policy statically, so neither
  construct can reach a push;
* `tests/judge/test_ci_masking.py` (28 tests) reproduces each defect on the
  old code.

Re-verified locally: a refused namespace now yields `UNSUPPORTED` with exit
code **2** (was `FAIL` with exit code 1); the repository's own workflows pass
the masking policy; `publish` runs the publisher instead of crashing.

## Failure Case 6 — The Regression Suite Could Not Run Inside the Hardened Container (Phase 18 close-out, Fixed & Re-Verified)

### Measured failure (before the fix)

The first CI run of the masking fix made the `docker-offline` job **red** —
which is the fix working: the failure is now visible instead of hidden. The
job log carried the real stderr:

```
Ran 653 tests in 64.948s | FAILED (failures=2, errors=4, skipped=25)
```

The cause was in the new regression suite itself, not in the image.

### Root cause

The test that simulates "a host that refuses unprivileged user namespaces"
wrote a fake `unshare(1)` script into a temporary directory and executed it.
The offline container mounts its temporary directory **`noexec`**
(`--tmpfs /tmp:rw,noexec,nosuid,mode=1777,size=256m`), so the execution
raised `PermissionError` instead of running the script:

```
PermissionError: [Errno 13] Permission denied: '/tmp/.../unshare'
```

Reproduced locally against a `noexec` tmpfs with the identical exception.

### Fix & re-verification (after the fix)

* the tool exposes `_run_command()` as a seam, and the tests replace the
  *call* instead of the *binary* — no test writes or executes anything;
* a non-executable `unshare` is now classified like a missing one: an
  environmental refusal, i.e. an explicit skip;
* `test_no_test_makes_a_temporary_file_executable` keeps the trap closed.

Re-verified locally against the same condition: the full suite passes with
`TMPDIR` on a `noexec` tmpfs, both directly and inside the
container-equivalent sandbox (read-only tree, uid 10001, `CapEff 0`,
`no_new_privs`, no network) — 12/12 gates.

The same CI run also confirmed the positive half of the masking fix: with
`kernel.apparmor_restrict_unprivileged_userns=0` applied to the runner, the
container-equivalent step executed the **real 70-second namespace run and
passed** — the validation that was impossible in CI now runs there.
