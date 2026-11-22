# ARCHITECTURE_AUDIT — TwinLedger v3.0

## A-1 Zone layout as observed

| Zone | Module(s) | Responsibility | Boundary check |
|---|---|---|---|
| Contracts | `contracts/` | Frozen schemas, models, loaders, canonical JSON | frozen (30-file manifest) |
| Generator | `gen/`, `scoring/` (partly) | Deterministic episode synthesis, clean twin, truth/provenance | public-only outputs in `public/` |
| Environment | `env/`, `adapter/` | `reset`/`step`, tools, cursors, budget, clock | never loads `sealed/` |
| Scoring | `scoring/official_scorer.py` | Matcher + official reward, judge-side only | not importable by policy process |
| Judge kit | `judge/` | Gates RC-001…RC-012, mutation, robustness, performance | imports env + scoring |
| Harness | `harness/` | Isolated policy process, sandbox launcher, replay | process boundary |
| Verifier | `verifier/` | Independent accounting reconstruction | public data only |
| Adapter | `judge_adapter.py`, `adapter/` | Official three-function surface | thin, no policy logic |

Import-boundary scan (`make lint`): **CLEAN (REQ-ARC-001..007)**.

## A-2 The architectural defect this audit found

**Two modules implementing the same domain rule.** `scoring/reward.py` and
`scoring/official_scorer.py` both computed the reward, with different
formulas. Nothing in the architecture prevented it: there was no single
"scoring owner" module and no cross-check test.

This is not a local bug; it is a boundary failure. The honest fix was to
collapse the rule to one implementation and make the second module a view,
rather than to patch the formula in two places (which would have left the
same trap for the next agent).

Post-fix there is exactly one definition in the tree:

```
$ grep -rn "def f1_score\|def precision\|def compute_reward\|def compute_official_metrics" --include=*.py . | grep -v ^./tests/
./scoring/official_scorer.py:387:def compute_official_metrics(
./scoring/reward.py:147:def f1_score(          <- delegates
./scoring/reward.py:153:def precision_score(   <- delegates
./scoring/reward.py:251:def compute_reward(    <- delegates via reward_metrics
```

`f1_score`/`precision_score` are thin helpers, not second formulas:
`f1_score` delegates to `compute_official_metrics`; `precision_score` and
`recall_score` intentionally keep the generator-side vacuous-truth convention
(documented in `D-18-01`).

## A-3 Public/private separation

- `episodes/*/sealed/truth.json` and `sealed/provenance.json` are the only
  private data. `adapter/official_env.py` loads `public/` + `manifest.json`
  only.
- `.dockerignore` excludes every `sealed/` depth (fixed in the previous phase;
  `episodes/*/sealed/` alone did not match `episodes/dev/ep_x/sealed/`).
- `make release-audit` FILELIST verifies 498 tracked files contain 0
  forbidden paths.

## A-4 Layering violations found

**None.** The import scan is clean, and no runtime module imports `tests/` or
`tools/`.

## A-5 Complexity hotspots (informational, not defects)

| File | Bytes | Note |
|---|---:|---|
| `tools/demo_server.py` | 44,543 | Demo only; not on the scoring path |
| `gen/pipeline.py` | large | Episode synthesis; covers 20 official recipes + interaction scenarios |
| `scoring/official_scorer.py` | large | Official matcher + reward; heavily tested (32 official tests + mutation) |

`artifacts/trajectories/trajectories.jsonl` is 2.49 MB and is now the largest
tracked file — expected, since it is the published evidence set (80 runs ×
§09 fields).

## A-6 Architecture risks left open

1. `scoring/reward.py` still exists mainly for backwards compatibility with
   `arena/`, `judge/mutation_suite.py` and `judge/robustness_audit.py`. A
   future refactor should move those callers onto `official_scorer` directly
   and delete the shim. **Not done here** because it is a larger change than
   this audit's scope and the shim is now provably faithful.
2. `configs/scoring/default.json` keeps `eta`/`provisional` keys that no
   longer drive anything. Frozen; documented in `D-18-01`.
3. The policy process isolation relies on the judge launching it in the
   sandboxed child (`harness/isolated_runner.py`). An in-process caller gets
   weaker isolation; the README states this and does not overclaim.
