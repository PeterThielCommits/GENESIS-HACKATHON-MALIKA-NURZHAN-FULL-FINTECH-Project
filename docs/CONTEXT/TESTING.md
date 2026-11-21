# Testing

**Runner:** stdlib `unittest` only (no pytest, no plugins, no network).
**Totals:** **273 tests, 0 failures, 0 errors, 0 skips.** (254 at the Phase 4 gate; documentation tests added afterwards.)

```bash
make test                                                     # everything
python3 -m unittest tests.invariants.test_invariants          # one suite
python3 -m unittest tests.gen.test_operators.SubtypeSpreadTests   # one class
```

---

## 1. Suite map

| Suite | Tests | What it proves |
|---|---:|---|
| `tests/unit/test_money.py` | 33 | minor units, HALF_EVEN/HALF_UP, JPY/KWD exponents, allocation conservation, conversion exactness |
| `tests/unit/test_time_rules.py` | 22 | offsets, periods, fiscal year, leap year, Berlin DST gap/overlap |
| `tests/unit/test_ids.py` | 17 | all four id styles, no shortcut, cross-table uniqueness, Luhn |
| `tests/contracts/test_schemas.py` | 24 | every schema validates a good fixture and rejects a malformed one; inventory complete |
| `tests/gen/test_clean_twin.py` | 24 | determinism, exact 12-file set, no floats, no shortcut in ids, locale text |
| `tests/gen/test_operators.py` | 33 | preconditions, affected ids, signature conformance, subtype spread, no-crash on bad params |
| `tests/gen/test_diff_truth.py` | 18 | diff exactness/amounts, clean-twin guard, truth requires diff **and** violation, evidence reachability |
| `tests/gen/test_reject_and_episodes.py` | 18 | bounded sampling, frozen reason codes, episode determinism, manifest privacy, both families generate |
| `tests/gen/test_registry.py` | 11 | registry ↔ catalogue agreement, drift detection, unknown operator handling |
| `tests/invariants/test_invariants.py` | 25 | all 17 checks registered and firing; positive baseline; one negative vector each |
| `tests/integration/test_serialize.py` | 16 | atomic publish, idempotence, tamper detection, public-only read, cross-process determinism |
| `tests/security/test_sealed_boundary.py` | 13 | no canary/seed/truth leak in public, layering rule, sealed path isolation |
| `tests/docs/test_docs_consistency.py` | 19 | documentation matches code; generated context is fresh |

## 2. Testing philosophy

### 2.1 Negative vectors are mandatory
For each invariant there is a targeted corruption that must trip it. A check that silently
inspects nothing passes a positive test forever; only a negative vector proves it works.

### 2.2 No `skipTest` for in-scope behaviour
If a test cannot run, it must **construct** the precondition (`dataclasses.replace`,
`with_rows`) rather than skip. A skipped gate is not a passed gate. The suite reports
`0 skipped`; treat any new skip as a defect.

### 2.3 Determinism is tested, not assumed
Two identical builds, plus a subprocess run under a different `PYTHONHASHSEED`.

### 2.4 Privacy is tested from the outside
Security tests read the produced files, not internal flags: they scan public bytes for
canary/seed/truth tokens, assert `read_public_episode` works with `sealed/` deleted, and parse
module ASTs to enforce layering.

### 2.5 Adversarial input is a first-class case
Invariant checks are fed a book corrupted in every dimension at once
(`_corrupt_everything`) and must report violations without raising.

## 3. Gate evidence

`tools/phase4_sweep.py` encodes the Phase 4 exit gate as six checks with an exit code:

| Gate | Meaning |
|---|---|
| G1 | both anomaly families produced by ordinary seeds |
| G2 | clean twin passed the invariant suite in every published episode |
| G3 | every finding is diff-backed with reachable evidence |
| G4 | no finding produced an invariant its family declares forbidden |
| G5 | rejection stayed a minority of attempts |
| G6 | identical seeds reproduce identical digests (two independent runs) |

```bash
make sweep   # writes artifacts/phase-04/sweep-24.json, exit 0 only if all six pass
```

## 4. Adding tests

| You changed | Add / extend |
|---|---|
| money or time semantics | hand-computed vectors in `tests/unit/*` (no round-tripping a function against itself) |
| an invariant | positive + negative vector in `tests/invariants/test_invariants.py` |
| an operator | `tests/gen/test_operators.py` (preconditions, affected ids, signature) |
| episode assembly | `tests/gen/test_reject_and_episodes.py` (determinism, manifest privacy) |
| serialisation | `tests/integration/test_serialize.py` (tamper, idempotence, public-only read) |
| a public file or the boundary | `tests/security/test_sealed_boundary.py` + schema tests |
| any `docs/` fact | run `python3 tools/export_context.py` (a test fails if you forget) |
| the documentation set itself | `make test-docs` (19 tests) and `make docs-check` |

## 5. Timing expectations

| Command | Wall clock (this environment) |
|---|---|
| `make test` | ~25 s |
| `make sweep` | ~25 s |
| `make verify` | ~50 s |

Slowest suites: `test_reject_and_episodes` and `test_operators` (they build real books and
episodes). Do not "optimise" them by stubbing generation — the value is that they exercise the
real path.

## 6. Known gaps in test coverage

* `verifier/` does not exist yet, so its independence is enforced by a test that will engage
  automatically.
* Anomaly types 3–4 are untested because unimplemented (declared `PLANNED`).
* Scoring/rubric execution is out of scope for this phase.
* No coverage measurement tool is used (no third-party dependencies); coverage is reasoned from
  the suite map above, not from a percentage.
