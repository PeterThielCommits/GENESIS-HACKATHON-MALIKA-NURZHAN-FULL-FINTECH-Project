# Clean Twin Model

**Code:** `gen/clean.py`, `gen/core/{company,history,journal,fx,reference,text,rng}.py`
**Gate:** `build_clean_book(...)` refuses to return a book that trips any of INV-01..17.

---

## 1. Why the clean twin is the hardest part

An anomaly is only detectable if the *clean* history is impeccable. If the baseline has its own
inconsistencies, every downstream signal becomes ambiguous: a verifier cannot tell a mutation
from a pre-existing flaw, and ground truth becomes unfalsifiable.

So the clean twin is generated **and then audited**: `check_all(book)` must return an empty
list. In practice this caught real design contradictions (see §6).

## 2. Generation order

```
1. Company profile      jurisdiction, timezone, currency, chart of accounts, policy
2. Reference data       accounts, counterparties
3. FX timeline          one rate per pair per publication day (seeded walk, no weekend publication)
4. Document plans        per month: invoices with service windows, credit notes, payments
5. Journal entries       recognition, settlement, adjustment — derived from the documents
6. Derived state         invoice statuses recomputed from public evidence
7. Audit                 check_all(book) → must be empty, else the build is refused
```

Everything draws from namespaced RNG streams, so a change in step 4 does not silently perturb
step 3.

## 3. Accounting model (synthetic but internally consistent)

| Event | Posting | Rate used |
|---|---|---|
| Invoice recognition | Dr receivable / Cr revenue | document-date rate of the invoice |
| Customer settlement | Dr bank / Cr receivable | invoice's document-date rate (policy basis) |
| Credit note | Dr revenue / Cr receivable | invoice's document-date rate |

**Why settlement uses the document-date rate:** the policy declares
`fx_rate_date_basis = document_date`, so a payment relieves the receivable at exactly the rate
it was recognised at. This removes artificial FX differences from the *clean* baseline — an FX
error is then an anomaly (Phase 5), not noise.

**Why credit notes use it too:** a credit note reduces the same receivable. Using a different
rate would create a residual FX balance that is not an accounting error but looks like one.

## 4. Document lifecycle

* **Invoices** carry `issue_timestamp`, `service_start`/`service_end`, `due_timestamp`,
  embedded `line_items`, and `status`.
* **Status** is *derived*, never dictated: `OPEN`, `PARTIALLY_PAID`, `PAID`, `CREDITED`,
  `OVERPAID`, `VOID` are recomputed from total − credited − allocated (INV-17 exists precisely
  to catch a stale status).
* **Payments** settle an invoice fully or partially (configured ratios), sometimes early,
  sometimes with unapplied cash. Allocations use `oldest_open_first`.
* **Credit notes** are capped at a configured share of the document (INV-16).
* **Bank lines** mirror payments; a match is explicit (`matched_payment_id` + `MATCHED`).

## 5. Configuration that shapes the corpus

`configs/generator/default.json` (abridged):

| Group | Notable values |
|---|---|
| history | 2025-01 start, 6 months, monthly periods, fiscal start 1 Jan |
| company | timezone pool `Asia/Almaty`, `Asia/Aqtobe`, `UTC`; functional `KZT`; currencies KZT/USD/EUR/JPY; id style pool A–D |
| volumes | 7 counterparties, 5 invoices/month (L1: 4, L3: 8), 35% foreign currency, credit notes 28%, partial payments 26%, unapplied cash 0.6% |
| fx | scale 6, pairs USD/EUR/JPY→KZT, mean reversion 3/20, weekday publication |
| difficulty | L1: 1 anomaly / 1 distractor pair; L2: 2 / 2; L3: 3 / 3 |

Changing any of these changes `config_hash`, hence episode ids and every digest. That is
intentional and is why published episodes quote their config hash.

## 6. Contradictions this model resolved

| Symptom | Root cause | Resolution |
|---|---|---|
| Clean twin tripped `INV-09` (cutoff) | Credit-note JE referenced the *invoice*, so it was judged against the invoice's recognition period | credit-note JE references the credit note; INV-09 excludes adjustment postings (D-004) |
| Clean twin tripped `INV-07` (FX policy) | Settlement/adjustment postings were judged with their own event date instead of the policy basis | INV-07 applies the document-date basis to settlement and adjustment postings |
| Clean twin tripped `INV-11` (id uniqueness) | Style-D numeric ids collided across tables; `source_document_id` is a cross-table pointer | numeric ids carry a two-digit table namespace (D-006) |

After these fixes: **0/180 unclean** books over 60 seeds × L1/L2/L3.

## 7. Reading a clean book

```python
from gen.config import load_generator_config
from gen.clean import build_clean_book

build = build_clean_book(master_seed="demo", config=load_generator_config(), difficulty="L2")
print(build.book.row_counts())      # {'accounts': 8, 'invoices': 36, 'payments': 46, ...}
print(build.book.public_digest())   # stable for this seed + config
print(build.violations)             # () — the audit result
```

`CleanBuild` exposes the book, the violation list, and the derived artefacts used by the
episode builder. It is a pure function of `(master_seed, config, difficulty)`.
