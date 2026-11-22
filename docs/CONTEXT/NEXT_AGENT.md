# Next agent — Phase 16 handoff (after Phase 15 re-audit)

Read `AGENTS.md`, `docs/CURRENT_STATE.md`, `docs/PHASE_REPORTS/PHASE-15.md` / `.json`, and decisions `D-15-01`, `D-15-02` before changing anything.

## Where the project stands
Phase 15 re-audit is **DONE** and EXIT GATE 15 is met: a judge can deploy from the README and verify the claims mechanically.

```
make verify        → 12/12 PASS, 477 tests, 21 evidence artifacts (docs gate runs automatically)
make docs-verify   → 22 measured facts, 11 checks PASS
make demo-backup   → verify + docs + replay 5/5 + freeze 30 files PASS
make demo          → 5-segment 3-minute walkthrough (seed 2025)
```

Measured on branch `arena/41a4694b-genesis-hackathon-malika-nurzh` (base `ff6e470`).

## Rules this phase established (do not break them)
- **Never hand-edit the README generated block.** It sits between
  `<!-- BEGIN GENERATED:measured-facts -->` and `<!-- END GENERATED:measured-facts -->`
  and is rendered by `tools/verify_doc_claims.py`. Regenerate with `--write` after
  the artifacts change; a manual edit fails `make docs-verify`.
- **The doc-claim gate is NOT a plain RC-001 test.** Inside RC-001 no artifact
  exists yet, so `tests/judge/test_doc_claims.py` can only prove the checker's
  mechanisms there and skips explicitly. The authoritative run is
  `judge/verify.py::_run_doc_claims()`, executed after every artifact is written.
  Do not "fix" the bootstrap skip by moving the check back into the test suite:
  that reintroduces a chicken-and-egg failure on clean checkouts.
- **Never assert a value produced by the run that is performing the check**
  (e.g. the gate pass-ratio). It is circular: one failing run poisons the next.
  Assert outcome-independent facts only.
- **Never put a sampled value in that block.** Latency, RSS and wall-clock
  durations change every run. Only budgets, verdicts, counts and contract enums
  are asserted (`D-15-01`). Read `performance_report.json` for samples.
- **Never write Phase-15-style reports into `artifacts/reports/latest/`.** That is
  the frozen 21-artifact Judge Kit set; extra files make artifact counts depend on
  target execution order.
- **Never cite a decision ID that is not in `docs/DECISIONS.md`** — a
  referential-integrity check fails the gate. A phantom `D-03-01` slipped in once.
- **`calc` vs `calculator` is intentional** (`D-15-02`). Core protocol = `calc`;
  official adapter = `calculator`. Do not "fix" either one; both frozen surfaces
  and the official harness depend on it.
- **Checked-in `episodes/dev/*` have no `sealed/truth.json`** by design (`D-01-04`).
  Any scoring demo must build an episode in a temp dir first.

## Single next action
Phase 16 (from `main` once this PR merges, on a fresh branch): clean-clone `make verify` on a fresh runner, offline Docker re-run, audit secrets / file list / package size / dependencies, verify the exact official entrypoint and submission format, then tag and open the GitHub release with the report and limitations.

Release/tag authority stays outside this handoff.
