# Anomaly Error Matrix

**Source of truth in code:** `gen/errors/signatures.py` (`ERROR_MATRIX`, `SUBTYPE_MATRIX`)
**Source of truth in contract:** `contracts/anomaly_catalog.json`
**Consistency check:** `gen/errors/registry.py::validate_against_catalogue`,
`tests/gen/test_registry.py`, sweep gate G4

---

## 1. What the matrix decides

For each anomaly family the matrix declares three disjoint sets of invariants:

| Set | Meaning | Verdict if violated |
|---|---|---|
| **intended** | must fire; this is what the anomaly *is* | should fire; missing → signature mismatch → reject |
| **allowed side effects** | may fire as a documented consequence | acceptable, not required |
| **forbidden** | must never fire; would indicate a broken operator | any hit → reject, and sweep gate G4 fails |

Disjointness is asserted by `test_forbidden_and_intended_never_overlap`.

## 2. Implemented families

### 2.1 `DUPLICATE_PAYMENT`

*Operator:* `OP-DUPLICATE_PAYMENT` — replays an existing payment as a new payment with its own
journal entry and bank line, so the invoice is settled twice.

| Set | Invariants |
|---|---|
| intended | `INV-04` (open balance goes negative) |
| allowed side effects | `INV-03`, `INV-05`, `INV-17` |
| forbidden | `INV-01`, `INV-06`, `INV-07`, `INV-09`, `INV-11`, `INV-12`, `INV-13`, `INV-14`, `INV-15`, `INV-16` |

**Why only INV-04 is intended:** the status (INV-17) is re-derived from public evidence in the
mutated twin, so a duplicate settlement legitimately changes it. INV-03 and INV-05 are
downstream consequences of the same extra settlement. The only *necessary* break is the
negative open balance.

### 2.2 `PARTIAL_PAYMENT_ALLOCATION`

Type-level union:

| Set | Invariants |
|---|---|
| intended | `INV-04`, `INV-15` |
| allowed side effects | `INV-03`, `INV-05`, `INV-17` |
| forbidden | `INV-01`, `INV-06`, `INV-07`, `INV-09`, `INV-11`, `INV-12`, `INV-13`, `INV-14`, `INV-16` |

Per-subtype expectations are authoritative:

| Subtype | intended | Notes |
|---|---|---|
| `OVER_ALLOCATE_TO_ONE_INVOICE` | `INV-04`, `INV-15` | invoice closed with the gross amount despite a credit note; payment smaller than the remaining balance |
| `ALLOCATE_TO_ALREADY_SETTLED_INVOICE` | `INV-04` | part of the payment lands on a document that is already settled |
| `ALLOCATIONS_EXCEED_PAYMENT` | `INV-15` | payment spread over two documents for more than it contains |

All three share the same allowed side effects (`INV-03`, `INV-05`, `INV-17`) and the same
forbidden set.

## 3. Declared but not implemented

`contracts/anomaly_catalog.json` declares four families so the contract does not drift when
later phases add them:

| Type | Status |
|---|---|
| `DUPLICATE_PAYMENT` | `IMPLEMENTED` |
| `PARTIAL_PAYMENT_ALLOCATION` | `IMPLEMENTED` |
| others | `PLANNED` |

`registry.required_anomaly_types_present()` checks only the families the current phase
requires, so adding a `PLANNED` family to code means switching its status and its required-list
entry in one change.

## 4. How a signature decision is recorded

`gen/errors/signatures.verify_signature(...)` produces a decision object, stored in the sealed
provenance and in `verifier_report.json`:

```json
{
  "anomaly_type": "DUPLICATE_PAYMENT",
  "subtype": null,
  "accepted": true,
  "reasons": [],
  "observed": ["INV-04"],
  "intended_hit": ["INV-04"],
  "intended_missing": [],
  "forbidden_hit": [],
  "unexpected": []
}
```

Reject reasons that can result: `SIGNATURE_MISMATCH`, `AMBIGUOUS_FINDINGS`,
`UNREACHABLE_EVIDENCE`, `DIFF_INCONSISTENT` (see `gen/reject.py::REJECT_REASONS`).

## 5. Adding a family

1. Implement the operator (`preconditions`, `apply_book`, `affected_ids`,
   `candidate_params`, optional `selection_table`).
2. Add its three sets to `gen/errors/signatures.py` **and** its entry to
   `contracts/anomaly_catalog.json` — the registry compares them field by field.
3. Register the operator in `gen/errors/registry.py::_FACTORIES`.
4. Add its config block to `configs/generator/mutations.json`.
5. Run `make verify`. Gate G4 is the one that will tell you if the operator over-reaches.
