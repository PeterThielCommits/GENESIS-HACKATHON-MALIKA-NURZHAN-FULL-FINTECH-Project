# TwinLedger — Changelog

## Unreleased — Phase 18: container hardening, pinned base image, real local container-equivalent run

- **The base image is pinned by digest (TZ §22.4, `BUG-TL-0011`).** The Dockerfile
  declares `ARG BASE_IMAGE="python:3.11-slim-bookworm@sha256:a36c24f9..."` (the
  multi-platform `linux/amd64` + `linux/arm64` manifest of CPython 3.11.16 on
  Debian bookworm) and `FROM ${BASE_IMAGE}`. The image now writes **its own
  provenance record** (`/usr/local/share/twinledger/build_info.json`: base image,
  base digest, CPython patch version, Debian release and the versions of the two
  Debian packages it installs). `docs/EVIDENCE/docker-build-info.json` records the
  pinned facts, `tools/release_audit.py` verifies that the Dockerfile and the
  record agree, and the new CI job `base-image` resolves the upstream tag digest
  and reports drift as a commit status plus an annotation.
- **The `.dockerignore` rules now match Docker's real anchoring (`BUG-TL-0010`).**
  Docker anchors every pattern at the context root, so `__pycache__` matched only
  `<root>/__pycache__`: **197 stale `.pyc` files** (and any nested `.env`,
  `*.pem`, `*.key`) entered the build context. All nested rules now use explicit
  `**/` prefixes, and the new `tools/docker_context.py` implements Docker's path
  semantics so the *effective* context is computable (750 files before → 556
  files and 0 stale bytecode now).
- **A real local container-equivalent run (`make container-local-check`).** The
  image is materialised the way `docker build` would (build context with
  `.dockerignore` applied, `compileall`, report directories) and the container's
  own command (`make verify`) runs in an unprivileged user+mount+network
  namespace as uid/gid 10001 with **every capability dropped**, `no_new_privs`, a
  **read-only image tree** and tmpfs over the writable paths. Measured on the
  execution host: PASS, 12/12 Judge Kit gates inside the sandbox, 20 artifacts
  identical in name to the host run. It is explicitly **not** a Docker build - the
  base image cannot be pulled without a registry - and the artifact says so.
- **The Compose profile is machine-checked (`BUG-TL-0012`).** Every service now
  declares `pids_limit` and an `fsize` ulimit, and the `verify` service mounts
  all three writable report paths as tmpfs. `tools/check_compose_profile.py`
  parses the file (stdlib-only YAML subset) and fails on any loss of network
  isolation, read-only rootfs, capability drop, non-root user, CPU/RAM ceiling,
  process/file-size limit, or on a bind mount or a sealed tmpfs. It runs in
  `make lint` and therefore in CI.
- **The dependency audit stopped matching a spelling (`BUG-TL-0013`).**
  `judge/performance_and_deps.py` parsed the Dockerfile with the literal
  substring `"FROM python:3.11"`, which the ARG-based `FROM` invalidated - a
  false `RC-012` FAIL while the measured performance and dependency facts were
  inside their targets. It now parses the declared base image and records the
  image's Python patch version and package versions.
- **The container run is capped.** `make docker-check-container` adds
  `--pids-limit 512` and `--ulimit fsize=268435456:268435456` (TZ §16.2
  "resource limits for CPU/RAM/processes/file size, where supported").
- **Contract freeze unchanged:** 30 files, aggregate `0747baf0…`. The base image
  pin is a *release* fact, not a benchmark-contract change, so the frozen surface
  was deliberately left untouched (the build record lives in `docs/EVIDENCE/`).

## 1.0.2 — Phase 17 deep execution: reconstructable release archive (2026-11-22)

