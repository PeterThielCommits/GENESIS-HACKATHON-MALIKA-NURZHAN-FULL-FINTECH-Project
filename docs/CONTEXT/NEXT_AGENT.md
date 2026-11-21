# Next agent — Phase 15 handoff (Phase 14 re-audit merged)

Read `AGENTS.md`, `docs/CURRENT_STATE.md`, `docs/PHASE_REPORTS/PHASE-14.md` / `.json`, and decisions `D-14-02`, `D-14-03` before changing anything.

## Where the project stands
Phase 14 re-audit is **merged into `main`**: PR #18, head `baa5b67`, merge commit `99df116`. Start Phase 15 from `main` @ `99df116` on a fresh branch.

Phase 14 re-audit is **DONE** and EXIT GATE 14 is verified the way TZ §24 defines it — in a **clean checkout**, not a dirty tree: a copy built from `git ls-files` with `artifacts/reports/latest/` holding only `.gitkeep` runs `make verify` → exit 0, 12/12 gates in ~62 s, 21 complete artifacts, replay 5/5, offline `report.html` with 0 external references.

Measured on branch `arena/102582b5-genesis-hackathon-malika-nurzh` (base `e9a4239`):
- full unittest **410 tests OK** (1 optional Hypothesis skip)
- `tests.judge.test_judge_kit` **38 tests OK**
- `make verify-core` 6/6 PASS; `make lint` CLEAN; freeze `--verify` PASS (30 files, `0747baf0…`)

## Do not repeat
- Do not re-run the gate in a dirty tree and call it PASS. The previous Phase 14 report did exactly that and hid two blocking defects. Copy with `git ls-files` and empty the evidence directory first.
- Do not add `{{}}`-style `or` defaults inside f-string replacement fields; they parse as set literals (`D-14-03`).
- Do not edit frozen files (`contracts/*`, `configs/*`, `judge/rubric_map.json`, Master TZ). The rubric-map `schema_version` discrepancy stays resolved by validator tolerance (`D-14-02`).

## Single next action
Phase 15, task 15.5/15.6: update `README.md` — the "317 unit/official/security tests" claim is stale (measured **410**) — and make every quantitative claim point at its artifact under `artifacts/reports/latest/`. Then run `make verify` and record the output.

Release/tag authority stays outside this handoff; tracking issue #16 remains open for QA review.
