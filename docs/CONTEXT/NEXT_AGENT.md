# Next agent — handoff after the post-release mandatory-target audit

Read `AGENTS.md`, `docs/CURRENT_STATE.md`, `docs/PHASE_REPORTS/PHASE-16.md` / `.json`, `docs/RELEASE_NOTES.md`, and decisions `D-15-01`, `D-15-02`, `D-15-03`, `D-16-01` before changing anything.

## Where the project stands
Phase 16 is **DONE** and EXIT GATE 16 is met: the release candidate is frozen,
verified on a clean machine, replayed end to end, audited, and its official
entrypoint is proven by execution.

```
make verify        -> 12/12 PASS, 490 tests, 20 evidence artifacts (docs gate runs inside)
make docs-verify   -> 22 measured facts, 11 checks PASS
make replay-all    -> 80/80 published runs, 567 steps byte-identical
make release-audit -> 6/6 PASS (secrets, file list, size, deps, entrypoint, submission)
make rc-check      -> verify + docs-verify + replay-all + release-audit, fail-closed
make demo-backup   -> verify + docs + replay 5/5 + freeze 30 files
```

`make rc-check` has been run PASS in three trees: a Git checkout, a clean clone
with an emptied evidence dir, and a `git archive` tarball with **no `.git`**.

## Rules this project established (do not break them)
- **Never hand-edit the README generated block.** It sits between
  `<!-- BEGIN GENERATED:measured-facts -->` and `<!-- END GENERATED:measured-facts -->`
  and is rendered by `tools/verify_doc_claims.py`. Regenerate with `--write` after
  the artifacts change; a manual edit fails `make docs-verify`.
- **The doc-claim gate is NOT a plain RC-001 test.** Inside RC-001 no artifact
  exists yet, so `tests/judge/test_doc_claims.py` can only prove the checker's
  mechanisms there and skips explicitly. The authoritative run is
  `judge/verify.py::_run_doc_claims()`, executed after every artifact is written.
- **Never gate a test on a gitignored output.** `artifacts/reports/release/` and
  `artifacts/reports/doc_claims/` are generated. Gate on the *input* (the
  evidence set, the committed trajectory log) or drive the real CLI into a temp
  directory. Violating this turned RC-001 into SKIPPED → exit 5 on clean clones —
  twice (`D-15-01`, then again in Phase 16).
- **Every gate must be shown to fail.** Each detector has a negative test with an
  injected violation. The secrets audit once flagged its own fixtures; the
  fixtures were fixed, not the audit.
- **Never assert a value produced by the run that is performing the check** (e.g.
  the gate pass-ratio, the test count of the same suite). Circular, and it
  deadlocks the gate.
- **Never put a sampled value in the generated block.** Latency, RSS and
  wall-clock change every run. Budgets, verdicts, counts and contract enums only.
- **Never write reports into `artifacts/reports/latest/`.** That is the frozen
  20-file Judge Kit evidence set; extra files make counts order-dependent
  (`D-15-03`).
- **Never cite a decision ID that is not in `docs/DECISIONS.md`** — a
  referential-integrity check fails the gate.
- **`calc` vs `calculator` is intentional** (`D-15-02`). Core protocol = `calc`;
  official adapter = `calculator`. Do not "fix" either one.
- **Checked-in `episodes/dev/*` have no `sealed/truth.json`** by design
  (`D-01-04`). Any scoring demo must build an episode in a temp dir first.
- **Gates must run where the artifact runs.** The Docker image has no `.git`
  (`.dockerignore`), and the container runs `LC_ALL=C` (ASCII stdout). Both were
  real failures; `tools/release_audit.py` and `_say()` handle them.

## Post-release audit (2026-11-22) — read this first
Tag `v1.0.0` (`8da0af2`) is released, but a post-release audit against the
Universal Phase Execution Prompt found that **nine TZ §23.2 targets had never
been executed** by any phase. Running them found four real defects, now fixed on
this branch (`D-16-02`):

1. **`v1.0.0` contains a release blocker:** `.dockerignore` used
   `episodes/*/sealed/`, which does not match the real depth-2 layout, so the
   image built from that tag would include `sealed/truth.json`. Fixed on `main`
   after this branch merges; `v1.0.0` itself is still affected.
2. `make verify-core` used to fail after `make build-episodes`.
3. `make official-eval` used to add a 21st file to the frozen evidence dir.
4. The published gate count followed the last run, not the frozen rubric map.

**All 19 mandatory targets now pass in one sequence on a dirty tree.** If you
change anything, re-run the whole list, not just `make verify` — that is exactly
how these four were missed.

## Single next action
**Phase 17 (post-release evidence freeze).** `v1.0.0` is released on commit
`8da0af2`; nothing is pending from Phase 16.

Phase 17 must make the release reconstructable from the repository alone:
archive the code and config hashes, the verify and replay reports, the final
rubric map and the decisions; create the final tag; write final status and known
limitations; and prove that a reader with only the repo can rebuild the context
without any oral explanation.

Do not move the `v1.0.0` tag, and do not re-run `make official-eval` casually:
it rewrites the committed `artifacts/trajectories/trajectories.jsonl`, which the
documented baseline numbers are measured from.