- **The release surface is now archived (`D-17-02`).** New `tools/evidence_freeze.py`
  writes `docs/EVIDENCE/evidence_freeze.json`: SHA-256 for every tracked release
  file (code, configs, contracts, rubric map, Dockerfile, Makefile, entrypoint,
  episodes, docs) plus the **verdicts** of the Judge Kit, replay, audit and
  doc-claim reports. Report bytes carry timestamps and are regenerable, so the
  archived fact is the *verdict* (status + counts), never the byte hash.
- **The release is reconstructible from the repository alone.** New
  `tools/release_evidence.py` writes
  `docs/EVIDENCE/phase-17-release-evidence-2026-11-22.json`: the frozen digest,
  the twelve rubric gates `RC-001..RC-012`, the decision register and the exact
  command list a stranger runs to rebuild and re-verify the release.
- **The archive is a gate, not a note.** `make evidence-write` /
  `make evidence-verify` are wired into `make rc-check` and into the CI `core`
  job: the committed archive must match the committed tree. `C-ARCHIVE` (new
  check in `tools/verify_doc_claims.py`) asserts the archive is honest, quotes
  the frozen digest, archives the rubric map, lists only existing decisions and
  names only reconstruct commands whose scripts exist.
- **The contract freeze is now a test.** `tests/judge/test_release_freeze.py`
  asserts the committed freeze matches the tree, that the frozen surface is
  exactly the declared 30 files, and that the aggregate is still the released
  `0747baf0…`. A silent re-freeze is no longer possible — it needs a CR.
- **Five published-evidence defects fixed (non-frozen, each with a failing-on-old-code
  regression test):** BUG-TL-0005 (P1) the reward-property matrix published the
  superseded provisional formula and `provisional: true` although its numbers
  were official; BUG-TL-0006 (P2) the robustness report published a
  `score_contract` claiming it was *not* scored by `official_scorer`; BUG-TL-0007
  (P3) stale "provisional / pending Q-005" wording in `scoring/matcher.py` and in
  a property-test comment; BUG-TL-0008 (P2) the documentation gate's artifact
  contract named `replay_all_report.json` - a file that **does not exist** -
  and
  omitted `reward_property_matrix.json`, so a correct citation was reported as a
  phantom path. The published reward contract is now **derived from the
  BUG-TL-0009 (P1) the CI workflow file itself was malformed YAML (an unquoted
  `": "` inside a step name), so every push ran a workflow with **zero jobs**
  and nothing in the repository failed -- the CI gate had silently disappeared.
  New `tools/check_workflows.py` (stdlib-only) plus 13 tests now parse the
  workflow files in `make lint` and in the test suite.
  live constants** (`scoring/official_scorer.official_formula_text()`), and
  `C-REWARD` audits generated artifacts as well as prose (`D-17-03`).
- **Docs:** Phase 17 report rewritten, `docs/HANDOFF/phase-17-evidence-freeze.md`
  added, `docs/STATUS.md` + `docs/CURRENT_STATE.md` + `docs/CONTEXT/NEXT_AGENT.md`
  updated, `docs/LIMITATIONS.md` extended to L1..L10, `docs/DECISIONS.md` gains
  `D-17-02` and `D-17-03`, the historical Phase 6 reward matrix annotated as
  superseded.
- No frozen file changed (`freeze_release --verify` → 30 files, `0747baf0…`); no
  tag moved (`v1.0.0`, `v1.0.1`); `code_version` stays `twinledger@1.0.0`;
  `schema_version` stays `1.0.0`; `official_score_claimed: false`.

### Also in this release — Phase 16 §7 risk-closure round (2026-11-22)


