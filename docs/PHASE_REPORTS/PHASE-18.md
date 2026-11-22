# Phase 18 — Container Hardening: Pinned Base Image, Computed Build Context, Local Container-Equivalent Run

**Outcome: DONE.** The submission image is now a *pinned artifact*, the build
context is a *computed* object instead of a guess, and the local host finally
produces real evidence about the container contract instead of only reading
the Dockerfile.

- Date: 2026-11-22
- Branch: `arena/87691cc0-genesis-hackathon-malika-nurzh`
- Base: `f3af314` (merge of PR #30, release `v1.0.2`)
- Master TZ v3.0.0 §22.4 (Docker: reproducible build, pinned base image digest,
  Python patch version, package versions, commands; network disabled; non-root),
  §22.5 (CPU 2 / RAM 4 GB, offline execution), §16.2 (real security boundaries,
  resource limits), §24 (release procedure)
- `official_score_claimed: false` (TZ §23.6)
- Frozen contract files changed: **none** (`freeze_release --verify` → 30 files,
  `0747baf0…`)
- Benchmark behaviour changed: **none** (no runtime code of the benchmark was
  touched; the changes are the container surface, its audits and the docs)

---

## 1. Why this phase existed

The task was explicit: run a **real** local Docker build and hardened offline
container verification, and audit the repository against the competition
criteria to completion. The first half of that request could not be satisfied
literally on this host, and the honest answer had to be found rather than
asserted:

```
docker        -> not found        podman      -> not found
buildah       -> not found        nerdctl     -> not found
ctr / runc    -> not found        containerd  -> not found
/var/run/docker.sock -> absent
registry-1.docker.io / ghcr.io / quay.io -> unreachable (TLS handshake refused)
```

So the image **cannot** be built here: the base image cannot be pulled. What
*can* be done locally is everything the image does apart from the pull - and
that is most of the contract. This phase therefore:

1. **fixed the container artifacts** where they did not meet TZ §22.4/§16.2;
2. **made the build context computable**, so the thing the image ships is
   measured rather than assumed;
3. **built the strongest local equivalent of the container run** that the host
   allows, and labelled it exactly for what it is.

## 2. What was broken (measured, not suspected)

| ID | Defect | Measurement before |
|---|---|---|
| BUG-TL-0010 | `.dockerignore` patterns are **root-anchored** in Docker | effective build context = **750 files**, **197** of them stale `.pyc` files |
| BUG-TL-0011 | the base image was a floating tag | no digest anywhere in the repository |
| BUG-TL-0012 | the Compose profile had no process/file-size limits and one unwritten path | no `pids_limit`, no `ulimits`, no `doc_claims` tmpfs, and **nothing parsed the file** |
| BUG-TL-0013 | the dependency audit matched the Dockerfile with a literal substring | `RC-012 FAIL` while every measured fact was inside its target |

The registry of defects, the root causes and the regression evidence are in
`docs/QUALITY_AUDIT/BUG_REGISTRY.md` (BUG-TL-0010..0013); the before/after
measurements are in `docs/FAILURE_ANALYSIS.md` (Failure Case 4).

## 3. What changed

| Area | Change | File |
|---|---|---|
| Base image | pinned by digest through a single `ARG BASE_IMAGE`; the image records its own provenance | `Dockerfile`, `docs/EVIDENCE/docker-build-info.json` |
| Build context | Docker's real anchoring rules implemented; the effective context is computed and asserted | `tools/docker_context.py`, `tools/container_local_check.py` |
| Compose profile | process/file-size limits, all writable paths on tmpfs, contract machine-checked | `docker-compose.yml`, `tools/check_compose_profile.py` |
| Container run | `--pids-limit 512`, `--ulimit fsize=…` | `Makefile` |
| Dependency audit | parses the declared base image instead of matching a string | `judge/performance_and_deps.py` |
| CI | new `base-image` job (digest + drift); `docker-offline` publishes the image's build record and runs the container-equivalent check informationally | `.github/workflows/ci.yml` |
| Tests | 22 new regressions, all failing on the old code | `tests/judge/test_docker_hardening.py` |

## 4. The local container-equivalent run

`make container-local-check` (`tools/container_local_check.py`):

1. computes the effective build context with Docker's own semantics and
   **refuses** to continue if it contains sealed truth, key material, VCS
   metadata or stale bytecode;
2. materialises the image (context + `compileall` + report directories);
3. runs the container's own command (`make verify`) inside unprivileged user,
   mount and network namespaces, as uid/gid 10001, with every capability
   dropped, `NoNewPrivs=1`, a read-only image tree and tmpfs over the three
   writable paths;
4. asserts each of those properties **before** the command starts, and captures
   the produced artifacts.

Measured on the execution host (2026-11-22):

| Measurement | Value |
|---|---|
| effective build context | 556 files, 0 stale bytecode, 0 forbidden paths |
| container run | **PASS** (exit 0), `uid=10001`, `CapEff=0`, `NoNewPrivs=1` |
| Judge Kit inside the sandbox | **12/12 gates PASS** |
| produced artifacts | **20**, identical in name to the host run |
| artifact | `docs/EVIDENCE/container-local-2026-11-22.json` |

**What it is not:** a Docker build. The base image cannot be pulled here, so
the image build and the real `docker run --network=none --read-only
--cap-drop ALL` remain CI-authoritative (job `docker-offline`). The artifact,
the tool's docstring, `docs/LIMITATIONS.md` (L9) and the release notes all say
so in the same words.

## 5. The pinned base image

```
ARG BASE_IMAGE="python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b"
FROM ${BASE_IMAGE}
```

* the digest is the **multi-platform** manifest list (`linux/amd64` +
  `linux/arm64`) of **CPython 3.11.16 / Debian bookworm**;
* it occurs **once** in the repository - the Dockerfile is the single source of
  truth, and the image copies it into its own build record;
* the image's own record (`/usr/local/share/twinledger/build_info.json`) was
  read back from the CI-built image:

```json
{"base_image": "python:3.11-slim-bookworm",
 "base_image_digest": "sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b",
 "python_version": "3.11.16", "os_release": "Debian GNU/Linux 12 (bookworm)",
 "apt_packages": {"make": "4.3-4.1", "util-linux": "2.38.1-5+deb12u3"}}
```

* the CI job `base-image` resolves the upstream tag's current digest on every
  commit and reports drift (at the time of writing: the tag has moved to
  `sha256:a83ba18a…`; the pinned digest is still what the release uses, by
  design - `D-18-02`).

The two Debian packages are **recorded, not pinned**: vendoring `.deb` files is
forbidden (TZ §22.3) and pinning an exact version would break the build as
soon as the mirror drops it (`docs/LIMITATIONS.md`, L11). The versions read
back from the CI-built image are published in
`docs/EVIDENCE/docker-build-info.json` (`apt_packages_observed`), and
`tools/docker_build_info.py publish` compares the image's own record with that
file: a **changed base image, digest or Python patch version is a hard
failure** (the image is no longer the released one), while a **changed package
version is reported as drift** (a warning), because a moved Debian mirror is
an environment fact, not a defect.

## 6. Gates

| Gate | Result |
|---|---|
| `make verify` | **PASS 12/12**, 655 tests, 20 artifacts |
| `make docs-verify` | **PASS**, 22 measured facts, 22/22 checks |
| `make replay-all` | **PASS**, 80/80 runs, 567 steps byte-identical |
| `make release-audit` | **PASS 6/6** (the SUBMISSION check now also verifies the base image pin) |
| `make evidence-verify` | **PASS**, release surface intact |
| `python3 tools/freeze_release.py --verify` | **PASS**, 30 frozen files, `0747baf0…` (unchanged) |
| `make container-local-check` | **PASS** (12/12 gates inside the sandbox) |
| CI `core` / `base-image` / `docker-offline` | see `docs/RELEASE_NOTES.md` |

## 7. Decisions

* `D-18-02` — the container environment is a pinned artifact, and the build
  context is computed, not guessed;
* `D-18-03` — the local container-equivalent run replaces "no local evidence",
  and says what it is not;
* `D-18-04` — a CI step may not mask its exit status, and an environment that
  cannot provide the isolation is an explicit skip, never a silent pass.

## 8. Still open (unchanged, human-owned)

`Q-ORG-01` / `Q-ORG-02` (organisational independence) remain open and are
tracked by issues #13 and #16; `Q-DOC-01` remains a judgement call. No jury
score is claimed anywhere (`official_score_claimed: false`).

## 9. Close-out — the masked CI failure (`BUG-TL-0015..0017`)

The release close-out audited the **successful** CI runs rather than assuming
that a green job meant a green run. The check-run annotations of the
`docker-offline` job carried a `Process completed with exit code 1` annotation
on a job whose conclusion was `success`. The step timings showed why: the
container-equivalent step's start and completion timestamps were **identical**
(zero seconds), while a genuine execution of the same tool takes 87–154
seconds. The step was failing before it could do any work, and the workflow
was hiding it.

### What was actually wrong

| # | Defect | Effect |
|---|---|---|
| 1 | `tools/container_local_check.py` reported a host that **forbids** unprivileged user namespaces as a generic FAIL (exit 1) | a host that proved nothing about the image was reported as a failure of the image — and the step hid even that |
| 2 | `.github/workflows/ci.yml` masked the exit status twice: `continue-on-error: true` on that step, `|| true` on the provenance-publish step | the job reported success; the failure existed only as an annotation on a green job |
| 3 | The `publish` branch of `tools/docker_build_info.py main()` was indented inside the `verify` branch **after** its `return` — unreachable dead code | `publish` fell through to `resolve()` and crashed with `AttributeError: 'Namespace' object has no attribute 'report_status'`; the CI step named "Publish the image build provenance" had never published anything, and the drift comparison it was supposed to perform never ran |
| 4 | `tools/check_workflows.py` had no policy against masking | nothing stopped defects 1–3 from being invisible |

The trigger is Ubuntu 24.04's AppArmor policy
`kernel.apparmor_restrict_unprivileged_userns=1`, which refuses
`unshare --map-root-user --mount --net` with `Operation not permitted`. It was
confirmed by differential measurement: a genuine run passes in 156.9 s
(`make verify` inside the sandbox: 153.6 s, 12/12 gates), and injecting the
refusal reproduces the failure in 1.2 s — the CI step's duration.

### What changed

* the tool **probes** the host with the same namespace recipe the run needs
  and reports an environmental refusal as `UNSUPPORTED` — an explicit skip
  with a reason and exit code **2**; a failure the probe cannot explain stays
  a FAIL with exit code **1**;
* the CI step handles the three outcomes explicitly (`0` = PASS, `2` =
  SKIPPED with a `::notice::` and a job-summary line, anything else =
  `::error::` **and a failed step**); `continue-on-error` and `|| true` are
  gone;
* the workflow tries to lift the AppArmor restriction on the runner
  (`sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0`) and
  reports whether that worked, so the real namespace-equivalent validation
  runs where the environment permits it;
* `publish` is reachable again, and a genuine base-image/digest drift now
  fails the authoritative `docker-offline` job instead of passing silently;
* `tools/check_workflows.py` gained a masking policy that `make lint`
  enforces over the repository's own workflows;
* `tests/judge/test_ci_masking.py` (30 tests) locks all of it, each with a
  failing-on-old-code counterpart.

The evidence artifact `docs/EVIDENCE/container-local-2026-11-22.json` now
records the probe result and the reason, so a skipped check can never be
read as a passed one (`REQ-JUDGE-003`).

### What the first CI run of the fix found

With the masking removed, the CI job `docker-offline` went **red** — which is
the fix working: the failure is now visible instead of hidden. It was not the
image: the new regression suite wrote a fake `unshare` script into a
temporary directory and executed it, and the container's `/tmp` is mounted
`noexec`, so the execution raised `PermissionError`
(`Ran 653 tests | FAILED (failures=2, errors=4)`).

Fixed by replacing the *binary* with a seam on the tool's command runner
(`tools/container_local_check.py::_run_command`), by treating a
non-executable `unshare` as an environmental refusal, and by adding a guard
(`test_no_test_makes_a_temporary_file_executable`) that keeps any test from
making a temporary file executable (`BUG-TL-0018`). Verified locally against
the same condition: the full suite passes with `TMPDIR` on a `noexec` tmpfs,
directly and inside the container-equivalent sandbox.

The same run also confirmed the positive half of the fix: with
`kernel.apparmor_restrict_unprivileged_userns=0` applied to the runner, the
container-equivalent step **executed the real 70-second namespace run and
passed** — the validation that used to be impossible in CI now runs there.
