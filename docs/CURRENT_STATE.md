# Current State — 2026-11-22 (post structural audit)

- Active branch: `arena/a30551a9-genesis-hackathon-malika-nurzh`, base `e0a2bbf`
  (`main`, merge of PR #24).
- **Phase 15 structural audit DONE, EXIT GATE 15 PASS** on the stricter reading of
  the gate text. Report: `docs/PHASE_REPORTS/PHASE-15-STRUCTURAL-AUDIT.md`;
  decisions `D-15-04`, `D-15-05`, `D-15-06`, `D-15-07`.
- **What changed and why:** the documentation gate verified only that published
  *numbers* match artifacts. It now also verifies that published *shapes* match the
  repository — 7 new detectors (`C-PATHS`, `C-DATADICT`, `C-DEMO`,
  `C-WORKBENCH-API`, `C-COMMANDS`, `C-REWARD`, `C-COUNTS`), with negative tests.
  The initial 19 structural defects are fixed. Follow-up fixed an ASCII-console
  crash and two stale prose totals missed by the old denylist (`D-15-07`).

## Latest measurements (historical commands labelled)

| Command | Result |
|---|---|
| `make verify` (empty evidence dir) | **12/12 PASS**, 47.416 s, 20 artifacts, **540 tests**, `critical_skipped=0` |
| ASCII-only `make verify` (empty evidence + trajectories) | **12/12 PASS**, 45.443 s, zero non-ASCII bytes, zero critical skips |
| `make verify-core` (initial audit) | 6/6 PASS, 41 s |
| `make docs-verify` | **22 measured facts, 18/18 checks**, PASS |
| `make lint` | `import boundary scan: CLEAN (REQ-ARC-001..007)` |
| `python3 tools/freeze_release.py --verify` | **30 frozen files intact**, `0747baf0…` |
| `python3 -m unittest tests.judge.test_doc_claims` | **60 tests OK** (was 25) |
| `python3 tools/demo_walkthrough.py` | 6 segments, `full_os_sandbox=True` |
| order-independence (`verify-core`→`docs`, `report`→`docs`, `docs`×2) | all exit 0 |

RC-001 in the clean normal run records 19 bootstrap/optional test skips; the
overall summary records 20 optional skips (including non-test checks). The ASCII
run without trajectories records 25 test skips / 26 overall optional skips.
These are explicit positional skips; neither run has a critical skip.
The populated-evidence regression suite passes 540 tests with one optional skip.

No frozen file changed (`contracts/*`, `configs/*`, `judge/rubric_map.json`,
Master TZ untouched). `official_score_claimed: false`.

## Open items (none block the next phase)

1. **`Q-ORG-01` — organisational independence is unevidenced.** The verifier was
   not built by a different human owner; this repository came from AI agents in one
   session context. The *technical* separation is proven (`RC-002` + runtime
   file-open spy). Needs a human owner: re-derive the verifier under a separate
   context, or accept and keep the disclosure. See `docs/INDEPENDENCE.md`.
2. **`Q-REL-01` — should `v1.0.1` be cut?** Tag `v1.0.0` (`8da0af2`) still carries
   the `.dockerignore` defect that ships `sealed/truth.json` into the image
   (`D-16-02`). The fix is on `main`, not in the tag. Release-authority decision.
3. **Prose describing behaviour is only partly mechanical.** `C-DATADICT`,
   `C-DEMO` and `C-WORKBENCH-API` pin the three shapes that mattered most; narrative
   claims about *how* something behaves still rely on review.

## Next actions

1. Human owner answers `Q-ORG-01`, then either records acceptance in
   `docs/DECISIONS.md` or scopes a separate verifier re-derivation.
2. Decide `v1.0.1`; if approved, tag from `main` after `make rc-check` on the
   reviewed commit, and note the image-content fix in the release body.
3. `Phase 17` remains complete as recorded; no re-freeze is required by this
   session because no frozen file changed.
