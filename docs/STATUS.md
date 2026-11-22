# Project Status Matrix (Release v1.0.2)

| Phase / Track | Title | Status | Gate / Primary Evidence |
| --- | --- | --- | --- |
| Phase 0–1 | Contracts, Schemas & Architecture Boundaries | DONE | Frozen v1.0.0 schemas, `tools/check_import_boundaries.py`, `docs/PHASE_REPORTS/PHASE-01.md` |
| Phase 2 | Canonical JSON, Money, Decimal, Time & ID Primitives | DONE | `core/money.py`, `core/time_rules.py`, `core/ids.py`, `docs/PHASE_REPORTS/PHASE-02.md` |
| Phase 3 | Clean Twin Accounting Generator & 16 Distractors | DONE | `gen/core/clean_twin.py`, `gen/distractors/`, `invariants/checks.py` |
| Phase 4 | Mutation Operators (Duplicate & Partial) & Truth Diff | DONE | `gen/errors/operators.py`, `gen/truth.py`, `gen/serialize.py` |
| Phase 5 | Public-Only Interactive Environment & Safe Calc | DONE | `env/environment.py`, `env/calc.py`, `env/cursors.py`, `env/jsonl_server.py` |
| Phase 6 | Optimal Matcher, Rational Reward & Diagnostics | DONE | `scoring/matcher.py`, `scoring/reward.py`, `scoring/diagnostics.py`, `docs/PHASE_REPORTS/PHASE-06.md` |
| Phase 7 | FX Rate Mismatch & Period Cutoff Operators | DONE | `gen/errors/fx_cutoff.py`, `docs/PHASE_REPORTS/PHASE-07.md` |
| Phase 8 | Independent Verifier, ProofGraph & Release Gate | DONE | `verifier/`, `scoring/crosscheck.py`, `docs/PHASE_REPORTS/PHASE-08.md` |
| Phase 9 | Kernel-Isolated Sealed Evaluation, CSPRNG Rekey & Receipts | DONE | `harness/ns_launcher.py`, `harness/sandbox.py`, `seal/`, `docs/PHASE_REPORTS/PHASE-09.md` |
| Phase 10 | Multilingual (`ru`/`kk`/`en`) Text, NLP & Evidence Hierarchy | DONE | `gen/core/text.py` (pinned dict versions), `nlp/` (lazy facade; hierarchy enforced in `scoring/scorer_cli.py`), `scoring/explanation_linter.py`, `tools/explanation_report.py`, `tests/nlp/test_phase10_text_layer.py`, `docs/PHASE_REPORTS/PHASE-10.md` (audit 2026-11-21, `D-10-02`) |
| Phase 11 | Prompt-Injection Robustness Twin Evaluation | DONE | `configs/robustness/default.json`, `judge/robustness_audit.py`, `docs/PHASE_REPORTS/PHASE-11.md` |
| Phase 12 | Arena (8 Baselines, 22 Attacks), AutoHacker & Shortcut/Canary Audits | DONE | `arena/`, `judge/shortcut_audit.py`, `judge/canary_fuzzer.py`, `docs/PHASE_REPORTS/PHASE-12.md` |
| Phase 13 | Property, Metamorphic (`M-01..M-07`), RNG & 26-Mutant Suites | DONE | `metamorphic/suite.py`, `judge/mutation_suite.py`, `docs/PHASE_REPORTS/PHASE-13.md` |
| Phase 14 | 12-Gate Judge Kit & Self-Contained Offline HTML Report | DONE (re-audit 2026-11-21) | `judge/verify.py`, `judge/report.py`, `judge/schemas.py`, `judge/performance_and_deps.py`, `tests/judge/test_judge_kit.py`, `docs/PHASE_REPORTS/PHASE-14.md` |
| Phase 15 | Complete Documentation & Demo (re-audit 2026-11-21) | DONE | `tools/verify_doc_claims.py`, `docs/API_USAGE.md`, `docs/POLICY_PROTOCOL.md`, `docs/DEMO.md`, `tests/judge/test_doc_claims.py`, `docs/PHASE_REPORTS/PHASE-15.md` |
| Phase 16 | Hardened Offline Docker, Compose & CI Gate Verification | DONE (re-verified 2026-11-22, `v1.0.1`) | `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`, `docs/PHASE_REPORTS/PHASE-16.md` (incl. v1.0.1 addendum); tag **`v1.0.1`** supersedes `v1.0.0` (`D-16-03`) |
| Phase 17 | Post-Release Evidence Freeze (contract + release surface + verdicts) | DONE (deep execution 2026-11-22) | `tools/freeze_release.py`, `configs/release_freeze.json` (0747baf0…, D-12-02), `tools/evidence_freeze.py`, `tools/release_evidence.py`, `docs/EVIDENCE/`, `docs/PHASE_REPORTS/PHASE-17.md` (D-17-02, D-17-03) |
| Official 2026-11-20 | FinTech Checks (`C01..C20`, `D01..D20`, `Block 3`, `P01..P20`, `Baselines`) | DONE | `judge_adapter.py`, `adapter/official_env.py`, `scoring/official_scorer.py`, `tests/official/` |

