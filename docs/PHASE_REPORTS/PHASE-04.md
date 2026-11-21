# PHASE 4 — ПЕРВЫЕ МУТАЦИОННЫЕ ОПЕРАТОРЫ И DIFF TRUTH

**Phase:** 4 of the TwinLedger v3.0 plan
**Status:** **DONE**
**Exit gate:** «два типа аномалий генерируются и проходят все текущие quality gates» → **PASSED**
**Date:** 2026-11-21
**Branch:** `arena/d94e8b76-genesis-hackathon-malika-nurzh` (base `c961a00`)
**Python:** 3.11.2, standard library only, fully offline

---

## 1. Executive summary

Phase 4 delivers the mutation core of the generator end to end: immutable clean/mutated
twin snapshots, two real mutation operators, a structural diff, candidate truth derived
from diff facts plus invariant signatures, the first distractor pair per anomaly type, and
bounded rejection sampling. Episodes are produced for both anomaly families and pass every
quality gate that exists in the repository today.

Everything below is measured, not asserted: **254 stdlib tests pass with zero skips**, and a
48-episode sweep (24 seeds × L1/L2) publishes **48/48 episodes with 0 rejects**, balanced
**36 DUPLICATE_PAYMENT / 36 PARTIAL_PAYMENT_ALLOCATION** findings, with six gate checks all
green (`make verify`).

Four real defects were found and fixed by the gates during this phase — three in the
generator/checks and one architectural (a public-layer package importing the generator).
They are listed in §7 so nothing is hidden behind the green suite.

---

## 2. Requirements traceability (Master TZ §24, tasks 4.1–4.7)

| TZ item | Requirement | Implementation | Verified by |
|---|---|---|---|
| 4.1 | Immutable clean/mutated twin snapshots | `contracts/book_model.py` (`Book`, frozen, cache-dropping `with_rows`), `gen/twins.py` (`build_book`, `TwinPair`) | `tests/gen/test_clean_twin.py` (24), `tests/gen/test_diff_truth.py::test_clean_twin_guard` |
| 4.2 | `DUPLICATE_PAYMENT` operator | `gen/errors/duplicate_payment.py` — replays an existing payment with new id, JE and bank line | `tests/gen/test_operators.py`, sweep G1/G4 |
| 4.3 | `PARTIAL_PAYMENT_ALLOCATION` operator | `gen/errors/partial_allocation.py`, 3 documented subtypes (`OVER_ALLOCATE_TO_ONE_INVOICE`, `ALLOCATE_TO_ALREADY_SETTLED_INVOICE`, `ALLOCATIONS_EXCEED_PAYMENT`) | `test_operators.py::SubtypeSpreadTests`, sweep `subtypes` |
| 4.4 | Structural diff C→M | `gen/truthdiff.py` (`structural_diff`, added/modified/removed, `changed_fields`, `touched_entities`, `assert_clean_untouched`) | `test_diff_truth.py::StructuralDiffTests` (9) |
| 4.5 | Candidate truth with invariant signatures | `gen/truth_build.py` (`build_candidate_truth`, evidence index, `to_truth_document`) | `test_diff_truth.py::TruthConstructionTests` (9) |
| 4.6 | First distractor pair per type | `gen/distractors/__init__.py` + `provenance.distractors`, 4 IDs per family in `configs/generator/mutations.json` | `test_reject_and_episodes.py::test_distractors_present_with_public_evidence` |
| 4.7 | Rejection sampling | `gen/reject.py` (frozen reason codes, bounded budget, `REJECT_BUDGET_EXHAUSTED`) | `test_reject_and_episodes.py::SampleTests` (7), sweep G5 |
| — | Operator registry | `gen/errors/registry.py` (validated against frozen `contracts/anomaly_catalog.json`) | `tests/gen/test_registry.py` (11) |
| — | Episode assembly | `gen/build_episodes.py` (`build_episode`, `build_episode_set`, seed-derived operator choice) | `test_reject_and_episodes.py::EpisodeTests` (11) |

Boundary requirements honoured: truth is derived from **diff + invariants + operator
provenance**, never from the operator alone — a finding with empty diff facts or no observed
violation is refused (`test_truth_rejected_without_diff_facts`,
`test_truth_rejected_without_violation`).

---

## 3. Implementation map

