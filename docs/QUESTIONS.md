# QUESTIONS — open items to the organizers

Every question is machine-checked for completeness (`tests/phase0/test_questions.py`).
Statuses: `OPEN` (asked, no answer), `ANSWERED` (answer quoted with a source),
`WITHDRAWN` (no longer relevant, with reason). A question may only become `ANSWERED`
together with an archived source in `docs/official/` and a decision in `docs/DECISIONS.md`.

Answers must be *written*. A verbal answer at a Q&A session is recorded as
`PROVISIONAL_VERBAL` in `docs/QUESTIONS.md` and is still not official until it appears in a
published document (D-0001).

**Submission deadline / local timezone (task 0.8).** The deadline is not stated in any
document available to this repository. All timestamps in this project are recorded in
UTC and the team operates in Asia/Almaty (UTC+05:00). Owner A0 must confirm the deadline
with the organizers and record it here — until then it is `OPEN-0` below.

---

## OPEN-0 — Submission deadline and timezone

- **Status:** OPEN
- **Asked to:** organizers
- **Date asked:** 2026-11-20
- **Owner:** A0 orchestrator
- **Related assumptions:** —
- **Close condition:** A written deadline (date, time, timezone) is quoted here with its source.
- **Impact if unanswered:** Release planning relies on an assumed buffer; the repository records UTC everywhere and cannot guarantee "in time".
- **Current mitigation:** Work is ordered by `A/B/C` levels so that Level A can be frozen at any moment.

---

## Q-001 — Exact tools, arguments, responses and error semantics

- **Status:** OPEN
- **Asked to:** organizers
- **Date asked:** 2026-11-20
- **Owner:** A0 orchestrator
- **Related assumptions:** A-001
- **Source in master spec:** §14.2, §14.3, Appendix H
- **Close condition:** A published tool list with argument names, types, limits, allowed tables and the error code table.
- **Impact if unanswered:** `adapter/` stays `UNBOUND`; the environment can only be exercised through the internal contract, never against the official harness.
- **Current mitigation:** Tool names, aliases and error codes are configuration (`configs/adapter/compatibility.json`, `contracts/tool_response.schema.json`); no core module branches on an external name.

## Q-002 — Exact reset/step, observation, termination and pagination rules

- **Status:** OPEN
- **Asked to:** organizers
- **Date asked:** 2026-11-20
- **Owner:** A0 orchestrator
- **Related assumptions:** A-004, A-009, A-010
- **Source in master spec:** §14.1, §14.5, §14.8
- **Close condition:** A published environment API description including observation fields, termination, truncation, cursor format and repeated-call behaviour.
- **Impact if unanswered:** Observation shape and cursor semantics are internal-only; an official harness could reject the adapter output.
- **Current mitigation:** `configs/environment/cursor.json` + `configs/environment/limits.json` isolate every numeric and structural choice.

## Q-003 — Exact finding schema, ID rules and array limits

- **Status:** OPEN
- **Asked to:** organizers
- **Date asked:** 2026-11-20
- **Owner:** A0 orchestrator
- **Related assumptions:** A-003
- **Source in master spec:** §15.1, §15.2, Appendix H.3
- **Close condition:** A published finding schema with required/optional fields, ID format, maximum array sizes and unknown-field behaviour.
- **Impact if unanswered:** A policy valid under our contract may be invalid officially, and vice versa.
- **Current mitigation:** `contracts/finding.schema.json` is versioned, fixture-tested and mapped field-by-field in `adapter/`.

## Q-004 — Exact anomaly taxonomy and accounting semantics

- **Status:** OPEN
- **Asked to:** organizers
- **Date asked:** 2026-11-20
- **Owner:** A0 orchestrator
- **Related assumptions:** A-002
- **Source in master spec:** §11
- **Close condition:** A published list of anomaly types with definitions, affected-ID rules and accepted subtypes.
- **Impact if unanswered:** Generator and verifier may implement a taxonomy the official scorer does not use; benchmark results would not transfer.
- **Current mitigation:** `spec/anomaly_catalog.json` is data, versioned and referenced by schema enums; types are never hardcoded in `if/elif` chains in core logic.

## Q-005 — Exact reward formula, match criteria and tolerance

- **Status:** OPEN
- **Asked to:** organizers
- **Date asked:** 2026-11-20
- **Owner:** A0 orchestrator
- **Related assumptions:** A-005, A-006, A-014
- **Source in master spec:** §15.2, §15.5, §9.2
- **Close condition:** A published formula with match rules, tolerance derivation, empty-truth rule and step accounting.
- **Impact if unanswered:** Every reward number and every baseline comparison is provisional; the internal suite can still verify *our* formula, not the official one.
- **Current mitigation:** `configs/scoring/reward.json` + `configs/scoring/tolerance.json`, both `provisional: true`, with an explicit proof obligation per anomaly type.

## Q-006 — Exact affected IDs per anomaly type

- **Status:** OPEN
- **Asked to:** organizers
- **Date asked:** 2026-11-20
- **Owner:** A0 orchestrator
- **Related assumptions:** A-002, A-003
- **Source in master spec:** §11.2–§11.5 ("кандидатный affected_ids" for each type)
- **Close condition:** A published rule per type, e.g. whether the invoice is an affected ID or only evidence.
- **Impact if unanswered:** Exact-ID matching can fail even for a semantically correct finding, collapsing recall to zero.
- **Current mitigation:** The rule is stored as `affected_ids_rule_candidate` per type in `spec/anomaly_catalog.json` and must be re-checked before release.

