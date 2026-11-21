# NEXT AGENT — start here

You are continuing TwinLedger v3.0. **Phase 4 is DONE** with its exit gate passed. Do not
re-do it; verify it in ~50 seconds and build the next phase on top of it.

---

## 1. First five minutes

```bash
make test      # expect: Ran 273 tests ... OK          (exit 0)
make sweep     # expect: "all_gates_pass": true        (exit 0)
```

If either fails, stop and fix it before writing new code — the Phase 4 contract is
load-bearing for everything after it.

Read, in order:
1. `docs/STATUS.md` — one screen: phase, gates, gaps.
2. `docs/README.md` — the map of all documentation.
3. `docs/PHASE_REPORTS/PHASE-04.md` §2 (traceability) and §6 (deviations).
4. `docs/DECISIONS.md` — thirteen decisions; D-001 (layering) and D-002 (determinism) are the
   ones most likely to trip you.
5. `docs/CONTEXT/INVARIANTS.md` §4 and §5 before touching accounting logic.

## 2. Ground rules that are enforced, not suggested

| Rule | Enforced by |
|---|---|
| Python 3.11 stdlib only, offline | no third-party imports anywhere; `pyproject.toml` has no dependencies |
| Money = integer minor units, `Decimal` from strings, never floats | `tests/unit/test_money.py`, `test_no_float_anywhere_in_public_payload`, INV-13 |
| Deterministic output for a given seed | `test_same_seed_same_bytes_across_processes` (two `PYTHONHASHSEED` values) |
| `contracts`/`core` must not import `gen` | `tests/security/test_sealed_boundary.py::LayeringTests` |
| `invariants` must not import `gen` | same test |
| No truth/provenance/seed/canary leak in `public/` | `tests/security/test_sealed_boundary.py`, canary scan in the builder |
| Invariant checks never raise on adversarial books | `tests/invariants/test_invariants.py` negative vectors |
| Operator must exist in registry **and** catalogue with identical sets | `gen/errors/registry.py::validate_against_catalogue`, `tests/gen/test_registry.py` |
| Documentation facts must match code | `tests/docs/test_docs_consistency.py` (`tools/export_context.py --check`) |

No `skipTest` for anything the current phase must prove. A skipped gate is not a passed gate.

## 3. Extension points (Phase 5: remaining anomaly types)

To add an anomaly family:

1. Implement `MutationOperator` in `gen/errors/<name>.py`: `preconditions`, `apply_book`,
   `affected_ids`, `candidate_params`, and optionally `selection_table` (for documented
   subtypes with configured weights).
2. Register it in `gen/errors/registry.py::_FACTORIES`; add its type to
   `REQUIRED_ANOMALY_TYPES` only when the plan requires it.
3. Add the family to `contracts/anomaly_catalog.json` (`intended_invariants`,
   `allowed_side_effects`, `forbidden_invariants`). If it disagrees with
   `gen/errors/signatures.py`, the registry self-check fails — intentionally.
4. Add its config block to `configs/generator/mutations.json`.
5. Tests: preconditions, affected ids, signature conformance, clean-twin-untouched, and a
   negative vector proving the intended invariant fires.
6. Update `docs/CONTEXT/ERROR_MATRIX.md`, then `python3 tools/export_context.py`, then
   `make verify`.

**Do not** create a second episode builder, a second diff, or a second truth path. Extend the
existing ones.

## 4. Traps found the hard way (do not rediscover)

* `dataclasses.replace` on `Book` copies `_index_cache` → stale lookups. Always use
  `Book.with_rows`, which drops the cache.
* `book.rows("allocations")` / `rows("journal_entry_lines")` raise — those rows are embedded in
  `payments[].allocations` and `journal_entries[].lines`.
* Two `issue_unique_id` calls inside one mutation can return the same id; use the batch API.
* A duplicate payment does not always modify the invoice — derive `diff_refs` from
  `_modified_keys()`, never assume.
* `reject(reason_code, reason=...)` collides on the keyword; never name a kwarg `reason`.
* Over-tight subtype signatures get rejected: INV-17 must stay an *allowed side effect*, never
  *intended*.
* Aware datetimes in the same zone compare equal even across a DST fold — compare in UTC.
* `ensure_ascii=False` is deliberate in canonical JSON; comparing against `json.dumps` without
  it produces phantom mismatches on non-ASCII names.
* Positional candidate selection (`candidates[k]`) silently starves subtypes; use the weighted
  stream (`selection_table` + `choices_weighted`).
* An operator family can legitimately have zero candidates on a given book; retrying the same
  family cannot help (see D-003).

## 5. What not to claim

* Never mark a phase DONE without a command, an exit code and a result for each gate.
* Never write "GitHub updated" without a real commit/PR URL.
* Never call the sealed boundary "secure" beyond what the tests demonstrate — they show no leak
  in produced artifacts and correct layering, not a sandbox guarantee.
* `SKIPPED` is not `PASS`.

## 6. Where the current phase expects you

| Next phase (per master TZ) | Ready-made interfaces | First thing to read |
|---|---|---|
| Phase 5 — remaining anomaly types | `gen/errors/base.py`, registry, catalogue | `docs/CONTEXT/ERROR_MATRIX.md` §5 |
| Phase 8 — independent verifier | `read_public_episode`, `contracts/book_model.py`, invariant semantics | `docs/CONTEXT/ARCHITECTURE.md` §4.2 |
| Query-plan / `optimal_steps` | `finding.optimal_steps_model_id = query_plan_v1` | `docs/CONTEXT/DATA_CONTRACTS.md` §4 |