- **Independent re-derivation implementation (`D-16-04`):** new `independent_verifier/` — a from-scratch Stage-1 verifier authored from `spec/` + `contracts/` alone (own money/FX via `Fraction`, `zoneinfo` fiscal periods, own discovery algorithms, own ProofGraph acyclicity/path checks, own evidence minimality/ablation). Measured agreement: all 10 committed dev/train episodes signature-identical (identical `episode_public_hash`); official `D01..D20` (`master_seed=2026`) re-derived and cross-checked at **F1 = 1 exact, FP = 0, FN = 0**; evidence enumeration complete. New `tools/verify_independent_rederivation.py` harness + `docs/EVIDENCE/independent-rederivation-2026-11-22.json`. **Not** organisational independence — `Q-ORG-01` stays OPEN.
- **Offline verification beyond CI:** new `tools/offline_local_check.py` (user+net+mount namespace, read-only bind of the tree, no network route, full suite PASS) + static Dockerfile/`.dockerignore` audit (10/10) + `docs/EVIDENCE/offline-local-2026-11-22.json`. The Docker image build remains CI-authoritative (`docker-offline` green on `main` and on the `v1.0.1` tag commit); local scope and limits are recorded in the artifact.
- **Documentation gate extended:** `tools/verify_doc_claims.py` gains `C-EVIDENCE`, `C-SCORE-HONEST`, `C-QORG-OPEN` (21/21 checks PASS, was 18).
- **GitHub release `v1.0.0` supersession pointer:** release body now opens with a SUPERSEDED banner pointing to `v1.0.1`; tags unmoved; repo docs already pointed at v1.0.1.
- **CI hygiene:** `tools/check_import_boundaries.py` and `tools/release_audit.py` now cover `independent_verifier/`; `Makefile` lint root and `Dockerfile` compileall include it; `tests/independent_verifier/` (8 tests) added — suite now 548.
- No frozen file changed (`freeze_release --verify` → 30 files, `0747baf0…`); no tag moved; `code_version` stays `twinledger@1.0.0`; `official_score_claimed: false`.

## 1.0.1 — Release-blocking image fix and post-release hardening (2026-11-22)

