# RUBRIC_COMPLIANCE — official check definitions vs implementation

Source of truth: `spec/official_fintech_checks_2026-11-20.md` (byte-identical
to the jury copy handed to the team; see `INPUT_INVENTORY.md`).

`official_score_claimed: false`. Everything below is an **internal
verification** that the implementation satisfies each published check. It is
not a jury score and cannot be one.

Status vocabulary: `VERIFIED` (real run + artifact) · `PARTIAL` · `FAILED`.

---

## Block 1 — 20 contract tests (25 points)

All 20 are implemented 1:1 in `tests/official/test_block1_contracts.py`.
Each was additionally re-executed manually against `judge_adapter.make_env()`
(not only through the test file), because the test file itself can be wrong
(see BUG-TL-0004).

| # | Requirement | Manual probe result | Status |
|---|---|---|---|
| C01 | reset returns JSON-compatible `(observation, info)` | `json.dumps` OK on both | VERIFIED |
| C02 | first obs has task/manifest/policy/remaining_steps, no seed/truth | `['manifest','policy','remaining_steps','task']` | VERIFIED |
| C03 | manifest carries schema_version, episode_id, base_currency, period_start/end, timezone, record counts, rounding rules; numbers match data | all 12 keys present; `total_records=704` on L fixture matches files | VERIFIED |
| C04 | one valid `list_records` returns 5-tuple, bool flags, JSON result+budget | `int/bool/bool`, `['error','remaining_steps','result']` | VERIFIED |
| C05 | pagination on L, limit 50, no gaps/dups, **all rows reachable** | **was FAILED** (BUG-TL-0002); now 4 tables walked, ledger 5 pages 214/214 | VERIFIED (was P0 defect) |
| C06 | same cursor twice → same records, same order | identical lists, 50 rows | VERIFIED |
| C07 | `get_record` existing R1 → correct record, no truth | correct, no leak | VERIFIED |
| C08 | `get_document` existing D1, no arbitrary FS | correct; `/etc/passwd` → `NOT_FOUND` | VERIFIED |
| C09 | `calculator("0.1+0.2")` → decimal `0.3` | `0.3` | VERIFIED |
| C10 | non-arithmetic expression → controlled error, nothing executed | `__import__('os').system('id')` → `CALC_ERROR`; `open('/etc/passwd')` → `CALC_ERROR` | VERIFIED |
| C11 | `get_record` missing U → bounded error, step consumed, no crash | `NOT_FOUND`, 100→99 | VERIFIED |
| C12 | `get_document` missing U → bounded error, step consumed | `NOT_FOUND`, 99→98 | VERIFIED |
| C13 | unknown action → bounded error, step consumed | `UNKNOWN_ACTION`, 98→97 | VERIFIED |
| C14 | budget decrements once per request, error is not free | 100→96 after 4 actions | VERIFIED |
| C15 | submit → terminated, findings final, later actions cannot change them | `terminated=True`; next action `ALREADY_TERMINATED`; second submit rejected | VERIFIED |
| C16 | 99 inspections + submit as action 100 → accepted | `terminated=True, truncated=False` | VERIFIED |
| C17 | 100 inspections, no submit → truncated, empty findings | `terminated=False, truncated=True, remaining=0` | VERIFIED |
| C18 | reproducible 60 s limit → truncated, empty findings | fake clock: 59.9 s accepted, 60.0 s `TIME_LIMIT` + truncated | VERIFIED |
| C19 | closed mode: inspection rewards `0`, numeric; truth only judge-side | rewards `{0}`, `type=int`; train mode returns `0.998` | VERIFIED |
| C20 | no truth/provenance/seed/answers in policy channel; no shell/SQL/FS/network | 7 attack vectors all bounded, `leak=False`; code review: no `eval`/`exec`/`pickle`/`os.system`/`shell=True` in runtime tree | VERIFIED |

## Block 2 — 20 closed episodes (25 points)

`tests/official/test_block2_episodes.py` builds all 20 from
`official_d20_recipes(seed=2026)` and asserts, per episode:

- scenario matrix composition (5 clean, 3 duplicate, 3 partial/missing,
  2 FX, 2 period, 3 interaction #1, 2 interaction #2);
- `provenance.structural_diff` empty for clean, non-empty for dirty;
- an **independent** verifier (`discover()` → `crosscheck()`, not our matcher)
  reaches FP=0, FN=0, F1=1 on every episode;
- every evidence set is reachable through public tools;
- an oracle submission via `judge_adapter.score_episode` reaches F1=1.0 and
  `return=0.98` (10 inspection steps).

Status: **VERIFIED**. Both anomalies the case requires (interaction #1
FX×period, interaction #2 duplicate×partial) are documented in `README.md`.

## Block 3 — 20 matcher/reward vectors (25 points)

`tests/official/test_block3_scorer.py` — 32 tests: vectors 1–20 plus worked
examples M01–M12. Re-executed manually for M01–M12 against
`score_official_findings`; all match the published expectations:

```
M01 reorder+dup affected -> 1,0,0      M06 currency case     -> 0,1,1
M02 extra unaffected     -> 0,1,1      M07 amount+1 tau=0    -> 0,1,1
M03 superset evidence    -> 1,0,0      M08 tau=1 +1/+2       -> 1 / 0
M04 U in evidence        -> 0,1,1      M09 amount str/bool   -> -1 / -1
M05 11 evidence ids      -> return -1  M10 max-cardinality   -> 2,0,0
M11 truth order swap     -> 2,0,0 (same reward)
M12 dup correct findings -> 1,1,0, return 47/150
```

Reward vectors 1/2/3/5/13/14/15/16/17 reproduced exactly through
`scoring/reward.compute_reward` **after** BUG-TL-0001 was fixed. Before the
fix, 10 of 11 were wrong.

Status: **VERIFIED**.

## Block 4 — 20 paired checks (15 points)

`tests/official/test_block4_paired.py` (25 assertions) applies
`transform_episode_copy` per the published matrix (P01–P05 permutation only,
P06–P10 bijective ID remap, P11–P20 both) and asserts: determinism on repeat,
oracle equivalence after inverse ID mapping, exact equality of
TP/FP/FN/P/R/F1/return at equal `inspection_steps`, and no new leak channel /
FX semantic key intact.

Status: **VERIFIED**.

## Engineering anchors (10 points)

| Criterion | Evidence | Score basis |
|---|---|---|
| Single documented start command | `make verify` runs the whole gate set with no manual step; `make help` lists 19 targets | 2 |
| Version/config pinning | `configs/release_freeze.json` (30 files, `aggregate_sha256=0747baf0…`), `config_hash` in every artifact, `python_version` + `platform` recorded in `performance_report.json` | 2 |
| Trajectories | `artifacts/trajectories/trajectories.jsonl`, 80 runs, §09 fields, replayable, no truth in observations | 2 |
| Measured failure analysis | `artifacts/reports/latest/robustness_report.json`, `shortcut_audit.json`, `docs/FAILURE_ANALYSIS.md` — measured numbers, cause, re-check | 2 |
| Honest limitations | `docs/LIMITATIONS.md` linked to scenarios; `official_score_claimed: false` everywhere | 2 |

Basis for each is quoted in `RUBRIC_TRACEABILITY.csv`.
