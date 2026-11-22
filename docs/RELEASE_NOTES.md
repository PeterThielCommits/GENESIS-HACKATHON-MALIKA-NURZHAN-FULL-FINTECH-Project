# TwinLedger v1.0.3 — Genesis FinTech 2026 release: hardened, pinned, reproducible container

**A self-auditing synthetic-finance benchmark: the ledger, the injected errors and
the proof that the score is real.**

v1.0.3 is a **patch** release on top of `v1.0.2`. It changes no frozen contract
(`freeze_release --verify` → 30 files, `0747baf0…`) and changes no benchmark
behaviour. What it changes is the **container the benchmark ships in**:

* the base image is **pinned by digest** (TZ §22.4), and the image records its
  own provenance;
* the build context is **computed with Docker's real rules**, so the image can
  no longer carry stale bytecode, key material or sealed truth by accident;
* the Compose profile is **machine-checked** against the full hardening
  contract, including the process and file-size limits of TZ §16.2;
* the execution host now produces **real container evidence** instead of only
  reading the Dockerfile.

`v1.0.3` **is** the recommended artifact. `v1.0.2`, `v1.0.1` and `v1.0.0` are
retained for history; published tags never move (`D-16-03`).

`official_score_claimed: false`. This release reports **internal verification
results**, never a jury score (Master TZ §23.6).

---

## What changed since v1.0.2

1. **The base image is pinned by digest (`D-18-02`, TZ §22.4).** The Dockerfile
   declares

   ```
   ARG BASE_IMAGE="python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b"
   FROM ${BASE_IMAGE}
   ```

   — the multi-platform (`linux/amd64` + `linux/arm64`) manifest of **CPython
   3.11.16 on Debian bookworm**. The digest occurs **once** in the repository.
   The image writes its **own provenance record**
   (`/usr/local/share/twinledger/build_info.json`: base image, base digest,
   CPython patch version, Debian release and the versions of the two Debian
   packages it installs); `docs/EVIDENCE/docker-build-info.json` records the
   same pinned facts, and the release audit fails when the two disagree.
2. **Upstream drift is reported, never adopted silently.** The new CI job
   `base-image` resolves the current digest of the upstream tag on every commit
   and publishes it as a commit status and as an annotation. A moved tag does
   not change the pinned digest: the release environment changes only through a
   reviewed commit.
3. **The build context is computed, not guessed (`BUG-TL-0010`).** Docker
   anchors **every** `.dockerignore` pattern at the context root, so the old
   rules (`__pycache__`, `.env`, `*.pem`, `*.key`) matched only the top level:
   **197 stale `.pyc` files** entered the image, and a nested key file would
   have done the same. All nested rules now use explicit `**/` prefixes, and
   `tools/docker_context.py` implements Docker's path semantics so the
   *effective* context is a computable object with tests (750 files before →
   556 files and zero stale bytecode now).
4. **The Compose profile is machine-checked (`BUG-TL-0012`).** Every service now
   declares `pids_limit` and an `fsize` ulimit, and the `verify` service mounts
   all three writable report paths as tmpfs. `tools/check_compose_profile.py`
   parses the file with a stdlib-only YAML-subset reader and fails on any loss
   of network isolation, read-only rootfs, capability drop, non-root user,
   CPU/RAM ceiling, process/file-size limit, or on a bind mount or a sealed
   tmpfs. It runs in `make lint`, i.e. in CI.
5. **A real local container-equivalent run (`D-18-03`).**
   `tools/container_local_check.py` (`make container-local-check`) materialises
   the image the way `docker build` would - build context with `.dockerignore`
   applied, `compileall`, report directories - and then runs the container's
   own command (`make verify`) inside unprivileged user, mount and network
   namespaces: **uid/gid 10001, every capability dropped (`CapEff = 0`),
   `NoNewPrivs = 1`, a read-only image tree and tmpfs over the writable
   paths**. Each property is asserted *before* the command starts.
   Measured on the execution host: **PASS**, 12/12 Judge Kit gates inside the
   sandbox, 20 produced artifacts identical in name to the host run.
