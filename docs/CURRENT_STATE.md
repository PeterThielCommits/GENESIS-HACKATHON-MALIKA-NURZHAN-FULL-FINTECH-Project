# Current State — 2026-11-21

- Active branch: `arena/41a4694b-genesis-hackathon-malika-nurzh`, base `ff6e470` (`Merge PR #19`, `main`).
- **Phase 14 re-audit DONE, EXIT GATE 14 PASS** on a clean checkout: the documented command `make verify` run against a tree built from `git ls-files` (empty `artifacts/reports/latest/`) exits 0 with 12/12 gates PASS in ~62 s and 21 complete artifacts. Scope, defects and evidence: `docs/PHASE_REPORTS/PHASE-14.md`; decisions `D-14-02`, `D-14-03`.
- Measured during the Phase 14 re-audit: `make verify` 12/12 PASS, `make verify-core` 6/6 PASS, `make lint` CLEAN, `tools/freeze_release.py --verify` PASS (30 frozen files, `0747baf0…`). The full-suite count has since grown with new tests — the authoritative current figure is always the generated block in `README.md`.
- Evidence dir is now self-describing: every JSON report carries the TZ §23.5 envelope (code version, config hash, timestamp, platform, Python, command), enforced by `make verify` as exit 2 on violation; `report_index.json` indexes all 21 artifacts with `missing: []`; `report.html` is fully offline (0 external references) and renders real replay 5/5.
- Exit-code contract exercised with negative tests: malformed rubric map → 2, missing `verify_summary.json` → 5, malformed summary → 2, offline-HTML violation → 4.
- No production or frozen release files changed (`contracts/*`, `configs/*`, `judge/rubric_map.json`, Master TZ untouched). Phase 12 PR #15 is merged, not open.
- **Merged:** PR **#18** → `main` as merge commit `99df116` (2026-11-21T23:43:03Z), head `baa5b67`; CI `core` + `docker-offline` PASS. The merged `main` tree is byte-identical to the verified head, and post-merge `make verify` on `main` is PASS 12/12 in 50.1 s with 21 artifacts; `freeze_release --verify` PASS (30 files, `0747baf0…`). No open PR for this phase.

- **Phase 15 re-audit DONE, EXIT GATE 15 PASS** (branch above). Documentation is now mechanically tied to evidence: `make docs-verify` re-measures 22 facts and runs 11 checks against `artifacts/reports/latest/` (and `make verify` runs it automatically once artifacts exist); `make demo-backup` chains verify + docs + replay + freeze. Decisions `D-15-01`, `D-15-02`.
- New this phase: `docs/API_USAGE.md`, `docs/POLICY_PROTOCOL.md` (Task 15.3 was previously missing), `docs/DEMO.md`, `tools/verify_doc_claims.py`, `tests/judge/test_doc_claims.py`; `docs/DESIGN.md` rewritten as-built.
- Measured: `make verify` **12/12 PASS** (61.9 s, 21 artifacts), also PASS on a clean `git ls-files` tree (61.1 s), full suite **435 tests** OK (1 optional Hypothesis skip, `critical_skipped=0`), `make docs-verify` PASS, `make demo-backup` PASS, lint CLEAN, freeze **30 files** intact (`0747baf0…`), `official_score_claimed: false`.
- No frozen file changed (`contracts/*`, `configs/*`, `judge/rubric_map.json`, Master TZ untouched).

## Next actions
1. Phase 16 (from `main` after this PR merges, on a fresh branch): clean-clone `make verify` on a fresh runner, offline Docker re-run, secrets/file-list/package-size audit, verify official entrypoint, tag release and open the GitHub release.
2. Review this phase's diff — especially `tools/verify_doc_claims.py` (new gate) and the README generated block.
3. Re-run `make verify && make docs-verify && python3 tools/freeze_release.py --verify` for the reviewed commit.
4. Release/tag authority remains outside this phase.
