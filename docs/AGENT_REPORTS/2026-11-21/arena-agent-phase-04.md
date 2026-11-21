# Agent Report — Phase 4 (2026-11-21)

**Agent:** Arena coding agent (Agent Mode)
**Phase:** 4 — first mutation operators and diff truth
**Branch:** `arena/d94e8b76-genesis-hackathon-malika-nurzh`
**Base commit:** `c961a009611e1711463f5116b2df926bb4726de8`
**Verdict:** Phase 4 **DONE**, exit gate **PASS**

---

## 1. What I was asked to do

Execute Phase 4 of the TwinLedger v3.0 master TZ end to end — immutable twins, the
`DUPLICATE_PAYMENT` and `PARTIAL_PAYMENT_ALLOCATION` operators, structural diff, candidate
truth with invariant signatures, the first distractor pair per type, and bounded rejection
sampling — judged by the real exit gate, not by a plan or by demo stubs. Standard-library
Python only, offline, deterministic, sealed boundary preserved, no fabricated results.

## 2. How I worked

1. **Read the repository before writing.** Established the existing layering
   (`contracts` → `core` → `invariants`/`gen`), the frozen schemas, and the frozen error
   matrix. Confirmed the schema validator could decode table rows against the whole-book
   resolver root before building on it.
2. **Built the gate first, then the code.** The sweep tool (`tools/phase4_sweep.py`) encodes
   the exit gate as six checks with a machine-readable verdict, so "it works" is a number and
   an exit code rather than a claim.
3. **Wrote the negative tests first where it mattered.** For every invariant there is a
   targeted corruption that must trip it; for the sealed boundary there are explicit leak
   probes. A check that silently inspects nothing cannot survive these tests.
4. **Let the gates find the bugs.** Every defect listed below was surfaced by a failing test
   or a failing gate, not by inspection, and each fix was followed by a re-run of the full
   suite.

## 3. Defects found by the gates (and fixed)

| # | Defect | How it surfaced | Fix |
|---|---|---|---|
| 1 | Credit-note journal entries referenced the invoice, so CUTOFF/FX checks judged an adjustment against the invoice's recognition period | A clean-twin sweep produced `INV-09` on a supposedly clean book | JE references the credit note; INV-07/INV-09 scoped to recognition vs. settlement/adjustment postings |
| 2 | Style-D ids (bare digits, per-table counters) collided across document tables | `INV-11` "id reused across tables" on a clean twin | Leading two digits encode the table namespace; regression test added |
| 3 | INV-05's reporting date was derived from the due dates it judged → the check could never fire | `test_inv05_aging_inconsistency` failed with `[] is not true` | Reporting date = end of the last period the book posts in |
| 4 | INV-06/07/08/10/13/17 raised `KeyError` / `MoneyError` / `TimeRuleError` on corrupted books | Negative-vector tests errored instead of finding violations | Each check now reports, or defers to the invariant that owns the malformation |
| 5 | `invariants/checks_clean.py` imported `gen.twins` — a public layer depending on the generator | New layering test | `Book` moved to `contracts/book_model.py`; `gen.twins` re-exports it |
| 6 | Candidate selection was positional (`candidates[k]`), so one subtype dominated (`27 / 23 / 1`) | Sweep subtype histogram | Seed-derived stream choice; subtype chosen by configured weights |
| 7 | When a family had no viable target, retries burned the budget without trying the other family | 4 `REJECT_BUDGET_EXHAUSTED` in an earlier sweep | Fallback to another configured family with candidates; seed-derived operator choice |

## 4. Evidence

* `python3 -m unittest discover -s tests -t .` → **254 tests, OK, 0 skipped** (exit 0)
* `python3 tools/phase4_sweep.py --seeds 24` → **48 published, 0 rejected**, 36/36 findings
  per family, **6/6 gates pass** (exit 0) → `artifacts/phase-04/sweep-24.json`
* Clean-twin invariant sweep: **0/180 unclean** (60 seeds × L1/L2/L3) at the point the id and
  credit-note defects were closed.

## 5. Judgement calls

* **Scope discipline.** The independent verifier, the last two anomaly types, and
  step-optimality were deliberately left to their own phases; the catalogue already declares
  them, so no contract change is needed later.
* **No `skipTest` for anything Phase 4 must prove.** Two tests that had skip branches were
  rewritten to construct the precondition instead — a skipped gate is not a passed gate.
* **Determinism treated as testable behaviour**, including a cross-process check under two
  different `PYTHONHASHSEED` values.
* **Documentation honesty.** Nothing is marked DONE that lacks a command, an exit code and a
  result; the "not in scope" table exists so that green tests can never be read as more than
  they are.

## 6. What I would hand to the next agent first

1. Read `docs/CONTEXT/NEXT_AGENT.md` — it lists the invariants that are now load-bearing and
   the two extension points (registry + catalogue).
2. Run `make verify` before changing anything: it reproduces the Phase 4 verdict in ~50 s.
3. If you add an operator, add its catalogue entry in the same commit; the registry
   self-check fails the build otherwise.
