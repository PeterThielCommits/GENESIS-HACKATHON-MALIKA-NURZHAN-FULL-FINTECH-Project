# DESIGN — architecture intent

Status: Phase 0. This document describes the **planned** system precisely enough that later
phases implement it, and marks honestly what exists today. `docs/CONTEXT/ARCHITECTURE_SNAPSHOT.md`
holds the short current-state diagram.

## 1. Principles that constrain every design decision

1. Evidence over presentation: every claim has a command, a commit and an artifact.
2. Truth is computed from counterfactual twins, never written by hand.
3. The verifier is an independent implementation, not a second call of the generator.
4. The environment never sees the answer key.
5. The policy never sees the evaluator.
6. A finding is exact: type, affected IDs, amount, currency, evidence.
7. Text supplements structure; it never creates a fact.
8. Determinism covers order, serialization, arithmetic, RNG, errors and replay.
9. Core is offline and stdlib-only.
10. A missing optional dependency degrades to `SKIPPED`, never to a false `PASS`.

## 2. Build-time pipeline (planned Phase 3–7)

```
master_seed ──► RNG service (addressable namespaces)
                    │
                    ├─► company / chart / counterparties / policy
                    ├─► FX timeline (Decimal OU walk, market calendar)
                    ├─► documents (invoices, credit notes, payments, bank lines)
                    └─► journal entries (balanced by construction)
                          │
                     CLEAN BOOK C ──► invariant suite (expect 0 violations)
                          │
                    operators O1..On (deterministic, versioned)
                          │
                     MUTATED BOOK M ──► invariant suite (expect declared signature only)
                          │
        canonical_diff(C, M) ──► candidate truth + invariant signatures
                          │
        independent verifier(public only) ──► findings + evidence certificates
                          │
        crosscheck(verifier, candidate truth) ──► accept or reject episode
                          │
        sealed/truth.json + sealed/provenance.json + manifest.json (hashes)
                          │
        commitment = SHA256(canonical_truth || salt)  → published in manifest
```

Design notes:

* Operators receive an immutable snapshot and return a new one; they never mutate C.
* Each operator declares `expected_invariant_signature` and `allowed_side_effects`; a single
  violation outside that set rejects the episode (`spec/anomaly_catalog.json`).
* The diff is *not* proof of semantic error: the verifier must independently reach the same
  conclusion, otherwise the episode is rejected.
* Evidence minimality: context files (company/policy/calendar/accounts) are always available
  and never consume evidence slots.

## 3. Evaluation-time pipeline (planned Phase 5–8)

```
HARNESS ──spawn──► ENV (cwd = episode/public, read-only, no sealed path)
   │  JSONL ▲▼
   └──spawn──► POLICY (cwd = scratch dir, allowlisted env, stdin/stdout only)
   │
   ├─ append-only trajectory: h_i = SHA256(h_{i-1} || canonical(event_i))
   │
   └─ env closed ──► SCORER (sealed truth, no channel to policy)
                          │
                     match → F1 → reward → breakdown + receipt
```

* Closed mode is the default: `step` returns `reward = 0`, `info` restricted to
  `steps_used`/`steps_remaining`.
* Only one successful `submit`; later calls return `ALREADY_SUBMITTED` and change nothing.
* Truncation comes from the deterministic step budget only.

## 4. Scoring design (planned Phase 9)

* `scoring/canon.py` canonicalizes IDs (NFC → namespace → dedupe → sort).
* `scoring/matcher.py` builds the bipartite graph, maximizes pair count, then minimizes total
  absolute amount error, then applies a lexicographic tie-break (input index last). A
  brute-force reference matcher validates it on small graphs.
* `scoring/reward.py` computes F1 and the step penalty in exact arithmetic from
  `configs/scoring/reward.json`; no literal appears in code.
* Diagnostics (precision/recall/F1, evidence coverage, truncation flags) never change reward.

## 5. Sealing design (planned Phase 8)

| Element | Design | Honest limitation |
|---------|--------|-------------------|
| Commitment | `SHA256(canonical_truth ‖ salt)`, published pre-run | proves immutability after commit, not correctness |
| Salt | `secrets.token_bytes(32)`, only in `sealed/` | test fixtures use a labelled constant |
| Trajectory | hash chain without wall-clock | deterministic replay |
| Receipt | code/config/manifest hashes + head + Merkle index | integrity evidence, not quality evidence |
| Process isolation | separate processes, dirs, env vars, fixed argv | not an OS sandbox (D-0012) |

## 6. Error and budget design (planned Phase 5)

* Every action consumes a step, including invalid ones (configurable, provisional).
* Errors are a closed set with bounded messages; `NOT_FOUND` is identical for "missing" and
  "exists but forbidden".
* After `submit`/`truncated`, every further call returns a bounded error and cannot change the
  score.

## 7. What exists today (Phase 0)

| Component | Reality |
|-----------|---------|
| Contracts | 12 schemas + 35 fixtures, validated on every build |
| Canonical JSON | implemented with golden tests |
| Schema validation | in-repo stdlib subset validator, fails on unsupported keywords |
| Adapter | unbound profile that fails closed with bounded errors |
| Governance | assumptions/questions/decisions/requirements/rubric map consistency + claim scan |
| Import boundaries | AST scan with the full §6 zone table |
| Verify runner | Phase 0 checks with artifact output and documented exit codes |
| Everything else | **not implemented**; Make targets exit `5` and say so |
