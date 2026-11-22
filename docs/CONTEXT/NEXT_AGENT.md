# Next agent — handoff after the Phase 15 structural audit

Read `AGENTS.md`, `docs/CURRENT_STATE.md`,
`docs/PHASE_REPORTS/PHASE-15-STRUCTURAL-AUDIT.md`, and decisions `D-15-04`,
`D-15-05`, `D-15-06` before changing anything. Then read `docs/INDEPENDENCE.md`
("Ownership — and an honest correction"), which is the most important paragraph in
the repository right now.

## Where the project stands

Phase 15 is `DONE` on a stricter reading of its exit gate than before. The
documentation is now checked on two axes: **numbers** (unchanged, still generated and
byte-compared) and **shapes** (new). Everything below was measured in one session on
this branch:

```
make verify        -> 12/12 PASS, 528 tests, 20 evidence artifacts, from an EMPTY evidence dir
make docs-verify   -> 22 measured facts, 17/17 checks PASS
make verify-core   -> 6/6 PASS
make replay-all    -> 80/80 runs, 567 steps byte-identical
make release-audit -> 6/6 PASS
make rc-check      -> PASS
19-target sweep    -> 19/19 exit 0
```

## Rules this project established (do not break them)

### Carried over, still binding
- **Never hand-edit the README generated block.** Regenerate with
  `python3 tools/verify_doc_claims.py --write`.
- **Never gate a test on a gitignored or generated output**, and **never read an
  artifact that does not exist yet in RC-001's bootstrap position**. Use
  `@unittest.skipUnless(ARTIFACTS_READY, NOT_READY_REASON)`. This has now bitten the
  project **four** times.
- **Never assert a value produced by the run that is performing the check.**
- **Never put a sampled value in the generated block.**
- **Never write reports into `artifacts/reports/latest/`.**
- **Never cite a decision ID that is not in `docs/DECISIONS.md`.**
- **`calc` vs `calculator` is intentional** (`D-15-02`).
- **Checked-in `episodes/dev/*` have no `sealed/truth.json`** (`D-01-04`).
- **Every gate must be shown to fail.** Six new detectors each have an injected-fault
  test; keep that standard.
- Do not run `make official-eval` casually — it rewrites the committed
  `artifacts/trajectories/trajectories.jsonl`. If a sweep runs it, restore with
  `git checkout -- artifacts/trajectories/trajectories.jsonl` (verified: only
  `duration_s` changes across all 80 rows).

### New in this session
- **A published fact must not depend on which target ran last** (`D-15-06`).
  Test counts come from `unittest` **discovery** over `tests/` and `tests/official/`,
  never from `verify_summary.json`. If you add a fact, ask: *would this value change
  between a `--core` run and a full run?* If yes, it cannot be published this way.
- **Pin a sentence to a source, not to a second copy.** The demo clock lives in
  `tools/demo_walkthrough.py::SEGMENTS`; the program prints it and `C-DEMO` compares
  `docs/DEMO.md` to the same tuple. Two copies of a clock is one copy too many.
- **Absence must be documentable.** `C-PATHS` exempts lines with a negation cue
  (`does not exist`, `forbidden`, `renamed`) so incident reports can say what is not
  there. Do not remove that exemption; do not widen it to whole documents.
- **A documented table that cannot be verified is worse than a failing one.** If you
  add a bullet to `docs/DATA_DICTIONARY.md`, add the file to
  `_DATADICT_TABLES` too, or `C-DATADICT` raises `UNRESOLVED_TABLE` by design.
- **Do not "fix" the honest ownership disclosure.** `Q-ORG-01` and `Q-ORG-02` are
  OPEN on purpose. The technical zero-common-mode separation is proven; the
  organisational separation is not, and saying otherwise would be the single most
  damaging claim in the repository.

## Known open items

| ID | Item | Owner |
|---|---|---|
| `Q-ORG-01` | Verifier was not built by a separate human/agent context. Re-derive, or accept and disclose. | Human owner |
| `Q-REL-01` | Cut `v1.0.1`? Tag `v1.0.0` still contains the `.dockerignore` defect (`D-16-02`). | Release authority |
| — | Narrative claims about *behaviour* are only partly mechanical. `C-DATADICT`/`C-DEMO`/`C-WORKBENCH-API` cover three shapes; prose about how something behaves still needs review. | Next agent |

## Single next action

Get a human answer to `Q-ORG-01`. If the answer is "accept and disclose", record it
in `docs/DECISIONS.md` as a new `D-xx-xx` and close the questions. If the answer is
"re-derive", scope a fresh `verifier/` authored from `spec/` and `contracts/` only,
with `tests/verifier/test_boundaries.py` proving the import and file-open boundaries
still hold against the old one. Do not attempt both.
