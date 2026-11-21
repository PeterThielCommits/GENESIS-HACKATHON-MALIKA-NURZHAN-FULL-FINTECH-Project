# Invariant Catalogue (INV-01 … INV-17)

**Implementation:** `invariants/checks_clean.py` (`check_all`)
**Signature model:** `invariants/model.py` (`Violation`)
**Enforced by:** every clean twin (must be empty), every mutated twin (must match the error
matrix), `tests/invariants/test_invariants.py` (positive + negative vector per invariant)

---

## 1. Why invariants are the backbone

An anomaly is only meaningful relative to a rule. The catalogue below is that rule set. It is
used three times in the pipeline:

1. **Clean twin gate** — a generated clean book with any violation is refused.
2. **Signature check** — the mutated twin's violations are compared with the frozen matrix:
   intended invariants must fire, allowed ones may, forbidden ones never.
3. **Ground truth** — the finding's `invariant_signature` is derived from the observed
   violation, not asserted by the operator.

## 2. Signature object

Every violation carries the same shape (12.3 of the master TZ):

| Field | Meaning |
|---|---|
| `invariant_id` | `INV-01` … `INV-17` |
| `entity_key` | canonical grouping key, e.g. `invoices:<id>`, `payments:<id>`, `journal_entries:<id>` |
| `expected_delta_minor` | money delta in minor units, or `null` when the rule is not monetary |
| `currency` | currency of the metric, or `null` |
| `direction` | `over` / `under` / `mismatch` / `invalid` |
| `tolerance_minor` | permitted absolute difference (0 unless rounding is involved) |
| `side_effect_class` | `intended` / `allowed` (assigned by the matrix, not by the check) |
| `detail` | human-readable explanation (never contains sealed material) |
| `entity_ids` | ids directly implicated |

`Violation.sort_key()` gives a total order, so violation lists are byte-stable.

## 3. Catalogue

Legend — **metric**: what is quantified; **tolerance**: how much difference is accepted;
**null semantics**: when the metric is not meaningful.

| ID | Name | Scope | Key | Metric | Tolerance | Null semantics |
|---|---|---|---|---|---|---|
| INV-01 | JE_BALANCE | every journal entry | `journal_entries:<je>` | debit − credit (transaction currency, and functional) | 0 | `—` (always monetary) |
| INV-02 | TRIAL_BALANCE | whole book | `trial_balance` | Σ functional debit − Σ functional credit | 0 | `—` |
| INV-03 | AP_SUBLEDGER_VS_DOCS | receivable ledger vs documents | `receivable_subledger:<cur>:<cp>` | ledger balance − Σ open balances | 0 | `—` |
| INV-04 | OPEN_BALANCE | every invoice | `invoices:<doc>` | `total − credited − allocated`; violation when < 0 | 0 | `—` |
| INV-05 | AGING | every open invoice | `invoices:<doc>` | overdue amount vs status; reporting date = end of last posted period | 0 | non-monetary when only status contradicts |
| INV-06 | BANK_MATCH | every bank line | `bank_lines:<id>` | line amount − matched payment amount | 0 | `expected_delta` null when the reference does not resolve |
| INV-07 | FX_POLICY | every foreign-currency line | `journal_entries:<je>` | booked rate vs policy rate (exact `Decimal`) | 0 | `—` |
| INV-08 | FX_RECALC | every foreign-currency line | `journal_entries:<je>` | functional amount − recomputed amount | 1 minor unit (rounding) | `—` |
| INV-09 | CUTOFF | recognition postings | `journal_entries:<je>` | posting period vs period of the recognition basis | 0 | period is a label, so `expected_delta_minor` is `null` |
| INV-10 | PERIOD_TOTALS | every entry | `period:<label>` | posting period vs period of the entry's own timestamp | 0 | `null` (label metric) |
| INV-11 | ID_UNIQUENESS | per table **and** across document tables | `<table>:<id>` / `global:<id>` | duplicate count | 0 | `null` (identity metric) |
| INV-12 | REFERENTIAL | every explicit reference | `<table>:<id>` | unresolvable reference count | 0 | `null` |
| INV-13 | CURRENCY_EXPONENT | currencies, rates, magnitudes | `<table>:<id>` | exponent validity, `|amount| ≤ MAX_ABS_MINOR`, no floats | 0 | `null` |
| INV-14 | TIMEZONE_VALID | every timestamp | `<table>:<id>` | parseability as ISO-8601 with offset | 0 | `null` |
| INV-15 | ALLOCATION_CONSERVATION | every payment | `payments:<id>` | Σ allocations − payment amount | 0 | `—` |
| INV-16 | CREDIT_NOTE_LIMIT | every invoice | `invoices:<doc>` | Σ credit notes − `cap_bps` share of total | 0 | `—` |
| INV-17 | DOCUMENT_STATUS | every invoice | `invoices:<doc>` | stored status vs derived status | 0 | `null` (categorical) |

## 4. Ownership: which check reports what

Checks must not double-report the same root cause (D-005). Deliberate delegations:

| Malformation | Reported by | Deferred by |
|---|---|---|
| dangling `source_document_id` / allocation target | INV-12 | INV-06 (reports "payment not found", then stops) |
| unparsable or offset-less timestamp | INV-14 | INV-07, INV-10 (skip the entry) |
| unsupported currency or malformed rate | INV-13 | INV-08 (skips the line) |
| unknown invoice row (identity destroyed) | INV-11 / INV-12 | INV-05, INV-17 (skip the balance) |
| credit note judged for recognition | — | INV-09 (adjustments are excluded by design) |

## 5. Documented scope decisions

These are real accounting judgements, not implementation shortcuts. Each is recorded in
`docs/DECISIONS.md`.

1. **Credit notes are their own accounting event** (D-004). A credit-note entry references the
   credit note and books at the invoice's document-date rate; INV-09 does not judge it against
   the invoice's recognition period.
2. **FX basis applies to settlement and adjustment postings** (D-004). Recognition entries use
   their own event date. A settlement that ignored the document-date basis *is* a violation.
3. **INV-11 is global across document tables** because `source_document_id` and allocation
   targets are cross-table pointers (D-006).
4. **INV-05 uses a calendar reporting date**, not one derived from the data it judges. The
   previous formulation was unreachable.
5. **INV-16 counts credit notes, not refunds**, because only credit notes exist in the public
   contract today.

## 6. Extending the catalogue

1. Add the check to `invariants/checks_clean.py` and register it in `check_all`.
2. Add a **positive** test (clean twin → no violation) and a **negative** vector (targeted
   corruption → that invariant fires) in `tests/invariants/test_invariants.py`.
3. Update `INVARIANT_CATALOGUE` in `tools/export_context.py`, then run
   `python3 tools/export_context.py` so `docs/CONTEXT/PROJECT_CONTEXT.json` stays current.
4. If the new invariant participates in anomaly signatures, extend
   `gen/errors/signatures.py` and `contracts/anomaly_catalog.json` **in the same change**.
