# Agent report — Phase 15 structural audit

- **Agent:** Arena agent session `a30551a9`
- **Human owner:** not assigned (see `Q-ORG-01` — this itself is part of the finding)
- **Date:** 2026-11-22
- **Phase:** 15 — DOCUMENTATION AND DEMO
- **Master TZ version:** v3.0.0 (`docs/reference/TwinLedger_v3_AI_Agents.txt`), unchanged
- **Branch:** `arena/a30551a9-genesis-hackathon-malika-nurzh`
- **Start commit:** `e0a2bbf4bdf652f40855fc3c9a55fb3ccf64772a`
- **End commit:** this branch's head after commit

## 1. Context loaded before any change

`AGENTS.md`, `docs/PROJECT_CONTEXT.md`, `docs/CURRENT_STATE.md`, `docs/DECISIONS.md`,
`docs/STATUS.md`, `docs/QUESTIONS.md`, `docs/CONTEXT/ARCHITECTURE_SNAPSHOT.md`,
`docs/PHASE_REPORTS/PHASE-14.md`, `PHASE-15.md`, `PHASE-16.md`, `PHASE-17.md`,
`docs/HANDOFF/*`, `docs/QUALITY_AUDIT/*`, the official check definitions
(`spec/official_fintech_checks_2026-11-20.md`), `judge/verify.py`,
`judge/rubric_map.json`, `tools/verify_doc_claims.py`, `tests/judge/test_doc_claims.py`.

## 2. Baseline (before any change)

| Command | Exit | Result |
|---|---:|---|
| `make verify` | 0 | 12/12 PASS, 47.2 s, 20 artifacts |
| `python3 tools/verify_doc_claims.py` | 0 | PASS, 22 facts, 11 checks |
| `python3 tools/freeze_release.py --verify` | 0 | 30 files intact, `0747baf0…` |
| `git status` | — | clean tree at `e0a2bbf` |

Working tree was clean; no other agent's uncommitted work was present or disturbed.

## 3. What I set out to verify, and what I found

The phase said `DONE`. Rather than re-reading the report, I executed every
jury-facing instruction in the documentation. Three of them were fine
(`docs/DEMO.md` probes a–e all ran), and then the rest were not:

- `docs/API_USAGE.md` published `GET .../overview` → **live 404**.
- `docs/CONTEXT/ARCHITECTURE_SNAPSHOT.md` named **7 modules that never existed**.
- `docs/DATA_DICTIONARY.md` documented **2 fields that do not exist** and omitted
  **6 that do**.
- `docs/DEMO.md` described **five segments** for a **six-segment** program, with the
  clock up to 5 s out of step.
- Three docs called the reward **provisional** after `D-18-01` made it official.
- `docs/RELEASE_NOTES.md` told a reviewer to run `python3.11 -m make verify`, which
  fails with `No module named make`.
- `docs/LIMITATIONS.md` published **292 rows / >500x-20x headroom**; measured
  **146 rows / 609x-685x**.
- `docs/INDEPENDENCE.md` claimed a **different human owner** built the verifier.
  `.github/CODEOWNERS` named four handles that do not exist.

None of these are visible to a numeric gate, and all 19 were individually
reproduced before being changed.

## 4. What I built

Six structural detectors in `tools/verify_doc_claims.py`, each pinned to a source
that defines the shape rather than to a second copy of the truth, each proven to
fail by an injected fault, each locked by a test:

`C-PATHS` · `C-DATADICT` · `C-DEMO` · `C-WORKBENCH-API` · `C-COMMANDS` · `C-REWARD`

Supporting changes: `tools/demo_walkthrough.py` gained a `SEGMENTS` tuple that both
the program and the checker read; `tools/demo_server.py` implements the `/overview`
route; `tests/judge/test_doc_claims.py` grew 25 → 51 tests.

## 5. Bugs I introduced, and how they were caught

Recorded because they are the point of the exercise:

1. **A hole in my own new detector.** Injecting `accounts.bogus_field` into the
   dictionary **passed**, because `accounts` was not in the comparison list and the
   loop skipped any table it could not resolve. All ten tables are now compared and
   an unresolvable one raises `UNRESOLVED_TABLE`. Regression test added.