6. **The container run is capped (TZ §16.2).** `make docker-check-container`
   adds `--pids-limit 512` and `--ulimit fsize=268435456:268435456`.
7. **The dependency audit stopped matching a spelling (`BUG-TL-0013`).**
   `judge/performance_and_deps.py` decided whether the image was pinned with
   the literal substring `"FROM python:3.11"`, which the ARG-based `FROM`
   invalidated - a false `RC-012` FAIL while the measured performance and
   dependency facts were inside their targets. It now parses the declared base
   image and records the image's Python patch version and package versions.
8. **22 new regressions**, each failing on the old code
   (`tests/judge/test_docker_hardening.py`).

The **benchmark itself did not change**: no contract, no generator, no verifier,
no matcher, no scorer and no episode was touched. The frozen contract surface
stays at 30 files with the published aggregate `0747baf0…`.

---

## Verify it yourself (offline, no network)

```bash
git clone <repo> && cd <repo>
make verify                # 12/12 Judge Kit gates
make docs-verify           # every documented number re-measured against its artefact
make replay-all            # all 80 published trajectories replayed, step by step
make release-audit         # secrets, file list, size, dependencies, entrypoint, base image pin
make container-local-check # the container command, hardened, without a container runtime
```

The **Phase 17** layer adds three more, all offline and stdlib-only:

```bash
python3 tools/freeze_release.py --verify     # 30 frozen contract surfaces
python3 tools/evidence_freeze.py --verify    # the whole release surface
python3 tools/release_evidence.py --verify   # the reconstructable release archive
```

The **Phase 18** layer adds two:

```bash
python3 tools/docker_build_info.py verify    # the base image is pinned by digest and the record agrees
python3 tools/check_compose_profile.py       # every Compose service keeps the hardening contract
```

With Docker and a registry available, `make docker-check` builds the image and
runs it hardened (`--network=none --read-only --cap-drop ALL --pids-limit
--ulimit fsize`). On a host without a container runtime,
`make container-local-check` is the local equivalent - and it says plainly that
it is **not** a Docker build.

---

## What was measured for this release

| Measurement | Value | Where |
|---|---|---|
| Judge Kit gates | **12/12 PASS** | `artifacts/reports/latest/verify_summary.json` |
| Test suite | **623 tests** (1 optional skip) | unittest discovery over `tests/` |
| Trajectory replay | **80/80 runs, 567 steps byte-identical** | `make replay-all` |
| Release audit | **6/6 PASS** | `make release-audit` |
| Documentation claims | **22 measured facts, 22/22 checks PASS** | `make docs-verify` |
| Frozen contract surface | **30 files, `0747baf0…`** (unchanged) | `python3 tools/freeze_release.py --verify` |
| Release-surface archive | **every tracked file, one aggregate digest** | `docs/EVIDENCE/evidence_freeze.json` |
| Container-equivalent run | **PASS** - uid 10001, `CapEff=0`, `NoNewPrivs=1`, read-only tree, no route out, 12/12 gates | `docs/EVIDENCE/container-local-2026-11-22.json` |
| Effective build context | **556 files, 0 stale bytecode, 0 forbidden paths** | `python3 tools/docker_context.py` |
| Pinned base image | `python:3.11-slim-bookworm@sha256:a36c24f9…` (CPython 3.11.16, bookworm) | `docs/EVIDENCE/docker-build-info.json` |
| Baseline means (seed 2026) | oracle +0.9920 · simple_reconciliation +0.9853 · random −0.5060 · mass_flagging −1.0000 | `artifacts/trajectories/trajectories.jsonl` |

---

## Known limitations

1. The official rubric weights are not published; internal verification is never
   presented as a score.
2. The reward *formula* is official (`D-18-01`); what is internal is the claim,
   never the arithmetic.
3. **The image build itself is CI-authoritative (L9).** The execution host has
   no container runtime and no registry access, so `docker build` cannot run
   there. `make container-local-check` is a *container-equivalent* run: it
   materialises the image and applies the same hardening, but it does not pull
   or build the base image. The CI job `docker-offline` remains the authority.
