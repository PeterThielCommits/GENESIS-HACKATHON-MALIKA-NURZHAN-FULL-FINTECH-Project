# TwinLedger Independent Verifier Algorithm Specification (Frozen v1.0.0)

- **Spec version**: `1.0.0`
- **Status**: FROZEN for Phase 8 (provisional where official organizer rules Q-004/Q-006 remain OPEN; see `docs/DECISIONS.md` D-08-01)
- **Zone / Owner**: Zone 3 (Verification), Owner C
- **Independence guarantee (REQ-ORG-001..005, REQ-VER-001, REQ-VER-002)**:
  This specification was authored exclusively from frozen `contracts/` v1.0.0,
  normative `spec/` files (`accounting_rules.md`, `anomaly_catalog.yaml`,
  `invariants.yaml`, `policy_semantics.md`), `docs/DATA_DICTIONARY.md`, and
  Master TZ v3.0.0 sections 8, 9, 11, 12, and 13 — **without reading any
  generator code in `gen/`**.

---

## 1. Trust Boundary & Input Contract

### 1.1 Allowed Inputs (Stage 1: Discovery)
The verifier discovery stage (`verifier.discover`) accepts ONLY:
1. A public episode directory (`public/`) or an equivalent in-memory
   `PublicEpisode` containing only the allowlisted public files (TZ §8.2):
   - Required: `company.json`, `policy.json`
   - Standard tables (defaulting to empty when absent):
     `accounts.json`, `counterparties.jsonl`, `journal_entries.jsonl`,
     `invoices.jsonl`, `credit_notes.jsonl`, `payments.jsonl`,
     `bank_lines.jsonl`, `fx_rates.jsonl`, `opening_balances.json`,
     `period_calendar.json`, `document_links.jsonl`
2. A deterministic `VerifierConfig` (e.g., `run_ablation`, `max_evidence_sets`).

### 1.2 Forbidden Inputs & Paths
- `verifier/` MUST NOT import `gen/` (REQ-VER-002) or any generator helper.
- To eliminate common-mode calculation bugs (TZ §9.3, §12.4), `verifier/`
  MUST NOT import `core/` or `invariants/` or `scoring/`; it depends ONLY on
  `contracts/` (schemas, currency exponent registry JSON, canonical JSON) and
  Python 3.11 stdlib.
- Discovery MUST NOT read files outside `public/`, dotfiles/hidden files,
  symlinks escaping `public/`, `index_hints.json` (forbidden by TZ §8.2),
  or any private/non-public artifact (REQ-VER-001, REQ-ARC-007).

### 1.3 Canonical Public Hash & Typed IDs
- `company.json` and `policy.json` are validated against
  `contracts/company.schema.json` and `contracts/policy.schema.json`.
- `episode_public_hash` is `SHA-256` of the canonical JSON bytes of the sorted
  `(filename, parsed_content)` mapping of all examined public files.
- Every subject record receives a typed ID matching
  `^(JE|INV|CN|PAY|BANK|FX|CP):[A-Za-z0-9._/-]+$`:
  - `journal_entries`: `JE:<je_id>`
  - `invoices`: `INV:<doc_id>`
  - `credit_notes`: `CN:<credit_note_id>`
  - `payments`: `PAY:<pay_id>`
  - `bank_lines`: `BANK:<bank_line_id>`
  - `counterparties`: `CP:<counterparty_id>`
  - `fx_rates`: `FX:<fx_id>` if `fx_id`/`rate_id` is present, else deterministic
    `FX:<pair>/<effective_date>/<source_code>`.

---

## 2. Independent Money, FX & Time Primitives

### 2.1 Money & Exact Rational FX Conversion
- Stored amounts MUST be Python `int` minor units (never `bool` or `float`,
  REQ-MONEY-001).
- FX rates MUST be positive fixed-point decimal strings matching
  `^[0-9]{1,24}(?:\.[0-9]{1,24})?$` (REQ-MONEY-002).
