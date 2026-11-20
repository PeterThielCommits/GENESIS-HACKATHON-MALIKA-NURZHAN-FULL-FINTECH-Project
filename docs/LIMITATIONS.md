# TwinLedger — Limitations (honest, specific)

## What is NOT guaranteed

- **No official score.** The organiser rubric is unpublished in this
  repo; `make verify` reports internal verification status only
  (`official_score_claimed: false`). No 100/100 or victory claims.
- **No accounting correctness claim.** Success on TwinLedger does not
  prove real-audit quality. Synthetic data only.
- **No sandbox claim.** Phase 1 has no process isolation yet. Future
  process separation will be described exactly as implemented; OS-level
  sandboxing only if actually enabled.
- **No completeness claim for evidence sets** until Phase 8 ablation
  tests exist.
- **No statistical claims** (learnability, shortcut AUC, timing
  equivalence) until Phases 12–13 experiments run with predeclared
  margins and grouped splits.

## Phase 1 scope limits

- Contracts/canonical/models/boundaries/CI/docs only. Generator, env,
  matcher/reward, verifier, harness, seal, arena are stubs or absent.
- `make build-episodes|replay|audit-shortcuts|mutation-test` are
  explicitly SKIPPED stubs (exit 0 with message, never PASS).
- Docker image is a smoke-test wrapper; base-image digest pinning is a
  Phase 16 task.

## Provisional parameters

Tool names, reward (ETA=0.05), budgets (100 steps, page 50), affected-ID
rules, rubric weights — all provisional (A-001…A-016). See
`docs/DECISIONS.md`, `docs/QUESTIONS.md`.

## Unsupported accounting policies

Only the policies expressible in `contracts/policy.schema.json`
(monthly/quarterly periods, 3 FX date rules, 2 fallback rules,
2 quote conventions, service/issue/delivery recognition). Anything
else needs a CR + new fixtures.
