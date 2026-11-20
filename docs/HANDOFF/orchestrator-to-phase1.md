# Handoff — Phase 0 → Phase 1

## Sender and receiver
- From: A0 orchestrator (Phase 0 session, 2026-11-20)
- To: Phase 1 owner (repository foundation hardening)
- Human owner: to be assigned (Owner D for CI/docs, A0 for contracts)

## Exact repository state
- Repository: `roadtoabroad346-commits/GENESIS-HACKATHON-MALIKA-NURZHAN-FULL-FINTECH-Project`
- Branch: `arena/6e3d45bc-genesis-hackathon-malika-nurzh`
- Base commit: `c961a009611e1711463f5116b2df926bb4726de8`
- Working tree: clean after the Phase 0 commit
- PR: see the branch (created from this session; check `gh pr list`)

## Completed work
- Contracts v0.1.0 (11 typed schemas + definitions, 35 fixtures, digest
  `d9b438cc58bdbb40317ee49024cdfa1fe1ccf56e4ab09cdc752093155f0016bc`).
- Adapter boundary, unbound and fail-closed.
- Configs and spec catalogs for every provisional value.
- Tooling: canonical JSON, schema validator, requirement extractor, boundary scan,
  governance check, verify runner.
- Governance records: 20 decisions, 14 questions + deadline finding, 16 assumptions,
  186 requirements, risk register, threat model, limitations, independence, data dictionary.
- 40 internal rubric checks (12 implemented, 28 `BLOCKED`) in `judge/rubric_map.json`.
- Verification harness `tools/verify.py` + 188 stdlib tests, all green; 13 governance checks;
  import-boundary scan; phase report generated from the run.

## Current architecture facts
- Contracts: `contracts/version.json`, payload version `1.0.0`, set version `0.1.0`.
- Canonical JSON: `tools/canonical_json.py` (floats rejected, Decimal as text).
- Config versioning: every config has `config_version`, `status`, `provisional`.
- Import zones: see `tools/check_import_boundaries.py` `FORBIDDEN` table.
- Verify profiles: `--profile core` (Phase 0 gate) and default (full matrix).

## Gate evidence to reproduce first (do not trust this text, run it)
| Command | Expected |
|---------|----------|
| `python3 -m unittest discover -s tests -t . -p 'test_*.py'` | `Ran 188 tests ... OK` |
| `python3 -m tools.check_governance` | `governance: PASS`, 13/13 |
| `python3 -m tools.check_import_boundaries` | `PASS (34 files)` |
| `python3 -m tools.verify --profile core` | exit `0`, `PASS_WITH_PLANNED_CHECKS_BLOCKED`, 12 passed / 28 blocked |

If any of these disagree, stop and report it — the environment, not the documentation, is the
truth (REQ-JUDGE-002).

## Open issues
- Reviewer 2 signature on `docs/official/CONTRACT_SIGNOFF.md` is PENDING (human).
- Submission deadline unknown (`docs/QUESTIONS.md` OPEN-0).
- No CI workflow file yet (Phase 1 task).
- Licence not chosen (Phase 16).

## Status of this handoff
Phase 1 (foundation) was executed in the same session and closed as `PASS_WITH_OPEN_ITEMS`
(`docs/PHASE_REPORTS/PHASE-01.md`). This document therefore also serves as the Phase 1 → Phase 2
handoff; the items below are done unless marked otherwise.

## Exact next steps
1. `make verify-core` and confirm every status matches `docs/STATUS.md`.
2. ~~Execute `docs/TASKS/T-1-01-contracts-hardening.md`~~ — done: CI, typed models, golden freeze.
3. ~~Add CI~~ — done: `.github/workflows/verify.yml`, linted by `tools/check_ci.py`.
4. Phase 2: `docs/TASKS/T-2-01-money-primitives.md` (money, time, IDs, invariants).
5. Human: sign Reviewer 2, record the deadline, apply branch protection, replace the CODEOWNERS
   placeholders.

## Do not repeat / do not change
- Do not rebuild `tools/` or the contract set from scratch.
- Do not bind `adapter/` to a guessed contract.
- Do not "fix" the PENDING signature by signing it.
- Do not weaken `tests/` to make CI green.

## Acceptance checklist for receiver
- [ ] Read `AGENTS.md` and `docs/PROJECT_CONTEXT.md`.
- [ ] Verified commit and clean status.
- [ ] Reproduced `make verify-core` output.
- [ ] Confirmed the next task scope.
- [ ] Added a new agent report after changes.