- Exponents come from `contracts/currency.json` (KZT/USD/EUR=2, JPY=0, KWD=3).
- Conversion from `source_currency` (`F`) to `target_currency` (`B`) uses exact
  rational arithmetic (`fractions.Fraction`) with ONE final integer rounding
  step according to `policy.rounding_mode` (`half_even` or `half_up`):
  - Pair orientation `BASE/QUOTE` means `QUOTE` major units per 1 `BASE` major unit:
    - If `pair == f"{F}/{B}"` (direct):
      `exact_minor = Fraction(amount_minor) * Fraction(rate) * Fraction(10**exp_B, 10**exp_F)`
    - If `pair == f"{B}/{F}"` (inverse pair):
      `exact_minor = Fraction(amount_minor) * Fraction(10**exp_B, 10**exp_F) / Fraction(rate)`
  - Half-way ties (`2 * rem == den`):
    - `half_up`: round away from zero (`q + 1`)
    - `half_even`: round to even (`q + (q & 1)`)

### 2.2 Company-Timezone Date & Fiscal Period
- Never use host local timezone or wall-clock time (REQ-TIME-005).
- ISO-8601 timestamps MUST contain an explicit UTC offset (REQ-TIME-001).
- Date-only strings `YYYY-MM-DD` represent company business dates directly.
- Full timestamps are converted via `zoneinfo.ZoneInfo(company.timezone)` to
  company-local calendar dates (handles DST spring-forward and fall-back).
- Fiscal period computation from `company.fiscal_year_start` (month-aligned) and
  `company.fiscal_period_rule`:
  - `monthly`: `YYYY-MM`
  - `quarterly`: `<FY>-Q<1..4>`, where `FY = year if month >= fy_start.month else year - 1`
    and `Q = ((month - fy_start.month) % 12) // 3 + 1`.
  - If `period_calendar.json` defines explicit `[start_date, end_date] -> period_id`
    ranges covering the local date, the verifier cross-checks and uses that
    calendar mapping.

---

## 3. Independent Anomaly Discovery Algorithms

### 3.1 `DUPLICATE_PAYMENT`
- **Goal**: Identify invoices paid more than once beyond net payable obligation
  without an explaining credit note, refund, reversal, or void event.
- **Algorithm**:
  1. Index all invoices by `doc_id`, credit notes by `invoice_id`, journal
     entries by `source_document_id`, and bank lines by `matched_payment_id`.
  2. Partition credit notes per invoice into:
     - **obligation-reducing credit notes** (normal commercial credit notes:
       e.g., `price_adjustment`, `return`, `discount`, `commercial_credit`, or
       any code not in the overpayment-offset set), reducing
       `net_payable = max(0, invoice.total_minor - sum(reducing_cns))`;
     - **overpayment-offsetting credit notes** (`reason_code` in
       `{"overpayment_credit", "duplicate_reversal", "duplicate_credit",
       "refund_credit", "credit_adjustment"}` when allocated payments exceed
       `invoice.total_minor`), which offset an overpayment (`D-DUP-01`).
  3. Identify reversal/refund payments (`payment_type` in `{"refund", "reversal",
     "void"}` or `amount_minor < 0` or negative allocations) and cancel their
     referenced payment or reduce net allocated amount (`D-DUP-04`).
  4. Consider only positive, non-reversed payments whose own allocations are
     currency-matching and counterparty-matching and do not violate INV-15
     over-allocation (`sum(allocations) <= payment.amount_minor`, so single-payment
     over-allocation is isolated to `PARTIAL_PAYMENT_ALLOCATION`).
  5. For each invoice with `>= 2` distinct positive non-reversed payments:
     - Sort those payments chronologically by `(parse_iso_instant(timestamp), pay_id)`.
     - Accumulate `cumulative_allocated`. Net effective total after offsetting
       credit notes/refunds is `effective_allocated = cumulative_allocated - offsets`.
     - If `effective_allocated <= net_payable`: NO anomaly; emit ProofGraph
       `contradicts`/`excludes` nodes for the offsetting credit note (`D-DUP-01`)
       or refund/reversal (`D-DUP-04`).
     - Otherwise, walk payments chronologically; any payment `dup_pay` whose
       allocation pushes cumulative net-of-offsets above `net_payable` is a
       `DUPLICATE_PAYMENT` finding:
       - `claimed_amount_minor = min(alloc_on_inv, excess_above_net_payable)`
       - `currency = invoice.currency`
       - `affected_ids`: sorted `[PAY:<dup_pay.pay_id>] + [JE:<je_id> ...]` for
         all JEs with `source_document_id == dup_pay.pay_id` (provisional rule
         per `spec/anomaly_catalog.yaml`).
       - Candidate evidence sets: `INV:<doc_id>`, `PAY:<dup_pay.pay_id>`,
         `JE:<dup_je_id>...`, any reducing `CN:<cn_id>` needed for `net_payable`,
         plus minimal subsets of prior payments on `INV:<doc_id>` whose sum
         together with `dup_pay` exceeds `net_payable` (naturally producing
         alternative minimal evidence sets when multiple prior payments exist!).
  6. **Distractor exclusions recorded in ProofGraph**:
     - `D-DUP-01`: Credit note / credit adjustment explaining the difference.
     - `D-DUP-02`: Same amount paid to two different invoices of the same
       counterparty.
     - `D-DUP-03`: Recurring subscription payments for different service periods
       (same counterparty and amount, distinct invoices with distinct
       `service_start`/`service_end`).
     - `D-DUP-04`: Valid refund/reversal/void offsetting the duplicate transfer.

