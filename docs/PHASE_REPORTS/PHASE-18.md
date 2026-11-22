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
| `make verify` | **PASS 12/12**, 625 tests, 20 artifacts |
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
  and says what it is not.

## 8. Still open (unchanged, human-owned)

`Q-ORG-01` / `Q-ORG-02` (organisational independence) remain open and are
tracked by issues #13 and #16; `Q-DOC-01` remains a judgement call. No jury
score is claimed anywhere (`official_score_claimed: false`).
