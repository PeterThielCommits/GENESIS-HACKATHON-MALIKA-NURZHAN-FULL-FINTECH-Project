# TwinLedger contracts v0.1.0 (payload 1.0.0)

Status: **PROVISIONAL**. The organizer contract is not archived in this repository
(`docs/official/MANIFEST.json`), so every external-facing element below is isolated behind
`adapter/` and `configs/`. Nothing here is an organizer fact.

A contract is an executable agreement, not an example: each schema has valid and invalid
fixtures under `contracts/fixtures/` and is validated by `python -m tools.validate_contracts`
(`make verify` check `CT-CONTRACTS-01`). This document is checked against the schemas by
`tests/phase0/test_contract_docs.py` (REQ-CONTRACT-005): a field documented here must exist
there, and vice versa.

## 1. Files

| File | Kind | Purpose |
|------|------|---------|
| `common.defs.json` | definitions | Shared `$defs`: schema version, ID namespaces, money, timestamps, anomaly types, invariant signature |
| `episode_manifest.schema.json` | data | Public manifest of one episode (hashes only) |
| `company.schema.json` | data | Synthetic company identity |
| `policy.schema.json` | data | Accounting policy read by generator and verifier |
| `finding.schema.json` | finding | A submitted audit conclusion |
| `truth.schema.json` | truth | Sealed reference findings |
| `tool_request.schema.json` | protocol | One inspection action |
| `tool_response.schema.json` | protocol | Bounded environment response |
| `trajectory_event.schema.json` | protocol | One hash-chain link |
| `receipt.schema.json` | receipt | Offline-verifiable integrity receipt |
| `verifier_report.schema.json` | verifier | Independent discovery output + ProofGraph |
| `rubric_check.schema.json` | judge | One verification check result |
| `version.json` | metadata | Set version, versioning rules, unknown-field policy |
| `currency.json` | data | Currency exponent registry (configuration, not ISO lookup) |

## 2. Canonical JSON (`tools/canonical_json.py`)

| Rule | Value |
|------|-------|
| Encoding | UTF-8, `ensure_ascii=False` |
| Key order | ascending Unicode code point (`sort_keys=True`) |
| Separators | `separators=("," , ":")` — no insignificant whitespace |
| Line endings | LF |
| Non-finite numbers | `NaN`, `Infinity`, `-Infinity` rejected |
| Floats | rejected (money is integer minor units; rates are decimal strings) |
| `Decimal` | serialized as plain decimal text, never exponent notation |
| Duplicate object keys | rejected when parsing |
| Arrays | order is significant; semantically-set arrays are sorted by the producer |

Two consequences worth stating: `canonical_json(x) == canonical_json(permute_keys(x))` is a
tested property, and no digest in this project may be computed with a plain
`json.dumps` call.

## 3. Identifiers

* Namespaces: `JE`, `INV`, `CN`, `PAY`, `BANK`, `FX`, `CP`. Canonical form `TYPE:raw-id`.
* `raw-id` matches `^[A-Za-z0-9][A-Za-z0-9_./-]*$`, max 64 chars; the namespaced form max 72.
* Canonicalization is Unicode NFC → namespace check → de-duplicate → sort. Prefix stripping
  that could create a collision is forbidden (§15.1).
* An ID never encodes seed, anomaly type, operator index or record position, and the four
  visual styles (`A`…`D`) are applied identically to clean and mutated records.

## 4. Money and time

* Amounts are `integer` minor units, bounded by ±9 007 199 254 740 991 (safe JSON integer).
* Exponents come from `currency.json` (KZT 2, USD 2, EUR 2, GBP 2, CNY 2, RUB 2, TRY 2,
  AED 2, JPY 0, KWD 3). Unknown currency is a bounded error, not a guess.
* Mixed-currency arithmetic is forbidden; conversion is explicit and returns rounding
  metadata.
* Timestamps are ISO-8601 with an explicit offset; the accounting period is computed in the
  company's IANA timezone, never in the machine's local time.

## 5. Findings (`finding.schema.json`)

Required: `schema_version` (const `1.0.0`), `type`, `affected_ids` (1..64 unique namespaced
IDs), `claimed_amount` (integer), `currency`, `evidence_ids` (1..64 unique). Optional:
`explanation` (≤ 2000 chars), `confidence` (0..1). Unknown fields are rejected; extensions
must be `x_twinledger_*`.

