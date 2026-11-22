# TwinLedger — Data Dictionary

As-built field reference for the twelve public episode files (TZ §8.2, §8.3).
Every field list below is **checked in both directions** against a real generated
episode by `tools/verify_doc_claims.py::C-DATADICT`: a field documented here that
the data does not contain fails the gate, and so does a real field omitted here.
This document therefore cannot drift from the generator.

## Public episode files (`<episode>/public/`)

`company.json`, `policy.json`, `accounts.json`, `counterparties.jsonl`,
`journal_entries.jsonl`, `invoices.jsonl`, `credit_notes.jsonl`,
`payments.jsonl`, `bank_lines.jsonl`, `fx_rates.jsonl`,
`opening_balances.json`, `period_calendar.json` — twelve files, exactly the
allowlist in `verifier/public_loader.py`. `index_hints.json` is forbidden, and no
dotfiles, symlinks or extra files are permitted inside `public/`.

`company.json`, `policy.json`, `accounts.json`, `opening_balances.json` and
`period_calendar.json` are JSON arrays or objects; the six `*.jsonl` files are
one JSON object per line, and their stored row order is sign-ificant (pagination
cursors page over rows exactly as written, for the paired `P01..P05` checks).

## Tables

- `journal_entries`: `je_id, timestamp, posting_period, source_document_id, description, lines`.
- `lines[]`: `line_id, account_id, debit_minor, credit_minor, currency, fx_rate_decimal, functional_debit_minor, functional_credit_minor, counterparty_id, analytic_tag`.
- `invoices`: `doc_id, counterparty_id, issue_timestamp, service_start, service_end, due_timestamp, currency, total_minor, tax_minor, line_items, status, recognition_rule, subscription_period`.
- `line_items[]`: `description, amount_minor`.
- `credit_notes`: `credit_note_id, invoice_id, counterparty_id, timestamp, amount_minor, currency, reason_code`.
- `payments`: `pay_id, timestamp, counterparty_id, currency, amount_minor, allocations, bank_reference, payment_channel, payment_type, related_payment_id`.
- `allocations[]`: `allocation_id, document_id, amount_minor, allocation_timestamp`.
- `bank_lines`: `bank_line_id, timestamp, amount_minor, currency, direction, reference_text, counterparty_text`.
- `fx_rates`: `fx_id, pair, effective_date, rate_decimal, source_code, publication_timestamp`.
- `accounts`: `account_id, account_type, name, normal_side`.
- `counterparties`: `counterparty_id, name, country, role, aliases`.
- `opening_balances`: `account_id, as_of_date, debit_minor, credit_minor, currency`.
- `period_calendar`: `period_id, start_date, end_date, status`.

Primary keys are unique per table/namespace (REQ-DATA-001). An explicit `null`
means *unknown or inapplicable*, never "guess it" (TZ §8.3). Money is integer
minor units (REQ-DATA-003); timestamps are ISO-8601 with an offset
(REQ-DATA-004). `bank_lines` deliberately carries **no** `matched_payment_id` or
`bank_account_id`: matching is the auditor's inference (*reference_text* plus
amount and date), not a field the generator pre-computes. A pre-computed match
field would be a shortcut the reward would have to defend against.

`company.json` and `policy.json` are configuration objects rather than accounting
tables, so they are described by `contracts/company.schema.json` and
`contracts/policy.schema.json` instead of by a bullet in this list.

### Optional fields (present only on the rows that need them)

Four fields appear on a minority of rows, and only where the row genuinely is
what the field says. They are the machine-readable half of the clean-distractor
catalogue: they exist so the anomaly operators can *exclude* legitimate cases
(a recurring invoice is not a duplicate; a refund is not a duplicate payment),
and so an auditor can too. An absent field means "not applicable", never "false".

| Field | Table | Rows in the reference episode | Meaning |
|---|---|---:|---|
| `recognition_rule` | `invoices` | 1/30 | Revenue-recognition basis when it is not the company default |
| `subscription_period` | `invoices` | 2/30 | Recurring-invoice period: this invoice legitimately repeats |
| `payment_type` | `payments` | 1/20 | Distinguishes `refund` / `standard` where the distinction matters |
| `related_payment_id` | `payments` | 1/20 | The original payment a refund reverses |

`counterparty_id` on a `bank_lines` row is *not* a field: the bank statement
carries `counterparty_text`, free text a real bank would supply. Resolving that
text to a counterparty is audit work, not a pre-computed join.

## IDs

Four families (A: `JE-000123`, B: `2025/05/J/0123`, C: `je_ab12cd`,
D: numeric + check digit) selected per episode by `company.id_style`. No
BUG/DUP/ERROR markers, no sequential "suspicious" blocks, no seed or type
encoding (TZ §8.4). Typed form in findings/truth: `JE:<raw>`, `INV:<raw>`,
`CN:<raw>`, `PAY:<raw>`, `BANK:<raw>`, `FX:<raw>`, `CP:<raw>`.

## Currencies / time

Exponents: KZT/USD/EUR = 2, JPY = 0, KWD = 3 (`contracts/currency.json`).
Timestamps are ISO-8601 with offset; the fiscal period is resolved in the
company's IANA timezone (`company.timezone`), never the host's local time.

## Sealed files (never public)

`truth.json`, `provenance.json`, mutation parameters, the clean twin when it
would reveal the mutation, private seeds, the ProofGraph, hidden labels, and any
salt before reveal. The environment and policy processes load none of them; the
scorer runs only after the environment process exits (TZ §9).