## Q-007 — Separate scorer process or a fixed harness?

- **Status:** OPEN
- **Asked to:** organizers
- **Date asked:** 2026-11-20
- **Owner:** A0 orchestrator
- **Related assumptions:** A-008
- **Source in master spec:** §16.1, §16.2
- **Close condition:** A published statement whether the organizers run the scoring or accept our harness/receipts.
- **Impact if unanswered:** Isolation evidence may be judged as "self-reported" only.
- **Current mitigation:** `docs/THREAT_MODEL.md` lists the controls we can actually demonstrate; `docs/LIMITATIONS.md` names the rest.

## Q-008 — Submission format: repository, archive, Docker, command, entrypoint?

- **Status:** OPEN
- **Asked to:** organizers
- **Date asked:** 2026-11-20
- **Owner:** A0 orchestrator
- **Related assumptions:** A-012
- **Source in master spec:** §0.4, §22.4
- **Close condition:** A published submission checklist: artifact type, entrypoint command, size limits, allowed files.
- **Impact if unanswered:** The final package may not match what the jury expects (release blocker in §29.6).
- **Current mitigation:** Everything is reachable from `make` targets, and generated data is excluded from Git (D-0008).

## Q-009 — Python version, network, CPU/RAM/disk, allowed dependencies

- **Status:** OPEN
- **Asked to:** organizers
- **Date asked:** 2026-11-20
- **Owner:** A0 orchestrator
- **Related assumptions:** A-011, A-013
- **Source in master spec:** §22.5
- **Close condition:** A published runtime table.
- **Impact if unanswered:** A run that passes locally may exceed the judge limits or use an unavailable package.
- **Current mitigation:** Stdlib-only core, pinned Python 3.11, no network at runtime; targets recorded in `configs/environment/resources.json` and measured later.

## Q-010 — May a sealed reference be included, and how is it protected from the policy?

- **Status:** OPEN
- **Asked to:** organizers
- **Date asked:** 2026-11-20
- **Owner:** A0 orchestrator
- **Related assumptions:** A-015
- **Source in master spec:** §16.1–§16.3, §3 «ДАННЫЕ, КОТОРЫЕ НИКОГДА НЕ ПОПАДАЮТ В PUBLIC»
- **Close condition:** A published statement about sealed data handling and permitted process boundaries.
- **Impact if unanswered:** The commit-reveal and isolation story is our own design, not a verified requirement.
- **Current mitigation:** Sealed paths are excluded from the policy and env working directories (design) and from Git (D-0008); claims are limited to what is enabled (D-0012).

## Q-011 — Are optional packages and vendored wheels allowed?

- **Status:** OPEN
- **Asked to:** organizers
- **Date asked:** 2026-11-20
- **Owner:** A0 orchestrator
- **Related assumptions:** A-013
- **Source in master spec:** §22.2, §22.3
- **Close condition:** A published list of allowed packages or an explicit "stdlib only".
- **Impact if unanswered:** Property-based tests may be reported as `SKIPPED` rather than passing.
- **Current mitigation:** Optional extras are declared but never imported by mandatory code; stdlib fallbacks are implemented for every critical property.

## Q-012 — What exactly do the official rubric checks verify?

- **Status:** OPEN
- **Asked to:** organizers
- **Date asked:** 2026-11-20
- **Owner:** A0 orchestrator
- **Related assumptions:** A-016
- **Source in master spec:** §0.3, §23.4
- **Close condition:** The official rubric with per-check descriptions and weights, archived with a hash.
- **Impact if unanswered:** Effort may be misallocated; the project can only report an internal pass rate (D-0002).
- **Current mitigation:** `judge/rubric_map.json` is intentionally *internal*: `official_rubric_available: false`, every check `official: false`.

## Q-013 — When is reward returned: every step, at submit, or after finalize?

- **Status:** OPEN
- **Asked to:** organizers
- **Date asked:** 2026-11-20
- **Owner:** A0 orchestrator
- **Related assumptions:** A-007, A-008
- **Source in master spec:** §14.9, §15
- **Close condition:** A published statement on reward visibility and scoring time.
- **Impact if unanswered:** Closed-mode behaviour and the truncated-episode rule stay provisional.
- **Current mitigation:** `configs/environment/mode.json` hides reward in `CLOSED_EVAL` by default and restricts `info` to two fields.

## Q-014 — Gymnasium-native API or compatibility only?

- **Status:** OPEN
- **Asked to:** organizers
- **Date asked:** 2026-11-20
- **Owner:** A0 orchestrator
- **Related assumptions:** A-001
- **Source in master spec:** §1.1, §21.8
- **Close condition:** A published statement whether a Gymnasium adapter is required for submission.
- **Impact if unanswered:** An optional adapter that is cheap to add stays optional, and is marked `SKIPPED` in reports if gymnasium is absent.
- **Current mitigation:** The internal `reset`/`step` contract is Gymnasium-shaped (observation/reward/terminated/truncated/info) without importing gymnasium.

---

## Question lifecycle rules

1. A question may only be `ANSWERED` with a quoted source and an archived file hash.
2. An answered question that contradicts an assumption turns that assumption into
   `MODIFIED` (or `CONFIRMED`), never into a silent code change: a CR is opened first.
3. `WITHDRAWN` requires a reason and an owner; it never removes the historical record.
4. New questions get the next free number; numbers are never reused.
