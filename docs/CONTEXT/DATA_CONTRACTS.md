# Data Contracts — episodes, public/sealed split, schemas

**Code:** `contracts/book_model.py`, `contracts/models.py`, `gen/serialize.py`
**Tests:** `tests/contracts/test_schemas.py` (24), `tests/integration/test_serialize.py` (16),
`tests/security/test_sealed_boundary.py` (13)

---

## 1. Episode on disk

```
<root>/<episode_id>/
    public/                     exactly 12 files — the only thing a solver may read
    sealed/                     truth.json, provenance.json,
                                verifier_crosscheck.json, reject_log.json
    manifest.json               public commitment + file hashes
    verifier_report.json        generator-side validation summary (public-safe)
```

* `episode_id` = `EP-{difficulty}-{16 hex}`, derived from `(master_seed, config_hash, difficulty)`.
* Writes are staged in a temp directory and moved into place with `rename`, so a reader never
  sees a partial episode.
* Re-writing the same package is idempotent. Re-writing a **different** package into an
  existing directory is refused (`ContractError`) instead of silently mixing two episodes.

## 2. Public files (frozen set — 12)

| File | Source | Notes |
|---|---|---|
| `company.json` | `Book.company` | id, legal names (kk/ru/en), timezone, functional currency |
| `policy.json` | `Book.policy` | recognition rule, FX basis, allocation rule, credit-note cap, account roles |
| `accounts.jsonl` | `Book.accounts` | chart of accounts, `currency_scope` |
| `counterparties.jsonl` | `Book.counterparties` | synthetic customers/suppliers |
| `journal_entries.jsonl` | `Book.journal_entries` | header + embedded `lines` |
| `invoices.jsonl` | `Book.invoices` | header + embedded `line_items`, `status` |
| `credit_notes.jsonl` | `Book.credit_notes` | adjustments against invoices |
| `payments.jsonl` | `Book.payments` | header + embedded `allocations` |
| `bank_lines.jsonl` | `Book.bank_lines` | bank statement, optional payment match |
| `fx_rates.jsonl` | `Book.fx_rates` | synthetic rate timeline per pair/day |
| `opening_balances.json` | `Book.opening_balances` | single JSON object |
| `period_calendar.json` | `Book.period_calendar` | rule, fiscal start, periods, ambiguity policy |

Ordering is fixed by `PUBLIC_FILE_ORDER`; JSONL rows are canonically sorted; JSON files are
canonical (sorted keys, LF only, `ensure_ascii=False`, no floats, no `Decimal`).

## 3. Manifest (`manifest.json`)

Public-safe by construction. Verified by `test_manifest_hides_private_facts`.

| Field | Contents |
|---|---|
| `manifest_version`, `episode_id`, `difficulty` | identity |
| `contract_version`, `generator_version`, `config_hash` | reproducibility |
| `schema_versions` | name → version for every frozen schema |
| `public_files` | per file: `name`, `sha256`, `bytes`, `rows` |
| `public_digest` | digest over the per-file hashes |
| `commitment` | `{algorithm: "sha256(salt||truth_digest)", commitment_hex}` |
| `table_counts` | row counts per book table |
| `timezone`, `functional_currency`, `created_at_utc` | context |
| `canary_scan` | `{scan_version, public_hits: 0}` — the *result*, never a token |

**Never present:** finding count, anomaly type, operator id, subtype, affected ids, seed,
distractor ids, provenance.

## 4. Sealed truth (`sealed/truth.json`)

| Field | Contents |
|---|---|
| `truth_version`, `episode_id`, `mode` | `CLEAN` or `ANOMALOUS` |
| `findings[]` | see below |
| `diff_summary` | added / modified / removed counts |
| `distractors[]` | `distractor_id`, `distractor_of`, `distinguishing_fact`, `public_evidence_ids` |

Each finding:

| Field | Meaning |
|---|---|
| `truth_id` | stable id within the episode |
| `type` | anomaly family |
| `affected_ids` | canonically sorted ids the answer must implicate |
| `amount_minor`, `currency`, `tolerance_minor` | the quantified claim (minor units, exact) |
| `evidence_sets[]` | each an alternative sufficient public-evidence set |
| `minimal_evidence_size` | size of the smallest sufficient set |
| `invariant_signature` | observed violation signature (`invariant_id`, key, delta, direction…) |
| `operator_version` | generator-side provenance of the mutation |
| `depends_on` | ids the finding logically depends on |
| `optimal_steps_model_id` | `query_plan_v1` |
| `optimal_steps` | `null` in Phase 4 (query-plan phase fills it) |

## 5. Sealed provenance (`sealed/provenance.json`)

`provenance_version`, `episode_id`, `master_seed_digest`, `base_config_hash`,
`clean_public_digest`, `mutated_public_digest`, `operator_applications[]`
(`params`, `affected_ids`, `pre_state_digest`, `post_state_digest`, `status`), `canaries`,
`reject_stats`, `distractors`, `diff_summary`, `signature_decisions`, `attempt_index`.

This is the audit trail: it can replay exactly how the mutated twin was built.

## 6. Frozen schemas (16)

`contracts/version.json` declares the contract and every schema version
(`contract_version: 1.0.0`, `status: FROZEN_FOR_MVP`).

`episode_manifest`, `company`, `policy`, `book`, `finding`, `truth`, `provenance`,
`tool_request`, `tool_response`, `trajectory_event`, `receipt`, `verifier_report`,
`invariant_signature`, `rubric_check`, `anomaly_catalog`, `period_calendar`.

The validator (`contracts/jsonschema_subset.py`) implements only the keywords these documents
use and **raises on unsupported keywords** rather than ignoring them — a schema that cannot be
enforced is a bug, not a default.

## 7. Money and time in the contract

* Money is **integer minor units**, always. Rates and quantities are `Decimal` parsed from
  **strings**. Floats are rejected by the canonical serialiser, by the row decoder and by
  INV-13.
* Currency exponents come from `contracts/currency.json` (KZT/USD/EUR = 2, JPY = 0, KWD = 3).
* Every timestamp is ISO-8601 **with an explicit offset**; company-local reasoning uses
  `zoneinfo` with a documented DST ambiguity policy (`prefer_earlier` by default).

## 8. Changing the contract

An incompatible change requires:

1. A version bump in `contracts/version.json` (major for breaking shape changes).
2. A decision entry in `docs/DECISIONS.md`.
3. Updated schema tests (valid fixture passes, malformed fixture fails).
4. `python3 tools/export_context.py` to refresh `docs/CONTEXT/PROJECT_CONTEXT.json`.
5. `make verify` — the sweep will show whether existing seeds still produce valid episodes.
