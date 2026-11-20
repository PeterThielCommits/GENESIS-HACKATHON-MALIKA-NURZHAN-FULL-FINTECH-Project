# Submission deadline, timezone and submission format

Phase 0 task 0.8 requires the submission deadline and the local timezone to be fixed. The
timezone half is answered; the deadline half is **not**, and it is recorded as unknown rather
than guessed.

## 1. Status

| Field | Value | Source |
|-------|-------|--------|
| Submission deadline (UTC) | **UNKNOWN** | no organizer statement exists (Q-001, `OPEN-0`) |
| Submission deadline (local) | **UNKNOWN** | same |
| Local timezone | `Asia/Almaty` (UTC+5, no DST) | team operating location, 2026-11-20 |
| Submission channel | **UNKNOWN** | not published |
| Submission format | **UNKNOWN** | not published |
| Deadline confirmed by | — | a human must quote the organizer message |

Machine-readable form: `configs/submission/submission.json`. Automated checks:

* `tools.check_governance` (`GOV-DEADLINE-01`) — the file must stay internally consistent and
  must keep `SUBMISSION_DEADLINE_UTC` empty until `DEADLINE_CONFIRMED_BY` is filled.
* `tests/phase0/test_deadline.py` — pins the timezone facts and the "never guess" rule.

## 2. Timezone facts we rely on

* Kazakhstan switched to a single UTC+5 zone on 2024-03-01; `Asia/Almaty` is UTC+5 all year and
  **does not observe DST** (so no 23/25-hour days, no ambiguous cut-offs).
* All timestamps inside the product are UTC (`contracts/common.defs.json` `utc_timestamp`);
  local time appears only in human-facing reports and in the deadline table above.
* A deadline recorded in local time must be converted with a fixed +05:00 offset, which is safe
  precisely because there is no DST. The conversion is asserted by the test, not assumed.

## 3. How to record the deadline when it is published

1. Quote the organizer message verbatim (channel, author, timestamp) in `docs/QUESTIONS.md`
   under `OPEN-0`, then move the closed text to the answered section.
2. Fill `configs/submission/submission.json`:
   `SUBMISSION_DEADLINE_UTC`, `SUBMISSION_DEADLINE_LOCAL`, `DEADLINE_CONFIRMED_BY`,
   `DEADLINE_CONFIRMED_AT`; leave `provisional: false` only after a human re-reads it.
3. Add a `DECISIONS.md` entry (`D-00xx — submission deadline is …`) so the date is auditable.
4. Re-run `make verify-core`; `GOV-DEADLINE-01` recomputes the local/UTC agreement.
5. Update the freeze plan: the repository must be releasable **72 hours** before the deadline,
   with the last 72 hours reserved for the submission itself and for re-running the gate from a
   clean clone.

## 4. What this means for planning today

Because the deadline is unknown, every schedule claim in this repository is expressed as a
phase order, not as a countdown. If the organizers publish a date and it is closer than the
remaining phases need, the priority order in the master specification §25 (A/B/C) decides what
is cut — never the test suite and never the honesty of the reports.
