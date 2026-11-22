# INPUT_INVENTORY — TwinLedger v3.0 forensic audit

Audit branch: `arena/45dc3a73-genesis-hackathon-malika-nurzh` (base `3a3988e`).
Inventory recorded at commit `ca04f3f`. Date: 2026-11-21.

## 1. Inputs supplied for this audit

| # | File | Bytes | SHA-256 | Role |
|---|---|---:|---|---|
| 1 | `fintech-checks (1).txt` (upload) | 53,434 | `2a597ebfb94daec700ba9b1b09d62c032366e788c6e992486d444e063be8d870` | **Official jury check definitions.** Priority-1 truth. |
| 2 | `TwinLedger_v3_Master_TZ_AI_Agents.txt` (upload) | 237,211 | `a46cdb63bb4b41aabb95a842406f5a4fff91e218ead1e4f97b22b60d1c748e36` | Master TZ (team specification). |
| 3 | `TwinLedger_Universal_Phase_Execution_Prompt.txt` (upload) | 41,418 | `9139e28e3cf6dcc14baaa947f11cdb918f50565927fe5ce7ee3263ad28d04e04` | Phase execution prompt. |

## 2. Critical inventory finding

`fintech-checks (1).txt` is **byte-identical** to the file already vendored in
the repository:

```
$ sha256sum "fintech-checks (1).txt" spec/official_fintech_checks_2026-11-20.md
2a597ebfb94daec700ba9b1b09d62c032366e788c6e992486d444e063be8d870  fintech-checks (1).txt
2a597ebfb94daec700ba9b1b09d62c032366e788c6e992486d444e063be8d870  spec/official_fintech_checks_2026-11-20.md
$ diff <(cat "fintech-checks (1).txt") spec/official_fintech_checks_2026-11-20.md && echo IDENTICAL
IDENTICAL
```

Consequences:

- The official definitions were **available to the implementation** the whole
  time. Any incompatibility found below is a defect in our code, not a
  missing requirement.
- `spec/official_fintech_checks_2026-11-20.md` can be used as the canonical
  citation for every official check; the upload adds no new requirement.
- Documents in the repo that claim "the official rubric is not published"
  were stale. `docs/PROJECT_CONTEXT.md` was corrected under `D-18-01`.

## 3. Official requirement surface extracted from the check document

| Block | Content | Points | Repo test surface |
|---|---|---:|---|
| Block 1 | Contract tests C01–C20 | 25 | `tests/official/test_block1_contracts.py` (20 tests, 1:1) |
| Block 2 | Closed episodes D01–D20 | 25 | `tests/official/test_block2_episodes.py` |
| Block 3 | Matcher/reward vectors 1–20 | 25 | `tests/official/test_block3_scorer.py` (32 tests incl. M01–M12) |
| Block 4 | Paired invariance P01–P20 | 15 | `tests/official/test_block4_paired.py` |
| Engineering | 0/1/2 anchors × 5 criteria | 10 | `judge/rubric_map.json`, `make verify` |
| Total | | 100 | |

Additional normative material in the same document that is *not* a scored
block but is binding: adapter interface and access boundary, fixtures C/E/L/U,
the exact matcher conventions (normalisation §1–8, τ tolerance, maximum
bipartite matching with deterministic tie-break, numeric comparison 1e-9),
worked examples M01–M12, and the border decisions on step accounting
(submit counts toward the 100-action budget but not toward
`inspection_steps`).

## 4. Other inputs consulted

| Source | Use |
|---|---|
| `spec/` (contracts, anomaly catalog, invariants) | Frozen contracts; not edited |
| `judge/rubric_map.json` | Internal gate definitions (12 gates) |
| `configs/release_freeze.json` | 30 frozen files; `freeze_release --verify` |
| `docs/DECISIONS.md` | Prior decisions D-01…D-17 authority for conflicts |

## 5. Inputs deliberately NOT modified

All three uploads are read-only. No user-provided input file was deleted,
moved or rewritten (`§28` prohibition).
