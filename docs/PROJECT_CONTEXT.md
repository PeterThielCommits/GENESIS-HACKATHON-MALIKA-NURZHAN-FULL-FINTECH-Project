# PROJECT_CONTEXT — everything a new agent needs

Read order (master spec Appendix F.1): `AGENTS.md` → this file → `docs/CURRENT_STATE.md` →
`docs/STATUS.md` → `docs/DECISIONS.md` → `docs/QUESTIONS.md` → relevant `contracts/` →
relevant code → latest phase report → latest handoff → linked issue.

If something below is not true in the repository, the repository wins and this file must be
fixed in the same change.

## 1. Mission

TwinLedger is a **reproducible, synthetic benchmark environment for AI accounting
auditors**. Each episode is a fictional company with invoices, payments, bank lines, journal
entries, FX rates, an accounting policy and documents. Some episodes are perfectly clean;
others contain one or more controlled accounting anomalies. An agent explores only the
public records through a small set of read-only tools and submits structured findings.

The product is not "an audit tool". It is a **trustworthy environment + a sealed evaluator**,
with a defensible answer to the question: *how do you know the ground truth is right?*

Answer implemented by design:

1. a clean book is generated (`clean twin`),
2. explicit, versioned mutation operators are applied (`mutated twin`),
3. the candidate truth is computed from the **diff** between the twins,
4. an **independent verifier** re-derives the anomalies from public data only,
5. every accepted finding carries an **evidence certificate** (ProofGraph),
6. the evaluator is **sealed** behind versioned JSONL, commit-reveal and receipts,
7. the reward is attacked with duplicates, splits, flag-all and 25+ mutants,
8. every run is replayable from an offline-verifiable receipt.

## 2. What the hackathon evaluates — and what is provisional

The master specification quotes a *preliminary* split: contract & isolation 25, data & truth
25, reward robustness 25, reproducibility 15, engineering 10 (100 total), with ~20 checks per
block plus 5 engineering criteria. **This is unconfirmed.** The official rubric is not
available (`docs/QUESTIONS.md` Q-012), so:

* `judge/rubric_map.json` contains only *internal* checks with `official: false`;
* no report may call an internal check an official one;
* no report may claim an official score (`docs/DECISIONS.md` D-0002).

## 3. Architecture and trust boundaries

```
              +--------------------------- build time (offline) ---------------------------+
              |  master seed + config                                                    |
              |        |                                                                 |
              |  RNG namespaces -> CLEAN BOOK C -> invariants(C)                        |
              |        |                                      |                          |
              |  operators O1..On -> MUTATED BOOK M <---- canonical diff(C, M) -> candidate truth
              |        |                                                        |         |
              |  public/ (C or M)                      independent verifier <--+         |
              |        |                                      |                          |
              |        |                                 evidence certificates + crosscheck |
              |        |                                                        |         |
              |        +--> sealed/truth.json (+ salt) <---- reject on mismatch ---------+
              +--------------------------------------------------------------------------+
                                            |
   runtime (sealed evaluation)              v
  POLICY  <--JSONL-->  HARNESS  <--JSONL-->  ENV(public/ only, read-only)
                          |                        |
                          +--> append-only trajectory (hash chain)
                          |
                          +--> after env close: SCORER(sealed truth) -> reward + receipt
```

Trust boundaries, stated honestly (D-0012):

| Boundary | What is enforced | What is *not* enforced here |
|----------|------------------|-----------------------------|
| policy ↔ env | stdin/stdout JSONL only, allowlisted env vars, fixed argv, no shell | no OS sandbox in the current environment |
| env ↔ sealed | env working dir contains only `public/` (by construction and later by mount) | no separate uid yet |
| scorer ↔ policy | scorer runs after env close, no socket to the policy process | process separation is not a sandbox |
| judge ↔ everything | judge reads sealed truth read-only after the run | nothing |

`docs/THREAT_MODEL.md` lists each control with status; `docs/LIMITATIONS.md` lists what the
project does not claim.

## 4. Module map (master spec §6, decision D-0020)

| Path | Status at Phase 0 | Responsibility |
|------|-------------------|----------------|
| `contracts/` | **implemented** | Frozen public schemas, fixtures, versioning, currency registry |
| `adapter/` | **implemented (unbound)** | The only place that knows external organizer names |
| `configs/` | **implemented** | Every provisional number/formula/limit, versioned |
| `spec/` | **implemented (catalog only)** | Anomaly catalog and invariant catalog (normative data) |
| `tools/` | **implemented** | Canonical JSON, schema validator, governance/boundary scans, verify runner |
| `tests/` | **implemented (Phase 0 scope)** | Contract, canonical JSON, adapter, governance tests |
| `judge/` | **implemented (map only)** | Rubric map (internal, provisional) |
| `docs/` | **implemented** | Context, decisions, questions, risk, threat model, limitations, reports |
| `gen/`, `invariants/`, `verifier/`, `env/`, `harness/`, `scoring/`, `seal/`, `arena/`, `metamorphic/`, `episodes/` | **NOT STARTED** | Phases 2–13 |

## 5. Data flow and the four anomaly types