2. **The gate caught my test additions.** Adding tests changed the count 502 → 522
   and `make verify` failed with `[DRIFT] G-BLOCK`. The redundant hand-written prose
   copy of the count was removed: one published copy, generated.
3. **Order dependency, third occurrence (`D-15-06`).** Test counts were read from
   whichever run wrote `verify_summary.json` last, so `verify-core && docs-verify`
   failed on a correct tree. Counts now come from `unittest` discovery.
4. **Bootstrap trap, met again.** Two doc-claim tests read artifacts that do not
   exist while RC-001 is running. Both are now `skipUnless(ARTIFACTS_READY)`; the
   full suite with an **empty** evidence dir gives 528 tests, OK, 19 explicit skips.
5. **Core-mode skip classified as critical.** My new skip reason was not in
   `judge/verify.py::_OPTIONAL_SKIP_RE`, so `verify-core` exited 2. Registered as a
   positional skip with the same reasoning as the existing bootstrap skip.

## 6. Final measured state

| Command | Exit | Result |
|---|---:|---|
| `make verify` (empty evidence dir) | 0 | **12/12 PASS**, 49.8 s, 20 artifacts, **528 tests** |
| `make verify-core` | 0 | 6/6 PASS |
| `make docs-verify` | 0 | 22 facts, **17/17 checks** |
| `make lint` | 0 | CLEAN |
| `freeze_release --verify` | 0 | 30 files, `0747baf0…` |
| `tests.judge.test_doc_claims` | 0 | 51 tests OK |
| full suite, empty evidence dir | 0 | 528 tests, OK (skipped=19) |
| **19-target sweep** | 0 | **19/19 exit 0** |
| order-independence ×3 | 0 | all pass |

## 7. What I did not do

- Did not touch any frozen file (`contracts/*`, `configs/*`, `judge/rubric_map.json`,
  Master TZ). Freeze verify PASS before and after.
- Did not close `Q-ORG-01` or `Q-ORG-02`. Only a human can.
- Did not move or create any tag. `v1.0.0` is untouched; `Q-REL-01` is a
  release-authority decision.
- Did not run `make official-eval` again after restoring the trajectory log (it had
  been run once in the sweep; the only field that differed was `duration_s`, and the
  committed version was restored rather than rewritten).
- Did not claim the structural checks cover narrative behaviour. They cover shapes.

## 8. Next action

Answers `Q-ORG-01` — a human decides whether the verifier gets re-derived under a
separate owner/context or the disclosed gap is accepted.

## 9. Follow-up findings and corrected guarantees (`D-15-07`)

The earlier “one published copy” claim in §5 was wrong: README still had 522 in
prose, and DEMO had 490. Both now track unittest discovery through `C-COUNTS`, the
seventh structural detector. `--write` repairs recognised prose totals as well as
the generated block; nine added tests cover detection, scoping, and exact numeric
repair. The detector is explicitly bounded by its scan set and phrase grammar;
it is not a guarantee about arbitrary narrative claims.

An ASCII-only clean run exposed a separate crash after the correct gate verdict.
All `judge/verify.py::main` console writes now use `_say`, including stderr and
failure annotations. Three tests guard transliteration, narrow-stream replacement,
and the absence of bypassing print calls. The original helper/raw-print mutations
were shown to fail tests before restoration.

Follow-up measurements: 540 tests pass with populated evidence (one optional skip).
With evidence and trajectories both empty, the ASCII full run passes 12/12,
produces 20 artifacts in 45.443 s, emits zero non-ASCII bytes, and reports 26
optional / zero critical skips. These supersede §6's suite/check totals; the
19-target sweep there remains a historical measurement of the earlier commit.
The documentation gate is now 22 facts / 18 checks. Freeze and tag untouched;
Q-ORG-01/02, Q-REL-01, Q-DOC-01 remain OPEN.


Latest normal empty-evidence verification (trajectories retained): **12/12 PASS**,
**540 tests**, **20 artifacts**, **47.416 s**, zero critical skips, no missing
artifacts or schema errors. RC-001 has 19 optional/bootstrap test skips; the
summary has 20 optional skips including non-test checks. Documentation is
**22 facts / 18 checks PASS**, lint CLEAN, and the 30-file freeze remains intact
(`0747baf0…`). These are the final follow-up measurements.
