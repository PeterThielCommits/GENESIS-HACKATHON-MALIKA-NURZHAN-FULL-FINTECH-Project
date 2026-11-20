# Contract summary — what we know, what we assume, what we do not know

Status of this document: **PROVISIONAL INTERNAL SUMMARY**. It is not an organizer document.
Every row is tagged so that no reader can mistake an assumption for a fact.

Legend: `PROVISIONAL` = our working value, isolated in configuration; `UNKNOWN` = no value
exists, behaviour must fail closed; `DERIVED` = follows mechanically from the archived
master specification.

## 1. External surface

| Item | Value used internally | Tag | Source | Isolated in |
|------|----------------------|-----|--------|-------------|
| Tools | `list_records`, `get_record`, `get_document`, `calc`, `submit` | PROVISIONAL | §14.2, A-001 | `configs/adapter/compatibility.json`, `contracts/tool_request.schema.json` |
| Tool argument names | `table`, `cursor`, `limit`, `filters`, `id`, `doc_id`, `expression`, `findings` | PROVISIONAL | §14.2, A-001 | `contracts/tool_request.schema.json` |
| Error codes | `UNKNOWN_TOOL, BAD_ARGS, BAD_FILTER, BAD_CURSOR, NOT_FOUND, BAD_FINDING, CALC_ERROR, LIMIT, TERMINATED, ALREADY_SUBMITTED, INTERNAL` | PROVISIONAL | §14.6 | `contracts/tool_response.schema.json` |
| Envelope shape | `{protocol_version, request_id, action{tool,args}}` request / `{ok, result|error}` response | PROVISIONAL | Appendix H (illustrative) | `adapter/`, `contracts/` |
| External field names | Unknown beyond Appendix H | UNKNOWN | Q-001 | `adapter/compatibility.py` |
| reset/step signature | `reset(public_ref, cfg) -> Observation`, `step(action) -> StepResult` | PROVISIONAL | §14.1, Q-002 | `configs/environment/*` |
| Observation fields | Not known; `info` restricted to `steps_used`, `steps_remaining` | UNKNOWN | Q-002, Q-013 | `configs/environment/mode.json` |
| Pagination/cursor format | Opaque `base64(payload||checksum)`, snapshot-bound | PROVISIONAL | §14.5, A-009 | `configs/environment/cursor.json` |

## 2. Budget and termination

| Item | Value used internally | Tag | Source |
|------|----------------------|-----|--------|
| Inspection budget | 100 steps | PROVISIONAL | §14.4, A-004 |
| Failed call cost | 1 step | PROVISIONAL | §14.4 |
| `submit` cost | 0 steps | PROVISIONAL | A-006 (unresolved) |
| Page size | 1..50 | PROVISIONAL | A-004 |
| Max findings per submit | 64 (internal guard, not an official number) | PROVISIONAL | internal |
| Truncation source | deterministic step budget only | DERIVED | §14.8 |
| Wall clock | watchdog 60 s, never a quiet truncation | PROVISIONAL | §14.8, A-011 |

## 3. Findings and scoring

| Item | Value used internally | Tag | Source |
|------|----------------------|-----|--------|
| Anomaly types | `DUPLICATE_PAYMENT`, `PARTIAL_PAYMENT_ALLOCATION`, `FX_RATE_MISMATCH`, `PERIOD_CUTOFF` | PROVISIONAL | A-002, Q-004 |
| Finding fields | `type, affected_ids, claimed_amount, currency, evidence_ids[, explanation][, confidence]` | PROVISIONAL | A-003, Q-003 |
| Amount unit | integer minor units | DERIVED | §9.1 |
| ID namespaces | `JE, INV, CN, PAY, BANK, FX, CP` | PROVISIONAL | §15.1 |
| Match rule | type + exact affected IDs + currency + amount within tolerance + complete evidence set | PROVISIONAL | §15.2, Q-005 |
| Reward | `max(0, F1 - 0.05 * steps_used / 100)` | PROVISIONAL | §15.5, A-005 |
| Empty-truth rule | F1 = 1 for an empty submission on a clean book | PROVISIONAL | §15.4 |
| Tolerance | `rounding_ops * 1` minor unit | PROVISIONAL | §9.2, A-014 |
| Affected IDs per type | candidate lists only | UNKNOWN | §11.2–§11.5, Q-006 |
| Reward return timing | after env close, in closed mode | PROVISIONAL | §14.9, Q-013 |

## 4. Process and isolation requirements

| Item | Requirement | Tag | Source |
|------|-------------|-----|--------|
| Scorer process | separate, started after the environment closes | PROVISIONAL | §16.1, Q-007 |
| Policy → env channel | JSONL over stdin/stdout only | DERIVED | §16.1 |
| Sealed reference allowed | Unknown; assumed yes, protected by process boundary | UNKNOWN | Q-010 |
| Commit-reveal | SHA-256 over canonical truth ‖ salt, published pre-run | PROVISIONAL | §16.3 |
| Sandbox level | process separation; OS controls only where enabled | DERIVED | §16.2, D-0012 |

## 5. Runtime and submission

| Item | Value used internally | Tag | Source |
|------|----------------------|-----|--------|
| Python | 3.11.x | PROVISIONAL | A-013, Q-009 |
| Network at runtime | forbidden | DERIVED | §22.3 |
| CPU/RAM/disk | 2 cores / 4 GB / 1 GB | PROVISIONAL | A-013, Q-009 |
| Optional packages | allowed in dev, never required | PROVISIONAL | Q-011 |
| Submission format | repository + one command (`make verify`) | PROVISIONAL | Q-008 |
| Deadline | not stated anywhere available to this repository | UNKNOWN | OPEN-0 |

## 6. Rubric

| Item | Value used internally | Tag |
|------|----------------------|-----|
| Official rubric | not available; `official_rubric_available: false` | UNKNOWN (Q-012) |
| Block weights | 25 / 25 / 25 / 15 / 10 = 100, **preliminary only** | PROVISIONAL (A-016) |
| Checks per block | 20 / 20 / 20 / 20 + 5 criteria, **preliminary only** | PROVISIONAL (A-016) |
| Reporting rule | internal suite pass rate, explicitly labelled internal | DERIVED (D-0002) |

## 7. What this summary deliberately does not do

* It does not claim any organizer confirmation.
* It does not convert a "preliminary" note in the master specification into a fact.
* It does not hide missing material: `MANIFEST.json` lists every absent document.

Review: `CONTRACT_SIGNOFF.md` holds the two required signatures (one AI, one human).
