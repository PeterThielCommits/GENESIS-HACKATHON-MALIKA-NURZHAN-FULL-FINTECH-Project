# Branch protection and repository settings

Phase 1 task 1.6 asks for branch protection. This file is deliberately a **human action list**:
an agent cannot enable repository settings here (it has no admin rights and no business asking
for them), and pretending the setting exists would be worse than the gap.

## Required settings on `main`

| Setting | Value | Why |
|---------|-------|-----|
| Require a pull request before merging | on | every contract change is reviewable |
| Required approvals | 1 (2 for `/contracts/**`) | D-0017 two-person review, extended to the contract set |
| Dismiss stale approvals on new commits | on | an approval must describe the diff that ships |
| Require status checks | `Phase gate (python 3.11)` | the CI job in `.github/workflows/verify.yml` |
| Require branches to be up to date | on | the gate must have run against the merge base |
| Require conversation resolution | on | an open objection is not a merge |
| Require linear history | on | the phase reports cite commits |
| Restrict force pushes / deletions | on | the archive and the digest are append-only |
| Require signed commits | recommended | not mandatory, because it would block contributors without keys |

## Required settings on the working branches

| Setting | Value |
|---------|-------|
| Allow force pushes | off |
| Require the `verify` workflow to pass | on |

## What happens without these settings

Nothing breaks immediately, and that is exactly the risk: without protection, a force push can
rewrite the frozen contract digest, and `make verify-core` would only catch it during the next
review. The golden file (`contracts/GOLDEN.json`) makes any such rewrite detectable, so the loss
is visibility, not correctness — record that trade-off here rather than leaving it implicit.

## CODEOWNERS

`.github/CODEOWNERS` maps directories to owners, but the GitHub handles are **placeholders**
(`@OWNER_A0_ORCHESTRATOR`, `@OWNER_CONTRACTS`, `@OWNER_SEAL`, `@OWNER_CI`, `@OWNER_TESTS`).
A human must replace them with real accounts; until then GitHub silently ignores those rules.
This is a known, listed gap, not an oversight.

## Checklist for the human who closes this

- [ ] Replace the five placeholder handles in `.github/CODEOWNERS`.
- [ ] Apply the settings above to `main`.
- [ ] Confirm the `verify` workflow appears as a selectable status check (it must run once first).
- [ ] Update `docs/STATUS.md` row "Branch protection" from `BLOCKED` to `PASS` with a screenshot
      or the settings URL as evidence.
