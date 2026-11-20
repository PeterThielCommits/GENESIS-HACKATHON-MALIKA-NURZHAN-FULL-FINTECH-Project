# AGENTS.md — rules for any AI agent working on TwinLedger

This file is the entry point required by the master specification (Appendix F.1, §4, §5).
Read it before touching code, then follow the reading order below.

## 1. Reading order (do not skip)

1. `AGENTS.md` (this file)
2. `docs/PROJECT_CONTEXT.md`
3. `docs/CURRENT_STATE.md`
4. `docs/STATUS.md`
5. `docs/DECISIONS.md`
6. `docs/QUESTIONS.md` and `docs/ASSUMPTIONS.json`
7. the `contracts/` relevant to your task, then `contracts/CONTRACT.md`
8. your task card (`docs/TASKS/`) and the latest `docs/PHASE_REPORTS/` + `docs/HANDOFF/`

If a file you need does not exist, say so — never invent its contents.

## 2. Before changing anything

* Run `git status` and `git log --oneline -5`; note the branch and the last verified commit.
* Do not overwrite another zone's work (see `docs/OWNERSHIP.md`).
* State a short plan and acceptance criteria **before** editing.
* Separate what is official from what is provisional. Today: everything external is
  provisional (D-0001); no organizer document is archived.

## 3. Hard rules

1. Never claim a test, command, build or CI run passed unless you actually ran it and saw the
   exit code. Never write "all tests pass" without the command.
2. Never hide a failure, a skip or a flake. `SKIPPED` and `BLOCKED` are legitimate states;
   a false `PASS` is a release blocker.
3. Never weaken a test to get a green build (REQ-TEST-002). A test change needs a `docs/CR/`
   entry that cites the official specification.
4. Never change frozen contracts without a CR plus a `docs/DECISIONS.md` record; the contract
   digest printed by `make verify` must change in the same commit.
5. Never put truth, provenance, seeds, salts or hidden labels into an observation, `info`,
   error message, log, filename or manifest.
6. Never let a policy import `gen`, `verifier`, `scoring`, `seal`, or read a private episode
   path. `tools/check_import_boundaries.py` enforces this and must stay green.
7. Never use real financial, personal or organizer data. Everything is synthetic.
8. Never add a network call or a required third-party package to the mandatory path.
9. All money is integer minor units; rates are `Decimal` from strings. Floats are rejected by
   canonical JSON for a reason.
10. Any nondeterminism must be found and explained, not tolerated.
11. Never claim an internal check is an official rubric item, and never claim an official
    score (D-0002, checked by `GOV-CLAIMS-01`).
12. Every deviation from the specification goes into `docs/DECISIONS.md` with a reason.
13. Every result is tied to a REQ id and to a report artifact.
14. Commit format: `<type>(<scope>): <imperative summary> [REQ-...]`
    (`feat|fix|test|docs|refactor|build|ci|perf|security|chore`).

## 4. Zone boundaries and forbidden operations

| Zone | Directories | Do not |
|------|-------------|--------|
| A — generator/data | `gen/`, `spec/`, `episodes/` | write the verifier (REQ-ORG-001) |
| B — env/evaluator | `env/`, `adapter/`, `harness/`, `scoring/`, `seal/` | read `gen/` internals or hidden truth at runtime |
| C — verification/red team | `verifier/`, `arena/`, `metamorphic/` | import the generator or read provenance during discovery |
| D — docs/QA/judge | `judge/`, `tools/`, `docs/`, CI | change scoring or generator logic "to make a test pass" |

Cross-zone edits require an orchestrator-approved exception recorded in `docs/CR/`.

## 5. Test, report and handoff obligations

After any non-trivial change:

1. Add or update tests (unit + contract; property/metamorphic where relevant).
2. Run `make lint && make test` (and `make verify-core` when touching contracts, configs or
   docs that the checks read). Record exact commands and exit codes.
3. Update `docs/CURRENT_STATE.md` (phase, last verified commit, next action) and
   `docs/STATUS.md` if a gate moved.
4. Write `docs/AGENT_REPORTS/<date>/<agent>-<task>.md` using Appendix B of the master
   specification. A report without command output is invalid.
5. If another agent continues, write `docs/HANDOFF/<from>-to-<to>-<ticket>.md` with branch,
   commit hash, open defects and the exact next step.
6. Update the GitHub issue/PR, or state explicitly `REMOTE GITHUB UPDATE NOT DONE`.

## 6. Definition of a finished task

`DONE` requires all of: task card, commit, executed tests with real output, independent
review of the diff, report, and a handoff or context update. Anything less is `PARTIAL` or
`BLOCKED`. A phase gate additionally requires `docs/PHASE_REPORTS/PHASE-XX.{md,json}`.

## 7. Phase-specific note (Phase 0 is closed)

Phase 0 delivered contracts v0.1, the adapter boundary, configs, governance records and the
verify harness. Phase 1 (repository foundation hardening) may start; **Phase 5 may not claim
official compatibility** until `adapter/` is bound to a real organizer contract.

Two items cannot be closed by an agent: the human second signature in
`docs/official/CONTRACT_SIGNOFF.md` and the submission deadline (`docs/QUESTIONS.md` OPEN-0).
Do not fabricate either.

## Phase 1 additions to the hard rules

15. **Never edit `contracts/` without a CR.** The set is frozen by `contracts/GOLDEN.json`; a
    change means: `docs/CR/` entry → schema + fixtures → `python3 -m tools.check_golden --write`
    → tests, in one commit. `make lint` fails otherwise.
16. **Never add a model field without a schema field, or the reverse.** `tools/check_models.py`
    enforces parity in both directions and rejects an unknown field instead of dropping it.
17. **Never weaken the CI gate to get a green run.** `tools/check_ci.py` resolves every `run:`
    command against the Makefile and `tools/`, so a deleted or renamed step fails locally.
18. **Never invent a deadline.** `configs/submission/submission.json` keeps
    `SUBMISSION_DEADLINE_UTC: null` until a human quotes the organizer message; `GOV-DEADLINE-01`
    refuses a date without `DEADLINE_CONFIRMED_BY`/`AT`.
19. **Regenerate, do not hand-edit, generated files.** `docs/RUBRIC_TRACEABILITY.md` and
    `docs/PHASE_REPORTS/PHASE-*.json` are produced by tools; `make lint` / `GOV-RUBRIC-01` fail
    when they are stale.
