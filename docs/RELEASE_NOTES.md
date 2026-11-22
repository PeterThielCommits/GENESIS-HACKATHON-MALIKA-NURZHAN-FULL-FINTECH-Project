# TwinLedger v1.0.0 — Genesis FinTech 2026 release candidate

**A self-auditing synthetic-finance benchmark: the ledger, the injected errors and
the proof that the score is real.**

TwinLedger generates a clean synthetic book, mutates it with accounting-meaningful
errors, exposes it through a read-only tool API, and scores a policy's findings
with an independent verifier. Everything — episodes, rewards, replays, reports —
is reproducible offline with nothing but Python.

`official_score_claimed: false`. This release reports **internal verification
results**, never a jury score (Master TZ §23.6).

---

## Verify it yourself (two commands, no network)

```bash
make verify        # lint + 12-gate Judge Kit + 477 tests  -> artifacts/reports/latest/
make rc-check      # verify + docs-verify + replay-all + release-audit
```

Python 3.11, standard library only. No install step, no downloads, no network.
A hardened offline container is provided as well:

```bash
make docker-check  # --network=none --read-only --cap-drop ALL, non-root
```

## What was measured for this release

| Claim | Command | Result |
|---|---|---|
| Verification suite | `make verify` | **12/12 gates PASS**, 477 tests, 20 evidence artefacts |
| Clean machine | fresh `git clone`, empty evidence dir | **12/12 PASS** |
| Determinism, all runs | `make replay-all` | **80/80 runs, 567 steps byte-identical** |
| Determinism, sealed replay | `make replay` | 5/5 byte-identical, Merkle root `d949fae3…` |
| No published claim drifts | `make docs-verify` | 22 facts, 11 checks PASS |
| Release audit | `make release-audit` | 6/6 PASS |
| Frozen contract surface | `freeze_release --verify` | 30 files, `0747baf0…` |

Release audit detail: 0 credentials in 494 files, 0 forbidden paths, 5 449 805
bytes (budget 50 MB), 109 runtime modules with **0** external dependencies, and
the official entrypoint imported from a foreign working directory with 5/5 tool
names accepted.

Baseline policies over D01..D20 (seed 2026, 20 scenarios each) — published in
the README generated block and re-measured by `make docs-verify`:

| Policy | Mean F1 | Mean return | Mean steps |
|---|---:|---:|---:|
| oracle (judge-side reference) | 1.0000 | +0.9920 | 4.0 |
| simple_reconciliation | 1.0000 | +0.9853 | 7.3 |
| random | 0.2500 | −0.5060 | 12.0 |
| mass_flagging | 0.0000 | −1.0000 | 1.0 |

## How the work was verified

The interesting part of this project is not that the tests pass — it is that each
gate was shown to **fail** when it should:

- a planted AWS key, an undeclared `requests` import, a forced `git add -f` of
  sealed truth, and an oversized file each produce a specific `FAIL`;
- a tampered metric and a tampered observation each break `replay-all`;
- an injected documentation drift produces `[DRIFT]` naming the exact line;
- a phantom decision ID produces `[PHANTOM_ID]`.

Every gate names its requirement ID, runs from a clean tree, and writes an
artefact (`REQ-JUDGE-002`). Optional checks are reported as explicitly SKIPPED,
never silently omitted (`REQ-JUDGE-003`).

## Known limitations

1. The official rubric weights are not published; internal verification is never
   presented as a score.
2. `eta = 0.05` is provisional (TZ §18).
3. `replay-all` replays recorded actions; it does not re-run the baseline
   policies, so policy-side changes are covered by `make official-eval` instead.
4. Baseline numbers derive from the committed `trajectories.jsonl`; regenerating
   it is a reviewer step, not part of `make verify`.
5. Difficulty calibration is validated on the D01..D20 set only.

The full, dated limitation list lives in `docs/LIMITATIONS.md`; the threat model
is in `docs/THREAT_MODEL.md`, and every deviation is recorded with its reasoning
in `docs/DECISIONS.md`.

## Documentation map

| Document | What it answers |
|---|---|
| `README.md` | Deploy and verify in two commands; every published number is generated |
| `docs/DESIGN.md` | How it is built, as built |
| `docs/API_USAGE.md` | The official entrypoint, worked example |
| `docs/POLICY_PROTOCOL.md` | Tool envelopes, error codes, budgets, limits |
| `docs/DEMO.md` | 3-minute demo and technical backup demo |
| `docs/LIMITATIONS.md` | What this does not do |
| `docs/THREAT_MODEL.md` | What it defends against, and how |
| `docs/INDEPENDENCE.md` | Why generator, verifier and scorer are separable |
| `docs/PHASE_REPORTS/` | Per-phase scope, defects, commands and evidence |

## Reproducibility

```bash
git clone <repo> && cd <repo>
python3.11 -m make verify      # or `make verify`
```

Expected: `verify: PASS`, exit 0, with `artifacts/reports/latest/verify_summary.json`
and 20 evidence artefacts. Any deviation is a bug worth reporting.