- **Submission image no longer ships sealed truth (`D-16-02`, release blocker):** `.dockerignore` matched only depth-1 `episodes/*/sealed/`; the real depth-2 layout (`episodes/dev/ep_x/sealed/`) entered the build context. Both depths now excluded; locked by `TestDockerIgnore`. Fixes a `REQ-ARENA-005` violation that affected tag `v1.0.0`.
- **Forensic audit vs the official 2026-11-20 check definitions (PR #24):** BUG-TL-0001 (P0, two competing reward implementations — the jury formula is now the only one), BUG-TL-0002 (P0, cursor HMAC `rsplit` defect stalling C05 at 150/214 rows), BUG-TL-0003 (P1, trailing base64 accepted), BUG-TL-0004 (P1, C05 mirror test never walked the broken `ledger` fixture); mutants MUT-07/08/13 re-armed (26/26 again).
- **Post-release mandatory-target audit (PR #23, `D-16-02`):** all 19 TZ §23.2 `make` targets executed in sequence; fixed `verify-core`-after-`build-episodes` (filesystem walk now honours ignore rules), relocated `official_eval_summary.json` out of the frozen evidence dir, and pinned the published gate count to the frozen rubric map.
- **Documentation gate hardened (PR #25, `D-15-04..D-15-07`):** structural detectors `C-PATHS`, `C-DATADICT`, `C-DEMO`, `C-WORKBENCH-API`, `C-COMMANDS`, `C-REWARD`, `C-COUNTS` (each failure-proven); phantom workbench route implemented; two order-dependency bugs (`D-15-06`); ASCII-locale console crash fixed (`D-15-07`); `docs/INDEPENDENCE.md` honestly marks organisational verifier independence as unevidenced (`Q-ORG-01`, `Q-ORG-02`, OPEN).
- **Package metadata aligned:** `pyproject.toml` `version` 0.1.0 → 1.0.1. Nothing frozen changed; `schema_version` remains `1.0.0`; frozen surface still 30 files, `0747baf0…`.
- **`v1.0.1` tagged and released after re-verification** (clean clone, tarball without `.git`, CI `docker-offline` green on the release commit). See `docs/PHASE_REPORTS/PHASE-16.md` (v1.0.1 addendum) and `docs/RELEASE_NOTES.md`.

## 1.0.0 — Full Master TZ v3.0 & Phase 9 Risk Remediation Release (2026-11-21)

- **Kernel Sandbox & Container Hardening (`P-012` / `R-09`):** Added stdlib Linux `unshare` + `MS_REC|MS_PRIVATE` `tmpfs` path masking + `PR_SET_NO_NEW_PRIVS` + `x86_64`/`aarch64` `seccomp-BPF` syscall filter (`harness/ns_launcher.py`, `harness/sandbox.py`), non-root `UID 10001` `Dockerfile`, offline `docker-compose.yml`, and CI `docker-offline` job (`--network=none`).
- **CSPRNG Production Sealing & Semantic Truth Attestation (`L4`):** Added `seal/rekey.py` (`python3 -m seal.cli rekey-production`) and Stage-2 `scoring/crosscheck.py` `semantic_truth_verification` inside `scoring/scorer_cli.py`.
- **Multilingual (`ru`/`kk`/`en`) & NLP Layer (Phase 10 + `L5`):** Added isolated `"text_layer"` generator (`gen/core/text.py`), `nlp/` (`normalize.py`, `matching.py`, 4-tier `hierarchy.py`, `injection_guard.py`), and diagnostic `scoring/explanation_linter.py`.
- **Prompt-Injection Robustness Track (Phase 11):** Added `configs/robustness/default.json` and paired Clean vs Injected twin evaluator (`judge/robustness_audit.py`).
- **Arena, 22 Attacks, AutoHacker, Shortcut & Canary Audits (Phase 12):** Added 7 public baselines (`arena/policies/catalog.py`) + separated `oracle_test_only`, 22 red-team attacks `AT-01..AT-22` (`arena/attacks/catalog.py`), seed-grouped `TRAIN`/`DEV`/`HELDOUT` AutoHacker with 95% bootstrap CIs (`arena/autohacker.py`), within-table L2 Logistic Regression shortcut auditor (`macro_ROC_AUC <= 0.55`, `judge/shortcut_audit.py`), and 10-channel canary & API fuzzer (`judge/canary_fuzzer.py`).
- **Metamorphic, RNG Isolation, Interleaved Env & 26-Mutant Suites (Phase 13):** Added `metamorphic/suite.py` (`M-01..M-07`), `judge/mutation_suite.py` (`26/26` mutants killed), `tests/generator/test_rng_isolation.py`, and `tests/env/test_interleaved_isolation.py`.
- **Judge Kit, Offline HTML Report, Jury Demo & Release Freeze (Phases 14–17):** Upgraded `judge/verify.py` (`RC-001..RC-012`), `judge/performance_and_deps.py`, `judge/report.py` (offline `report.html`), `tools/demo_walkthrough.py`, and `tools/freeze_release.py` (`configs/release_freeze.json`).

## 0.9.0 — Phases 2–9 & Official 2026-11-20 Compliance (2026-11-21)

- Exact integer/rational money, timezone, anti-shortcut ID, and 15-invariant primitives (`core/`, `invariants/`).
- Clean Twin accounting generator, 16 clean distractors, and 4 anomaly operators (`gen/`).
- Independent public-only verifier with ProofGraph DAG and minimal-evidence ablation (`verifier/`, `scoring/crosscheck.py`).
- Official Genesis FinTech 2026-11-20 adapter & mirror suite (`judge_adapter.py`, `tests/official/`).
- 3-process `CLOSED_EVAL` harness, commit-reveal, hashchain, size-bound Merkle receipts, and fresh-process replay (`seal/`, `harness/`).

## 0.1.0 — Phase 1 (2026-11-20)

- Repository skeleton per Master TZ 6; frozen v1.0.0 JSON schemas; canonical JSON; AST import-boundary scanner.
