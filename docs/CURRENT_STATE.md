# Current State — TwinLedger v3.0

**Updated:** 2026-11-21
**Phase:** 4 complete (DONE), Phase 5 not started
**Branch:** `arena/d94e8b76-genesis-hackathon-malika-nurzh` (base `c961a00`)
**Python:** 3.11 stdlib only, offline, deterministic

> Orientation for a new agent: start at [`docs/README.md`](README.md), then
> [`STATUS.md`](STATUS.md), then [`CONTEXT/NEXT_AGENT.md`](CONTEXT/NEXT_AGENT.md).

---

## 1. Where the project stands

| Phase | Scope | Status |
|---|---|---|
| 1–2 | Contracts, schemas, money, time rules, ids | DONE |
| 3 | Clean twin generation (deterministic, invariant-clean) | DONE |
| 4 | **First mutation operators + diff truth** | **DONE — exit gate PASS** |
| 5 | (next) remaining anomaly types per plan | Not started |
| 8 | Independent verifier | Not started (boundary test already in place) |

Phase 4 evidence: `docs/PHASE_REPORTS/PHASE-04.md`, `docs/PHASE_REPORTS/PHASE-04.json`,
`artifacts/phase-04/sweep-24.json`.

---

## 2. Verified numbers (reproducible)

| Metric | Value | Command |
|---|---|---|
| Full test suite | 273 tests, 0 failures, 0 skips | `make test` |
| Gate sweep (24 seeds × L1/L2) | 48 published / 0 rejected | `make sweep` |
| Findings per family | DUPLICATE_PAYMENT 36 / PARTIAL_PAYMENT_ALLOCATION 36 | `make sweep` |
| Forbidden-invariant violations | 0 | `make sweep` |
| Determinism | identical digests across runs and processes | `make test` |
| Clean twin invariant sweep | 0/180 unclean (60 seeds × L1/L2/L3) | ad-hoc sweep |
| Schemas | 16 frozen, all validating | `tests.contracts.test_schemas` |
| Documentation consistency | 19 tests, generated snapshot current | `tests.docs.test_docs_consistency` |

---

## 3. Architecture as it stands

```
contracts/   frozen schemas, row models, immutable Book model, canonical JSON, error types
core/        money (integer minor units, Decimal), time rules (zoneinfo, DST), ids
invariants/  INV-01..17 over the public book model (no gen import)
gen/         clean twin builder, mutation operators + registry, diff, truth, reject, episodes, publish
tools/       phase4_sweep.py (gate as executable), export_context.py (docs snapshot)
tests/       unit, contracts, gen, invariants, integration, security, docs
docs/        map + reference documents + generated context + phase/agent reports
```

Layering rule, enforced by `tests/security/test_sealed_boundary.py::LayeringTests`:
`contracts` and `core` may not import `gen`, `invariants` or `verifier`;
`invariants` may not import `gen`.

Full detail: [`CONTEXT/ARCHITECTURE.md`](CONTEXT/ARCHITECTURE.md).

---

## 4. Load-bearing invariants (do not weaken)

1. **Truth is diff-backed.** A finding requires simultaneous diff facts, an observed
   violation matching the frozen signature, and reachable public evidence.
2. **Operators never mutate the clean book.** `assert_clean_untouched` enforces byte equality.
3. **Determinism is a property of the seed, not of the attempt.** Operator choice is
   seed-derived; retries advance the stream instead of repeating a position.
4. **Ids carry no shortcut** (no seed, type, index or position) and are unique **across**
   document tables, because `source_document_id` points across tables.
5. **Style-D numeric ids** prefix two namespace digits; do not reintroduce bare counters.
6. **Credit notes are their own accounting event** (JE references the credit note, document-date
   rate) and must not be judged against the invoice's recognition period.
7. **Checks are total**: given an adversarial book they report a violation or defer, never raise.
8. **Public surface is closed**: `public/` holds exactly 12 files; no canary, seed, operator id,
   truth attribute or provenance field appears there or in `manifest.json`.
9. **Documentation cannot drift**: generated facts come from code and are test-checked.

---

## 5. Documentation state

| Need | Document |
|---|---|
| orientation | [`README.md`](README.md) |
| status | [`STATUS.md`](STATUS.md) |
| handover | [`CONTEXT/NEXT_AGENT.md`](CONTEXT/NEXT_AGENT.md) |
| context exchange rules | [`CONTEXT/AI_HANDOFF_PROTOCOL.md`](CONTEXT/AI_HANDOFF_PROTOCOL.md) |
| architecture | [`CONTEXT/ARCHITECTURE.md`](CONTEXT/ARCHITECTURE.md) |
| invariants | [`CONTEXT/INVARIANTS.md`](CONTEXT/INVARIANTS.md) |
| anomaly matrix | [`CONTEXT/ERROR_MATRIX.md`](CONTEXT/ERROR_MATRIX.md) |
| episode/contract shapes | [`CONTEXT/DATA_CONTRACTS.md`](CONTEXT/DATA_CONTRACTS.md) |
| determinism model | [`CONTEXT/DETERMINISM.md`](CONTEXT/DETERMINISM.md) |
| test map | [`CONTEXT/TESTING.md`](CONTEXT/TESTING.md) |
| clean twin model | [`CONTEXT/CLEAN_TWIN_MODEL.md`](CONTEXT/CLEAN_TWIN_MODEL.md) |
| recipes and troubleshooting | [`CONTEXT/OPERATIONS.md`](CONTEXT/OPERATIONS.md) |
| terminology | [`GLOSSARY.md`](GLOSSARY.md) |
| decisions | [`DECISIONS.md`](DECISIONS.md) |
| machine snapshot | [`CONTEXT/PROJECT_CONTEXT.json`](CONTEXT/PROJECT_CONTEXT.json) |

---

## 6. Working commands

```bash
make test      # 273 tests, exit 0
make sweep     # 48 episodes, 6/6 gates, writes artifacts/phase-04/sweep-24.json
make verify    # both, i.e. the Phase 4 exit gate
python3 tools/export_context.py            # refresh docs/CONTEXT/PROJECT_CONTEXT.json
python3 tools/export_context.py --check    # fail if the snapshot is stale
python3 -m unittest tests.gen.test_diff_truth       # one suite
python3 -m unittest tests.docs.test_docs_consistency # documentation vs code
```