## Phase 11 re-audit (2026-11-21)
24-pair robustness engineering gate PASS; 360 tests and 12/12 verify gates PASS.
Release-freeze verification FAIL (existing loader hash drift); human sign-off pending.
See `docs/PHASE_REPORTS/PHASE-11.md`; do not interpret earlier DONE rows as release approval.

## Phase 12 re-audit (2026-11-21)
Arena 7 baselines + oracle separated, 22/22 attacks AT-01..AT-22 defended, seed-grouped AutoHacker delta +0.2502, shortcut 0.5389 ≤0.55, 0 canary hits (10 channels) — 12/12 verify PASS, 360 tests, lint CLEAN; env/loader D-10-03 bounded-read restoration applied (RC-001 fix).
Freeze re-synced under D-12-02: `contracts/loader.py` 610f07…→4dbb8b… (1717→4244 B), aggregate caf9405e…→0747baf0…; `freeze --verify` now PASS (30 files). Docker structurally validated; clean-clone verified via file:// clone.
See `docs/PHASE_REPORTS/PHASE-12.md` and `docs/AGENT_REPORTS/2026-11-21/arena-phase-12-re-audit.md`.

## Phase 13 re-audit (2026-11-21)
EXIT GATE 13 PASS: 26/26 instrumented mutants killed, 7/7 metamorphic transforms over 28 pairs; 372 tests (one optional Hypothesis skip), 12/12 verify gates. Optional Hypothesis path independently passed. See `docs/PHASE_REPORTS/PHASE-13.md` and issue #16; QA/CI review remains pending.

## Phase 14 re-audit (2026-11-21)
EXIT GATE 14 PASS **on a clean checkout**: `make verify` against a tree built from `git ls-files` (empty `artifacts/reports/latest/`) → exit 0, 12/12 gates in ~62 s, 21 complete artifacts; 410 tests (1 optional Hypothesis skip), 38 Judge Kit tests, lint CLEAN, freeze `0747baf0…` intact.
Three blocking defects fixed, all in non-frozen files: (1) `judge/report.py` f-string `x or {{}}` parsed as a set literal → `TypeError: unhashable type: 'dict'` on every clean clone; (2) `judge/verify.py` invoked `report.py` before writing `verify_summary.json` → exit 5 on a clean clone; (3) the pre-report completeness check permanently forced exit 5. Also fixed: `Replay Suite 0/0` mis-rendering (real 5/5), missing TZ §23.5 metadata envelope on `replay_report.json` and on the reward-property matrix report, invariant catalog 15→17, and unguarded metric access in `judge/performance_and_deps.py`.
New: `judge/schemas.py` (stdlib validators incl. §23.5 envelope, exit 2 on violation), `tests/judge/` (38 tests), `docs/PHASE_REPORTS/TEMPLATE.md`. Decisions `D-14-02`, `D-14-03`.
Merged as PR **#18** (`baa5b67` → merge commit `99df116`, 2026-11-21T23:43:03Z); CI `core` + `docker-offline` PASS; post-merge `make verify` on `main` PASS 12/12 (50.1 s, 21 artifacts), freeze intact. Merged tree byte-identical to the verified head. See `docs/PHASE_REPORTS/PHASE-14.md` / `.json`. This row is not release authorization.

