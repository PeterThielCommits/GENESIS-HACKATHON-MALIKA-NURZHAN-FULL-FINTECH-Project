# T-0-01 — Official source discovery and archiving

| Field | Value |
|-------|-------|
| Phase | 0 (task 0.1, 0.2) |
| Human owner | A0 orchestrator |
| Status | DONE (with an unavoidable open item) |
| Requirement ids | REQ-ADAPTER-001, D-0001, D-0018 |

## Goal
Find the official technical specification, rubric, samples and starter code; archive an
unmodified copy with version, date, source and hash.

## What was done
* Searched the user attachment, the master specification's own preamble, public web search and
  the GitHub API. Result: **no organizer document exists** in any accessible source
  (`docs/official/SOURCE_SEARCH_LOG.md`, six logged channels).
* Archived the master specification byte-identically and recorded its SHA-256, byte count and
  line count in `docs/official/MANIFEST.json`.
* Recorded the four absent documents explicitly instead of substituting guesses.

## Acceptance evidence
| Check | Command | Result |
|-------|---------|--------|
| archive integrity | `python -m tools.check_governance` (`GOV-ARCHIVE-01`) | PASS |
| absence recorded | `docs/official/MANIFEST.json` `absent[]` | 4 entries |
| hash test | `python -m unittest tests.phase0.test_official_archive` | PASS |

## Deviation
The task's goal ("find the official TZ") could not be fully achieved: it does not exist in any
accessible channel. The honest outcome is a documented absence plus an isolation strategy, not
a fabricated contract (D-0001).