4. **The Debian package versions are recorded, not pinned (L11).** The base
   image digest fixes the userland and the Python patch version; `make` and
   `util-linux` are resolved by `apt` at build time. Vendoring is not permitted
   (TZ §22.3) and pinning an exact version would break the build as soon as
   the mirror drops it, so the versions actually installed live in the image's
   own record and CI publishes them.
5. `replay-all` replays recorded actions; it does not re-run the baseline
   policies, so policy-side changes are covered by `make official-eval` instead.
6. Baseline numbers derive from the committed `trajectories.jsonl`; regenerating
   it is a reviewer step, not part of `make verify`.
7. Difficulty calibration is validated on the D01..D20 set only.
8. Organisational independence of the verifier remains **unevidenced** (`Q-ORG-01`,
   `Q-ORG-02`, OPEN): the codebase was produced by AI agents in one shared session
   context. The *technical* zero-common-mode separation is proven and tested; the
   organisational half is disclosed, not claimed. See `docs/INDEPENDENCE.md`.
9. The evidence archive is **per-commit** and the release evidence is a
   **snapshot**: a later patch release needs its own archive (limitation L8).

The full, dated limitation list lives in `docs/LIMITATIONS.md`; the threat model
is in `docs/THREAT_MODEL.md`, and every deviation is recorded with its reasoning
in `docs/DECISIONS.md`.

---

## Documentation map

| Document | What it answers |
|---|---|
| `README.md` | Deploy and verify in two commands; every published number is generated |
| `docs/PHASE_REPORTS/PHASE-18.md` | This release: what was broken, what was measured, what is still CI-authoritative |
| `docs/EVIDENCE/docker-build-info.json` | The pinned base image, the Python patch version, the declared packages |
| `docs/EVIDENCE/container-local-2026-11-22.json` | The local container-equivalent run and its exact scope |
| `docs/LIMITATIONS.md` | What this does not do (L9: the image build; L11: the package versions) |
| `docs/QUALITY_AUDIT/BUG_REGISTRY.md` | BUG-TL-0010..0013: symptom, impact, root cause, regression evidence |
| `docs/DECISIONS.md` | `D-18-02`, `D-18-03` and every earlier decision |

---

## Release record

| Item | Value |
|---|---|
| Tag | `v1.0.3` (annotated) on the merge commit of the Phase 18 PR, cut **after** `make rc-check` PASS and CI green on the merge commit |
| Parent release | `v1.0.2` (`48cfb17`), retained for history |
| Behaviour | unchanged: no frozen contract, no runtime code, no episode |
| Frozen contract surface | 30 files, `0747baf0…` (unchanged) |
| Container | base image pinned by digest; effective build context computed and asserted; Compose profile machine-checked |
| `official_score_claimed` | `false` (TZ §23.6) |

---

## Appendix — v1.0.2 release notes (previous release)



**A self-auditing synthetic-finance benchmark: the ledger, the injected errors and
the proof that the score is real.**

v1.0.2 is a **patch** release on top of `v1.0.1`. It changes no frozen contract
(`freeze_release --verify` → 30 files, `0747baf0…`) and changes no benchmark
behaviour. What it adds is the **Phase 17 evidence archive**: the release can now
be restored *and* verified from the repository alone, with no oral explanation
from the team.

`v1.0.2` **is** the recommended artifact: it is behaviour-identical to `v1.0.1`
(same benchmark, same hardened image) and adds the Phase 17 evidence archive.
`v1.0.1` is retained for history. Tags `v1.0.0` and `v1.0.1` are **not** moved —
published tags never move (`D-16-03`).

`official_score_claimed: false`. This release reports **internal verification
results**, never a jury score (Master TZ §23.6).

---

## What changed since v1.0.1

1. **The release surface is archived (`D-17-02`).** `tools/evidence_freeze.py`
   writes `docs/EVIDENCE/evidence_freeze.json`: a SHA-256 for **every tracked
   release file** — runtime code, operational configs, contracts, the rubric map,
   the Dockerfile, the Makefile, the official entrypoint, the committed episodes
   and the whole documentation set — plus the **verdicts** of the Judge Kit,
   replay, release-audit and documentation-claim reports. The archived fact is
   the *verdict* (status + counts), not the report bytes: reports carry
   timestamps and run-ids and are regenerable, so byte-identity is deliberately
   not required on a re-run.
