# Source search log (Phase 0, task 0.1)

Purpose: record exactly what was searched, when, with what result, so that "we could not
find the official contract" is a reproducible statement rather than an impression.

Date of search: 2026-11-20. Environment: offline sandbox with outbound access limited to
`github.com`, `codeload.github.com`, `api.github.com`, `registry.npmjs.org`, `pypi.org`,
`files.pythonhosted.org`.

| # | Channel | Query / action | Result | Classification |
|---|---------|----------------|--------|----------------|
| 1 | User attachment | `TwinLedger_v3_Master_TZ_AI_Agents.txt` (4062 lines) | Received. Self-describes as a *derived* master specification and states the external share link did not open. | `DERIVED_INTERNAL` — archived |
| 2 | Master specification text | §0 preamble and §2.2 | States explicitly that the Claude share link was inaccessible and no attachments were readable, and forbids agents from presenting an assumption as an official fact. | Evidence of absence |
| 3 | Public web search | "Genesis hackathon TwinLedger proof-carrying audit environment официальное техническое задание" | Returned issues from a third-party repository (`24kBlood/GenesisHackathon`) referencing "ТЗ FinTech §03–04, §07, §10" without publishing the document. | Not authoritative — not used |
| 4 | GitHub repository search | `genesis hackathon fintech` via the GitHub API | Other participants' repositories (`itsaibarr/auditgym`, this repository, unrelated projects). No organizer repository. | Not authoritative — not used |
| 5 | GitHub code search | `TwinLedger in:file` | 220 hits across participants' repositories. No organizer publication. | Not authoritative — not used |
| 6 | Organizer channel | None available in this environment (no chat/portal access) | — | UNKNOWN |

## Rules applied to the search result

1. A participant's repository is **never** treated as the organizer contract, even when it
   looks complete: it is neither published by the organizers nor verifiable, and copying it
   would propagate another team's guesses (master specification §2.2, D-0001).
2. The two inaccessible sources are recorded as missing, not silently replaced.
3. Every requirement we implement is therefore tagged `PROVISIONAL_MASTER_TZ` in
   `docs/REQUIREMENTS.json`.

## What would close this log

A file (PDF, DOCX, Markdown, or a starter repository archive) published by the organizers,
added to `docs/official/` with `classification: OFFICIAL_ORGANIZER` and its SHA-256, plus a
`docs/CR/` entry describing the contract diff against the current assumptions.