`explanation` and `confidence` never influence the base reward (§15.2). `evidence_ids` must
contain at least one complete admissible evidence set and every ID must be reachable through
the public tools.

## 6. Protocol (`tool_request` / `tool_response`)

* Exactly one of five tool shapes may match a request (`oneOf`); an ambiguous request is a
  contract error, not a "best guess".
* Tools: `list_records {table, cursor?, limit? 1..50, filters?}`, `get_record {table, id}`,
  `get_document {doc_id}`, `calc {expression ≤ 512}`, `submit {findings[]}`.
* Tables: `company, policy, accounts, counterparties, journal_entries, invoices,
  credit_notes, payments, bank_lines, fx_rates, opening_balances, period_calendar,
  document_links`.
* Filter keys: `counterparty_id, currency, period, date_from, date_to, status, doc_id,
  account_id, direction, pair, source_document_id`.
* A response is either `{ok: true, result: …}` or `{ok: false, error: {code, message}}`,
  never both. Result shapes: `{rows, next_cursor}`, `{record}`, `{document}`, `{value}`,
  `{accepted}`.
* Error codes are a closed set: `UNKNOWN_TOOL`, `BAD_ARGS`, `BAD_FILTER`, `BAD_CURSOR`,
  `NOT_FOUND`, `BAD_FINDING`, `CALC_ERROR`, `LIMIT`, `TERMINATED`, `ALREADY_SUBMITTED`,
  `INTERNAL`. Messages are bounded (≤ 512 chars) and must not contain stack traces, absolute
  paths, seeds or sealed content.

## 7. Episode manifest (`episode_manifest.schema.json`)

Versioned references (generator, contracts, config hash), per-file `path`/`sha256`/`bytes`,
`public_manifest_hash`, `truth_commitment`, and an optional `salt_ref` **reference** — never
the salt value. Fields that would leak the answer (finding count, mutation count, affected
IDs, clean flag) are forbidden by schema, and `findings_count` is additionally excluded by a
`not` constraint so the intent survives future schema edits.

## 8. Truth (`truth.schema.json`)

Per finding: `truth_id`, `type`, sorted `affected_ids`, `amount_minor`, `currency`,
`tolerance_minor`, `evidence_sets` (1..16 alternatives, each 1..32 IDs),
`evidence_enumeration_complete`, `minimal_evidence_size`, `optimal_steps_model_id`,
`optimal_steps`, `depends_on`, `rounding_ops`, `invariant_signature`, `operator_version`.
Truth lives in `sealed/` with separate permissions and is never mounted into the policy or
environment process.

## 9. Trajectory, receipt, verifier report, rubric check

* `trajectory_event`: `event_index`, `logical_step`, `kind`, `action_digest`,
  `response_digest`, `previous_hash`, `event_hash`. No wall-clock field, so replay is exact.
* `receipt`: code/config/manifest hashes, `truth_commitment`, `trajectory_head`,
  `merkle_leaf_index`, `policy_identifier`, `reward_breakdown_ref`, `verification_status`.
  A receipt proves integrity, never finding quality.
* `verifier_report`: `verified` findings with `evidence_sets`, `proof_graph_ref` and a
  machine-readable `explanation_code`; optional `proof_graph.nodes` with
  `RecordNode/FactNode/RuleNode/CalculationNode/FindingNode`; `unresolved_ambiguities` are
  mandatory output.
* `rubric_check`: `official` is `const: false` — an internal check can never be presented as
  an official rubric item.

## 10. Unknown fields, extensions and versioning

* Default: reject unknown fields (`REQ-CONTRACT-003`).
* Extensions: only keys matching `^x_twinledger_`.
* Major bump: removed field, changed meaning, changed namespace, changed reward semantics.
* Minor bump: optional field, new enum member, new extension namespace.
* Patch: description-only.
* Every behavioral change needs a `docs/CR/` entry plus a `docs/DECISIONS.md` record; the
  contract digest (`python -m tools.validate_contracts --hash`) must change in the same
  commit.

## 11. Fixtures

`contracts/fixtures/index.json` declares every case with `schema`, `file`, `expect`
(`valid`/`invalid`) and, for invalid cases, the exact JSON pointer and keyword that must
fail. Each schema must have at least one valid and one invalid case; the validator fails the
build otherwise, which prevents "schemas that validate nothing".