2. **The release is reconstructible from the repository alone.** New
   `tools/release_evidence.py` writes
   `docs/EVIDENCE/phase-17-release-evidence-2026-11-22.json`: the frozen digest,
   the twelve rubric gates `RC-001..RC-012`, the decision register, and the
   exact command list a stranger runs to rebuild and re-verify the release.
3. **The archive is a gate, not a note.** `make evidence-verify` is wired into
   `make rc-check` **and** into the CI `core` job, so the committed archive must
   match the committed tree; a new check `C-ARCHIVE` in
   `tools/verify_doc_claims.py` asserts the archive is honest
   (`official_score_claimed: false`), quotes the frozen digest, archives the
   rubric map, lists only decisions that exist, and names only reconstruct
   commands whose scripts exist. The contract freeze became a **test**
   (`tests/judge/test_release_freeze.py`): a frozen file cannot move without a
   failing suite and an approved CR.
4. **Five defects in published evidence fixed (`D-17-03`) — all non-frozen,
   each with a regression test that fails on the old code:
   - **BUG-TL-0005 (P1):** the reward-property matrix published the *superseded
     provisional formula* and `provisional: true`, although every number in it
     had been computed by the official implementation since `D-18-01`. The
     published formula is now **derived from the live constants**
     (`scoring/official_scorer.official_formula_text()`), so it cannot drift
     again.
   - **BUG-TL-0006 (P2):** the robustness report published
     `score_contract: "scoring.reward (internal provisional; not
     official_scorer)"` — false since `D-18-01` made
     `scoring.official_scorer` the single reward implementation.
   - **BUG-TL-0007 (P3):** stale "provisional / pending Q-005" wording in
     `scoring/matcher.py` and in a property-test comment, although `Q-005` was
     resolved on 2026-11-20.
   - **BUG-TL-0008 (P2):** the documentation gate's artifact contract named
     `replay_all_report.json` — a file that **does not exist** (the real one is
     `trajectory_replay.json`) — and omitted `reward_property_matrix.json`,
     which is part of the published 20-file evidence set. A *correct* citation
     was therefore reported as a phantom path. The contract is now derived from
     the producers.
   - **BUG-TL-0009 (P1):** the CI workflow file was malformed YAML — an
     unquoted `"  : "` inside a step name — so GitHub ran a workflow with
     **zero jobs** on every push and nothing in the repository failed. The
     twelve gates, the offline container check and the evidence gate had all
     silently disappeared. `tools/check_workflows.py` (stdlib-only) now parses
     the workflow files in `make lint` and in the test suite.
5. **Documentation.** The Phase 17 report was rewritten;
   `docs/HANDOFF/phase-17-evidence-freeze.md` was added; `docs/STATUS.md`,
   `docs/CURRENT_STATE.md`, `docs/CONTEXT/NEXT_AGENT.md`, `docs/LIMITATIONS.md`
   (now L1..L10) and `docs/DECISIONS.md` (`D-17-02`, `D-17-03`) were updated;
   the historical Phase 6 reward matrix is annotated as superseded.

---

## Verify it yourself (offline, no network)

```bash
git clone <repo> && cd <repo>
make verify                # 12/12 Judge Kit gates
make docs-verify           # every documented number re-measured against its artefact
make replay-all            # all 80 published trajectories replayed, step by step
make release-audit         # secrets, file list, size, dependencies, entrypoint
```

The **Phase 17** layer adds three more, all offline and stdlib-only:

```bash
python3 tools/freeze_release.py --verify     # 30 frozen contract surfaces
python3 tools/evidence_freeze.py --verify    # the whole release surface
python3 tools/release_evidence.py --verify   # the reconstructable release archive
```

`tools/evidence_freeze.py --verify` works on a bare clone: the archived digest
covers the tracked release files only. Add `--require-reports` (the CI and
`make rc-check` gate) to also compare the archived gate verdicts against a
fresh `make verify` run.

