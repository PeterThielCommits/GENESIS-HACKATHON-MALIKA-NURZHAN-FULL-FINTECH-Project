# TwinLedger Policy Semantics (normative, Phase 1 skeleton)

`policy.json` (see `contracts/policy.schema.json`) declares:

- `rounding_mode`: `half_even` | `half_up` (REQ-MONEY-003).
- `fx_policy.rate_date_rule`: `document_date` | `operation_date` | `payment_date`.
- `fx_policy.fallback_rule`: `last_available` | `none` (weekends/holidays).
- `fx_policy.source_codes`: allowed FX sources.
- `fx_policy.quote_convention`: `foreign_per_functional` | `functional_per_foreign`.
- `cutoff_policy.recognition_event`: `service_date` | `issue_date` | `delivery_date`.
- `cutoff_policy.timezone_source`: `company` (always; REQ-TIME-002).
- `allocation_policy.allow_advances` / `allow_multi_invoice_split`.
- `credit_note_cap_minor`: policy-defined cap (INV-16).
- Budget: `max_steps`, `max_page_size`, `max_findings`, `max_evidence_ids`, `eta`.

All numeric parameters are validated; hidden defaults are forbidden for
parameters affecting data, reward, budget or determinism (TZ 7.4).
