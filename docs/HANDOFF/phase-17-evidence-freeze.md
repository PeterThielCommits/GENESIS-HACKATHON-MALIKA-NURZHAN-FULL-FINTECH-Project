# Handoff — Phase 17 deep execution: post-release evidence freeze

**From:** Phase 17 execution (branch `arena/4c2f056f-genesis-hackathon-malika-nurzh`,
base `6f25a90`)
**To:** the next agent (or a reviewer with no access to the team)
**Date:** 2026-11-22

---

## 1. What Phase 17 is for

Master TZ §24, Phase 17 — *POST-RELEASE EVIDENCE FREEZE*:

```
17.1 Archive final code version and config hashes.
17.2 Archive verify and replay reports.
17.3 Archive final rubric map and decisions.
17.4 Create final commit/release tag.
17.5 Write final status and known limitations.
17.6 Ensure next agent can reconstruct context from repo only.

EXIT GATE 17: релиз можно восстановить и проверить без устных пояснений команды.
```

The gate sentence is the acceptance criterion: **the release must be
restorable and verifiable without oral explanations from the team.** This
handoff therefore starts with the commands, not with the story.

## 2. Reconstruct and verify the release (repo only)

From a clean checkout of the release tag:

```bash
python3 tools/freeze_release.py --verify      # 30 frozen contract surfaces
make verify                                   # 12/12 Judge Kit gates
make docs-verify                              # 22 measured facts, 22 checks
make replay-all                               # 80/80 runs, 567 steps
make release-audit                            # secrets/size/deps/entrypoint
python3 tools/evidence_freeze.py --verify --require-reports   # surface + verdicts
python3 tools/release_evidence.py --verify --strict           # the release-evidence archive
python3 -m unittest discover -s tests -t .    # the full suite
```

Everything is offline, stdlib-only and deterministic. The same list, with the
measured outcome of each command, is archived in
`docs/EVIDENCE/phase-17-release-evidence-2026-11-22.json`
(`reconstruct.commands` + `gates`).

**Bare checkout vs. full gate.** `python3 tools/evidence_freeze.py --verify`
(produced by `make evidence-verify`) checks the **release surface** — every
tracked file's SHA-256 and the aggregate digest — and needs nothing but the
repository, so a fresh clone can prove "this is the released tree" before any
artifact exists. The archived gate **verdicts** are compared additionally only
when the reports are present; `--require-reports` (used by CI and
`make rc-check`, where `make verify` has just run) turns a missing report into
an error. This split keeps the archive checkable on a bare clone without
weakening the release gate.

## 3. What is archived, and where

| Task | Deliverable | What it pins |
|---|---|---|
| 17.1 | `docs/EVIDENCE/evidence_freeze.json` (written by `tools/evidence_freeze.py`) | SHA-256 of every tracked release file + the aggregate digest |
| 17.2 | same file, `reports` section | the **verdicts** of the Judge Kit / replay / audit / doc-claim reports (status + counts, no timestamps) |
| 17.3 | `docs/EVIDENCE/phase-17-release-evidence-2026-11-22.json` | the rubric map (RC-001..RC-012), the decision register, the frozen digest, and the reconstruct command list |
| 17.4 | git tag + GitHub release | the released tree (`docs/RELEASE_NOTES.md`) |
| 17.5 | `docs/STATUS.md`, `docs/LIMITATIONS.md` | final status and the honest limitations |
| 17.6 | this file, `docs/CONTEXT/NEXT_AGENT.md` | the context a stranger needs |

The **contract** freeze stays where it always was:
`configs/release_freeze.json` — 30 files, aggregate `0747baf0…`
(`tools/freeze_release.py`, `D-17-01`). The new evidence archive lives under
`docs/EVIDENCE/` on purpose: a new file under `configs/` would itself drift
the contract freeze.

## 4. The invariant you must keep

> **The committed archive must match the committed tree.**

`make evidence-verify` is wired into `make rc-check` **and** into the CI
`core` job. If you change any tracked file, run `make evidence-write` in the
same commit — otherwise CI fails with the exact path that drifted.

Order matters when releasing:

```bash
git add -A                       # the file list must be final first
make verify && make docs-verify && make replay-all && make release-audit
python3 tools/release_evidence.py --write
make evidence-write              # hashes the *staged* tree
git add docs/EVIDENCE/evidence_freeze.json
git commit
```

Two consequences worth knowing:

* The manifest hashes the **tracked** files. A file that is not committed is
  not part of the archive — that is the point of "the release is what is in
  git".
* The archive files themselves are excluded from the hashed surface: an
  archive cannot contain its own digest. Their integrity is the commit.

## 5. Rules that changed in this phase

* **A published reward contract is derived, never re-typed** (`D-17-03`).
  `scoring/official_scorer.official_formula_text()` renders the formula from
  the live constants; `scoring.reward.FORMULA` and the reward-property matrix
  publish that string; the robustness report names the single implementation.
  `C-REWARD` now audits the *generated artifacts* as well as the prose.
* **The contract freeze is a gate, not a command** (`D-17-02`).
  `tests/judge/test_release_freeze.py` fails if a frozen file moves. A
  re-freeze needs an approved CR (AGENTS.md).
* The frozen `configs/scoring/default.json` still carries `eta: 0.05` and
  `provisional: true` **on purpose** (`D-18-01`, `D-14-02`): it is a
  historical record, and it no longer influences the reward. Do not "fix" it
  without a CR.

## 6. What is still open (and who owns it)

| ID | Item | Owner |
|---|---|---|
| `Q-ORG-01` | Organisational separation of the verifier is still unevidenced. The technical zero-common-mode re-derivation exists (`independent_verifier/`); the *organisation* does not. | Human owner |
| `Q-ORG-02` | `CODEOWNERS` personas are intended, not real accounts. | Human owner |
| `Q-DOC-01` | Should the 16-family distractor catalogue appear in narration? It does not today. | Next agent / owner |
| — | The Docker-offline gate is **CI-authoritative**; no container runtime exists on the execution host (`tools/offline_local_check.py` is the local substitute, scope recorded in `docs/EVIDENCE/offline-local-2026-11-22.json`). | Maintainer with Docker |

## 7. Single next action

Answer `Q-ORG-01` as a human owner: *accept and disclose* (record a new
`D-xx-xx` and close the question) or *re-derive under a separate owner*.
Everything else in the release is DONE, tagged and machine-verified.
