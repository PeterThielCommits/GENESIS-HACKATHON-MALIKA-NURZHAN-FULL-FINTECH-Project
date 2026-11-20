# `docs/official/` — source archive

This directory holds the *bytes* every requirement, decision and question in this
repository cites, plus an explicit record of what is **missing**.

## What is here

| Path | Classification | SHA-256 |
|------|----------------|---------|
| `master_tz/TwinLedger_v3_Master_TZ_AI_Agents.txt` | `DERIVED_INTERNAL` | `a46cdb63bb4b41aabb95a842406f5a4fff91e218ead1e4f97b22b60d1c748e36` |

The archived master specification is stored **unmodified** (4062 lines, 237 211 bytes) and
is verified on every `make verify` run (`tools/check_governance.py`, check `GOV-ARCHIVE-01`).

## What is *not* here — and why this matters

There is **no organizer-published document** in this repository:

* no official technical specification,
* no official rubric (the "20 checks × 4 blocks + 5 criteria / 100 points" split is
  preliminary and unconfirmed),
* no starter code, environment adapter or sample inputs/outputs.

The master specification itself records that the external share link did not open and that
no attachments were readable. Public code search returns other participants' repositories,
which are not authoritative and are therefore **not** used as a requirement source (see
`SOURCE_SEARCH_LOG.md`).

Consequences, stated plainly:

1. The whole external contract is `provisional` (`contracts/version.json`).
2. All sixteen open assumptions are `UNRESOLVED` and isolated behind `adapter/` and
   `configs/` (`docs/ASSUMPTIONS.json`).
3. No report in this repository may describe an internal check as an official check
   (`judge/rubric_map.json` enforces `official: false`).
4. When the official material arrives, it is added here **as a new file** with its own hash
   and classification `OFFICIAL_ORGANIZER`, and every affected decision is superseded by a
   new one — files in this directory are never edited in place.

## Classification rules

* `OFFICIAL_ORGANIZER` — published by the hackathon organizers. A requirement derived from
  such a document may be marked `CONFIRMED`.
* `DERIVED_INTERNAL` — written by this team. It is citable engineering input, and it can
  never make an assumption `CONFIRMED`.

## How the summary is produced and reviewed

* `CONTRACT_SUMMARY.md` — the extracted external contract, with every item tagged
  `PROVISIONAL` / `UNKNOWN`.
* `CONTRACT_SIGNOFF.md` — the two-person review required by Phase 0. Reviewer 1 (AI
  orchestrator) signs the *internal* summary against the archive; Reviewer 2 is a **human**
  and is currently `PENDING`. An AI agent cannot sign for a human, and a `PENDING` slot is
  reported as `HUMAN_ACTION_REQUIRED` rather than silently treated as done.