---

## What was measured for this release

| Measurement | Value | Where |
|---|---|---|
| Judge Kit gates | **12/12 PASS** | `artifacts/reports/latest/verify_summary.json` |
| Test suite | **601 tests** (1 optional skip) | unittest discovery over `tests/` |
| Trajectory replay | **80/80 runs, 567 steps byte-identical** | `make replay-all` |
| Release audit | **6/6 PASS** | `make release-audit` |
| Documentation claims | **22 measured facts, 22/22 checks PASS** | `make docs-verify` |
| Frozen contract surface | **30 files, `0747baf0…`** (unchanged) | `python3 tools/freeze_release.py --verify` |
| Release-surface archive | **every tracked file, one aggregate digest** | `docs/EVIDENCE/evidence_freeze.json` |
| Baseline means (seed 2026) | oracle +0.9920 · simple_reconciliation +0.9853 · random −0.5060 · mass_flagging −1.0000 | `artifacts/trajectories/trajectories.jsonl` |

---

## How the work was verified

The interesting part of this project is not that the tests pass — it is that each
gate was shown to **fail** when it should:

- a planted AWS key, an undeclared `requests` import, a forced `git add -f` of
  sealed truth, and an oversized file each produce a specific `FAIL`;
- a tampered metric and a tampered observation each break `replay-all`;
- an injected documentation drift produces `[DRIFT]` naming the exact line;
- an injected pagination-cursor corruption stalls the L-fixture walk (C05 regression);
- a phantom decision ID produces `[PHANTOM_ID]`;
- **a one-character edit to any tracked release file makes
  `python3 tools/evidence_freeze.py --verify` name that file** — the archive is
  a real gate, not a note.

Every gate names its requirement ID, runs from a clean tree, and writes an
artefact (`REQ-JUDGE-002`). Optional checks are reported as explicitly SKIPPED,
never silently omitted (`REQ-JUDGE-003`).

---

## Known limitations

1. The official rubric weights are not published; internal verification is never
   presented as a score.
2. The reward *formula* is official (`D-18-01`); what is internal is the claim,
   never the arithmetic. `configs/scoring/default.json` still records
   `eta: 0.05, provisional: true` as a frozen historical artifact and no longer
   influences any computed reward.
3. `replay-all` replays recorded actions; it does not re-run the baseline
   policies, so policy-side changes are covered by `make official-eval` instead.
4. Baseline numbers derive from the committed `trajectories.jsonl`; regenerating
   it is a reviewer step, not part of `make verify`.
5. Difficulty calibration is validated on the D01..D20 set only.
6. Organisational independence of the verifier remains **unevidenced** (`Q-ORG-01`,
   `Q-ORG-02`, OPEN): the codebase was produced by AI agents in one shared session
   context. The *technical* zero-common-mode separation is proven and tested; the
   organisational half is disclosed, not claimed. See `docs/INDEPENDENCE.md`.
7. The Docker offline check is exercised by CI (`docker-offline` job), not by every
   developer machine; where no Docker daemon exists it is recorded as UNVERIFIED
   rather than PASS (see `docs/PHASE_REPORTS/PHASE-16.md`, limitation L-C).
8. The evidence archive is **per-commit** and the release evidence is a
   **snapshot**: a later patch release needs its own archive (limitation L8).

The full, dated limitation list lives in `docs/LIMITATIONS.md`; the threat model
is in `docs/THREAT_MODEL.md`, and every deviation is recorded with its reasoning
in `docs/DECISIONS.md`.

---

## Documentation map

| Document | What it answers |
|---|---|
| `README.md` | Deploy and verify in two commands; every published number is generated |
| `docs/DESIGN.md` | How it is built, as built |
| `docs/API_USAGE.md` | The official entrypoint, worked example |
| `docs/POLICY_PROTOCOL.md` | Tool envelopes, error codes, budgets, limits |
| `docs/DEMO.md` | 3-minute demo and technical backup demo |
| `docs/LIMITATIONS.md` | What this does not do |
| `docs/THREAT_MODEL.md` | What it defends against, and how |
| `docs/INDEPENDENCE.md` | Why generator, verifier and scorer are separable — and what is *not* proven |
| `docs/PHASE_REPORTS/` | Per-phase scope, defects, commands and evidence |
| `docs/EVIDENCE/` | The Phase 17 release archive and the earlier re-derivation / offline evidence |
| `docs/HANDOFF/phase-17-evidence-freeze.md` | How to reconstruct and re-verify this release |

