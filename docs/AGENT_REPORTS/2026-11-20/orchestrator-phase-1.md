# Agent report — A0 orchestrator, Phase 1 (foundation) and Phase 0 hardening

| Field | Value |
|-------|-------|
| Date | 2026-11-20 |
| Agent | Arena coding agent (A0 orchestrator role) |
| Branch | `arena/6e3d45bc-genesis-hackathon-malika-nurzh` |
| Scope | Phase 0 completeness audit + Phase 1 (repository foundation, contract freeze) |
| Outcome | `PHASE-00 = PASS_WITH_OPEN_ITEMS` (hardened), `PHASE-01 = PASS_WITH_OPEN_ITEMS` |
| Human actions left | 4 (Reviewer 2, deadline, branch protection, CODEOWNERS handles) |

## Why this pass happened

Phase 0 was closed with two statements that nobody could falsify: *"no organizer starter code
exists"* and *"the deadline is unknown"*. Both were true and both were unverifiable from the
repository. Phase 1 was also the declared next step, and its items (CI, typed models, freeze)
were partly present but unproven. This pass turned all of it into something a reviewer can run.

## What was built

### Phase 0, hardened (task by task in `docs/PHASE0_CHECKLIST.md`)

| Task | Before | Now |
|------|--------|-----|
| 0.7 starter smoke test | a sentence saying it is skipped | `tools/probe_starter.py`: scans 7 paths, compiles any bundle, runs only configured commands, reports `SKIPPED` **with evidence** |
| 0.8 deadline + timezone | "unknown" | `configs/submission/submission.json` + `SUBMISSION_DEADLINE.md`: timezone answered (`Asia/Almaty`, UTC+5, no DST, proven with `zoneinfo`), date `null` and locked by `GOV-DEADLINE-01` |
| tests + exit gate | prose | `PHASE0_CHECKLIST.md` maps all 8 tasks, 3 tests and 3 exit-gate criteria to evidence |

### Phase 1 (foundation)

* `models/` — 11 dataclasses mirroring the schemas, with construction-time validation, `x_`
  extension preservation and `canonical()` as the only serialisation hinge.
* `tools/check_models.py` — parity of field names **and** required sets in both directions, plus
  round-trip of 14 valid fixtures and rejection of 21 invalid ones.
* `contracts/GOLDEN.json` + `tools/check_golden.py` — per-file freeze, payload digest, fixture
  digest; refresh only through a CR.
* `.github/workflows/verify.yml` + `tools/check_ci.py` — the gate runs in CI, and every `run:`
  command is resolved against the Makefile so a rename cannot silently skip a step.
* `.github/pull_request_template.md`, 4 issue forms, `CODEOWNERS`, `docs/BRANCH_PROTECTION.md`.
* `tools/gen_traceability.py` — `docs/RUBRIC_TRACEABILITY.md` is generated; staleness fails the
  build.
* 5 new rubric checks (`CT-GOLDEN-01`, `EN-MODELS-01`, `EN-CI-01`, `EN-SUBMIT-01`,
  `EN-PROBE-01`) and 3 new governance checks (`GOV-CI-01`, `GOV-DEADLINE-01`, `GOV-MODELS-01`).

## Verification (executed)

| Command | Exit | Result |
|---------|------|--------|
| `python3 -m unittest discover -s tests -t . -p 'test_*.py'` | 0 | 231 tests, 0 failures |
| `make lint` | 0 | boundaries, contracts, registry, models, freeze, CI, traceability |
| `python3 -m tools.check_governance` | 0 | 16/16 checks, 37/37 required documents |
| `python3 -m tools.verify --profile core` | 0 | 45 checks: 17 executed (16 pass, 1 `SKIPPED`), 28 `BLOCKED` |
| `python3 -m tools.check_golden` | 0 | 50 contract files match the freeze |
| `python3 -m tools.probe_starter` | 0 | `SKIPPED` with scanned paths and manifest evidence |

## Judgement calls

* **D-0021** — the CI file is linted by a stdlib tool instead of importing PyYAML: a gate that
  only works on a machine with an extra package is a gate nobody runs.
* **D-0022** — the freeze records per-file hashes, not a single digest, because "something
  changed" is not reviewable but "this file changed" is.
* **D-0023** — schemas remain the authority; models are checked mirrors. Generated models were
  rejected because they would need their own trust chain.
* **D-0024** — the deadline stays `null`. Inventing a plausible date would silently destroy the
  schedule buffer, which is the one resource a hackathon cannot recover.

## Mistakes made in this pass

* Added `GOLDEN.json` inside `contracts/`, which changed the schema payload digest and broke a
  report test. Fixed by excluding freeze metadata from `contract_digest()` — the digest names the
  payload, not the bookkeeping.
* The first `models/` draft guessed four schema shapes (truth, tool_response, trajectory_event,
  verifier_report) and the parity tool caught every wrong field immediately. Kept as evidence
  that the checker is not decorative.
* `Finding` initially dropped contract-permitted `x_` extensions; now they round-trip.

## What is still not done (and is not hidden)

* Reward, data, verifier and environment: Phases 2–13, reported as `28 BLOCKED` checks.
* Branch protection and real CODEOWNERS handles: repository settings only a human admin can set.
* Reviewer 2 signature and the real deadline: human input.