```
contracts/
  book_model.py        immutable public Book model, canonical public files (moved out of gen/)
  models.py            frozen row models, schema-validated decode
  anomaly_catalog.json frozen 4-type catalogue (2 IMPLEMENTED, 2 PLANNED)
gen/
  twins.py             twin construction (Book + build_book + TwinPair)
  clean.py             deterministic clean history builder
  core/                company, accounts, documents, journal, history, reference, rng
  errors/
    base.py            MutationOperator contract, OperatorSpec, OperatorApplication
    registry.py        NEW — operator registry + catalogue validation
    signatures.py      frozen error matrix + signature verification
    duplicate_payment.py
    partial_allocation.py
    ids.py             mutation-side id issuing (unique across tables)
  truthdiff.py         structural diff of two books
  truth_build.py       diff+invariant -> candidate findings, evidence reachability
  distractors/         distinguishable near-miss cases
  reject.py            bounded rejection sampling, frozen reason codes
  build_episodes.py    episode assembly, seed-derived operator and subtype selection
  serialize.py         atomic publish (public/ vs sealed/), public-only reader, verifier
invariants/
  checks_clean.py      INV-01..17, total over adversarial books
tools/
  phase4_sweep.py      reproducible gate sweep (exit code = gate verdict)
```

Money stays integer minor units with `Decimal` parsed from strings; all ordering, RNG and
serialisation is deterministic (`canonical_json`, `canonical_jsonl`, `ensure_ascii=False`).

---

## 4. Tests and gates (executed in this session)

| Command | Exit | Result |
|---|---|---|
| `python3 -m unittest tests.unit.test_money` | 0 | 33 tests OK |
| `python3 -m unittest tests.unit.test_time_rules` | 0 | 22 tests OK |
| `python3 -m unittest tests.unit.test_ids` | 0 | 17 tests OK |
| `python3 -m unittest tests.contracts.test_schemas` | 0 | 24 tests OK |
| `python3 -m unittest tests.gen.test_clean_twin` | 0 | 24 tests OK |
| `python3 -m unittest tests.gen.test_operators` | 0 | 33 tests OK |
| `python3 -m unittest tests.gen.test_diff_truth` | 0 | 18 tests OK |
| `python3 -m unittest tests.gen.test_reject_and_episodes` | 0 | 18 tests OK |
| `python3 -m unittest tests.gen.test_registry` | 0 | 11 tests OK |
| `python3 -m unittest tests.invariants.test_invariants` | 0 | 25 tests OK |
| `python3 -m unittest tests.integration.test_serialize` | 0 | 16 tests OK |
| `python3 -m unittest tests.security.test_sealed_boundary` | 0 | 13 tests OK |
| `python3 -m unittest discover -s tests -t .` | 0 | **254 tests OK, 0 skipped** |
| `python3 tools/phase4_sweep.py --seeds 24` | 0 | 48 published / 0 rejected, all 6 gates pass |
| `make test` | 0 | 254 tests OK |
| `make sweep` | 0 | sweep JSON written to `artifacts/phase-04/sweep-24.json` |

### Sweep evidence (`artifacts/phase-04/sweep-24.json`)

| Gate | Meaning | Value |
|---|---|---|
| G1 | both anomaly families generated by ordinary seeds | PASS — 36 / 36 findings |
| G2 | clean twin passed the invariant suite in every episode | PASS |
| G3 | every finding is diff-backed with reachable evidence | PASS |
| G4 | no finding produced an invariant its family forbids | PASS (0 violations) |
| G5 | rejection stayed a minority of attempts | PASS — 0 rejects / 7 attempts |
| G6 | identical seeds reproduce identical digests | PASS (`deterministic: true`) |

Subtype distribution over the sweep: `ALLOCATE_TO_ALREADY_SETTLED_INVOICE 23`,
`ALLOCATIONS_EXCEED_PAYMENT 9`, `OVER_ALLOCATE_TO_ONE_INVOICE 4` — all three declared
subtypes are actually produced.

### What the tests actually prove

* **Diff exactness and amounts** — the duplicate adds exactly one payment, one bank line and
  one journal entry; the added payment's amount equals its allocated amount; modified
  invoices report the changed `status` field; the partial operator reports the changed
  `allocations` field.
* **Only intended invariants change** — every observed violation id is checked against the
  frozen error matrix; G4 fails the sweep if a family ever trips a forbidden invariant.
* **Clean twin unchanged by mutation** — `assert_clean_untouched` verifies the clean book is
  byte-identical after mutation is applied, and raises otherwise.
