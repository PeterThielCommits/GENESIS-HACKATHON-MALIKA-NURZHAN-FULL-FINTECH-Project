# INDEPENDENCE — independent verifier and red-team boundaries

Requirements: REQ-ORG-001…005 (§4), §12.4, §13.2.

## 1. Ownership at Phase 0

| Zone | Human owner | AI role | Current state |
|------|-------------|---------|---------------|
| 1 — generator & data (`gen/`, `spec/`, `episodes/`) | Owner A | Gen architect, error operator engineer | `spec/` catalogs exist; `gen/` not started |
| 2 — environment & evaluator (`env/`, `adapter/`, `harness/`, `scoring/`, `seal/`) | Owner B | Env, scoring, harness engineers | `adapter/` unbound exists; rest not started |
| 3 — verification & red team (`verifier/`, `arena/`, `metamorphic/`) | Owner C | Verifier, red team | not started |
| 4 — docs, QA, judge kit (`judge/`, `tools/`, `docs/`, CI) | Owner D | QA, docs, judge kit | implemented (Phase 0) |
| Orchestration | A0 | this agent session | implemented |

**Honest statement:** this repository was produced by a single AI agent session acting across
all four zones. REQ-ORG-001 ("the verifier must be written by a different human owner than
the generator") is therefore **not satisfied by people**; it is satisfied only by the
structural controls in §2 until a second human reviews the verifier. This is recorded as an
open item in `docs/STATUS.md` and is not hidden behind the word "independent".

## 2. Structural controls that exist now

1. **Import boundary (enforced).** `tools/check_import_boundaries.py` fails the build if
   `verifier/` imports `gen/`, if `env/` imports `gen|verifier|scoring|seal`, if
   `scoring/` imports `gen|env`, or if policy code touches `scoring`/`seal`. The zone table
   already covers directories that do not exist yet, so Phase 6 cannot accidentally violate
   it.
2. **Forbidden-token scan.** `env/` must not contain `truth.json`, `provenance`, `sealed/`,
   `mutation_` or `master_seed`; policy code must not reference `scoring.`, `seal.` or
   private paths (REQ-ARC-002/003).
3. **Separate discovery interface.** The verifier contract
   (`contracts/verifier_report.schema.json`) accepts only public sources and machine-readable
   reason codes; there is no field for provenance, mutation parameters or seeds.
4. **Crosscheck is a second stage.** Discovery output must be hashed and recorded before
   `crosscheck(report, sealed_truth)` runs (REQ-VER-021/022, planned Phase 6).
5. **Spec-first development.** The anomaly catalog and the invariant catalog
   (`spec/*.json`) are data read by both sides; neither side imports the other's *algorithm*
   — the specification is shared, the implementation must not be.

## 3. Known shared dependencies (declared, not hidden)

| Dependency | Shared by | Risk | Control |
|------------|-----------|------|---------|
| `tools/canonical_json.py` | everything that hashes | common-mode serialization bug | golden vectors + permutation tests (`tests/unit/test_canonical_json.py`) |
| `contracts/currency.json` (exponents) | generator, verifier, scorer | a wrong exponent is wrong everywhere | hand-authored KZT/USD/JPY/KWD vectors in Phase 2 |
| `spec/invariants.json` | generator checks, verifier | a wrong invariant hides a bug on both sides | invariant vectors authored by hand, not generated (REQ-INV-004) |
| money conversion helper (planned) | generator, verifier | common-mode rounding | tiny, vector-tested; **rate selection must be implemented twice** (R-17) |

No shared anomaly-detection function is permitted. If one ever appears, this table must list
it and `make verify` must report it as a common-mode dependency (§12.4).

## 4. Review obligations

* `docs/PHASE_REPORTS/PHASE-06.md` must include a signed statement that the verifier was
  written from `spec/` + `contracts/` only, with the discovery commit hash recorded before
  any truth comparison.
* The import-boundary report (`artifacts/reports/latest/import_boundaries_report.json`) is an
  artifact of every release, not a one-off check.

## 5. What would strengthen independence further

1. A second human (Owner C) takes over `verifier/` before Phase 6 and reviews the algorithm
   independently.
2. A deliberately broken generator mutant is used to confirm the verifier does **not** follow
   the generator's bug (planned: verifier false-positive/false-negative suite in Phase 6).
3. Differential invariant implementations: two independent computations of the same invariant
   compared on synthetic data.
