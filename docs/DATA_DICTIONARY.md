# TwinLedger — Data Dictionary (Phase 1)

## Public episode files (planned, TZ 8.2)

`company.json`, `policy.json`, `accounts.json`, `counterparties.jsonl`,
`journal_entries.jsonl`, `invoices.jsonl`, `credit_notes.jsonl`,
`payments.jsonl`, `bank_lines.jsonl`, `fx_rates.jsonl`,
`opening_balances.json`, `period_calendar.json`.
`index_hints.json` is forbidden. No hidden files/metadata in `public/`.

## Tables (internal normalised model, TZ 8.3)

- `journal_entries`: `je_id, timestamp, posting_period,
  source_document_id|null, description, lines[]`.
- `lines[]`: `line_id, account_id, debit_minor, credit_minor, currency,
  fx_rate_decimal, functional_debit_minor, functional_credit_minor,
  counterparty_id|null, analytic_tag|null`.
- `invoices`: `doc_id, counterparty_id, issue_timestamp, service_start,
  service_end|null, due_timestamp, currency, total_minor, tax_minor|null,
  line_items[], status`.
- `credit_notes`: `credit_note_id, invoice_id, counterparty_id,
  timestamp, amount_minor, currency, reason_code`.
- `payments`: `pay_id, timestamp, counterparty_id, currency,
  amount_minor, allocations[], bank_reference|null, payment_channel`.
- `allocations[]`: `allocation_id, document_id, amount_minor,
  allocation_timestamp`.
- `bank_lines`: `bank_line_id, timestamp, amount_minor, currency,
  direction, reference_text, matched_payment_id|null, bank_account_id`.
- `fx_rates`: `pair, effective_date, rate_decimal, source_code,
  publication_timestamp|null`.

Primary keys unique per table/namespace (REQ-DATA-001). Explicit `null`
means unknown/inapplicable, never "guess it" (TZ 8.3). Money = integer
minor units (REQ-DATA-003). Timestamps = ISO-8601 with offset
(REQ-DATA-004).

## IDs

Four families (A: `JE-000123`, B: `2025/05/J/0123`, C: `je_ab12cd`,
D: numeric + check digit). No BUG/DUP/ERROR markers, no sequential
"suspicious" blocks, no seed/type encoding (TZ 8.4). Typed form in
findings/truth: `JE:<raw>`, `INV:<raw>`, `CN:<raw>`, `PAY:<raw>`,
`BANK:<raw>`, `FX:<raw>`, `CP:<raw>`.

## Currencies / time

Exponents: KZT/USD/EUR=2, JPY=0, KWD=3 (`contracts/currency.json`).
Timestamps ISO-8601 + offset; period in company timezone (IANA).

## Sealed files (never public)

`truth.json`, `provenance.json`, mutation params, clean twin (if
revealing), private seeds, ProofGraph, hidden labels, salt pre-reveal.
