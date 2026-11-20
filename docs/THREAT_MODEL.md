# THREAT MODEL

Scope: the TwinLedger benchmark run — build time (episode generation) and evaluation time
(policy → harness → env → scorer). This document states assets, attackers, surfaces,
controls and residual risk. If a control is not enabled, it is not claimed (D-0012).

## 1. Assets

| Asset | Why it matters |
|-------|----------------|
| `sealed/truth.json` | the answer key; leaking it makes every score meaningless |
| `sealed/provenance.json` | mutation parameters and distractor facts |
| salt / commitment | pre-run secrecy of the truth |
| scorer code + config | tampering changes the score without changing the agent |
| held-out episodes | contamination invalidates generalisation claims |
| trajectory + receipts | the evidence that a run happened as reported |
| policy process boundary | the only channel an agent should influence |

## 2. Adversaries

| Adversary | Capability | Goal |
|-----------|------------|------|
| Honest-but-curious policy | reads all public data, can issue any allowlisted tool call | infer truth from shortcuts (IDs, ordering, metadata, error shapes, timing) |
| Cheating policy | can read its own cwd, env vars, process list | find sealed files, scorer state, or another process's memory |
| Prompt-injecting document | text inside a synthetic document | make the policy follow instructions and report a wrong finding |
| Careless developer | commits artifacts, logs a seed, prints truth in a debug branch | accidental leakage into Git or logs |
| Reward gamer | duplicates, splits, merges, tolerance edges, flag-all | inflate reward without doing the audit |

## 3. Trust boundaries and controls (actual status)

| # | Boundary | Control | Status at Phase 0 | Evidence / owner |
|---|----------|---------|-------------------|------------------|
| 1 | policy → env | JSONL over stdin/stdout, versioned envelope | PLANNED (Phase 5/8) | REQ-ARC-006 |
| 2 | env → public data | env loads only `public/`, read-only | PLANNED (Phase 5/8) | REQ-ARC-004 |
| 3 | env ↔ sealed | no sealed path in env cwd or config | DESIGNED, tested Phase 8 | REQ-SEAL-001 |
| 4 | policy ↔ sealed | no sealed path in policy cwd; no episode path handed to policy | DESIGNED, tested Phase 8 | REQ-SEAL-002 |
| 5 | policy ↔ scorer | scorer process starts after env close; no shared socket/pipe | DESIGNED, tested Phase 8 | REQ-SEAL-003 |
| 6 | environment variables | allowlist only; no secrets passed | PLANNED (Phase 8) | REQ-SEAL-004 |
| 7 | argv / shell | fixed argv, `shell=False`, no string interpolation | PLANNED (Phase 8) | §16.2 |
| 8 | Git | sealed/hidden/generated data ignored, policy documented | **ENABLED** | `.gitignore`, `GOV-GIT-01`, D-0008 |
| 9 | reports | no truth, seed, salt or held-out data in reports | **ENABLED (docs)**; Phase 12 adds canary scan | REQ-GH-007, REQ-JUDGE-005 |
| 10 | claims | automated scan blocks "official score"/"100/100"/guaranteed-win claims | **ENABLED** | `GOV-CLAIMS-01`, R-24 |
| 11 | OS sandbox (separate uid, namespaces, seccomp, cgroups) | not available in this environment | **NOT ENABLED** | `docs/LIMITATIONS.md` |
| 12 | network isolation at runtime | static import scan now; runtime socket block in Phase 16 | PARTIAL | `EN-OFFLINE-01`, REQ-OPS-001 |

## 4. Attack surfaces and specific tests planned

| Surface | Probe | Test phase |
|---------|-------|-----------|
| observation fields | attempt to read seed, truth, mutation names | 8 |
| `info` dict | ask for diagnostics in closed mode | 8 |
| error messages | compare `NOT_FOUND` for existing-but-forbidden vs missing IDs | 5, 12 |
| cursor | wrong table, stale snapshot, forged token, replay | 5, 12 |
| pagination | ordering/rounding biases around inserted rows | 12 |
| timing | response-time distribution per row class | 12 |
| IDs | sequential blocks, checksum patterns, styles A–D | 12 |
| tool budget | free repeat requests after errors or after submit | 5 |
| resubmit | overwrite a submission after `submit` | 5 |
| scorer | duplicate/split/merge/flag-all/tolerance-edge submissions | 9, 12 |
| text | prompt injection inside documents | 11 |
| build | committed artifacts, seeds, salts in Git | 0 (**enabled**) |

## 5. Residual risks we accept and state publicly

1. **No OS-level sandbox** in the development environment. Process separation, path
   discipline and data-flow rules are real controls; "sandbox" is not claimed.
2. **A compromised developer machine** can read sealed truth. Commit-reveal detects truth
   changes after commitment, not a wrong truth written before it (R-10).
3. **Shortcut thresholds** are statistical thresholds, not proofs. Phase 12 reports an
   equivalence margin instead of "p > 0.05 therefore safe" (R-12).
4. **Commit-reveal proves integrity, not correctness.** Correctness comes from diff checks,
   invariants, the independent verifier and evidence reachability.
