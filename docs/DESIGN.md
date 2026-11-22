# TwinLedger — Design

As-built design of the released system (v1.0.1). The original Phase 1 skeleton
notes are superseded by this document; the per-phase reports in
`docs/PHASE_REPORTS/` record how each layer arrived.

## 1. Layering and ownership

```
contracts/  ←  frozen boundary: schemas, version, canonical JSON, money, IDs
   ↑
core/  invariants/  →  primitives and INV-01..INV-17
   ↑
gen/  →  clean twin + 16 distractor families + 4 anomaly operators + truth diff
   ↑
verifier/  →  public-only Stage-1 discovery + ProofGraph (never imports gen/)
   ↑
env/  adapter/  →  public-only stateful environment, exact calculator, JSONL server
   ↑
scoring/  seal/  harness/  →  matcher, reward, Merkle receipts, 3-process runner
   ↑
arena/  metamorphic/  nlp/  →  baselines, red team, invariance, multilingual text
   ↑
judge/  tools/  →  Judge Kit gates, report synthesis, freeze, doc-claim checks
```

Dependencies point **downward only**, machine-enforced by
`tools/check_import_boundaries.py` (`RC-002`, release blocker). The generator and
the verifier are deliberately disjoint: a generator bug cannot silently become a
verifier assumption (`D-01-02`).

## 2. Frozen contracts

- Flat packages per Master TZ §6 (`D-01-02`); import rules are directory rules.
- Contracts are the frozen boundary (`D-01-01`): JSON Schema draft-07, validated
  by stdlib-only `contracts/validate.py` so offline runs never need `jsonschema`.
- Canonical JSON is the single hashing primitive (TZ §7.2): UTF-8,
  `ensure_ascii=False`, sorted keys, separators `(",", ":")`, no NaN/Inf,
  LF-terminated bytes, money as integer minor units, Decimal as pre-formatted
  string.
- Configs are versioned envelopes; `config_hash` = SHA-256 of canonical JSON
  (`REQ-CONTRACT-021`). Unknown config versions are bounded errors, never
  best-effort parses.
- Unknown public fields are rejected; extensions must be namespaced
  `x_twinledger_*` (`REQ-CONTRACT-003`).
- The 30 frozen files (contracts, configs, `judge/rubric_map.json`, Master TZ)
  are digest-locked in `configs/release_freeze.json`; `tools/freeze_release.py
  --verify` is a gate.

## 3. Truth lifecycle

```
clean C ──operators──► mutated M ──diff(C,M)──► candidate truth
                                    │
                          independent verifier on public M   (Stage 1)
                                    │
                          cross-check attestation          (Stage 2)
                                    │
                          commit-reveal seal + Merkle receipt
                                    │
                               episodes/
```

`diff(C, M)` proves **what changed**, never **that it is wrong**. Semantic
wrongness comes from the invariant catalog plus the independent verifier. This
distinction is the reason the reward cannot be gamed by "anything that differs
from the twin" (see `D-08-01`, zero common-mode verifier implementation, and
`D-08-02`, Stage-1/Stage-2 crosscheck separation).

## 4. Process boundaries

| Process | Sees | Never sees |
|---|---|---|
| P0 `harness` (supervisor) | everything, coordinates lifecycle | — |
| P1 `policy` (external client) | JSONL tool responses only | `episodes/`, `sealed/`, scoring, truth |
| P2 `env` (public-only) | `public/` (12 allowlisted files) | `sealed/`, truth, salts |
| P3 `scorer` (starts after P2 exits) | `sealed/truth.json` | the policy process |

Process separation alone is **not** called a sandbox. On Linux with user/mount/net
namespaces and `seccomp-BPF`, `harness/ns_launcher.py` adds private mount masking
over `episodes/` and `sealed/`, a read-only policy `cwd`, `PR_SET_NO_NEW_PRIVS`
and a syscall filter → `profile_id = linux-kernel-ns-seccomp-v1`
(`is_full_os_sandbox: true`). Elsewhere it degrades **honestly** to
`posix-subprocess-isolated-v1` with the unavailable controls listed
(`docs/LIMITATIONS.md` L2, `docs/THREAT_MODEL.md` §2).

## 5. Scoring design

- Canonical typed IDs (`JE:`, `INV:`, `CN:`, `PAY:`, `BANK:`, `FX:`, `CP:`).
- Exact match predicate: type + ID set + currency + amount within `tau` + a
  covering evidence set, every `evidence_id` resolvable in public data.
- Deterministic maximum-cardinality bipartite matching; ties broken by sorting
  truth `issue_id` by Unicode code points and taking the lexicographically
  smallest `(issue_id, finding_index)` list. Duplicate findings stay separate
  vertices.
- `Fraction`-exact arithmetic end to end; no float ever touches a reward.
- `return = clip([-1, 1], 2 * F1 - 1 - 0.2 * inspection_steps / 100)`.
  Clean book with no findings yields `f1 = 1`, `precision = recall = 0`.
- The step penalty is the organisers' fixed `0.2 * inspection_steps / 100`,
  implemented once (`scoring/official_scorer.compute_official_metrics`) after
  `D-18-01` collapsed two competing implementations into one. The frozen
  `configs/scoring/default.json` retains `eta: 0.05, provisional: true` as a
  historical record only; it no longer influences the reward. The *result* is
  never presented as an organiser score (`official_score_claimed: false`).

## 6. Evidence and verification design

- One command reproduces all evidence: `make verify` → 12 gates, and the complete
  artifact set indexed by `report_index.json` (the live count is published in the
  README generated block, never typed here).
- Every JSON report carries the TZ §23.5 envelope (code version, config hash,
  timestamp, platform, Python version, command); a violation is exit 2.
- Exit codes are contractual: `0` pass, `1` test fail, `2` config/contract,
  `3` resource/environment, `4` release blocker, `5` incomplete suite. Precedence
  `4 > 3 > 2 > 1 > 5 > 0`.
- Optional extras (e.g. `hypothesis`) skip **explicitly**; a critical skip can
  never yield exit 0.
- Documentation is part of the evidence: `tools/verify_doc_claims.py` re-measures
  every published number and fails if `README.md`/docs disagree.

## 7. Key data flows

```text
Build:     gen → verifier (public only) → seal → episodes/
Run:       policy ⇄ harness ⇄ env → trajectory → scoring → receipt
Reproduce: harness.replay → byte-identical responses + reward + receipt
Verify:    judge/verify.py → artifacts/reports/latest/
Assert:    tools/verify_doc_claims.py → artifacts/reports/doc_claims/
```

## 8. Module map

See `docs/CONTEXT/ARCHITECTURE_SNAPSHOT.md` for the directory-level map and
`docs/PHASE_REPORTS/PHASE-XX.md` for the reasoning behind each layer.
