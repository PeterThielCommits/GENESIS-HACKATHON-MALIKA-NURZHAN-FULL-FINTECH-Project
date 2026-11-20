# DATA DICTIONARY

Normative source: `docs/official/master_tz/…` §8, `spec/anomaly_catalog.json`,
`spec/invariants.json`, and the schemas in `contracts/`. Where this page and a schema differ,
the schema wins and this page is a bug.

Conventions used throughout:

| Convention | Value |
|------------|-------|
| Encoding | UTF-8, LF line endings |
| Tabular files | JSON Lines (`.jsonl`), one object per line, no trailing commas |
| Key order inside a line | canonical (sorted) so that file bytes are reproducible |
| Money | integer **minor units** (never float); exponent per `contracts/currency.json` |
| Rates | decimal **string** (`"462.350000"`), converted with `Decimal` |
| Timestamps | ISO-8601 with explicit offset, e.g. `2026-03-14T23:40:00+05:00` |
| Periods | `YYYY-MM`, computed in the company IANA timezone |
| IDs | `TYPE:raw` for cross-table references; raw form inside the owning table |
| Null | explicit `null` = unknown / not applicable; never "guess this" |

## 1. `company.json` — `contracts/company.schema.json`

| Field | Type | Notes |
|-------|------|-------|
| `company_id` | string `CO-XXXXXX` | synthetic |
| `legal_name` / `name_variants.{ru,kk,en}` | string | fictional, three languages |
| `jurisdiction_code` | `X[A-Z]` | **internal placeholder, not ISO-3166** |
| `timezone` | IANA name | drives every period/cut-off decision |
| `functional_currency` | currency code | must exist in the exponent registry |
| `supported_currencies` | array ≤ 8 | foreign-currency documents use these |
| `fiscal_year_start` | date | affects period keys |
| `fiscal_period_rule` | `MONTHLY` / `QUARTERLY` | |
| `accounting_basis` | object | `revenue_recognition`, `expense_recognition`, `cutoff_rule` |
| `id_style` | `A`–`D` | visual identity style, applies to clean and mutated rows alike |
| `text_profile` | object | languages and register for descriptions |
| `company_size` | `L1`–`L4` | size profile, not a difficulty claim by itself |

## 2. `policy.json` — `contracts/policy.schema.json`

| Field | Type | Notes |
|-------|------|-------|
| `rounding_mode` | `ROUND_HALF_EVEN` / `ROUND_HALF_UP` | used by every conversion |
| `fx.rate_date_basis` | `DOCUMENT_DATE` / `PAYMENT_DATE` / `POSTING_DATE` | the verifier must select the rate **independently** |
| `fx.non_business_day_rule` | `LAST_AVAILABLE_PRIOR` / `NEXT_AVAILABLE` | weekend/holiday handling |
| `fx.allowed_sources` | array | a rate from another source is not bookable |
| `fx.inverse_quote_allowed` | bool | inverse quoting must be exactly consistent |
| `recognition.revenue_basis` / `expense_basis` | `SERVICE_DATE` / `SERVICE_COMPLETION` / `INVOICE_DATE` | cut-off rule |
| `recognition.cutoff_timezone` | `COMPANY_LOCAL` | never the machine timezone |
| `allocation.max_allocation_basis` | `DOCUMENT_TOTAL_MINUS_CREDITS` | over-allocation is an anomaly |
| `allocation.advance_accounting` | `SEPARATE_LIABILITY` / `DIRECT_ALLOCATION` | changes `INV-03`/`INV-15` exceptions |
| `allocation.allow_multi_invoice_allocation` | bool | legitimate split payments |
| `credit_notes.cap_basis` | `DOCUMENT_TOTAL` / `NONE` | with optional `cap_ratio_decimal` |
| `tolerance.rule_id` | `ROUNDING_OPERATIONS_V1` | provisional tolerance model |

## 3. Tables (`public/*.jsonl`)

### `accounts.jsonl`

| Field | Type | Notes |
|-------|------|-------|
| `account_id` | `ACC`-style raw ID | primary key |
| `code` | string | chart-of-accounts code |
| `name` | string | synthetic |
| `type` | `ASSET` / `LIABILITY` / `EQUITY` / `REVENUE` / `EXPENSE` | |
| `currency` | currency code or `null` | `null` = functional currency |

### `counterparties.jsonl`

`counterparty_id` (PK), `legal_name` + `name_variants`, `country_code` (`XA`–`XZ`),
`is_customer`, `is_supplier`, `payment_terms_days`, `default_currency`, `tax_id` (synthetic).

### `journal_entries.jsonl`

