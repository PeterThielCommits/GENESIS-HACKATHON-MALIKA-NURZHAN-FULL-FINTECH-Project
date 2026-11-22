# Current State — 2026-11-22 (Phase 17 deep execution, release v1.0.2)

> **Latest session (2026-11-22, branch `arena/4c2f056f-genesis-hackathon-malika-nurzh`,
> based on `main` @ `6f25a90`): Phase 17 re-executed against the strict reading of
> its exit gate — the release must be restorable *and* verifiable from the
> repository alone.**
>
> | Command / condition | Result |
> |---|---|
> | `python3 tools/freeze_release.py --verify` | **PASS** — 30 frozen contract files intact, `0747baf0…` |
> | `python3 tools/evidence_freeze.py --verify` | **PASS** — every tracked release file matches `docs/EVIDENCE/evidence_freeze.json` |
> | `python3 tools/release_evidence.py --verify` | **PASS** — the release archive is honest, self-consistent and current |
> | `make verify` (full Judge Kit) | **PASS 12/12** gates, 588 tests, 20 evidence artifacts |
> | `make docs-verify` | **PASS** — 22 measured facts, 22 checks (new: `C-ARCHIVE`) |
> | `make replay-all` | **PASS** — 80/80 runs, 567 steps byte-identical |
> | `make release-audit` | **PASS 6/6** — secrets, file list, size, deps, entrypoint, submission |
> | `tools/check_import_boundaries.py` | **CLEAN** (REQ-ARC-001..007) |
> | `official_score_claimed` | **false** everywhere; `Q-ORG-01` / `Q-ORG-02` / `Q-DOC-01` remain **OPEN** (human decisions) |
>
> Docker-offline verification remains **CI-authoritative**: no container runtime
> exists on the execution host; the local namespace check
> (`tools/offline_local_check.py`) is supporting evidence only, with its exact
> scope recorded in `docs/EVIDENCE/offline-local-2026-11-22.json`.

- Active branch: `arena/4c2f056f-genesis-hackathon-malika-nurzh`, base
  `6f25a90` (`main`, merge of PR #28). The merge commit of the Phase 17 PR is
  the target of the **`v1.0.2`** tag.
- **Phases 0–17 are `DONE`** (see `docs/STATUS.md`). The repository is
  feature-frozen; this session added audit/replay tooling only — no runtime
  behaviour of the benchmark changed.
- **Phase 16 remains the release** (`v1.0.1`, the recommended submission
  artifact). `v1.0.2` is a patch release that adds the Phase 17 evidence
  archive and fixes four published-evidence defects; it does not change the
  contract surface.

## What changed in this session

| Area | Change |
|---|---|
| Phase 17 archive | `tools/evidence_freeze.py` (release-surface digest + report verdicts) and `tools/release_evidence.py` (reconstructable release archive), `docs/EVIDENCE/` |
| Gates | `make evidence-write` / `make evidence-verify`, wired into `make rc-check` and the CI `core` job; `C-ARCHIVE` in `tools/verify_doc_claims.py`; `tests/judge/test_release_freeze.py` turns the contract freeze into a test |
| Defects | BUG-TL-0005 (published formula), BUG-TL-0006 (published score contract), BUG-TL-0007 (stale "provisional" wording), BUG-TL-0008 (documentation gate's artifact contract) — all non-frozen, each with a failing-on-old-code regression test |
| Docs | `docs/STATUS.md`, `docs/LIMITATIONS.md` (L8–L10), `docs/DECISIONS.md` (`D-17-02`, `D-17-03`), `docs/CHANGELOG.md`, `docs/RELEASE_NOTES.md`, `docs/PHASE_REPORTS/PHASE-17.md`, `docs/HANDOFF/phase-17-evidence-freeze.md`, `docs/CONTEXT/NEXT_AGENT.md` |

## Latest measurements (this session, 2026-11-22)

| Command / condition | Result |
|---|---|
| `make verify` (working tree) | **exit 0** — 12/12 gates, 588 tests (1 optional skip), 20 artifacts |
| `make replay-all` | **80/80** runs, **567** steps byte-identical |
| `make release-audit` | **6/6** PASS |
| `python3 tools/verify_doc_claims.py` | **22** measured facts, **22/22** checks PASS |
| `python3 tools/freeze_release.py --verify` | **30** files intact, `0747baf0…` |
| `python3 tools/evidence_freeze.py --verify` | release surface intact (one aggregate digest) |

RC-001 records explicit optional skips (bootstrap/optional); there is no critical
skip. `official_score_claimed: false` everywhere.

## Open items (none block the release)

1. **`Q-ORG-01` / `Q-ORG-02` — organisational independence is unevidenced.**
   The verifier was not built by a different human owner; this repository came
   from AI agents in one session context. The *technical* separation is proven
   (`RC-002` + runtime file-open spy + the `independent_verifier/`
   re-derivation), the organisational half is disclosed, not claimed. Needs a
   human owner: re-derive the verifier under a separate context, or accept and
   keep the disclosure. See `docs/INDEPENDENCE.md`.
2. **`Q-DOC-01`** — whether the 16-family distractor catalogue should appear in
   narration at all. Currently derived per-episode; not published. OPEN
   (judgement).
3. **Narrative behavioural claims** are mechanical for the numeric and
   structural axes (`C-PATHS`, `C-DATADICT`, `C-DEMO`, `C-WORKBENCH-API`,
   `C-COMMANDS`, `C-REWARD`, `C-COUNTS`, `C-EVIDENCE`, `C-ARCHIVE`,
   `C-SCORE-HONEST`, `C-QORG-OPEN`); prose beyond these pins still needs
   human review.
4. **The evidence freeze is per-commit** (limitation L8): a later patch release
   needs its own archive. That is the design, not a defect.

## Next actions

1. Human owner answers `Q-ORG-01`; record acceptance in `docs/DECISIONS.md` or
   scope a separate verifier re-derivation (see `docs/CONTEXT/NEXT_AGENT.md`).
2. Nothing else is pending for the release: `v1.0.2` is cut, documented and
   tagged; `v1.0.1` remains the recommended submission artifact.
3. If a future defect is found in the released artifact, fix on a new branch,
   re-run `make evidence-write` in the same commit, and let the fix ride the
   next patch release (`v1.0.3`); do not move `v1.0.1` or `v1.0.2`.