---

## Reproducibility

```bash
git clone <repo> && cd <repo>
make verify                    # requires Python 3.11 on PATH
```

Expected: `verify: PASS`, exit 0, with `artifacts/reports/latest/verify_summary.json`
and 20 evidence artefacts. Any deviation is a bug worth reporting.

---

## Release record

| Item | Value |
|---|---|
| Tag | `v1.0.2` (annotated) — tag object `3d5855a4ad2c05723cab56a0cd120bc11c772949`, commit `48cfb17` (the merge commit of PR #29), cut **after** `make rc-check` PASS and CI green on the merge commit |
| Parent release | `v1.0.1` (`640c585`), retained for history |
| Release-surface archive | `docs/EVIDENCE/evidence_freeze.json` (every tracked file at the release commit, + the gate verdicts) |
| Release audit (tag tree) | 551 tracked files (the release-surface archive counts 550: it excludes itself), 0 credentials, 0 forbidden paths, 0 undeclared external imports (118 runtime modules) |
| CI on the tagged commit | `core` **pass**, `docker-offline` **pass** (run `45038110934`) |
| Tag-tree verification | the full reconstruct sequence (`freeze_release --verify` → `make verify` → `make docs-verify` → `make replay-all` → `make release-audit` → `evidence_freeze --verify --require-reports` → `release_evidence --verify --strict` → `unittest`) exits **0** on a fresh `git clone --branch v1.0.2` |
| Release evidence | `docs/EVIDENCE/phase-17-release-evidence-2026-11-22.json` (frozen digest, rubric map, decisions, reconstruct commands) |
| Frozen contract surface | 30 files, `0747baf0…` (unchanged; this release touches no frozen file) |
| `official_score_claimed` | `false` (TZ §23.6) |

---

## Appendix — v1.0.1 release notes (previous release)

**A self-auditing synthetic-finance benchmark: the ledger, the injected errors and
the proof that the score is real.**

v1.0.1 supersedes v1.0.0 (`8da0af2`). Tag `v1.0.0` remains published for history,
but it ships a submission image that would have contained `sealed/truth.json`
(`.dockerignore` matched only depth-1 `episodes/*/sealed/`, not the real depth-2
layout — `D-16-02`). **v1.0.1 is the recommended submission artifact.**

`official_score_claimed: false`. This release reports **internal verification
results**, never a jury score (Master TZ §23.6).

---

## What changed since v1.0.0

All changes are correctness fixes on non-frozen files; the frozen contract
surface is untouched (`freeze_release --verify` → 30 files, `0747baf0…`).

1. **Submission image no longer ships sealed truth (`D-16-02`, release blocker).**
   `.dockerignore` listed `episodes/*/sealed/`, but Docker matches patterns per
   path element, so the real depth-2 layout `episodes/dev/ep_x/sealed/` was
   included in the build context. Both depths are now listed, locked by
   `TestDockerIgnore`.
2. **Forensic audit against the official check definitions (PR #24).** Two P0 and
   two P1 defects, each fixed with a regression test that fails on the old code:
   - **BUG-TL-0001 (P0):** two competing reward implementations existed;
     `scoring/reward.py` used the superseded provisional reward while the jury
     reaches the official `clip([-1,1], 2·F1 − 1 − 0.2·steps/100)`. Ten of eleven
     published reward vectors were wrong; negative rewards were impossible.
   - **BUG-TL-0002 (P0):** pagination-cursor `rsplit(b".")` broke verification for
     ~6.5% of offsets (16-byte HMAC containing `0x2E`); the official L-fixture
     stalled at 150 of 214 rows with `BAD_CURSOR`.
   - **BUG-TL-0003 (P1):** trailing base64 garbage was accepted by cursor
     verification. The old test passed by luck.
   - **BUG-TL-0004 (P1):** the official C05 test only walked `invoices`, never the
     broken `ledger` offset 200. Now exercised on both.
   - Three mutation mutants (MUT-07/08/13) silently disarmed by the reward refactor
     were re-armed; the suite is 26/26 again.
3. **Post-release mandatory-target audit (PR #23).** All 19 required TZ §23.2 make
   targets had never actually been executed. Running them exposed four defects;
   fixes: `verify-core` after `build-episodes` (the no-git filesystem walk now
   honours ignore rules — 20 false `FILELIST` hits gone), the official-eval summary
   relocated out of the frozen evidence directory (`artifacts/reports/evaluation/`),
   and the published gate count now comes from the frozen rubric map instead of the
   last run's summary. Decision `D-16-02`.
4. **Documentation gate hardened (PR #25, `D-15-04..D-15-07`).** Structural detectors
   `C-PATHS`, `C-DATADICT`, `C-DEMO`, `C-WORKBENCH-API`, `C-COMMANDS`, `C-REWARD`,
   `C-COUNTS` added to `tools/verify_doc_claims.py`, each proven able to fail by an
   injected fault; a phantom documented workbench route
   (`GET /api/episode/<split>/<id>/overview`) was implemented instead of erased; two
   order-dependency bugs fixed (`D-15-06`); ASCII-only console crash fixed (`D-15-07`);
   the 19-defect structural audit is recorded in
   `docs/PHASE_REPORTS/PHASE-15-STRUCTURAL-AUDIT.md`.
5. **Package metadata aligned.** `pyproject.toml` declared `version = "0.1.0"`;
   it now declares `1.0.1`. Nothing frozen changed; `schema_version` remains
   `1.0.0` (the frozen contract line, `D-01-01`).

---

## Verify it yourself (two commands, no network)

```bash
make verify        # lint + 12-gate Judge Kit + full test suite -> artifacts/reports/latest/
make rc-check      # verify + docs-verify + replay-all + release-audit
```

Python 3.11, standard library only. No install step, no downloads, no network.
A hardened offline container is provided as well:

```bash
make docker-check  # --network=none --read-only --cap-drop ALL, non-root
```

## What was measured for this release

| Claim | Command | Result |
|---|---|---|
| Verification suite | `make verify` | **12/12 gates PASS**, full suite, 20 evidence artefacts |
| Clean machine | fresh `git clone`, empty evidence dir | **12/12 PASS** (re-measured on this tree) |
| No-Git submission tree | `git archive` extraction, no `.git` | audit **6/6 PASS** |
| Determinism, all runs | `make replay-all` | **80/80 runs, 567 steps byte-identical** |
| Determinism, sealed replay | `make replay` | 5/5 byte-identical |
| No published claim drifts | `make docs-verify` | 22 facts, 18/18 checks PASS |
| Release audit | `make release-audit` | **6/6 PASS** (secrets, file list, size, dependencies, entrypoint, submission) |
| Frozen contract surface | `freeze_release --verify` | 30 files, `0747baf0…` |
| Offline container | CI `docker-offline` (GitHub Actions) | green on the release merge commit: `--network=none --read-only --cap-drop ALL`, `PIP_NO_INDEX=1`, non-root `USER 10001` |

The exact package byte size is printed by `make release-audit` (budget 50 MB) and is
re-measured on every tree; it is never transcribed into this file. The figures
recorded for the `v1.0.0` tag's tree (494 files / 5 449 805 bytes) are preserved as
history in `docs/PHASE_REPORTS/PHASE-16.md`.

Baseline policies over D01..D20 (seed 2026, 20 scenarios each) — published in
the README generated block and re-measured by `make docs-verify`:

| Policy | Mean F1 | Mean return | Mean steps |
|---|---:|---:|---:|
| oracle (judge-side reference) | 1.0000 | +0.9920 | 4.0 |
| simple_reconciliation | 1.0000 | +0.9853 | 7.3 |
| random | 0.2500 | −0.5060 | 12.0 |
| mass_flagging | 0.0000 | −1.0000 | 1.0 |

## How the work was verified

The interesting part of this project is not that the tests pass — it is that each
gate was shown to **fail** when it should:

- a planted AWS key, an undeclared `requests` import, a forced `git add -f` of
  sealed truth, and an oversized file each produce a specific `FAIL`;
- a tampered metric and a tampered observation each break `replay-all`;
- an injected documentation drift produces `[DRIFT]` naming the exact line;
- an injected pagination-cursor corruption stalls the L-fixture walk (C05 regression);
- a phantom decision ID produces `[PHANTOM_ID]`.

Every gate names its requirement ID, runs from a clean tree, and writes an
artefact (`REQ-JUDGE-002`). Optional checks are reported as explicitly SKIPPED,
never silently omitted (`REQ-JUDGE-003`).

## Known limitations

1. The official rubric weights are not published; internal verification is never
   presented as a score.
2. The reward *formula* is official (`D-18-01`); what is internal is the claim,
   never the arithmetic. `configs/scoring/default.json` still records
   `eta: 0.05, provisional: true` as a frozen historical artifact and no longer
   influences any computed reward.
3. `replay-all` replays recorded actions; it does not re-run the baseline
   policies, so policy-side changes are covered by `make official-eval` instead.
4. Baseline numbers derive from the committed `trajectories.jsonl`; regenerating
   it is a reviewer step, not part of `make verify`.
5. Difficulty calibration is validated on the D01..D20 set only.
6. Organisational independence of the verifier remains **unevidenced** (`Q-ORG-01`,
   `Q-ORG-02`, OPEN): the codebase was produced by AI agents in one shared session
   context. The *technical* zero-common-mode separation is proven and tested; the
   organisational half is disclosed, not claimed. See `docs/INDEPENDENCE.md`.
7. The Docker offline check is exercised by CI (`docker-offline` job), not by every
   developer machine; where no Docker daemon exists it is recorded as UNVERIFIED
   rather than PASS (see `docs/PHASE_REPORTS/PHASE-16.md`, limitation L-C).

The full, dated limitation list lives in `docs/LIMITATIONS.md`; the threat model
is in `docs/THREAT_MODEL.md`, and every deviation is recorded with its reasoning
in `docs/DECISIONS.md`.

## Documentation map

| Document | What it answers |
|---|---|
| `README.md` | Deploy and verify in two commands; every published number is generated |
| `docs/DESIGN.md` | How it is built, as built |
| `docs/API_USAGE.md` | The official entrypoint, worked example |
| `docs/POLICY_PROTOCOL.md` | Tool envelopes, error codes, budgets, limits |
| `docs/DEMO.md` | 3-minute demo and technical backup demo |
| `docs/LIMITATIONS.md` | What this does not do |
| `docs/THREAT_MODEL.md` | What it defends against, and how |
| `docs/INDEPENDENCE.md` | Why generator, verifier and scorer are separable — and what is *not* proven |
| `docs/PHASE_REPORTS/` | Per-phase scope, defects, commands and evidence |

## Reproducibility

```bash
git clone <repo> && cd <repo>
make verify                    # requires Python 3.11 on PATH
```

Expected: `verify: PASS`, exit 0, with `artifacts/reports/latest/verify_summary.json`
and 20 evidence artefacts. Any deviation is a bug worth reporting.

## Release record

| Item | Value |
|---|---|
| Tag | `v1.0.1` (annotated, object `3601493…`) on commit `640c585` (merge of PR #26), cut **after** `make rc-check` PASS from clean-clone conditions and CI green on the merge commit (`core` + `docker-offline`, run `45020669250`) |
| Release audit (tag tree) | 524 tracked files, 5 790 897 bytes (budget 52 428 800), 0 credentials, 0 forbidden paths, 0 undeclared external imports (109 runtime modules) |
| Parent release | `v1.0.0` (`8da0af2`), retained for history |
| Frozen contract surface | 30 files, `0747baf0…` (unchanged; this release touches no frozen file) |
| `official_score_claimed` | `false` (TZ §23.6) |
