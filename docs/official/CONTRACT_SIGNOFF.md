# Contract summary sign-off (Phase 0, task 0.2/0.4)

Phase 0 requires the official contract summary to be reviewed by **two people**. Two slots
exist below. A slot is only `SIGNED` when it names a person or agent, a date, the scope that
was actually reviewed and the evidence used. Nothing else counts as a signature.

Machine handling: `tools/check_governance.py` (check `GOV-SIGNOFF-01`) validates the
structure of both slots; a `PENDING` slot is reported as `HUMAN_ACTION_REQUIRED` in
`docs/STATUS.md` and in every `make verify` report. It is never counted as a pass and never
silently dropped.

### Reviewer 1 — AI orchestrator (internal summary vs archived specification)

**Status:** SIGNED
**Name:** Arena coding agent acting as A0 orchestrator (session label `phase-0-orchestrator`)
**Date:** 2026-11-20
**Scope:** Structural review of `docs/official/CONTRACT_SUMMARY.md` against the archived
master specification: every quoted section number, every assumption id, the finding and
tool schemas, the reward and tolerance parameters, and the explicit UNKNOWN markers.
**Evidence:**
- archive hash `a46cdb63bb4b41aabb95a842406f5a4fff91e218ead1e4f97b22b60d1c748e36`
  (recomputed by `GOV-ARCHIVE-01`);
- `docs/REQUIREMENTS.json` (186 extracted requirements, regenerated and compared byte-for-byte);
- `docs/ASSUMPTIONS.json` (16 assumptions, all `UNRESOLVED`, all with existing isolation points);
- `make verify` output in `artifacts/reports/latest/verify_summary.json`.
**What this signature does *not* mean:** it is not a human second opinion, and it does not
confirm any organizer fact. An AI agent cannot certify the organizer contract.

### Reviewer 2 — human owner (organizer-facing review)

**Status:** PENDING
**Name:** _to be signed by the human zone owner (Owner B: environment/evaluator, or Owner A0
orchestrator if reassigned)_
**Date:** —
**Scope required before signing:**
1. Confirm that no organizer document exists that this repository failed to archive.
2. Confirm the externally visible parameter set in `docs/official/CONTRACT_SUMMARY.md`
   §1–§5 against whatever the organizers published (chat, link, PDF, starter repo).
3. Confirm that every `UNKNOWN` row is still unknown and that its isolation point is
   sufficient for the phase we are entering.
4. Confirm or correct the deadline entry (`OPEN-0` in `docs/QUESTIONS.md`).
**Evidence to attach when signing:** the organizer source (file name + hash, or quoted
message with date) and the resulting `docs/CR/` entry if anything changes.

**Why this is not signed by the agent:** fabricating a human signature would be exactly the
kind of unverifiable claim this project exists to prevent. Until a person signs, Phase 0 is
`PASS_WITH_OPEN_ITEMS`, not `DONE` (docs/DECISIONS.md D-0017).