## Phase 15 re-audit (2026-11-21)
EXIT GATE 15 PASS. The phase's own sentence — "the jury can deploy from the README and verify the key claims" — is now machine-enforced: `make verify` (12/12, 490 tests, 20 artifacts, on a clean tree too) → `make docs-verify` (22 measured facts, 11 checks) → `make demo-backup` (verify + docs + replay 5/5 + freeze), all exit 0.
Task 15.3 had **no deliverable** before this pass; added `docs/API_USAGE.md` and `docs/POLICY_PROTOCOL.md`. Corrected a factually wrong encoding-transform list in `docs/THREAT_MODEL.md` (claimed 9, listed 8, four bogus names), the stale 317-test README claim, non-matching baseline durations, and a phantom `D-03-01` citation now blocked by a referential-integrity check. `docs/DESIGN.md` rewritten as-built.
New: generated README facts block + stale-literal denylist + decision-ID integrity, proven to fire against four injected faults. Decisions `D-15-01`, `D-15-02`. No frozen file changed; freeze `0747baf0…` intact. This row is not release authorization.

## Phase 16 release candidate (2026-11-22)
EXIT GATE 16 PASS: feature-frozen, verified on a clean machine, replayed end to end, audited, and the official entrypoint proven by execution.
- **16.2 clean clone:** `make verify` on a fresh `git clone` with an emptied evidence dir → **12/12 PASS** (69.7 s); `make rc-check` PASS.
- **16.3 offline Docker:** CI `docker-offline` green (`--network=none --read-only --cap-drop ALL --cpus=2 --memory=4g`, `PIP_NO_INDEX=1`, non-root `USER 10001`).
- **16.4 all trajectories:** NEW `make replay-all` → **80/80 runs, 567 steps byte-identical** (policy-independent: recorded actions replayed against rebuilt episodes).
- **16.5 audit:** NEW `make release-audit` → 6/6 PASS — 0 credentials in 494 files, 0 forbidden paths, 5 449 805 bytes (budget 50 MB), 109 runtime modules with **0** external dependencies.
- **16.6 submission:** official entrypoint imported from cwd=`/` — 3 exports, `reset` 2-tuple, `step` 5-tuple, **5/5** tool names accepted; non-root offline image with the single documented command.
Five real defects fixed (all non-frozen): `.gitkeep` counted as evidence made the artifact count 21/20 depending on the machine (**D-15-03**); C-locale `UnicodeEncodeError` in the container; clean-clone tests gating on gitignored outputs (the D-15-01 trap, one directory over); RC-001 reading a gitignored report; and an audit that errored on `.git`-less trees — which is exactly what the Docker image is. Decisions `D-15-03`, `D-16-01`. Verified in three trees (checkout, clean clone, `git archive` tarball); 30 frozen files intact, `official_score_claimed: false`.
**Released:** tag **`v1.0.0`** (annotated) on commit **`8da0af2`** (merge of PR #21); GitHub release https://github.com/PeterThielCommits/GENESIS-HACKATHON-MALIKA-NURZHAN-FULL-FINTECH-Project/releases/tag/v1.0.0 from `docs/RELEASE_NOTES.md`.
The tag was placed only after `make rc-check` PASS **on that commit** from clean-clone conditions (verify 12/12, replay-all 80/80, release-audit 6/6).
See `docs/PHASE_REPORTS/PHASE-16.md` / `.json` and `docs/RELEASE_NOTES.md`. This row is not a jury score.

## Mandatory-target audit (2026-11-22, post-release)
Audited against the Universal Phase Execution Prompt and TZ §23.2. Honest finding: nine required `make` targets had **never been executed** by earlier phases — only assumed — and running them exposed four real defects, one a release blocker.
- **All 19 targets now executed in one sequence, on a dirty tree, `LC_ALL=C`: 19/19 exit 0, 0 failures** — `help, setup, lint, test-property, build-episodes, verify-core, replay, audit-shortcuts, mutation-test, test-official, report, official-eval, test, docs-verify, demo, demo-backup, replay-all, release-audit, rc-check`.
- **Defect 1 (release blocker):** `.dockerignore` had `episodes/*/sealed/`, which does **not** match the real depth-2 layout `episodes/dev/ep_x/sealed/` (Docker matches per path element). The submission image would have carried `truth.json` — a `REQ-ARENA-005` violation. Fixed; `TestDockerIgnore` fails on the old pattern.
- **Defect 2:** `make verify-core` FAILED after `make build-episodes`, because the no-git filesystem walk scanned untracked sealed truth (20 false `FILELIST` hits). The walk now honours ignore rules.
- **Defect 3:** `make official-eval` wrote `official_eval_summary.json` into the frozen evidence dir, making the documented "20 artifacts" false. Relocated to `artifacts/reports/evaluation/`.
- **Defect 4:** the published gate count came from the *last run's* summary, so `verify-core` (6 gates) made the next full run report `DRIFT`. It now comes from the frozen rubric map (12 gates).
- Determinism across the sweep: `trajectories.jsonl` rewritten by `official-eval` differs in **`duration_s` only** across all 80 rows; `replay-all` still PASS 80/80.
- `CONTRIBUTING.md` created (was missing). Decision `D-16-02`. Report: `docs/AGENT_REPORTS/2026-11-22/arena-universal-prompt-audit.md`.
- These fixes are **post-release hardening** and are not in tag `v1.0.0`; cutting `v1.0.1` is a release-authority decision.

## Phase 15 structural audit (2026-11-22)
EXIT GATE 15 re-established on a stricter reading. The numeric claim gate was sound
but measured one axis; auditing the literal gate text ("the jury can deploy from the
README and verify the key claims") found **19 defects in which every number was
correct and the prose around it described something that does not exist**.
- **Added 6 structural detectors** to `tools/verify_doc_claims.py`, each proven to
  fail by injected fault: `C-PATHS` (17 docs vs the filesystem), `C-DATADICT`
  (field lists vs a real episode, both directions), `C-DEMO` (published demo table
  vs `demo_walkthrough.py::SEGMENTS`), `C-WORKBENCH-API` (routes vs dispatchers),
  `C-COMMANDS` (scripts/modules/targets vs the tree), `C-REWARD` (provenance vs
  `official_scorer`'s live constants). `tests/judge/test_doc_claims.py` 25 → 51.
- **Serious find, disclosed not fixed:** `docs/INDEPENDENCE.md` claimed a "different
  human owner" built the verifier. This repository was produced by AI agents in one
  session; `.github/CODEOWNERS` named four handles that do not exist. The technical
  zero-common-mode separation *is* proven and tested; the organisational half is
  now explicitly marked **unevidenced** and raised as `Q-ORG-01`/`Q-ORG-02` (OPEN).
- **Phantom workbench route implemented:** `GET /api/episode/<split>/<id>/overview`
  was documented since Phase 15 and returned **404**. Now serves public metadata,
  manifest validity and table counts; still 404s on unknown episodes and `../`.
- `docs/CONTEXT/ARCHITECTURE_SNAPSHOT.md` was a plan: it named 7 modules that never
  existed. Rewritten as-built. `docs/DATA_DICTIONARY.md` documented 2 fields that do
  not exist and omitted 6 that do (including the four distractor-exclusion fields).
  `docs/DEMO.md` described "five segments" for a six-segment program with a clock up
  to 5 s out of step. Three docs called the reward "provisional" after `D-18-01`
  made it official. `python3.11 -m make verify` does not run.
- **Two order-dependency bugs fixed** (`D-15-06`, third occurrence of this class):
  test counts were read from whichever run wrote `verify_summary.json` last, so
  `make verify-core && make docs-verify` failed on a correct tree; and two doc-claim
  tests re-litigated the whole gate inside RC-001. Counts now come from `unittest`
  discovery; the locale test asserts the locale contract only. Proven in three
  sequences: `verify-core`→`docs-verify`, `report`→`docs-verify`, `docs-verify`×2.
- Measured: `make verify` **12/12 PASS** (49.8 s, 20 artifacts, **528 tests**,
  `critical_skipped=0`) **from an empty evidence directory**; docs gate **22 facts,
  17/17 checks**; lint CLEAN; freeze **30 files intact** (`0747baf0…`);
  `official_score_claimed: false`. No frozen file changed.
- Decisions `D-15-04`, `D-15-05`, `D-15-06`. Report `docs/PHASE_REPORTS/PHASE-15-STRUCTURAL-AUDIT.md`.


## Phase 15 follow-up hardening (2026-11-22, D-15-07)

Supersedes the earlier audit's test/check totals, not its historical sweep.
- Fixed `judge/verify.py` crashing on ASCII-only console output after completing
  its gates; all main-console writes use a locale-safe helper. Regression tests
  also cover arbitrary Unicode diagnostics and explicit narrow streams.
- Added seventh detector `C-COUNTS`: README's stale 522 and DEMO's stale 490 were
  not covered by the old literal denylist. Recognised prose totals now derive
  from discovery; `--write` repairs numeric spans without changing formatting.
- Latest clean `make verify`: **12/12 PASS**, **540 tests**, 20 artifacts,
  47.416 s; RC-001 has 19 optional/bootstrap skips, summary 20 optional skips,
  **zero critical skips**, no missing artifacts or schema errors.
- Empty evidence + trajectories under `LC_ALL=C PYTHONIOENCODING=ascii`:
  **12/12 PASS**, 45.443 s, zero non-ASCII bytes; 26 summary optional skips,
  **zero critical skips**. Populated-evidence suite: 540 tests OK, one optional skip.
- `make docs-verify`: **22 facts / 18 checks PASS**. Lint CLEAN. Freeze still
  **30 files intact**, `0747baf0…`. No scoring, tag, or frozen-contract changes.
- Count recognition is intentionally bounded (see D-15-07); organisational
  independence remains unevidenced. Q-ORG-01/02, Q-REL-01, Q-DOC-01 remain OPEN.

## Phase 16 v1.0.1 re-verification and release (2026-11-22)

Phase 16 was re-executed in full against the post-`v1.0.0` tree (merge of PRs #23, #24, #25)
before cutting the release the repo recommended since `D-16-02`. The tag `v1.0.0` ships a
submission image that would contain `sealed/truth.json`; `v1.0.1` is the corrected submission
artifact (`D-16-03`). **EXIT GATE 16 re-confirmed PASS on this tree.**

- **16.2 clean clone:** `make rc-check` from a fresh `git clone` with an emptied evidence dir →
  **exit 0** — verify **12/12** (82.2 s), docs **22 facts / 18 checks**, replay-all **80/80 runs,
  567 steps**, release-audit **6/6**. Third tree `git archive` (no `.git`, i.e. the image case):
  release-audit **6/6**, entrypoint PASS.
- **16.3 offline Docker:** no Docker daemon in the execution sandbox (recorded UNVERIFIED there,
  never PASS); CI `core` + `docker-offline` both **success** on the release-candidate commit
  (`9737961`, run `45009197767`): `--network=none --read-only --cap-drop ALL --cpus=2 --memory=4g`,
  `PIP_NO_INDEX=1`, non-root `USER 10001`.
- **16.4 replay-all:** PASS (**80/80 runs, 567 steps byte-identical**) — rerun on this tree.
- **16.5 audit:** SECRETS 0 matches (523 text files scanned), FILELIST 0 forbidden paths, SIZE
  within the 50 MB budget, DEPS **0 undeclared external imports** (109 runtime modules).
- **16.6 submission:** official entrypoint imported from cwd=`/` — 3 exports, `reset` 2-tuple,
  `step` 5-tuple, **5/5 tool names accepted**; non-root offline image with the single documented
  command; literal-conformance of `judge_adapter.py` re-checked by eye.
- **Freeze:** 30 frozen files intact, `aggregate_sha256 = 0747baf0…` (no frozen change).
- **Fixes in this session:** `pyproject.toml` `version` 0.1.0 → 1.0.1 (unreferenced package
  metadata, stale); release notes retitled to v1.0.1 with `v1.0.0` kept as history.
- **Released:** annotated tag **`v1.0.1`** (object `3601493…`) on merge commit
  `640c585` (PR #26); CI green on the merge commit (run `45020669250`) and on the PR
  (run `45020405354`); `make rc-check` PASS from a clean GitHub clone before tagging.
  GitHub release `v1.0.1` published 2026-11-22T12:11:27Z with report and limitations
  from `docs/RELEASE_NOTES.md` and the measured tag-tree figures.
  `official_score_claimed: false` (TZ §23.6). Tag `v1.0.0` retained, unchanged.
- **Open, carried:** `Q-ORG-01` / `Q-ORG-02` (organisational independence unevidenced — human
  owner decision), `Q-DOC-01` (partial), `Q-REL-01` **RESOLVED**.
- Report: `docs/PHASE_REPORTS/PHASE-16.md` (v1.0.1 addendum) and
  `docs/AGENT_REPORTS/2026-11-22/arena-phase-16-v1-0-1-release.md`.

## Post-v1.0.1 risk-closure round (2026-11-22, branch `arena/d0407793-genesis-hackathon-malika-nurzh`)

Phase-16 final-report risks, closed with evidence (not by moving tags, not by editing frozen files):

- **Independent re-derivation (risk: organisational independence unevidenced).**
  New `independent_verifier/` — a from-scratch Stage-1 implementation authored from
  `spec/verifier_algorithm.md` + `contracts/` alone (own `Fraction` FX, `zoneinfo`
  periods, ProofGraph acyclicity + path checks, minimal-evidence ablation).
  Measured: all 6 dev + 4 train committed episodes re-derive signature-identically
  (identical `episode_public_hash`); official `D01..D20` (`master_seed=2026`)
  cross-check to sealed truth at **F1 = 1 exact, FP = 0, FN = 0** on all 20; evidence
  enumeration complete; zero ProofGraph invariant errors. Regression-locked by
  `tests/independent_verifier/test_independent_rederivation.py` (8 tests incl.
  runtime file-open spy, fresh-subprocess import, boundary-scanner inclusion).
  Evidence: `docs/EVIDENCE/independent-rederivation-2026-11-22.json`.
  **`Q-ORG-01` remains OPEN** — same-session authorship; organisational separation
  is a human decision, not a code change.
- **Docker offline check was CI-only.** No container runtime exists on the execution
  host (probed: `docker`/`podman`/`buildah`/`nerdctl`/`ctr`/`runc`/`containerd`
  absent). Added `tools/offline_local_check.py`: user+net+mount namespace, read-only
  bind of the tree, tmpfs `artifacts/`, no network route,
  `PYTHONDONTWRITEBYTECODE=1` — full suite **OK (skipped=26)**. Static
  Dockerfile/`.dockerignore`/Makefile hardening audit: 10/10 PASS. The Docker image
  build remains **CI-authoritative** (run `45021422570` on `main` = `core` +
  `docker-offline` success; also `45020669250` on the `v1.0.1` tag commit). Local
  approximation scope and limits recorded in
  `docs/EVIDENCE/offline-local-2026-11-22.json`.
- **Prose machine-checkability extended.** `tools/verify_doc_claims.py` gains
  `C-EVIDENCE` (evidence artifacts exist, carry full git SHA, record PASS),
  `C-SCORE-HONEST` (every `official_score_claimed` asserts `false`),
  `C-QORG-OPEN` (`Q-ORG-01`/`Q-ORG-02` not presented as RESOLVED). Gate now
  **21/21 checks PASS** (was 18).
- **v1.0.0 release notes lacked a supersession pointer.** GitHub release `v1.0.0`
  body now opens with a SUPERSEDED banner pointing at `v1.0.1` (`D-16-02`/`D-16-03`);
  the tag itself is unchanged (tags cannot move). Repo docs already carried the
  pointer (`docs/RELEASE_NOTES.md`, `docs/CHANGELOG.md`).
- Suite is now **548 tests** (8 new); README generated block re-rendered by
  `python3 tools/verify_doc_claims.py --write` (the only sanctioned edit path).
- `code_version` stays `twinledger@1.0.0` (names the frozen contract line, `D-16-03`);
  `official_score_claimed: false`; `Q-ORG-01`/`Q-ORG-02`/`Q-DOC-01` OPEN.

## Phase 17 deep execution (2026-11-22) — release v1.0.2

EXIT GATE 17 re-executed against the strict reading of its sentence: *"релиз можно
восстановить и проверить без устных пояснений команды"* — the release must be
restorable **and** verifiable from the repository alone. The previous Phase 17
only froze the 30 **contract** surfaces; the **release surface**, the measured
**verdicts**, the rubric map, the decisions and a **reconstruct command list**
were not archived anywhere.

- **17.1 — release surface archived.** New `tools/evidence_freeze.py` hashes
  every tracked file (code, configs, contracts, rubric map, Dockerfile,
  Makefile, entrypoint, episodes, docs) into
  `docs/EVIDENCE/evidence_freeze.json` (548 tracked files, one aggregate digest).
- **17.2 — verify/replay reports archived as verdicts.** The manifest stores the
  *verdicts* of `verify_summary`, `replay_report`, `report_index`,
  `release_audit`, `doc_claims` and `trajectory_replay` (status + counts).
  Report bytes carry timestamps/run-ids and are regenerable, so byte-identity
  is deliberately **not** required on a re-run; the verdict is the archived fact.
- **17.3 — rubric map + decisions archived.** New `tools/release_evidence.py`
  builds `docs/EVIDENCE/phase-17-release-evidence-2026-11-22.json`: the frozen
  digest, the twelve rubric gates `RC-001..RC-012`, the decision register, and
  the exact commands a stranger runs to rebuild and re-verify the release.
- **17.4 — final commit + release tag.** Tag **`v1.0.2`** on the merge commit of
  the Phase 17 PR; `v1.0.0` and `v1.0.1` are **not** moved (published tags never
  move — `D-16-03`).
- **17.5 — final status + limitations.** This section, `docs/LIMITATIONS.md`
  (now L1..L10), `docs/CURRENT_STATE.md`.
- **17.6 — next agent can reconstruct from the repo only.**
  `docs/HANDOFF/phase-17-evidence-freeze.md` + `docs/CONTEXT/NEXT_AGENT.md` +
  the machine-checked `reconstruct.commands` list in the archive.

**Four real defects were found and fixed while auditing the published
evidence** (all non-frozen; each with a regression test that fails on the old
code):

| ID | Severity | Defect |
|---|---|---|
| BUG-TL-0005 | P1 | `reward_property_matrix.json` published the **superseded provisional formula** and `provisional: true` although every number in it had been computed by the official implementation since `D-18-01` |
| BUG-TL-0006 | P2 | `robustness_report.json` published `score_contract: "scoring.reward (internal provisional; not official_scorer)"` — false since `D-18-01` made `scoring.official_scorer` the single implementation |
| BUG-TL-0007 | P3 | stale "provisional / pending Q-005" wording in `scoring/matcher.py` and in a property-test comment, although `Q-005` was resolved on 2026-11-20 |
| BUG-TL-0008 | P2 | the documentation gate's artifact contract named `replay_all_report.json` (a file that does not exist; the real file is `trajectory_replay.json`) and omitted `reward_property_matrix.json`, so a correct citation was reported as a phantom path |

The published reward contract is now **derived, never re-typed**
(`scoring/official_scorer.official_formula_text()` → `scoring.reward.FORMULA`
→ the reward matrix), and `C-REWARD` audits the *generated artifacts* as well
as the prose (`D-17-03`).

**Two gates closed:** the contract freeze is now a **test**
(`tests/judge/test_release_freeze.py`: the tree must match the committed
manifest, the frozen surface must be exactly the declared 30 files, and the
aggregate must still be the released `0747baf0…`), and the release archive is
now a **check** (`C-ARCHIVE` in `tools/verify_doc_claims.py`). `make
evidence-verify` is wired into `make rc-check` and into the CI `core` job, so
the committed archive must match the committed tree.

`official_score_claimed: false`; `Q-ORG-01` / `Q-ORG-02` / `Q-DOC-01` remain
OPEN (human decisions). No frozen file changed (`freeze_release --verify` →
30 files, `0747baf0…`); no published tag moved; `code_version` stays
`twinledger@1.0.0`. See `docs/PHASE_REPORTS/PHASE-17.md` and
`docs/HANDOFF/phase-17-evidence-freeze.md`. This row is not a jury score.
