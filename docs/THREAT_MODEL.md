# TwinLedger — Threat Model (Phase 1)

## Assets

Sealed truth, provenance, seeds, salt, scorer internals, heldout
episodes, canary tokens.

## Trust boundaries

Policy | Env (public only) | Harness | Scorer (sealed, post-episode)
| Judge. Env never loads truth (REQ-PROD-005). Policy never imports
scorer/verifier/generator (REQ-ARC-003).

## Attackers / surfaces

- Policy reading sealed files / scorer memory → mitigated by process
  separation + read-only public mount + no sealed path in policy/env
  containers (Phase 9). Phase 1: import-boundary scan only.
- Truth leak via observation/info/error/log/metadata → bounded errors,
  no sealed fields in public schemas (Phase 5 tests).
- Shortcut via ID/order/amount metadata → metadata-only classifier
  audit (Phase 12).
- Reward exploits (duplicates, split, flag-all) → matcher properties +
  attack suite (Phases 6/12).
- Prompt injection in document text → separate robustness track
  (Phase 11), never part of official reward.
- Timing/size side channels → equivalence tests with predeclared
  margin (Phase 12); `p > 0.05` is not equivalence.

## Residual risks

Process separation ≠ sandbox. Timing tests cannot prove absence of all
side channels. Commit-reveal proves integrity after commitment, not
initial truth correctness (needs diff + invariants + verifier).
