# Phase 05 — СРЕДА RESET/STEP И PUBLIC TOOL API

**Result: PARTIAL; exit gate BLOCKED.** Agent: Arena coding agent (A2/A0 role); human owner unassigned. Date 2026-11-21. Branch `arena/eb1e0f8a-genesis-hackathon-malika-nurzh`, baseline `c961a009611e1711463f5116b2df926bb4726de8`, final commit: commit containing this report and subsequent handoff updates (`git log`). Master TZ v3.0.0 SHA-256 `a46cdb63bb4b41aabb95a842406f5a4fff91e218ead1e4f97b22b60d1c748e36`; execution prompt SHA-256 `9139e28e3cf6dcc14baaa947f11cdb918f50565927fe5ce7ee3263ad28d04e04`. Neither document is represented as an organizer-issued contract.

## Baseline and dependencies
Initial branch was clean and contained only a README; no contracts, tests, Phase 0–4 reports, generator, adapter, context docs or CI. There was no baseline test/lint/build command. Remote GitHub inspection found open PR [#1](https://github.com/PeterThielCommits/GENESIS-HACKATHON-MALIKA-NURZHAN-FULL-FINTECH-Project/pull/1) proposing Phase 1 schema freeze, and [#2](https://github.com/PeterThielCommits/GENESIS-HACKATHON-MALIKA-NURZHAN-FULL-FINTECH-Project/pull/2) for Phase 2; neither is on this branch. Phase 3/4 inputs are absent on this branch. Organizer rules/examples and official adapter remain unknown. [Issue #3](https://github.com/PeterThielCommits/GENESIS-HACKATHON-MALIKA-NURZHAN-FULL-FINTECH-Project/issues/3) records blockers. PR #1's finding, JSONL and calc requirements differ from this branch: [draft CR-05-01](../CR/CR-05-01.md). No contract has been approved or frozen in this branch.

## Task / requirements traceability

Details, owners and dependencies: [task card](../TASKS/T-05-01.md). REQ references below are mapped to partial implementation, not claims of full conformance.

| Task | REQ-IDs | Result / evidence |
|---|---|---|
| 5.1 public-only loader | PROD-005, ARC-001..007, DATA-020..022 | PARTIAL: `env/state.py`, tests for unlisted/sealed path and symlink rejection; no producer/OS isolation proof |
| 5.2 reset/step | ENV-001..004 | PARTIAL: `env/server.py`, lifecycle tests; official adapter absent |
| 5.3 list/get/document | PROD-002, ENV-001..004 | PARTIAL: `env/tools.py`, tests; no schema compatibility with real generated episodes |
| 5.4 filters/order/cursors | ENV-010..013 | PARTIAL: `env/filters.py`, `env/cursors.py`, test pagination/foreign/tampered cursors; no complete replay/shortcut proof |
| 5.5 bounded errors/budget | ENV-001..004 | PARTIAL: tested selected errors and exhaustion; manifest and official budget policy absent |
| 5.6 submit validation/lifecycle | CONTRACT-001..005 | PARTIAL: validation and duplicate submit tests; differs from PR #1 proposed freeze |
| 5.7 calculator | ENV-020..023 | BLOCKED: organizer requirement unknown, PR #1 includes calc; no implementation or fuzz tests |
| 5.8 closed evaluation | ENV-030..032 | PARTIAL: reward 0 and empty info tested; no make verify, OPEN_DEV, scorer or post-episode finalize |

## Changes
Created `env/`, `tests/env/`, hand-authored `tests/fixtures/example/public/`, provisional interface notes in `contracts/`, Makefile, .gitignore, task/decision/question/context/handoff reports, draft CR, logs and archived attached specs. Modified README. No files deleted. Source supplies a file allowlist, symlink-resistant public directory traversal, exact-match filter allowlists, deterministic ID ordering and keyed opaque in-memory cursor handles, bounded error codes, budget and one-submit lifecycle. It does not validate entire public schemas, all references, data provenance or semantic correctness. An explicit cursor key is required; a fixed CLI demo key is public and offers no adversarial security. No OS sandbox is implemented. Selected private field name checks cannot prove public data contains no secrets. The test fixture is not a generated or verified episode.

## Tests and gates

| Command | Exit | Status | Evidence |
|---|---:|---|---|
| `make test` (initial) | 2 | FAIL then fixed | discovery shadowed `env` with `tests/env`; corrected with `-t .` |
| `make test` (final) | 0 | PASS | 12 unittest methods, [test log](logs/phase-05-test.txt); not exhaustive official contract/security tests |
| `make smoke` | 0 | PASS | local JSONL list + submit, [smoke log](logs/phase-05-smoke.txt); not official adapter |
| `python3 -m compileall -q env tests` | 0 | PASS | syntax compilation; Python 3.11.2 |
| `git diff --check` | 0 | PASS | before staging; staged diff checked separately |
| Official adapter and schemas, calculator fuzz, full action matrix, producer integration, isolation, replay, full verify, independent review, CI | — | NOT RUN / BLOCKED | contract, upstream implementation or review missing; no green release claim |

EXIT GATE 5: reset/step works for selected provisional local cases (**partial**); stable and complete through the official adapter for MVP (**blocked**, adapter and organizer examples unavailable). All valid/invalid official actions and CLOSED_EVAL process isolation have not been established.

## Decisions, risks, follow-up
D-05-01..04 are provisional; CR-05-01 is draft, not approval. Cursors require a key controlled outside untrusted policy processes; this implementation cannot enforce that boundary. Invalid submits are charged, exhaustion immediately truncates; official behavior is unknown. Data validation is deliberately incomplete and assumes public files are safe. Exact table keys, period/opening balance representation and submission format need upstream reconciliation. Independent reviewer and human owner are unassigned. This branch is not ready for Phase 6; close official contract and upstream dependencies first. Next action: A0 review PR #1 and obtain organizer examples, then decide CR-05-01. See [handoff](../HANDOFF/phase-05-to-a0.md).

GitHub issue #3 was created; branch publication / PR and CI are tracked separately in the agent report and actual Git history. Do not infer a CI pass from PR #1/#2's runs.

Publication: code commit `151c101` pushed to the current branch; [draft PR #4](https://github.com/PeterThielCommits/GENESIS-HACKATHON-MALIKA-NURZHAN-FULL-FINTECH-Project/pull/4) created. REMOTE GITHUB UPDATE DONE. PR is draft; no current-branch CI or independent review is claimed.

## 2026-11-21 follow-up

The current branch now supports the separate Phase 4 snapshot's public layout and FX composite keys. A real generated public episode passed the local inspection smoke, and the snapshot's own suite and sweep passed when run in a separate exported directory. See [follow-up report](PHASE-05-FOLLOWUP.md). This does not merge upstream code, establish an official contract, close the adapter gate, or constitute independent truth verification. Overall status remains PARTIAL / gate BLOCKED.
