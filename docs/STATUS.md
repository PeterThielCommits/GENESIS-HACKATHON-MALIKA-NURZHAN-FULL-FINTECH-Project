# Project Status Matrix (Release v1.0.0)

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
| Phase 16 | Hardened Offline Docker, Compose & CI Gate Verification | DONE | `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`, `docs/PHASE_REPORTS/PHASE-16.md` |
| Phase 17 | Post-Release Cryptographic Evidence Freeze | DONE | `tools/freeze_release.py`, `configs/release_freeze.json` (0747baf0…, D-12-02), `docs/PHASE_REPORTS/PHASE-17.md` |
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
Three blocking defects fixed, all in non-frozen files: (1) `judge/report.py` f-string `x or {{}}` parsed as a set literal → `TypeError: unhashable type: 'dict'` on every clean clone; (2) `judge/verify.py` invoked `report.py` before writing `verify_summary.json` → exit 5 on a clean clone; (3) the pre-report completeness check permanently forced exit 5. Also fixed: `Replay Suite 0/0` mis-rendering (real 5/5), missing TZ §23.5 metadata envelope on `replay_report.json` and `reward_property_matrix.json`, invariant catalog 15→17, and unguarded metric access in `judge/performance_and_deps.py`.
New: `judge/schemas.py` (stdlib validators incl. §23.5 envelope, exit 2 on violation), `tests/judge/` (38 tests), `docs/PHASE_REPORTS/TEMPLATE.md`. Decisions `D-14-02`, `D-14-03`.
Merged as PR **#18** (`baa5b67` → merge commit `99df116`, 2026-11-21T23:43:03Z); CI `core` + `docker-offline` PASS; post-merge `make verify` on `main` PASS 12/12 (50.1 s, 21 artifacts), freeze intact. Merged tree byte-identical to the verified head. See `docs/PHASE_REPORTS/PHASE-14.md` / `.json`. This row is not release authorization.

## Phase 15 re-audit (2026-11-21)
EXIT GATE 15 PASS. The phase's own sentence — "the jury can deploy from the README and verify the key claims" — is now machine-enforced: `make verify` (12/12, 481 tests, 20 artifacts, on a clean tree too) → `make docs-verify` (22 measured facts, 11 checks) → `make demo-backup` (verify + docs + replay 5/5 + freeze), all exit 0.
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
See `docs/PHASE_REPORTS/PHASE-16.md` / `.json` and `docs/RELEASE_NOTES.md`. This row is not release authorization.
