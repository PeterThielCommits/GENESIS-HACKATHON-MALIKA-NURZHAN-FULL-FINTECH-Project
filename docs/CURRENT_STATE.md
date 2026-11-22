# Current State — 2026-11-22

- Active branch: `arena/a85b561e-genesis-hackathon-malika-nurzh`, base `36a265c` (merge of PR #20, `main`).
- **Phase 14 re-audit DONE, EXIT GATE 14 PASS** on a clean checkout: the documented command `make verify` run against a tree built from `git ls-files` (empty `artifacts/reports/latest/`) exits 0 with 12/12 gates PASS in ~62 s and 21 complete artifacts. Scope, defects and evidence: `docs/PHASE_REPORTS/PHASE-14.md`; decisions `D-14-02`, `D-14-03`.
- Measured during the Phase 14 re-audit: `make verify` 12/12 PASS, `make verify-core` 6/6 PASS, `make lint` CLEAN, `tools/freeze_release.py --verify` PASS (30 frozen files, `0747baf0…`). The full-suite count has since grown with new tests — the authoritative current figure is always the generated block in `README.md`.
- Evidence dir is now self-describing: every JSON report carries the TZ §23.5 envelope (code version, config hash, timestamp, platform, Python, command), enforced by `make verify` as exit 2 on violation; `report_index.json` indexes all 20 evidence files with `missing: []`; `report.html` is fully offline (0 external references) and renders real replay 5/5.
- Exit-code contract exercised with negative tests: malformed rubric map → 2, missing `verify_summary.json` → 5, malformed summary → 2, offline-HTML violation → 4.
- No production or frozen release files changed (`contracts/*`, `configs/*`, `judge/rubric_map.json`, Master TZ untouched). Phase 12 PR #15 is merged, not open.
- **Merged:** PR **#18** → `main` as merge commit `99df116` (2026-11-21T23:43:03Z), head `baa5b67`; CI `core` + `docker-offline` PASS. The merged `main` tree is byte-identical to the verified head, and post-merge `make verify` on `main` is PASS 12/12 in 50.1 s with 21 artifacts; `freeze_release --verify` PASS (30 files, `0747baf0…`). No open PR for this phase.

- **Phase 15 re-audit DONE, EXIT GATE 15 PASS** (branch above). Documentation is now mechanically tied to evidence: `make docs-verify` re-measures 22 facts and runs 11 checks against `artifacts/reports/latest/` (and `make verify` runs it automatically once artifacts exist); `make demo-backup` chains verify + docs + replay + freeze. Decisions `D-15-01`, `D-15-02`.
- New this phase: `docs/API_USAGE.md`, `docs/POLICY_PROTOCOL.md` (Task 15.3 was previously missing), `docs/DEMO.md`, `tools/verify_doc_claims.py`, `tests/judge/test_doc_claims.py`; `docs/DESIGN.md` rewritten as-built.
- Measured: `make verify` **12/12 PASS** (61.9 s, 20 artifacts), also PASS on a clean `git ls-files` tree (61.1 s), full suite **479 tests** OK (1 optional Hypothesis skip, `critical_skipped=0`), `make docs-verify` PASS, `make demo-backup` PASS, lint CLEAN, freeze **30 files** intact (`0747baf0…`), `official_score_claimed: false`.
- No frozen file changed (`contracts/*`, `configs/*`, `judge/rubric_map.json`, Master TZ untouched).

## Phase 16 release candidate DONE, EXIT GATE 16 PASS (branch above, PR #21)
- **16.2 clean machine:** `make verify` on a fresh `git clone` with an emptied evidence dir → **12/12 PASS** (69.7 s); `make rc-check` PASS.
- **16.3 offline Docker:** CI `docker-offline` green (`--network=none --read-only --cap-drop ALL --cpus=2 --memory=4g`, `PIP_NO_INDEX=1`, non-root).
- **16.4 all trajectories:** NEW `make replay-all` → **80/80 runs, 567 steps byte-identical**, policy-independent.
- **16.5 audit:** NEW `make release-audit` → 6/6 PASS: 0 credentials in 494 files, 0 forbidden paths, 5 449 805 bytes (budget 50 MB), 109 runtime modules with **0** external dependencies.
- **16.6 submission:** entrypoint imported from cwd=`/` — 3 exports, `reset` 2-tuple, `step` 5-tuple, 5/5 tool names accepted; non-root offline image with the single documented command.
- `make rc-check` chains verify + docs-verify + replay-all + release-audit, and was run PASS in **three trees**: Git checkout, clean clone, and a `git archive` tarball with no `.git`.
- Five real defects fixed (none frozen): `.gitkeep` counted as evidence made the artifact count depend on the machine (**D-15-03**); C-locale `UnicodeEncodeError` inside the container; clean-clone tests gating on gitignored outputs (the `D-15-01` trap, one directory over); RC-001 reading a gitignored report; an audit that errored on `.git`-less trees — which is exactly what the Docker image is (**D-16-01**).
- Measured: `make verify` **12/12 PASS** (71.6 s, 20 artifacts, **479 tests**, `critical_skipped=0`), `make docs-verify` PASS (22 facts, 11 checks), lint CLEAN, freeze **30 files** intact (`0747baf0…`), `official_score_claimed: false`.

## Next actions
1. **16.7 / 16.8 (release authority):** after PR #21 merges, tag the merge commit (`v1.0.0`) and publish the GitHub release using `docs/RELEASE_NOTES.md`; record the tag and commit hash in `docs/STATUS.md` and `docs/PHASE_REPORTS/PHASE-16.json`.
2. Phase 17 (post-release evidence freeze): archive code/config hashes, the verify and replay reports, the rubric map and decisions; final tag; final status and limitations; confirm the repository alone reconstructs the context.
3. Review this phase's diff — especially `tools/release_audit.py`, `tools/replay_all_trajectories.py` and `judge/report.py` (`_is_artifact`).
4. Re-run `make rc-check && python3 tools/freeze_release.py --verify` for the reviewed commit.