### 3.2 `PARTIAL_PAYMENT_ALLOCATION`
- **Goal**: Detect payments whose allocations violate conservation, policy
  rules, counterparty/currency integrity, or leave an invoice prematurely marked
  `"paid"` with unpaid balance.
- **Algorithm**:
  1. For each positive, non-reversed payment `P`:
     - Let `alloc_total = sum(a.amount_minor for a in P.allocations)`.
     - **Case A (Over-allocation, INV-15)**: `alloc_total > P.amount_minor` or
       any `a.amount_minor < 0`:
       - `claimed_amount_minor = alloc_total - P.amount_minor` (or `abs(neg)`).
       - `affected_ids = sorted([PAY:<P.pay_id>] + [INV:<a.document_id> ...])`.
     - **Case B (Unallocated balance without advance policy)**:
       `alloc_total < P.amount_minor`:
       - If `policy.allocation_policy.allow_advances is True`: valid advance
         (`D-PART-02`); record `excludes` in ProofGraph with `RuleNode`.
       - Else: finding with `claimed_amount_minor = P.amount_minor - alloc_total`,
         `affected_ids = sorted([PAY:<P.pay_id>] + [INV:<a.document_id> ...])`.
     - **Case C (Disallowed multi-invoice split)**:
       Distinct allocated `document_id` count `>= 2`:
       - If `policy.allocation_policy.allow_multi_invoice_split is True` and
         conservation holds: valid split (`D-PART-03`); record `excludes` in
         ProofGraph with `RuleNode`.
       - Else: finding with `claimed_amount_minor = alloc_total`,
         `affected_ids = sorted([PAY:<P.pay_id>] + [INV:<doc_id> ...])`.
     - **Case D (Wrong-counterparty or wrong-currency allocation)**:
       For each allocation `a` to invoice `I`:
       - If `I.counterparty_id != P.counterparty_id` or `I.currency != P.currency`:
         finding with `claimed_amount_minor = a.amount_minor`,
         `currency = P.currency`, `affected_ids = sorted([PAY:<P.pay_id>, INV:<I.doc_id>])`.
  2. For each invoice `I` (INV-04, INV-17):
     - Compute `net_payable = max(0, I.total_minor - sum(reducing_cns))` and
       `net_allocated = sum(valid_allocations_on_I) - sum(refund_offsets_on_I)`.
     - If `I.status == "paid"` and `0 < net_allocated < net_payable`:
       - Premature closure on partial payment!
       - `claimed_amount_minor = net_payable - net_allocated`,
         `currency = I.currency`,
         `affected_ids = sorted([INV:<I.doc_id>] + [PAY:<p.pay_id> ...])`.
     - **Distractor exclusions recorded in ProofGraph**:
       - `D-PART-01`: Multiple partial payments whose sum closes the invoice
         (`net_allocated == net_payable`, `status == "paid"`).
       - `D-PART-02`: Valid unallocated advance when `allow_advances == True`.
       - `D-PART-03`: Valid multi-invoice split when `allow_multi_invoice_split == True`.
       - `D-PART-04`: Partial credit note / partial refund closing the remaining
         invoice balance (`net_allocated == net_payable`, `status == "paid"`).

