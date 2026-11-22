# Current State — 2026-11-22 (Phase 18 container hardening, release v1.0.3)

> **Latest session (2026-11-22, branch `arena/87691cc0-genesis-hackathon-malika-nurzh`,
> based on `main` @ `f3af314`): the submission container was hardened against
> TZ §22.4 / §16.2 and the local host finally produced real evidence about it.**
>
> | Command / condition | Result |
> |---|---|
> | `python3 tools/freeze_release.py --verify` | **PASS** — 30 frozen contract files intact, `0747baf0…` (unchanged) |
> | `python3 tools/evidence_freeze.py --verify` | **PASS** — every tracked release file matches `docs/EVIDENCE/evidence_freeze.json` |
> | `python3 tools/release_evidence.py --verify` | **PASS** — the release archive is honest, self-consistent and current |
> | `make verify` (full Judge Kit) | **PASS 12/12** gates, 623 tests, 20 evidence artifacts |
> | `make docs-verify` | **PASS** — 22 measured facts, 22 checks |
> | `make replay-all` | **PASS** — 80/80 runs, 567 steps byte-identical |
> | `make release-audit` | **PASS 6/6** — secrets, file list, size, deps, entrypoint, submission (now also the base image pin) |
> | `make container-local-check` | **PASS** — the container command runs as uid 10001 with no capabilities, `no_new_privs`, a read-only tree and no network; 12/12 gates inside the sandbox |
> | `tools/check_compose_profile.py` | **PASS** — every Compose service keeps the hardening contract |
> | `tools/check_import_boundaries.py` | **CLEAN** (REQ-ARC-001..007) |
> | `official_score_claimed` | **false** everywhere; `Q-ORG-01` / `Q-ORG-02` / `Q-DOC-01` remain **OPEN** (human decisions) |
>
> The Docker **image build** remains **CI-authoritative** (no container runtime
> and no registry access on the execution host). The local evidence is now the
> *container-equivalent* run (`tools/container_local_check.py`), which
> materialises the image from the build context and executes the container's
> own command under the CI hardening; its exact scope is recorded in
> `docs/EVIDENCE/container-local-2026-11-22.json`.

- Active branch: `arena/87691cc0-genesis-hackathon-malika-nurzh`, base
  `f3af314` (`main`, merge of PR #30). The merge commit of the Phase 18 PR is
  the target of the **`v1.0.3`** tag.
- **Phases 0–18 are `DONE`** (see `docs/STATUS.md`). The repository is
  feature-frozen; this session changed the *container surface* and its audits
  only — no runtime behaviour of the benchmark changed.
- **`v1.0.3` is the recommended submission artifact**: it pins the base image
  by digest, ships a correct build context, machine-checks the Compose profile
  and adds a local container-equivalent run. `v1.0.2` and `v1.0.1` are
  retained for history; none of the published tags was moved.

## What changed in this session

| Area | Change |
|---|---|
| Base image | `Dockerfile` pins `python:3.11-slim-bookworm@sha256:a36c24f9…` (multi-platform, CPython 3.11.16 / bookworm); the image writes its own provenance record; `docs/EVIDENCE/docker-build-info.json`; the CI job `base-image` reports upstream drift |
| Build context | `.dockerignore` rules now use Docker's real anchoring (`**/` prefixes) — 197 stale `.pyc` files no longer enter the image; `tools/docker_context.py` computes the effective context |
| Compose profile | process/file-size limits, all writable paths on tmpfs, contract machine-checked by `tools/check_compose_profile.py` |
| Local container evidence | `tools/container_local_check.py` (`make container-local-check`): the image is materialised and `make verify` runs as uid 10001 with no capabilities, `no_new_privs`, a read-only tree and no network — **PASS**, 12/12 gates inside the sandbox |
| Defects | BUG-TL-0010 (root-anchored `.dockerignore`), BUG-TL-0011 (floating base image), BUG-TL-0012 (Compose limits), BUG-TL-0013 (substring audit) — each with a failing-on-old-code regression test |
| Docs | `docs/LIMITATIONS.md` (L9, L11), `docs/DECISIONS.md` (`D-18-02`, `D-18-03`), `docs/FAILURE_ANALYSIS.md` (Failure Case 4), `docs/PHASE_REPORTS/PHASE-18.md`, `docs/CHANGELOG.md`, `docs/RELEASE_NOTES.md`, `docs/CONTEXT/NEXT_AGENT.md` |
| Phase 17 archive | `tools/evidence_freeze.py` (release-surface digest + report verdicts) and `tools/release_evidence.py` (reconstructable release archive), `docs/EVIDENCE/` |
| Gates | `make evidence-write` / `make evidence-verify`, wired into `make rc-check` and the CI `core` job; `C-ARCHIVE` in `tools/verify_doc_claims.py`; `tests/judge/test_release_freeze.py` turns the contract freeze into a test |
| Defects | BUG-TL-0005 (published formula), BUG-TL-0006 (published score contract), BUG-TL-0007 (stale "provisional" wording), BUG-TL-0008 (documentation gate's artifact contract), BUG-TL-0009 (malformed CI workflow disabled the CI gate) — all non-frozen, each with a failing-on-old-code regression test |
| Docs | `docs/STATUS.md`, `docs/LIMITATIONS.md` (L8–L10), `docs/DECISIONS.md` (`D-17-02`, `D-17-03`), `docs/CHANGELOG.md`, `docs/RELEASE_NOTES.md`, `docs/PHASE_REPORTS/PHASE-17.md`, `docs/HANDOFF/phase-17-evidence-freeze.md`, `docs/CONTEXT/NEXT_AGENT.md` |

## Latest measurements (this session, 2026-11-22)

| Command / condition | Result |
|---|---|
| `make verify` (working tree) | **exit 0** — 12/12 gates, 623 tests (1 optional skip), 20 artifacts |
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
2. Nothing else is pending for the release: `v1.0.3` is cut, documented and
   tagged; it is the recommended artifact (same benchmark behaviour as
   `v1.0.2`, plus the container hardening) and the earlier tags are retained
   for history.
3. If a future defect is found in the released artifact, fix on a new branch,
   re-run `make evidence-write` in the same commit, and let the fix ride the
   next patch release (`v1.0.4`); do not move `v1.0.0`, `v1.0.1`, `v1.0.2` or
   `v1.0.3`.
4. A maintainer **with Docker and a registry** should run `make docker-check`
   once and record the result in `docs/EVIDENCE/`; that retires the remaining
   part of limitation L9 (the image build itself stays CI-authoritative).
