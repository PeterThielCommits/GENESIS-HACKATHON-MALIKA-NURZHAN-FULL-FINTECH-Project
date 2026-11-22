# NEXT_AGENT — handoff after the forensic audit

Read this first, then `FINAL_QUALITY_REPORT.md`, then `BUG_REGISTRY.md`.

## State you are inheriting

Branch `arena/45dc3a73-genesis-hackathon-malika-nurzh`, tip `aa4fd18`,
PR **#24** open against `main` with CI green.

```
tests            502 OK (18 documented bootstrap skips)
official tests   55 OK
mutation         26/26 killed
replay           80/80 runs, 567 steps byte-identical
make verify      12/12 RC gates PASS (~72 s)
clean extract    12/12 PASS in 65.8 s
release-audit    6/6, 498 files, 0 external imports
freeze           30 files intact, aggregate_sha256 0747baf0...
```

## The two things that will bite you if you don't know them

**1. There is exactly ONE reward formula. Do not add a second.**
`scoring/official_scorer.compute_official_metrics` is authoritative:
`return = clip([-1,1], 2*F1 − 1 − 0.2*inspection_steps/100)`.
`scoring/reward.py` is a **view** over it via `reward_metrics()`.
The pre-audit tree had two implementations and the internal one was silently
wrong on 10 of 11 published vectors (BUG-TL-0001). If you need to change the
formula, change it in `official_scorer.py` only, and update
`tests/official/test_block3_scorer.py` with an official citation.

**2. `configs/scoring/default.json` still says `eta: 0.05` and it means nothing.**
The file is a frozen contract (don't edit it — D-14-02). Its `eta` and
`provisional` keys no longer drive the reward. This is deliberate and recorded
in `D-18-01`. Do not "fix" it by editing the frozen file, and do not
reintroduce `eta` into the reward path.

## Order of work if you continue

1. **Merge PR #24** (CI green). Don't tag a release without the maintainer:
   `v1.0.0` predates two P0 fixes, so it no longer represents the best
   artifact.
2. **Decide on re-tagging** `v1.0.0` → `v1.0.1`. This is a maintainer decision,
   not an agent one.
3. **Optional cleanup (safe, not urgent):** move `arena/autohacker.py`,
   `judge/mutation_suite.py` and `judge/robustness_audit.py` off
   `scoring/reward.py` onto `scoring/official_scorer` directly, then delete the
   shim. It is now provably faithful, so this is tidying, not a fix. If you do
   it, re-run `make mutation-test` **and** re-check that MUT-07/08/13 still
   patch a live symbol — otherwise you will recreate the false-negative
   described below.
4. **Docker verification**: run `make docker-check` where Docker exists. Locally
   it is UNVERIFIED. CI's `docker-offline` job is the authoritative run.
5. **Phase 17** is still **not authorised**. Do not start it.

## Traps discovered the hard way (do not repeat)

| Trap | Detail |
|---|---|
| A green mutation score can be a lie | MUT-07/08/13 patched `reward_mod.f1_score` after it left the reward path → 23/26 while the code was *correct*. A mutation suite only means something for symbols actually on the execution path. |
| A test can pass for the wrong reason | `valid_cursor + "x"` was rejected by the old `rsplit` accident, hiding BUG-TL-0003 for real. If a tamper test passes, verify *why*. |
| Don't encode the example, encode the requirement | Official C05 says "three pages"; the requirement is "all rows reachable". Walking only `invoices` hid a P0 on `ledger`. Always test the *largest* fixture the contract allows. |
| Cursor tokens are embedded in the published trajectories | Changing the cursor format invalidates `trajectories.jsonl`. After any such change: `make official-eval`, then diff and prove **only** cursor tokens changed, then `make replay-all`. |
| `make verify` regenerates artifacts mid-run | Never probe exit codes by deleting generated files (learned in Phase 16). Use `classify_check` unit tests. |
| Doc-claims block is generated | Run `python3 tools/verify_doc_claims.py --write`, then fix by hand only the counts the generator does not own (the command block and the headline line in `README.md`). |
| Two conventions for empty-denominator P/R exist on purpose | Official reward: `P=R=0` with `F1=1` (Block 3 test 3). Generator cross-check: vacuous `1`, needed by EXIT GATE 8. Both documented in the docstrings and `D-18-01`. Do not "unify" them. |

## Where the evidence lives

| Question | File |
|---|---|
| What is the official requirement? | `spec/official_fintech_checks_2026-11-20.md` |
| Was the attached upload the same file? | `INPUT_INVENTORY.md` |
| What broke, why, and what proves it fixed? | `BUG_REGISTRY.md`, `ROOT_CAUSE_ANALYSIS.md`, `FIX_VERIFICATION_MATRIX.md` |
| Does each official check pass? | `RUBRIC_COMPLIANCE.md`, `RUBRIC_TRACEABILITY.csv` |
| Are the tests meaningful? | `TEST_QUALITY_REPORT.md` |
| Is it fast / reproducible / secure? | `PERFORMANCE_*`, `REPRODUCIBILITY_AUDIT.md`, `SECURITY_AUDIT.md` |
| What is still weak? | `FINAL_QUALITY_REPORT.md` §5 (10 items) |
| Git/CI state | `FINAL_GITHUB_REPORT.md` |

## Non-negotiables carried forward

Frozen files (`contracts/`, `configs/`, `spec/`, `judge/rubric_map.json`,
Master TZ text) are not edited; discrepancies go through validator tolerance
(D-14-02). `official_score_claimed: false` in every report. Never claim a gate
PASS without running the command and quoting output. Never claim no bugs
remain.