### 3.3 `FX_RATE_MISMATCH`
- **Goal**: Independently select the policy-permitted FX rate(s) for each
  foreign-currency journal entry, recalculate functional amounts with exact
  rational arithmetic and single rounding, and detect mismatches.
- **Algorithm**:
  1. Let `B = company.functional_currency`, `fxp = policy.fx_policy`,
     `rmode = policy.rounding_mode`.
  2. For each journal entry `JE` containing any line with `line.currency != B`:
     - Determine `target_date` and `date_source_id` (if a source document was
       required) strictly from `fxp.rate_date_rule`:
       - `document_date`: linked invoice `issue_timestamp` (or credit note
         `timestamp`; or if JE links to a payment allocated to 1 invoice, that
         invoice's `issue_timestamp`; if payment allocates to >1 invoices with
         different issue dates -> record unresolved ambiguity).
       - `operation_date`: `je.timestamp`.
       - `payment_date`: linked payment `timestamp` (if JE links to a payment;
         or if JE links to an invoice with 1 linked payment, that payment's
         `timestamp`; if >1 payments with different dates -> record ambiguity).
     - Select permitted quotes from `fx_rates.jsonl`:
       - `row.source_code in fxp.source_codes`
       - `row.pair in {f"{F}/{B}", f"{B}/{F}"}`
       - If `fallback_rule == "none"`: `effective_date == target_date`.
       - If `fallback_rule == "last_available"`: `effective_date <= target_date`,
         take maximal `effective_date` (`D-FX-01`).
     - If no permitted quote exists: append deterministic entry to
       `unresolved_ambiguities` and skip emitting a finding (REQ-VER-005).
     - For every permitted quote on the selected date, recalculate every foreign
       line's expected functional minor amount using Section 2.1 (handles
       inverse pair `D-FX-03` and exact rounding `D-FX-04`).
     - If two permitted quotes on the selected date yield DIFFERENT expected
       functional amounts for any line: append to `unresolved_ambiguities` and
       do not guess (REQ-VER-005).
     - Compute one-sided misstatement across foreign lines:
       `debit_diff = abs(sum(booked_func_debit) - sum(expected_func_debit))`
       `credit_diff = abs(sum(booked_func_credit) - sum(expected_func_credit))`
       `misstatement = max(debit_diff, credit_diff)`.
     - If `misstatement == 0`: NO anomaly; emit ProofGraph `excludes` nodes for
       weekend fallback (`D-FX-01`), document-vs-payment date (`D-FX-02`),
       inverse quote (`D-FX-03`), or policy rounding boundary (`D-FX-04`).
     - If `misstatement > 0`: emit `FX_RATE_MISMATCH`:
       - `affected_ids = [JE:<je.je_id>]` (provisional rule per `spec/anomaly_catalog.yaml`)
       - `claimed_amount_minor = misstatement`
       - `currency = B`
       - Candidate evidence sets: one set per permitted quote on the selected
         date: `[JE:<je.je_id>, FX:<fx_id>]` + (`[date_source_id]` if the
         date rule required a linked document whose date differs or is needed).

### 3.4 `PERIOD_CUTOFF`
- **Goal**: Verify that each recognition journal entry's `posting_period`
  matches the company-timezone fiscal period of the policy's recognition event.