* **No generator shortcut in ids/order/position** — ids contain no seed, anomaly type,
  operator index or record position (styles A/B/C/D, per-table namespaces); candidate choice
  is seed-derived, not attempt- or position-derived.
* **Public/sealed separation** — no canary, seed, operator id, provenance field or truth
  attribute appears in `public/` or the manifest; `read_public_episode` proves it needs no
  `sealed/` directory at all.
* **Determinism** — same seed reproduces identical bytes **across processes** (checked under
  two different `PYTHONHASHSEED` values) and identical episode digests across two runs.

---

## 5. Exit gate verdict

> «два типа аномалий генерируются и проходят все текущие quality gates»

* Both anomaly types generate from ordinary seeds: **yes** (36 / 36 findings; both families
  also appear on L1 and L2 independently).
* All current quality gates pass: **yes** — schema validation, INV-01..17 on both twins,
  signature conformance, evidence reachability, sealed-boundary checks, determinism, and
  serialisation round trip.

**Phase 4 verdict: PASS** (evidence: `make verify` → exit 0; `artifacts/phase-04/sweep-24.json`).

---

## 6. Deviations and decisions

1. **`Book` moved from `gen/twins.py` to `contracts/book_model.py`** (decision recorded in
   `docs/DECISIONS.md`). The invariant layer needs to read the book, and
   `invariants/checks_clean.py` previously imported `gen.twins`, which would have made the
   Phase 8 verifier depend on the generator. `gen.twins` re-exports the model, so the public
   API is unchanged.
2. **Selection of operator and subtype is now stream-driven.** A fixed positional pick made
   the first configured subtype dominate (`ALLOCATE_TO_ALREADY_SETTLED_INVOICE 27`,
   `ALLOCATIONS_EXCEED_PAYMENT 1`). Operator choice is seed-derived, subtype choice is
   weighted by `subtype_weights_bps`.
3. **Retries may switch family.** If a configured family has no viable target on a clean twin
   (legitimately possible, e.g. no credit note), the episode falls back to another configured
   family with candidates instead of burning the budget. Rejection is still reported if
   nothing is applicable.
4. **Credit notes are their own accounting event.** A credit-note journal entry now references
   the credit note (not the invoice) and books at the invoice's document-date rate; INV-07 and
   INV-09 were corrected to judge adjustment postings accordingly. This fixed an internal
   contradiction that had been silently producing "unclean clean twins".
5. **Style-D ids carry a table namespace.** Purely numeric ids with per-table counters
   collided across tables (`bank_lines` vs `credit_notes` vs `invoices` vs `payments`), which
   broke cross-table document references. The leading two digits now encode the table.
6. **INV-05 rewritten.** Its previous reporting date was derived from the very due dates it
   judged, so the condition was unreachable. It now uses the last period the book posts in.
7. **Checks are total.** INV-06/07/08/10/13/17 previously raised (`KeyError`,
   `MoneyError`, `TimeRuleError`) on deliberately corrupted books, which would have crashed
   the verifier on adversarial input. Each now reports a violation or defers the finding to
   the invariant that owns it.

---

## 7. Known issues / not in Phase 4 scope

| Item | Status | Notes |
|---|---|---|
| Independent verifier (`verifier/`) | Not started (Phase 8) | Boundary test is written and will enforce "no `gen`/`invariants` import" as soon as the package exists. |
| Anomaly types 3–4 (FX error, cutoff/period error) | Catalogue-declared `PLANNED` | Catalogue already frozen for all four; Phase 4 implements two as specified. |
| `optimal_steps` in findings | Emitted as `null` with `query_plan_v1` | Step-optimality is a later-phase (query plan) concern. |
| L3 difficulty | Generation works, invariant suite clean | Phase 4 evidence is collected on L1/L2 as scoped; L3 is exercised in the clean-twin sweep (0/60 unclean). |
| Distractor reachability | Verified for both families | Deeper adversarial-distractor scoring belongs to the scoring phase. |

No fabricated results: every number above comes from a command run in this session and is
reproducible with `make verify`.

---

## 8. Next phase readiness

Phase 5 (per the master plan) can extend the operator set without touching the Phase 4
contract: add an operator, register it in `gen/errors/registry.py`, and extend
`contracts/anomaly_catalog.json` in the same change — `validate_against_catalogue` will fail
the build if the two disagree.
