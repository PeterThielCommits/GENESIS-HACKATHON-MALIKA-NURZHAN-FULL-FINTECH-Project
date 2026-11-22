# Next agent — handoff after the Phase 16 v1.0.1 release

Read `AGENTS.md`, `docs/CURRENT_STATE.md`, `docs/PHASE_REPORTS/PHASE-16.md`
(including the v1.0.1 addendum), `docs/QUESTIONS.md` (the process questions),
and decisions `D-16-02`, `D-16-03`, `D-15-04..D-15-07` first. Then read
`docs/INDEPENDENCE.md` ("Ownership — and an honest correction"), which is the
most important paragraph in the repository.

## Where the project stands

Phase 16 is `DONE` and re-verified on the `v1.0.1` tree. The release is cut and
published. Phases 0–17 are all `DONE` (see `docs/STATUS.md`). The repository is
feature-frozen; nothing in this handoff authorises new features.

```
v1.0.1   -> annotated tag (object 3601493...) on 640c585, merge commit of PR #26; release published 2026-11-22 (D-16-03)
v1.0.0   -> retained for history; superseded for submission (sealed-truth image defect, D-16-02)
make rc-check (clean clone, emptied evidence dir) -> verify 12/12, docs 22/18, replay-all 80/80 (567 steps), release-audit 6/6
CI (9737961, run 45009197767)                  -> core PASS, docker-offline PASS
freeze_release --verify                         -> 30 files intact, 0747baf0…
```

## Rules this project established (do not break them)

### Carried over, still binding
- **Never hand-edit the README generated block.** Regenerate with
  `python3 tools/verify_doc_claims.py --write`.
- **Never gate a test on a gitignored or generated output**, and **never read an
  artifact that does not exist yet in RC-001's bootstrap position**. Use
  `@unittest.skipUnless(ARTIFACTS_READY, NOT_READY_REASON)`. This has bitten the
  project **four** times.
- **Never assert a value produced by the run that is performing the check.**
- **Never put a sampled value in the generated block.**
- **Never write reports into `artifacts/reports/latest/`.**
- **Never cite a decision ID that is not in `docs/DECISIONS.md`.**
- **`calc` vs `calculator` is intentional** (`D-15-02`).
- **Checked-in `episodes/dev/*` have no `sealed/truth.json`** (`D-01-04`).
- **Every gate must be shown to fail.** Keep the injected-fault standard.
- **Do not move a published tag.** Fix-forward on a new branch; next patch tag.
- **Do not run `make official-eval` casually** — it rewrites the committed
  `artifacts/trajectories/trajectories.jsonl`. If a sweep runs it, restore with
  `git checkout -- artifacts/trajectories/trajectories.jsonl`.

### Console and docs
- **Console verdicts must survive an ASCII-only locale** (`D-15-07`). Use `_say`
  for every console write in `judge/verify.py::main`.
- **Recognised prose totals track discovery** through `C-COUNTS`. Adding a test
  requires `python3 tools/verify_doc_claims.py --write` to update the facts block
  and recognised prose copies.
- **A published fact must not depend on which target ran last** (`D-15-06`).
  Test counts come from `unittest` **discovery**, never from `verify_summary.json`.
- **Pin a sentence to a source, not to a second copy** (demo clock, `C-DEMO`).
- **Absence must be documentable.** `C-PATHS` negation-cue exemption: keep it.
- **Do not "fix" the honest ownership disclosure.** `Q-ORG-01` and `Q-ORG-02` are
  OPEN on purpose. The technical zero-common-mode separation is proven; the
  organisational separation is not.

## Known open items

| ID | Item | Owner |
|---|---|---|
| `Q-ORG-01` | Verifier was not built by a separate human/agent context. Re-derive, or accept and disclose. | Human owner |
| `Q-ORG-02` | CODEOWNERS personas are intended, not real accounts (already disclosed in the file header). | Human owner |
| `Q-DOC-01` | Should the 16-family distractor catalogue appear in narration? Not published today. | Next agent / owner |
| — | Narrative behavioural claims are only partly mechanical; prose needs review. | Next agent |

`Q-REL-01` is **RESOLVED** (`v1.0.1` cut, `D-16-03`, 2026-11-22).

## Single next action

Get a human answer to `Q-ORG-01`. If the answer is "accept and disclose", record it
in `docs/DECISIONS.md` as a new `D-xx-xx` and close the question. If the answer is
"re-derive", scope a fresh `verifier/` authored from `spec/` and `contracts/` only,
with `tests/verifier/test_boundaries.py` proving the import and file-open boundaries
still hold against the old one. Do not attempt both.
