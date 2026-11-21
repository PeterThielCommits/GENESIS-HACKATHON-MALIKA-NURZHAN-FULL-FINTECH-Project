# Phase 7 — FX И PERIOD CUTOFF OPERATORS

**PARTIAL — Exit Gate 7 not met.** Arena agent; generator owner Zone 1 (A),
contract decisions A0. Master v3.0.0, uploaded copy identical to the tracked
reference (SHA-256 `a46cdb63bb4b41aabb95a842406f5a4fff91e218ead1e4f97b22b60d1c748e36`).
Branch `arena/4e70eb5b-genesis-hackathon-malika-nurzh`; clean start
`fcd618d287c6c7bcbf9c513e54baffccda181744` ([PR #5](https://github.com/PeterThielCommits/GENESIS-HACKATHON-MALIKA-NURZHAN-FULL-FINTECH-Project/pull/5)); implementation `7e87c33`.

| Task | Traceability | Baseline → result / evidence |
|---|---|---|
| 7.1 FX_RATE_MISMATCH | §11.4, REQ-GEN-003, REQ-MONEY-001…003, INV-07/08 | Missing → scoped PASS: policy date/source/fallback, exact quote inversion, once-rounded balanced rebooking, booked versus permitted amount delta |
| 7.2 PERIOD_CUTOFF | §11.5, REQ-GEN-003, REQ-TIME-002, INV-09 | Missing → scoped PASS: replace posting period using another public event, preserve original events and amounts |
| 7.3 Distractors | §11.6 | Missing → PARTIAL: four labeled normalized examples per new operator, no episode-level provenance/tool reachability and no verified payment suite |
| 7.4 Financial and period invariants | REQ-INV-001…003, INV-01/07/08/09/10 | Partial → scoped journal checks PASS; aggregate trial balance and period roll-forward INV-10 not tested without a ledger/aggregate pipeline |
| 7.5 Mixed currency and DST | REQ-INV-005, REQ-TIME-002 | Missing → PASS at fixture level: JPY→KWD, NYC month rollover and fall-back instant, fiscal quarter rollover |
| 7.6 Official affected IDs | §11.4–11.5, A-006, Q-004/Q-006 | BLOCKED: official spec not supplied; journal key in internal signatures is not an official affected_ids mapping |

## Invariant and distractor evidence

`tests/generator/test_phase07.py` uses hand-authored expected periods and
amounts. FX observations: INV-01 stays clean, INV-07 fails, policy benchmark
for INV-08 is 12 KWD minor units vs 20 booked (delta +8). Case facts: last
published quote on weekend, document vs payment date, inverse convention,
half-even rounding. Cutoff observations: INV-01 stays clean, INV-09 fails;
case facts: company-local date, issue before service, delivery-date
recognition, late issue after a DST-fold service instant. The advance and
service-interval examples exercise date selection only, not full advance
accounting or interval allocation. Labels live in tests, not generated records.

The normalized API rejects unbalanced inputs, ambiguous permitted FX amounts,
wrong pair/no-op replacements and same-period moves. It does not change or
claim to implement any frozen wire schema. No release truth records are built.

## Verification

| Command | Exit | Status | Evidence |
|---|---:|---|---|
| Baseline `make verify` | 0 | PASS | 131 tests; `/tmp/tl-baseline` (session-local) |
| `make verify` | 0 | PASS | 136 unit/contract tests incl. 5 Phase 7 methods, 3 properties, import scan, RC-001…003; `/tmp/tl-phase07-verify`, `artifacts/reports/latest/verify_summary.json` |
| `make setup report` | 0 | PASS | Python 3.11.2; `artifacts/reports/latest/report_index.json` |
| `git diff --cached --check` (implementation) | 0 | PASS | no whitespace errors |
| `make docker-check` | — | NOT RUN | Docker executable absent |
| Optional pytest/Hypothesis/jsonschema | — | SKIPPED | absent; stdlib checks ran |

## Exit Gate 7 and handoff

Exact gate: **all four types generate deterministically, are distinguishable
and discoverable.** The two transformations are deterministic on the tested
normalized data (including reordered quote input), with visible distinguishing
facts in fixtures. Four-type episode generation and public-tool discovery are
not verified. The pinned tree has placeholders for the Phase 3 clean generator
and Phase 4 payment operators/diff. Their reported parallel heads still exist
(`9c04f63`, `e740784`), but are not in this tree. Do not import their contract
line without an approved decision. The public environment is not integrated
here either. See [issue #3](https://github.com/PeterThielCommits/GENESIS-HACKATHON-MALIKA-NURZHAN-FULL-FINTECH-Project/issues/3)
and draft CR-06-01. Phase 8 release inputs are not ready. A0 must reconcile
upstream Phase 3–5 and answer the official semantics questions; then Zone 1
can run the four-type matrix, rebuild aggregate period totals, and demonstrate
public evidence reachability before declaring this gate passed.

## Follow-up: aggregate fixture and upstream compatibility audit

`make verify` exited 0 with 137 tests and 3 property tests after adding a
three-journal mixed-currency fixture. Against independently specified policy
recognition totals, the cutoff moves 500 USD minor units out of March and
into April; KZT is unchanged, and trial balance (INV-02) still holds for each
period/currency. This exercises INV-10 on normalized inputs, not published
ledger reports. `git diff --check` exited 0. Session log:
`/tmp/tl-phase07-followup`.

Inspection of Phase 4 head `e740784` confirmed that its generator has a real
`build_episode` pipeline but produces an episode-envelope truth schema
(`truth_version`, `episode_id`, `findings`, `diff_summary`, `distractors`)
where this checkout freezes individual findings (`schema_version`,
`truth_id`, `affected_ids`, `invariant_signature`, etc.). Its pipeline also
imports its branch's canonicalization, error types, and clean-book invariant
runner. A wholesale merge or importing the generator directory would not be
a compatible Phase 7 integration. CR-06-01 still requires A0 disposition;
issue #3 records no organizer approval. A compatible port needs explicit
producer-to-frozen-finding translation and an approved public record/adapter
mapping, not acceptance of the other branch's identically versioned schema.

Prior PR CI passed at `a62d97d`; that result does not close the Phase 7 gate.
PR #6 stays draft and unmerged pending the required external decisions and
four-type evidence described above.
