# OWNERSHIP

Four zones plus an orchestrator (master spec §4). One human owner per zone; an AI agent works
only inside its assigned zone unless the orchestrator grants an exception in writing.

| Zone | Directories | Human owner | AI roles | Phase 0 deliverable |
|------|-------------|-------------|----------|--------------------|
| A0 | cross-cutting: contracts, gates, CR, release | orchestrator (to be named) | this session | contracts v0.1, decisions, questions, risk register, verify runner |
| A | `gen/`, `spec/`, `episodes/`, generator tests | Owner A | gen architect, error engineer | `spec/anomaly_catalog.json`, `spec/invariants.json` |
| B | `env/`, `adapter/`, `harness/`, `scoring/`, `seal/` | Owner B | env/scoring/harness engineers | `adapter/` (unbound), `configs/environment/*`, `configs/scoring/*` |
| C | `verifier/`, `arena/`, `metamorphic/` | Owner C | verifier, red team | coverage in `spec/`, rubric checks DT-VER-*, RW-ATTACK-* |
| D | `judge/`, `tools/`, `docs/`, CI | Owner D | QA, docs, judge kit | `tools/*`, `docs/*`, `judge/rubric_map.json`, reports |

## Rules

1. **One owner per task.** A task card names exactly one accountable human owner.
2. **No cross-zone edits without an exception.** The exception is a line in the PR description
   plus an orchestrator approval recorded in `docs/CR/`.
3. **The verifier is never written by the generator owner** (REQ-ORG-001). If one person must
   cover both zones temporarily, `docs/INDEPENDENCE.md` §2 controls apply and the deviation is
   recorded in `docs/STATUS.md`.
4. **Frozen contracts.** `contracts/` changes require a CR plus a decision entry; the digest
   printed by `make verify` must change in the same commit.
5. **Test changes need justification.** Weakening a test to get a green build is forbidden
   (REQ-TEST-002); a CR citing the official specification is the only path.

## Status vocabulary for tasks

`TODO → IN_PROGRESS → BLOCKED / PARTIAL → DONE`, plus `DEFERRED` and `REJECTED` with a reason.
`DONE` requires: task card, commit, executed tests with output, independent review, GitHub or
local report update, and a handoff if another agent continues.
