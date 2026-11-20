# Phase 0 — task-by-task checklist against the master specification §24

Every row is a literal item from the archived specification, not a summary of one. "Evidence" must
be a path a reviewer can open or a command they can re-run; nothing here is satisfied by a
sentence. Regenerate the numbers with `make verify-core`.

Phase 0 status: **`PASS_WITH_OPEN_ITEMS`** — all agent-actionable tasks are done; three items are
human or external and are named in §3.

## 1. Tasks 0.1 – 0.8

| # | Task (verbatim intent) | Status | Evidence | Note |
|---|------------------------|--------|----------|------|
| 0.1 | find the full official TZ, rubric, sample I/O and starter code | `PASS` (documented absence) | `docs/official/SOURCE_SEARCH_LOG.md` (6 channels), `docs/official/MANIFEST.json` `absent[]` | no organizer document exists in any reachable channel; recorded, not invented |
| 0.2 | store an unmodified local copy with version/date/source/hash | `PASS` | `docs/official/master_tz/…txt`, `MANIFEST.json` (`a46cdb63…c748e36`, 4062 lines, 237 211 bytes), `GOV-ARCHIVE-01` | byte-identical, verified on every run |
| 0.3 | write out exact tool names, schemas, reward, budget, limits, submission format, env restrictions | `PASS` | `docs/official/CONTRACT_SUMMARY.md` (7 sections), `configs/` (11 files), `contracts/` (11 schemas) | every row tagged `PROVISIONAL`/`UNKNOWN`/`DERIVED`; submission format stays `UNKNOWN` |
| 0.4 | map every official item onto the assumptions of this document | `PASS` | `docs/ASSUMPTIONS.json` (A-001…A-016), `docs/REQUIREMENTS.json` (186), `docs/RUBRIC_TRACEABILITY.md` | all 16 assumptions `UNRESOLVED`, each with isolation point + question + covering test |
| 0.5 | produce `docs/DECISIONS.md` with CONFIRMED / CHANGED / OPEN | `PASS` | `docs/DECISIONS.md` (D-0001…D-0024) | **0 CONFIRMED** by design: without an organizer document nothing can be confirmed (D-0001) |
| 0.6 | create `docs/QUESTIONS.md` and ask the organizers | `PASS` (asking is human) | `docs/QUESTIONS.md` (Q-001…Q-014 + `OPEN-0`) | each has owner, asked-to, closure condition, impact and mitigation |
| 0.7 | run a minimal smoke test of the official starter environment, if it exists | `SKIPPED` (executable) | `python3 -m tools.probe_starter`, `configs/submission/starter_probe.json` | no bundle exists; the probe scans 7 paths, would compile and smoke-test one if it appeared |
| 0.8 | record the submission deadline and local timezone | `PASS` for timezone, `NOT RUN` for date | `docs/official/SUBMISSION_DEADLINE.md`, `configs/submission/submission.json`, `GOV-DEADLINE-01` | `Asia/Almaty` = UTC+5, no DST; the date is `null` + `OPEN-0`, never guessed |

## 2. Required outputs

| Output | Status | Where |
|--------|--------|-------|
| `docs/official/` | `PASS` | archive + manifest + summary + sign-off + search log + deadline + probe evidence |
| `docs/DECISIONS.md` | `PASS` | 24 decisions, machine-checked fields, assumption register mirror |
| `docs/QUESTIONS.md` | `PASS` | 14 questions + 1 blocking unknown |
| `contracts/` v0.1 | `PASS` | 11 schemas + definitions, 35 fixtures, `CONTRACT.md`, digest, golden freeze |
| `docs/RUBRIC_TRACEABILITY.md` | `PASS` | 45 internal checks, requirement coverage table, per-area unmapped list |
| `docs/STATUS.md` | `PASS` | gate table with honest vocabulary |

## 3. Phase 0 tests (§24 "Тесты") and exit gate

| Requirement | Status | Evidence |
|-------------|--------|----------|
| every A-xxx has an answer or an explicit OPEN status | `PASS` | `tests/phase0/test_assumption_registry.py`, `GOV-ASSUMPTIONS-01` |
| no provisional formula is called official | `PASS` | `GOV-CLAIMS-01`, `tests/phase0/test_no_official_claims.py`, `official: false` const in `contracts/rubric_check.schema.json` |
| the contract summary was reviewed by two people | **`BLOCKED` — human** | Reviewer 1 signed; Reviewer 2 `PENDING` (`docs/official/CONTRACT_SIGNOFF.md`) |
| mandatory interfaces are known | `PASS` (provisionally) | `contracts/CONTRACT.md` + 11 schemas + typed models in `models/` |
| unknowns are isolated in `adapter/` and config | `PASS` | `adapter/` `UNBOUND` fail-closed, `configs/` 11 files, `CT-ADAPTER-01`, `CT-BOUNDARY-01` |
| a blocking risk is either removed or has a documented safe solution | `PASS` | `docs/RISK_REGISTER.md` P0-1 … P0-5, `docs/THREAT_MODEL.md`, `docs/LIMITATIONS.md` |

Open items that no agent can close:

1. Reviewer 2 signature (D-0017).
2. The real submission deadline (task 0.8, `OPEN-0`).
3. The organizer contract itself (`Q-001`); until it arrives the isolation strategy *is* the answer.

## 4. What was added after the first close, and why

The first close was honest but had two unfalsifiable statements ("no starter code exists", "the
deadline is unknown"). Both are now executable (`tools/probe_starter.py`, `GOV-DEADLINE-01`), and
the timezone half of task 0.8 is answered rather than deferred. Phase 1 items that Phase 0 needed
anyway — a frozen golden digest, typed models, CI — were delivered in the same pass and are
reported in `docs/PHASE_REPORTS/PHASE-01.md`, never mixed into this table as Phase 0 work.
