# Architecture

**Status:** describes the code as it exists at Phase 4 complete.
**Verified by:** `tests/security/test_sealed_boundary.py::LayeringTests`,
`tests/integration/test_serialize.py`, `make test`.

---

## 1. Purpose and shape

TwinLedger produces **episodes**: one synthetic company history rendered twice (clean and
mutated), plus a sealed ground truth. Everything else in the repository exists to make that
production *deterministic*, *auditable* and *safe to publish*.

```
                        ┌──────────────────────────────────────────────┐
                        │            configs/generator/*.json          │
                        │  volumes, fx model, difficulty profiles      │
                        └───────────────┬──────────────────────────────┘
                                        │ load + validate (config_hash)
                                        ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │ gen/clean.py  build_clean_book(seed, config, difficulty)               │
   │   → gen/core/{company,history,journal,fx,reference,text,rng}           │
   │   → contracts/book_model.Book  (immutable, canonical public files)     │
   │   → invariants/checks_clean.check_all  (must be empty)                 │
   └───────────────┬────────────────────────────────────────────────────────┘
                   │ clean twin  C
                   ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │ gen/build_episodes.py  (bounded rejection sampling)                    │
   │   operator selection ← seed hash      subtype ← weighted RNG stream    │
   │   gen/errors/*.apply()  → mutated twin M (new Book, C untouched)       │
   │   gen/truthdiff.structural_diff(C, M)  → diff facts                    │
   │   invariants.check_all(M)              → observed violations           │
   │   gen/truth_build.build_candidate_truth(diff, violations, provenance)  │
   │   gen/errors/signatures.verify_signature  → accept / reject            │
   └───────────────┬────────────────────────────────────────────────────────┘
                   │ EpisodePackage
                   ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │ gen/serialize.write_episode()   atomic staging + rename                │
   │   public/  12 book files (hashed in manifest)                          │
   │   sealed/  truth.json, provenance.json, crosscheck, reject_log          │
   │   manifest.json, verifier_report.json                                  │
   └────────────────────────────────────────────────────────────────────────┘
```

## 2. Layers and the dependency rule

| Layer | Role | May import | Must never import |
|---|---|---|---|
| `contracts` | frozen schemas, row models, immutable `Book`, canonical JSON, error types | `core` | `gen`, `invariants`, `verifier` |
| `core` | money (integer minor units), time rules (zoneinfo/DST), deterministic ids | `contracts` | `gen`, `invariants`, `verifier` |
| `invariants` | `INV-01..17` over the public book | `contracts`, `core` | `gen` |
| `gen` | generation, mutation, diff, truth, publish | all of the above | — (top layer today) |
| `verifier` | *Phase 8* — independent discovery from public data | `contracts`, `core` | `gen`, `invariants` |

The rule is **executable**: `LayeringTests` walks every module's AST and fails on a
violation. This is why `Book` lives in `contracts/book_model.py` and not in `gen/twins.py`
(decision D-001): the invariant layer must be usable by something that has never seen the
generator.

`gen/twins.py` re-exports `Book`, so existing imports keep working.

## 3. Module responsibilities

### `contracts/`
| Module | Responsibility |
|---|---|
| `book_model.py` | frozen `Book`, table access, lookups, role mapping, canonical `public_files()`, `public_digest()` |
| `models.py` | frozen row models (`Account`, `Invoice`, `JournalEntry` + `JournalLine`, `Payment` + `Allocation`, `CreditNote`, `BankLine`, `FxRate`), schema-validated decode, canonical sort |
| `jsonschema_subset.py` | the deliberately small JSON-Schema subset actually used; unsupported keywords **raise** |
| `canonical.py` | canonical JSON/JSONL (sorted keys, LF only, `ensure_ascii=False`), SHA-256 helpers, float/`Decimal` rejection |
| `errors.py` | error taxonomy with structured context (`ContractError`, `ConfigError`, `MoneyError`, `TimeRuleError`, `IdError`, `InvariantError`, `RejectError`, `RejectBudgetExhausted`, `OperatorError`) |
| `anomaly_catalog.json`, `version.json`, `*.schema.json` | frozen contract surface |

### `core/`
| Module | Responsibility |
|---|---|
| `money.py` | `Decimal` parsed from strings, integer minor units, `convert_minor`, `scale_minor`, `allocate_minor`, rounding traces, currency exponents from `currency.json` |
| `time_rules.py` | ISO-8601 with mandatory offset, `PeriodCalendar` (fiscal start, cutoff offset, period labels/bounds), DST gap/overlap resolution |
| `ids.py` | four id families (A/B/C/D), per-table namespaces, collision detection, Luhn for numeric ids |

### `gen/`
| Module | Responsibility |
|---|---|
| `config.py` | loads and validates generator config, derives `config_hash` |
| `clean.py` | `build_clean_book(...)` → `CleanBuild(book, violations, ...)`; rejects a book that trips any invariant |
| `core/` | company profile, accounts, documents/history, journal entries, FX timeline, reference data, text provider, RNG service |
| `twins.py` | `build_book`, `TwinPair` |
| `errors/` | mutation operator base contract, the two operators, frozen signature matrix, **registry** |
| `truthdiff.py` | structural diff C→M (added/modified/removed, changed fields, touched entities) |
| `truth_build.py` | candidate truth from diff + violations + provenance; evidence index and reachability |
| `distractors/` | near-miss cases that must not be reported as findings |
| `reject.py` | bounded sampling, frozen reason codes, `RejectLog` |
| `build_episodes.py` | episode assembly, `build_episode` / `build_episode_set`, canary scan, commitment |
| `serialize.py` | atomic publish, public-only reader, on-disk re-verification |

## 4. Two boundaries, both enforced

### 4.1 Public ↔ sealed
* `public/` contains **exactly** the 12 book files listed in `PUBLIC_FILE_ORDER`.
* Sealed material (`truth.json`, `provenance.json`, `verifier_crosscheck.json`,
  `reject_log.json`) lives outside `public/` and is never referenced by the manifest.
* `read_public_episode()` works with `sealed/` deleted — this is asserted.
* A canary scan runs on every public file before publishing; any hit is a hard reject.
* Commit-reveal: the manifest carries `sha256(salt || truth_digest)`; the salt is sealed and
  derived from `(config_hash, episode_id)`, so the commitment cannot equal the plain digest.

### 4.2 Generator ↔ verifier
The generator knows the answer; a solver must not. Therefore the invariant layer reads only
the public book model, and the Phase 8 verifier is forbidden from importing `gen` (and
`invariants`). The test that will enforce this for the verifier is already written; today it
guards the layers that exist.

## 5. Failure philosophy

* **No `except Exception: pass`.** Errors carry structured context and are either handled at
  a documented boundary or propagated.
* **Checks are total.** Given an adversarial book, an invariant check reports a violation or
  defers to the invariant that owns the malformation — it never raises (D-005).
* **Validation at boundaries only.** Rows are schema-validated when decoded; internal code
  trusts types.
* **Rejection over approximation.** If an episode cannot pass every gate within the attempt
  budget, it is rejected with a frozen reason code — never published half-valid.

## 6. What is deliberately absent

| Not here | Why | Where it belongs |
|---|---|---|
| `verifier/` | independent re-implementation is its own phase | Phase 8 |
| Anomaly types 3–4 | scoped to later phases, already declared `PLANNED` in the catalogue | Phase 5+ |
| `optimal_steps` values | requires query-plan modelling | later phase |
| Scoring / rubric execution | consumes episodes, does not build them | scoring phase |
| Network, DB, LLM calls | offline determinism requirement | never |