- **Algorithm**:
  1. Read `cutoff_policy.recognition_event` (`service_date` | `issue_date` |
     `delivery_date`) and `company.timezone`, `company.fiscal_year_start`,
     `company.fiscal_period_rule`.
  2. For each journal entry `JE` linked to an `invoice` (`source_document_id`
     resolves to `INV:<doc_id>`):
     - **Prepayment / advance exclusion (`D-CUT-02`)**: If all non-cash/non-AP
       recognition lines post to an account with `account_type` in
       `{"prepayment", "advance", "deferred_revenue", "deferred_expense"}` or
       carry `analytic_tag` in `{"prepayment", "advance", "deferred"}`, exclude
       as a valid prepayment (`D-CUT-02`) with explicit ProofGraph `excludes` node.
     - Determine recognition event timestamp/date:
       - `service_date`: `invoice.service_start` (or `invoice.service_end` if
         `invoice.recognition_rule == "service_end"`).
       - `issue_date`: `invoice.issue_timestamp`.
       - `delivery_date`: `invoice.delivery_timestamp` (fallback to
         `invoice.service_end` if explicitly present; if absent -> record
         unresolved ambiguity).
     - **Service interval exclusion (`D-CUT-03`)**: If `invoice.service_end` is
       non-null and spans across periods (`P_start != P_end`):
       - If `invoice.recognition_rule == "pro_rata"` and `P_start <= je.posting_period <= P_end`:
         exclude as valid interval recognition (`D-CUT-03`) in ProofGraph.
       - If `invoice.recognition_rule == "service_end"` and `je.posting_period == P_end`:
         exclude as valid completion recognition (`D-CUT-03`) in ProofGraph.
     - Compute `expected_period` in `company.timezone` (Section 2.2).
     - If `je.posting_period == expected_period`: NO anomaly; emit ProofGraph
       `excludes` nodes when UTC period differs from company-local period
       (`D-CUT-01`), or when `issue_timestamp` period differs from
       `service_start` period (`D-CUT-04`).
     - If `je.posting_period != expected_period`: emit `PERIOD_CUTOFF`:
       - `affected_ids = [JE:<je.je_id>]` (provisional rule per `spec/anomaly_catalog.yaml`)
       - `claimed_amount_minor = sum(line.functional_debit_minor for line in je.lines)`
       - `currency = company.functional_currency`
       - Candidate evidence set: `[INV:<doc_id>, JE:<je.je_id>]`.

---

## 4. ProofGraph DAG Semantics (TZ §13.4, §21.1, §21.4)

- Node types: `RecordNode`, `FactNode`, `RuleNode`, `CalculationNode`, `FindingNode`.
- Edge types: `derived_from`, `supports`, `contradicts`, `governed_by`, `excludes`.
- Required node fields: `node_id`, `node_type`, `source_ids`, `rule_id`,
  `value_digest` (64-hex SHA-256), `parent_node_ids`.
- Deterministic sorting: nodes sorted by `node_id`; edges sorted by
  `(from_node_id, to_node_id, edge_type)`.
- Graph invariants:
  1. Strict DAG (zero cycles).
  2. Every `FindingNode` has directed paths from >=1 `RecordNode` and >=1 `RuleNode`.
  3. Every `FactNode` has non-empty `source_ids` and `rule_id`.
  4. Every distractor exclusion records a `contradicts` or `excludes` edge from
     the distinguishing public `RecordNode`/`FactNode`/`RuleNode`.

---

## 5. Evidence Reachability, Minimality & Ablation (TZ §13.5, §21.3)

- **Background context** (always available, never occupies `evidence_ids` slots):
  `company.json`, `policy.json`, `accounts.json`, `opening_balances.json`,
  `period_calendar.json`.
- **Subject evidence records**: typed IDs in `JE`, `INV`, `CN`, `PAY`, `BANK`,
  `FX`, `CP` reachable via public tools (`list_records`, `get_record`,
  `get_document`).
- **Sufficiency**: Re-running discovery on `subset_episode(episode, S)` derives
  the exact same finding `(type, affected_ids, claimed_amount_minor, currency)`.
- **Minimality (Ablation)**: For every `e in S`, re-running discovery on
  `subset_episode(episode, S - {e})` FAILS to derive that exact finding.
- **Enumeration cap**: Up to `MAX_EVIDENCE_SETS = 32` minimal sets per finding
  (each with `1 <= len(S) <= min(policy.max_evidence_ids, 20)`). If truncated,
  `evidence_enumeration_complete = False`; otherwise `True`.

---

## 6. Stage-2 Independent Crosscheck (`scoring/crosscheck.py`, TZ §13.2, §13.7)

- Stage 2 is strictly separate from Stage 1 discovery.
- Input `verifier_report` MUST be validated against
  `contracts/verifier_report.schema.json` and its canonical SHA-256 digest
  verified BEFORE comparison to truth findings (REQ-ORG-003).
- Matching delegates to `scoring.matcher.optimal_matching` (REQ-SCORE-001).
- Any mismatch (`fp > 0`, `fn > 0`), insufficient evidence, failed ablation, or
  `unresolved_ambiguities` sets `release_blocked = True` (REQ-VER-020).