| Type | One-line definition | Candidate affected IDs (unconfirmed, Q-006) |
|------|--------------------|---------------------------------------------|
| `DUPLICATE_PAYMENT` | one obligation settled twice with no credit note/refund/reversal | the second `PAY` and its `JE` |
| `PARTIAL_PAYMENT_ALLOCATION` | allocation inconsistent with paid amount and remaining balance | the `PAY` and the invoices whose remainder is affected |
| `FX_RATE_MISMATCH` | booked rate differs from the policy-required rate for that date/source | the `JE` records that use the wrong rate |
| `PERIOD_CUTOFF` | posting period does not match the policy recognition event in company time | the `JE` records posted in the wrong period |

Every type has four clean distractors that differ by exactly one *accessible* fact
(`spec/anomaly_catalog.json`). A distractor whose distinguishing fact is not reachable
through a public tool is invalid.

## 6. Invariants (catalog: `spec/invariants.json`)

`INV-01` JE balance, `INV-02` trial balance, `INV-03` AP subledger vs documents, `INV-04`
open balance, `INV-05` aging, `INV-06` bank match, `INV-07` FX policy, `INV-08` FX recalc,
`INV-09` cut-off, `INV-10` period totals, `INV-11` ID uniqueness, `INV-12` referential,
`INV-13` currency exponent, `INV-14` timezone validity, `INV-15` allocation conservation,
`INV-16` credit-note limit, `INV-17` document status.

Clean twin: zero violations. Mutated twin: the operator's declared signature **plus only**
allowed side effects; anything else rejects the episode.

## 7. Reward (provisional, `configs/scoring/reward.json`)

`R = max(0, F1 - ETA * steps_used / max_steps)` with `ETA = 0.05`, `max_steps = 100`.
Exact arithmetic, no floats. `submit` does not cost a step; failed calls do. On a clean book
an empty submission has F1 = 1 — silence is correct there, and a truncated clean episode is
flagged separately so it is never called a successful audit.

Ten sanity examples (A…J in §15.6) become executable tests in Phase 9, including the
tolerance boundary cases.

## 8. Determinism rules

* One `master_seed`, many **addressable RNG streams** (`company`, `chart`, `counterparties`,
  `fx/<month>`, `history/<month>/<event>`, `id/<type>`, `text/<lang>/<doc>`, `order/<table>`,
  `mutation/<operator>/<index>`), each derived by SHA-256 of `namespace || master_seed`.
* No global `random`, no wall clock, no locale, no dict-order dependence.
* Adding a mutation never changes the clean twin; adding a text never changes IDs or amounts.
* Seeds never appear in observations, `info`, errors, filenames or manifests.

## 9. Money, FX, time

Integer minor units; `Decimal` from strings for rates; explicitly configured rounding mode;
currency exponents from `contracts/currency.json` (JPY 0, KWD 3 are the interesting cases).
FX: policy decides the rate date (`DOCUMENT_DATE`/`PAYMENT_DATE`/`POSTING_DATE`) and the
non-business-day rule; the generator and the verifier implement rate *selection*
independently. Time: `zoneinfo`, IANA names, period computed in the company timezone, DST
boundaries tested explicitly.

## 10. Test strategy

| Layer | What it proves | Where |
|-------|----------------|-------|
| Contract | schemas accept/reject exactly as declared | `tests/contracts/` |
| Unit | canonical JSON, adapter, config invariants | `tests/unit/` |
| Governance | Phase 0 exit criteria, untruthful claims, archive integrity | `tests/phase0/` |
| Property | canonical stability, money bounds, allocation law | `tests/` (Phase 2+) |
| Metamorphic | permutation/ID-bijection/timezone equivalence | Phase 13 |
| Security | leak paths, canaries, cursor/error probing | Phase 12 |
| Replay | byte-identical responses and hashes | Phase 8 |
| Acceptance | one command, rubric-linked, artifact per check | `make verify` |

A skipped check is never a pass (`docs/STATUS.md`).

## 11. Repository ownership

See `docs/OWNERSHIP.md`: four zones (generator/data, environment/evaluator, independent
verifier/red team, documentation/QA/judge kit) plus A0 orchestrator. The verifier may never be
written by the generator owner (REQ-ORG-001); for a one-person team the substitute controls
(separate specification, separate test vectors, separate import tree) are listed in
`docs/INDEPENDENCE.md`.

## 12. Current constraints and open questions

* No organizer contract, rubric, starter code or samples → everything external is
  `PROVISIONAL` (D-0001).
* No deadline stated anywhere → `OPEN-0` in `docs/QUESTIONS.md`.
* Environment: Python 3.11 only, stdlib only, offline, 2 CPU / 4 GB RAM / 1 GB disk
  (provisional).
* Sealed/hidden/generated data is never committed (D-0008).

## 13. Glossary

| Term | Meaning |
|------|---------|
| clean twin (C) | fully valid synthetic book |
| mutated twin (M) | C plus declared operator deltas |
| diff truth | candidate truth computed from `diff(C, M)` |
| ProofGraph | DAG from public records + policy rules to a finding |
| evidence set | minimal public IDs sufficient to derive a finding |
| sealed truth | `truth.json` + provenance, never visible to policy/env |
| commitment | `SHA256(canonical_truth || salt)` published before the run |
| receipt | offline-verifiable record of integrity, not of quality |
| internal check | a check we wrote; never an official rubric item |
| provisional | explicitly unconfirmed value, isolated in config/adapter |
