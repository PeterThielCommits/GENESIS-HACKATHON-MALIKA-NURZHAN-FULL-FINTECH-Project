# REMEDIATION_LOG — chronological

All work on branch `arena/45dc3a73-genesis-hackathon-malika-nurzh`, based on
`3a3988e`. Commits are listed in order.

## Step 0 — Input reconciliation

- Hashed the three uploads and compared with the vendored spec.
- `fintech-checks (1).txt` is **byte-identical** to
  `spec/official_fintech_checks_2026-11-20.md`
  (`sha256 2a597ebf…`), so the official requirements were already in the repo
  and every incompatibility found below is a project defect, not a missing
  requirement. Recorded in `INPUT_INVENTORY.md`.

## Step 1 — Read the official definitions in full

Extracted the scorable surface: Block 1 (C01–C20), Block 2 (D01–D20),
Block 3 (vectors 1–20 + M01–M12), Block 4 (P01–P20), engineering anchors
(0/1/2 × 5), matcher normalisation rules 1–8, τ tolerance, maximum-cardinality
matching, 1e-9 float tolerance, and the border decisions on step accounting.

## Step 2 — Executed the contract, not just the tests

Ran the official semantics directly against `judge_adapter.make_env()`.

| Probe | Result |
|---|---|
| C01–C04, C06–C20 | conform |
| C05 on fixture L (limit 50) | **fails at page 4** → BUG-TL-0002 |
| 11 published reward vectors vs `scoring/reward.py` | **10 of 11 wrong** → BUG-TL-0001 |
| M01–M12 matcher conventions | conform |
| adapter 3 exports, invalid submit | conform |
| 60 s boundary at 59.9/60.0/61.0 | conform |

## Step 3 — BUG-TL-0002 (P0): cursor tokens

- Measured the failure rate of the old layout: 65 of 1000 offsets unusable,
  first at offset 4.
- Replaced `raw || b"." || sig` + `rsplit` with `sig || raw` and a
  fixed-width `_SIG_LEN` prefix.
- Verified 1000/1000 round-trips and that all five tamper classes are still
  rejected.

## Step 4 — BUG-TL-0001 (P0): one reward implementation

- Delegated `compute_reward` to `compute_official_metrics` via a new
  `reward_metrics()` seam.
- `RewardBreakdown.eta`/`penalty` now report the applied weight (0.2).
- Left `configs/scoring/default.json` untouched (frozen); recorded D-18-01.
- Re-based the reward expectations in `test_reward_sanity`,
  `test_diagnostics`, `test_reward_properties` (P5), `test_property`, and the
  mutation suite's own arithmetic checks, each citing its official vector.
- Kept `precision_score`/`recall_score` vacuous-truth semantics for the
  generator cross-check and documented why.

## Step 5 — Follow-on: three disarmed mutants

- Mutation score dropped to 23/26 because MUT-07/08/13 patched a symbol no
  longer on the reward path.
- Added `reward_metrics()` as the live seam and re-pointed all three.
- 26/26 killed again.

## Step 6 — BUG-TL-0003 (P1): canonical token encoding

- The tamper test started failing once step 3 changed the layout, revealing
  that `token + "x"` was accepted.
- Added a canonical re-encode check; added two property-style tests.

## Step 7 — BUG-TL-0004 (P1): C05 test covered the wrong table

- Rewrote C05 to walk all four canonical tables with per-table exact counts.
- Confirmed it fails on the old cursor code with `BAD_CURSOR` at
  `ledger page 3`.

## Step 8 — Artifact regeneration and determinism proof

- `make official-eval` regenerated `trajectories.jsonl` (cursor format changed).
- Proved the change is confined to cursor tokens: 0 rows differ otherwise;
  metrics, final findings and initial observations identical; baselines
  unchanged to the digit.
- `make replay-all` → PASS 80/80, 567 steps.

## Step 9 — Full gate sweep

See `FIX_VERIFICATION_MATRIX.md`. Highlights: `make test` 502 OK,
official 55 OK, `make verify` 12/12 PASS, `make mutation-test` 26/26,
`make release-audit` 6/6, `make rc-check` PASS, freeze 30 files intact,
clean-extraction `make verify` 12/12 PASS in 65.8 s.

## Step 10 — Documentation truth

- Corrected `docs/PROJECT_CONTEXT.md` (it claimed the official rubric was not
  published).
- Added `D-18-01`.
- Regenerated the README doc-claims block (490 → 502 tests) via
  `verify_doc_claims.py --write`, and fixed the two hand-written counts that
  the generator does not own.

## Commits

| Commit | Content |
|---|---|
| `ca04f3f` | fix(scoring,env): reward consolidation, cursor repair, canonical encoding, C05 strengthening, test re-basing |
| `0afdbd8` | docs: D-18-01, PROJECT_CONTEXT correction, README facts, QUALITY_AUDIT registry |

## Deliberately NOT done

- **Not** edited: `contracts/`, `configs/`, `spec/`, `judge/rubric_map.json`,
  Master TZ text (all frozen; D-14-02).
- **Not** deleted: any failing test. Expectations were re-based with a cited
  official vector, never relaxed to match output.
- **Not** claimed: any gate PASS without running it. Docker is reported
  UNVERIFIED, not PASS.
- **Not** started: Phase 17 (not authorised).
