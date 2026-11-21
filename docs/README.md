# TwinLedger v3.0 — Documentation Map

> **You are an AI agent picking this project up cold.** Read this page top to bottom
> (~4 minutes). It tells you what the project is, what state it is in, which
> documents are authoritative, and how to prove the state is real before you change
> anything.

---

## 1. In one paragraph

TwinLedger generates **deterministic synthetic accounting episodes** for evaluating AI
agents on financial discovery. Each episode ships two snapshots of the same books — a
**clean twin** and a **mutated twin** — plus a **sealed ground truth** committed by hash.
The public surface (12 files) contains no answer: the agent must find the discrepancy from
documents alone. Phase 4 (the mutation core) is complete and its exit gate passes.

## 2. Current state (verify it, don't trust it)

| Fact | Value |
|---|---|
| Phase | **4 complete — DONE**, exit gate passed |
| Tests | **273** stdlib tests, 0 failures, **0 skips** |
| Gate sweep | 48/48 episodes published, 0 rejected, 6/6 gates |
| Anomaly families | `DUPLICATE_PAYMENT`, `PARTIAL_PAYMENT_ALLOCATION` (3 subtypes) |
| Public files per episode | exactly **12** |
| Schemas | **16** frozen `*.schema.json`, all validating |
| Invariants | **17** (`INV-01`..`INV-17`) |
| Runtime deps | none — Python 3.11 standard library, offline |

```bash
make test     # expect: Ran 273 tests ... OK
make sweep    # expect: "all_gates_pass": true
```

If either fails, fix that before anything else. The Phase 4 contract is load-bearing.

## 3. Document map

### Start here
| Document | What it gives you |
|---|---|
| `docs/STATUS.md` | one screen: phase, gates, gaps |
| `docs/CONTEXT/NEXT_AGENT.md` | handover brief, traps, extension recipe |
| `docs/CONTEXT/AI_HANDOFF_PROTOCOL.md` | **how we exchange context without losing it** |
| `docs/CONTEXT/PROJECT_CONTEXT.json` | machine-readable snapshot (generated, verified fresh) |

### Understand the system
| Document | Contents |
|---|---|
| `docs/CONTEXT/ARCHITECTURE.md` | layers, data flow, module responsibilities, boundaries |
| `docs/CONTEXT/DATA_CONTRACTS.md` | episode layout, schemas, public vs sealed, manifest/truth shapes |
| `docs/CONTEXT/INVARIANTS.md` | all 17 invariants: scope, key, metric, tolerance, null semantics |
| `docs/CONTEXT/ERROR_MATRIX.md` | which invariants each anomaly type may/must/never break |
| `docs/CONTEXT/DETERMINISM.md` | seed derivation, RNG namespaces, id families, canonical JSON |
| `docs/CONTEXT/CLEAN_TWIN_MODEL.md` | how a clean book is generated and why it is clean |
| `docs/CONTEXT/TESTING.md` | suite map, what each test proves, how to add tests |
| `docs/CONTEXT/OPERATIONS.md` | how to generate, publish, verify, inspect episodes |

### History and decisions
| Document | Contents |
|---|---|
| `docs/DECISIONS.md` | append-only decision log (D-001…D-012) |
| `docs/PHASE_REPORTS/PHASE-04.md` / `.json` | phase report with command→exit→result evidence |
| `docs/AGENT_REPORTS/2026-11-21/` | what an agent actually did, including its mistakes |
| `docs/GLOSSARY.md` | terms: twin, sealed boundary, signature, distractor, commitment |
| `docs/official/` | the master TZ and the universal phase-execution prompt (source of truth for scope) |

## 4. The five rules that matter most

1. **Truth is earned, not declared.** A finding needs diff facts + a matching invariant
   violation + reachable public evidence. Any two of the three is not enough.
2. **The sealed boundary is absolute.** `sealed/` never influences `public/`; no seed,
   operator id, truth attribute or canary may appear in public output.
3. **Determinism is a product feature.** Same seed → same bytes, across processes.
4. **Layers point one way.** `contracts`/`core` never import `gen`; `invariants` never
   imports `gen`. Enforced by tests, not by convention.
5. **Never claim a gate you did not run.** Every number in these docs has a command, an
   exit code and a result behind it.

## 5. Where to make the next change

| If you want to… | Change this | Guard that will catch you |
|---|---|---|
| add an anomaly family | `gen/errors/<name>.py` + `gen/errors/registry.py` + `contracts/anomaly_catalog.json` | `tests/gen/test_registry.py` |
| change generation volumes | `configs/generator/default.json` | `config_hash` changes → all digests change, sweep re-runs |
| change a public file | `contracts/book_model.py::PUBLIC_FILE_ORDER` | `test_public_file_set_is_exact`, schema tests |
| change money or time semantics | `core/money.py`, `core/time_rules.py` | `tests/unit/*` with hand-computed vectors |
| write the independent verifier | new `verifier/` package | `tests/security/test_sealed_boundary.py::LayeringTests` |

## 6. Documentation contract

These documents are part of the deliverable, not commentary:

* `docs/CONTEXT/PROJECT_CONTEXT.json` is **generated** by `tools/export_context.py` and
  **checked** by a test. Never hand-edit it.
* Every phase ends with a report in `docs/PHASE_REPORTS/` containing a
  command → exit code → result table.
* Every non-obvious decision is appended to `docs/DECISIONS.md` (never edited or deleted).
* `docs/STATUS.md` and `docs/CURRENT_STATE.md` are updated in the same change as the work.