| Field | Type | Notes |
|-------|------|-------|
| `je_id` | raw ID | PK |
| `timestamp` | ISO-8601 + offset | posting timestamp |
| `posting_period` | `YYYY-MM` | must equal period of `timestamp` in company tz |
| `source_document_id` | namespaced ID or `null` | invoice / payment / credit note |
| `description` | object `{ru,kk,en}` | supplemental only, never proof |
| `lines[]` | array ≥ 2 | see below |

`lines[]`: `line_id` (PK), `account_id`, `debit_minor`, `credit_minor` (exactly one non-zero),
`currency`, `fx_rate_decimal` (string, `null` for functional currency), `functional_debit_minor`,
`functional_credit_minor`, `counterparty_id` or `null`, `analytic_tag` or `null`.
`INV-01` requires `Σ functional_debit == Σ functional_credit` per JE.

### `invoices.jsonl`

`doc_id` (PK), `counterparty_id`, `issue_timestamp`, `service_start`, `service_end` or `null`,
`due_timestamp`, `currency`, `total_minor`, `tax_minor` or `null`, `line_items[]`, `status`
(`OPEN`/`PARTIALLY_PAID`/`PAID`/`CREDITED`/`VOID`).
`line_items[]`: `line_id` (PK), `description` (object), `quantity_decimal` or `null`,
`unit_price_minor` or `null`, `amount_minor`, `service_reference` or `null`.

### `credit_notes.jsonl`

`credit_note_id` (PK), `invoice_id`, `counterparty_id`, `timestamp`, `amount_minor`, `currency`,
`reason_code` (`PRICE_ADJUSTMENT`/`RETURN`/`DISPUTE`/`GOODWILL`).

### `payments.jsonl`

`pay_id` (PK), `timestamp`, `counterparty_id`, `currency`, `amount_minor`, `allocations[]`,
`bank_reference` or `null`, `payment_channel` (`BANK_TRANSFER`/`CARD`/`CASH`/`OFFSET`).
`allocations[]`: `allocation_id` (PK), `document_id` (namespaced invoice ID),
`amount_minor`, `allocation_timestamp`.
`INV-15` requires `Σ allocations ≤ payment.amount_minor` for the declared accounting mode.

### `bank_lines.jsonl`

`bank_line_id` (PK), `timestamp`, `amount_minor`, `currency`, `direction` (`IN`/`OUT`),
`reference_text`, `matched_payment_id` or `null`, `bank_account_id`.
A line may legitimately be unmatched when the policy documents a reason (`INV-06`).

### `fx_rates.jsonl`

`pair` (`USD/KZT`), `effective_date`, `rate_decimal` (string), `source_code`, `publication_timestamp`
or `null`. Weekends/holidays may be absent according to the market profile; the policy decides
which prior date is used.

### `opening_balances.json`

Map of `account_id` → `amount_minor` as of `fiscal_year_start`, with `currency` and the
declared `source` (`AUDITED_CARRY_FORWARD`). Referenced by `INV-02`.

### `period_calendar.json`

Array of periods: `period_key`, `start_date`, `end_date`, `is_closed`, `close_timestamp`.
Cut-off and period-total invariants use this calendar, never the system clock.

### `document_links.jsonl` (only if the contract provides this object)

`link_id`, `from_id`, `to_id`, `relation` (`SERVICE_OF`/`CREDIT_OF`/`PAYMENT_OF`),
`created_at`. Optional: if the official contract has no such object, it is not emitted.

## 4. IDs

| Namespace | Entity | Style examples |
|-----------|--------|----------------|
| `JE` | journal entry / line | `JE-000123`, `2026/03/J/0123`, `je_ab12cd` |
| `INV` | invoice | `INV-2026-0042`, `S-0042-26`, `in_9f2e` |
| `CN` | credit note | `CN-2026-0007` |
| `PAY` | payment | `PAY-7F3A91`, `P0007F3A` |
| `BANK` | bank line | `BNK-00012345` |
| `FX` | FX rate row | `FX-2026-03-14-USD-KZT-1` |
| `CP` | counterparty | `CP-00192` |

Rules: unique per table; a raw ID never encodes seed/anomaly/position; insertion of a mutated row
uses the same generator and distribution as a normal row; cross-table references always resolve
or are explicitly `null`.

## 5. Null semantics and forbidden shortcuts

* `null` is meaningful and public: "unknown" or "not applicable". It never means "figure it out".
* No file, field, ordering or timestamp may reveal which rows were inserted: `INV-11`/`INV-12`
  plus the metadata classifier in Phase 12 check this.
* `index_hints.json` (a file that would point at anomalies) is **forbidden** by §8.2 and by
  review; any internal index must be derived purely from `public/` and must not be exposed.
