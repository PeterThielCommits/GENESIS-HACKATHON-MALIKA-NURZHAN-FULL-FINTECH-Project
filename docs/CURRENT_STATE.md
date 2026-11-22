# Current State — 2026-11-22 (Phase 16 release v1.0.1 + post-release risk-closure round)

> **Latest session (2026-11-22, branch `arena/d0407793-genesis-hackathon-malika-nurzh`,
> based on `main` @ `3b83864`): Phase 16 §7 risks closed with evidence.**
>
> | Command / condition | Result |
> |---|---|
> | Independent re-derivation, on-disk episodes | **10/10 signature-identical** to committed `verifier_report.json`, identical `episode_public_hash` |
> | Independent re-derivation, official `D01..D20` (`master_seed=2026`) | **F1 = 1 exact, FP = 0, FN = 0** on all 20; evidence enumeration complete |
> | `docs/EVIDENCE/independent-rederivation-2026-11-22.json` | written, verdict `pass: true` |
> | `tools/offline_local_check.py` (userns+netns, read-only bind of the tree) | **540→548 tests OK (skipped=26)**, no network route, read-only source tree |
> | `docs/EVIDENCE/offline-local-2026-11-22.json` | written, `static_audit_pass: true`; CI `docker-offline` on `main` success (run `45021422570`) |
> | `python3 tools/verify_doc_claims.py` | **21/21 checks PASS** (new: `C-EVIDENCE`, `C-SCORE-HONEST`, `C-QORG-OPEN`) |
> | GitHub release `v1.0.0` notes | supersession banner added; tag `v1.0.0` **not** moved; repo docs already pointed to v1.0.1 |
> | `official_score_claimed: false` | everywhere; `Q-ORG-01` / `Q-ORG-02` remain **OPEN** (organisational separation is a human decision) |
>
> Docker-offline verification remains **CI-authoritative**: no container runtime
> exists on the execution host; the local namespace check is supporting evidence
> (exact scope in `docs/EVIDENCE/offline-local-2026-11-22.json`).

- Active branch: `arena/3af502e1-genesis-hackathon-malika-nurzh`, base `9737961`
  (`main`, merge of PR #25). This branch carries the v1.0.1 release docs; the
  merge commit of its PR is the `v1.0.1` tag target.
- **Phase 16 re-executed in full; EXIT GATE 16 PASS** — release **`v1.0.1`**
  (annotated tag object `3601493…`, target merge commit `640c585`, PR #26) is cut
  and published (`D-16-03`). `v1.0.0` retained for history; it ships the
  `.dockerignore` sealed-truth defect (`D-16-02`) and is superseded for submission.
- **Phase 15 structural audit DONE** on the stricter reading of its gate
  (`docs/PHASE_REPORTS/PHASE-15-STRUCTURAL-AUDIT.md`; decisions `D-15-04..D-15-07`).
- **Phase 17 complete**; no re-freeze required — no frozen file changed in this
  session (`freeze_release --verify` → 30 files, `0747baf0…`).

## Latest measurements (this session, 2026-11-22)

| Command / condition | Result |
|---|---|
| `make rc-check` (working tree) | **exit 0** — verify 12/12 (87.8 s), docs 22 facts/18 checks, replay-all 80/80 (567 steps), release-audit 6/6 |
| `make rc-check` (fresh `git clone`, emptied evidence dir) | **exit 0** — verify 12/12 (82.2 s), same downstream gates |
| `make release-audit` (`git archive` tarball, no `.git`) | **6/6 PASS** (the submission-image case) |
| `make replay-all` | **80/80 runs, 567 steps byte-identical** |
| `make test` counts (in verify) | 540 total (1 optional Hypothesis-class skip); official mirror 55 |
| CI on `9737961` (run `45009197767`) | `core` **success**, `docker-offline` **success** (`--network=none --read-only --cap-drop ALL`, `PIP_NO_INDEX=1`, non-root) |
| `python3 tools/freeze_release.py --verify` | **30 files intact**, `0747baf0…` |

RC-001 records explicit optional skips (bootstrap/optional); there is no critical
skip. `official_score_claimed: false` everywhere.

## Open items (none block the release)

1. **`Q-ORG-01` / `Q-ORG-02` — organisational independence is unevidenced.** The
   verifier was not built by a different human owner; this repository came from AI
   agents in one session context. The *technical* separation is proven (`RC-002` +
   runtime file-open spy). Needs a human owner: re-derive the verifier under a
   separate context, or accept and keep the disclosure. See `docs/INDEPENDENCE.md`.
2. **`Q-DOC-01`** — whether the 16-family distractor catalogue should appear in
   narration at all. Currently derived per-episode; not published. OPEN (judgement).
3. **Narrative behavioural claims** are now partly mechanical beyond the
   original three shapes: `C-EVIDENCE` (evidence artifacts exist and record
   PASS), `C-SCORE-HONEST` (every `official_score_claimed` asserts false) and
   `C-QORG-OPEN` (`Q-ORG-01`/`Q-ORG-02` not presented as RESOLVED) join
   `C-DATADICT`, `C-DEMO`, `C-WORKBENCH-API`. Prose beyond these pins still
   needs review.

## Next actions

1. Human owner answers `Q-ORG-01`; record acceptance in `docs/DECISIONS.md` or
   scope a separate verifier re-derivation (see `docs/CONTEXT/NEXT_AGENT.md`).
2. Nothing else is pending for the release: `v1.0.1` is cut, documented and tagged.
3. If a future defect is found in the released artifact, fix on a new branch, and
   let the fix ride the next patch release (`v1.0.2`); do not move `v1.0.1`.
