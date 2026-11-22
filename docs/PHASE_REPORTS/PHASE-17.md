# Phase 17 — Post-Release Evidence Freeze

**Outcome: DONE. EXIT GATE 17 PASS** — *"релиз можно восстановить и проверить без
устных пояснений команды"* (the release can be restored and verified without oral
explanations from the team).

- Date: 2026-11-22
- Branch: `arena/4c2f056f-genesis-hackathon-malika-nurzh`
- Base: `6f25a90` (merge of PR #28, Phase 16 §7 round)
- Master TZ v3.0.0 §Phase 17, lines 3096–3106
- `official_score_claimed: false` (TZ §23.6)
- Frozen files changed: **none** (`freeze_release --verify` → 30 files, `0747baf0…`)
- Tags moved: **none** (`v1.0.0`, `v1.0.1` untouched; `v1.0.2` cut on the merge commit)

---

## 1. What this phase had to prove

Phase 17 is not a feature phase. Its six tasks and its exit gate are:

| Task | Requirement | How it is satisfied |
|---|---|---|
| 17.1 | Archive final code version and config hashes | `docs/EVIDENCE/evidence_freeze.json` — SHA-256 of **every tracked release file** + one aggregate digest (`tools/evidence_freeze.py`) |
| 17.2 | Archive verify and replay reports | the same manifest, `reports` section: the **verdicts** of `verify_summary`, `replay_report`, `report_index`, `release_audit`, `doc_claims`, `trajectory_replay` |
| 17.3 | Archive final rubric map and decisions | `docs/EVIDENCE/phase-17-release-evidence-2026-11-22.json` — rubric gates `RC-001..RC-012`, the decision register, the frozen digest (`tools/release_evidence.py`) |
| 17.4 | Create final commit/release tag | tag **`v1.0.2`** on the merge commit of this PR; `docs/RELEASE_NOTES.md` + GitHub release |
| 17.5 | Write final status and known limitations | `docs/STATUS.md`, `docs/CURRENT_STATE.md`, `docs/LIMITATIONS.md` (L1..L10) |
| 17.6 | Next agent can reconstruct context from repo only | `docs/HANDOFF/phase-17-evidence-freeze.md`, `docs/CONTEXT/NEXT_AGENT.md`, and the machine-checked `reconstruct.commands` list |

The previous Phase 17 (2026-11-21, `D-17-01`) froze the **30 contract surfaces**.
That answers *"did the contracts move?"*. It does **not** answer the gate
sentence, which is about the **release** as a whole:

> the release must be **restorable** *and* **verifiable** — from the repository
> alone, by someone who was not in the room.

Three gaps stood between the old state and that sentence:

1. **The release surface had no digest.** 549 tracked files — runtime code,
   operational configs, the rubric map, the Dockerfile, the Makefile, the official
   entrypoint, the committed episodes and the whole documentation set — were
   protected by nothing but the git history.
2. **The measured evidence was not archived.** The gate verdicts existed only as
   prose in status documents; the reports themselves are gitignored and
   regenerable.
3. **The contract freeze was a manual command.** `tools/freeze_release.py
   --verify` was never asserted by a test, so CI could not fail on drift.

---

## 2. What was built

### 2.1 `tools/evidence_freeze.py` — the release-surface archive (task 17.1/17.2)

```
docs/EVIDENCE/evidence_freeze.json
  schema_version, phase, code_version, official_score_claimed: false
  source_commit, generated_at_utc            (informational anchors)
  frozen_file_count, aggregate_sha256         (the release digest)
  files:   [{path, bytes, sha256}] × every tracked file
  reports: {verify_summary, replay_report, report_index,
            release_audit, doc_claims, trajectory_replay} -> verdict
```

Design decisions, each of which had to be right for the archive to be usable:

* **Verdicts, not bytes.** Report bytes carry `generated_at_utc`, `run_id` and
  `duration_s`; they are regenerated on every run. The archived fact is the
  *verdict* — status plus counts. A re-run that changes only a timestamp still
  verifies; a re-run whose verdicts changed does not.
* **Status-level facts only.** A detail string such as *"540 text files
  scanned"* drifts the moment the tree grows, so verdict extraction deliberately
  drops it (verified by `tests/judge/test_evidence_freeze.py`).
* **Required vs optional reports.** `verify_summary`, `replay_report` and
  `report_index` come from `make verify` / `make report` and are **required**;
  `release_audit`, `doc_claims` and `trajectory_replay` come from other targets
  and are compared when present, skipped when their target was not run.
* **The manifest lives outside `configs/`.** A new file under `configs/` would
  itself drift the contract freeze, which must stay at 30 files / `0747baf0…`.
* **The manifest excludes itself** (and the companion archive): an archive
  cannot contain its own digest. Their integrity is the commit.

### 2.2 `tools/release_evidence.py` — the reconstructable release archive (task 17.3/17.6)

`docs/EVIDENCE/phase-17-release-evidence-2026-11-22.json` is generated from
*measured* sources only — the frozen manifest, the Judge Kit reports, the
rubric map and the decision register — and states:

* the frozen contract digest and file count;
* the four measured gate verdicts (verify, replay-all, release audit, doc
  claims);
* the rubric map: `RC-001..RC-012`, with the rubric's own `provisional` flag;
* the decision register: every `D-xx-xx` id, its date and its title;
* `reconstruct.commands` — the ordered list a stranger runs:

```
python3 tools/freeze_release.py --verify
make verify
make docs-verify
make replay-all
make release-audit
python3 tools/evidence_freeze.py --verify --require-reports
python3 tools/release_evidence.py --verify --strict
python3 -m unittest discover -s tests -t .
```

`--verify` re-derives the archive and compares it. The *snapshot* sections
(the measured verdicts, the decision list) are checked for internal consistency
and honesty on every commit, and for exact equality with a fresh measurement
only at release time (`--strict`).

### 2.3 The gates that were closed

| Gate | Before | After |
|---|---|---|
| Contract freeze | a manual command | `tests/judge/test_release_freeze.py`: the tree must match the committed manifest, the frozen surface must be exactly the declared 30 files, the aggregate must still be the released `0747baf0…` |
| Release archive | did not exist | `C-ARCHIVE` in `tools/verify_doc_claims.py` (22 checks now, was 21) + `make evidence-verify` in `make rc-check` **and** in the CI `core` job |
| Published reward contract | prose only | `C-REWARD` now also audits the **generated artifacts**, not only the docs |

**The invariant the next agent must keep:** *the committed archive must match
the committed tree.* Any change to a tracked file requires `make evidence-write`
in the same commit; CI then fails with the exact path that drifted. The release
procedure is in `docs/HANDOFF/phase-17-evidence-freeze.md` §4.

---

## 3. Defects found while auditing the published evidence

The Phase 17 sweep read every **published** artifact and doc against the
decisions the repository had already taken. It found four places where the
published text contradicted the live implementation — the same failure mode as
BUG-TL-0001 (a second copy of the reward formula), one level up: the *numbers*
were migrated, the *label* was not.

| ID | Severity | Defect | Fix |
|---|---|---|---|
| BUG-TL-0005 | P1 | `reward_property_matrix.json` published `"formula": "R = max(0, F1 - eta * steps_used / max_steps)"` and `"provisional": true`, although every number in it had been computed by the official implementation since `D-18-01` (a clean honest run at 20 steps reads `24/25`, which is `clip([-1,1], 2*F1-1-0.2*steps/100)`; the superseded formula would have read `0.99`) | the published formula is now **derived** from the live constants: `scoring/official_scorer.official_formula_text()` → `scoring.reward.FORMULA` → the matrix; the matrix publishes `provisional: false` |
| BUG-TL-0006 | P2 | `robustness_report.json` published `score_contract: "scoring.reward (internal provisional; not official_scorer)"` — false since `D-18-01` made `scoring.official_scorer` the single reward implementation | `judge/robustness_audit.SCORE_CONTRACT` names the single implementation and carries the live formula; a note keeps the "internal measurement, not a jury score" meaning explicit |
| BUG-TL-0007 | P3 | stale "provisional / pending Q-005" wording in `scoring/matcher.py` and in a property-test comment, although `Q-005` was resolved on 2026-11-20 | docstring and comment corrected |
| BUG-TL-0008 | P2 | the `C-PATHS` artifact contract of the documentation gate named `replay_all_report.json` — a file that **does not exist** (the real one is `trajectory_replay.json`) — and omitted `reward_property_matrix.json`, which is part of the published 20-file evidence set; a correct citation was reported as a phantom path | the contract is now derived from the producers; `tests/judge/test_doc_claims.py::test_generated_artifact_contract_matches_the_producers` fails on the old list |

Each fix carries a regression test that **fails on the old code**:
`tests/scoring/test_formula_provenance.py` (6 tests) and the artifact
assertions in `tests/scoring/test_reward_properties.py`; the artifact branch of
`C-REWARD` fails on the stale matrix and on the stale score contract.

The historical Phase 6 reward matrix
(`docs/PHASE_REPORTS/PHASE-06-reward-matrix.json`) was **annotated**, not
rewritten: it is a dated snapshot, and it now says so.

---

## 4. Verification

| Gate | Command | Result | Artifact |
|---|---|---|---|
| Contract freeze | `python3 tools/freeze_release.py --verify` | **PASS** — 30 files, `0747baf0…` | `configs/release_freeze.json` |
| Full Judge Kit | `make verify` | **PASS 12/12**, 588 tests (1 optional skip), 20 artifacts | `artifacts/reports/latest/verify_summary.json` |
| Documentation claims | `make docs-verify` | **PASS** — 22 measured facts, **22/22** checks | `artifacts/reports/doc_claims/doc_claims_report.json` |
| All trajectories | `make replay-all` | **PASS** — 80/80 runs, 567 steps byte-identical | `artifacts/reports/release/trajectory_replay.json` |
| Release audit | `make release-audit` | **PASS 6/6** — secrets, file list, size, deps, entrypoint, submission | `artifacts/reports/release/release_audit.json` |
| Import boundaries | `python3 tools/check_import_boundaries.py` | **CLEAN** (REQ-ARC-001..007) | stdout |
| Release archive | `python3 tools/evidence_freeze.py --verify` | **PASS** — release surface intact | `docs/EVIDENCE/evidence_freeze.json` |
| Release gate | `python3 tools/evidence_freeze.py --verify --require-reports` | **PASS** — surface + archived gate verdicts | `docs/EVIDENCE/evidence_freeze.json` |
| Evidence archive | `python3 tools/release_evidence.py --verify` | **PASS** — honest and self-consistent | `docs/EVIDENCE/phase-17-release-evidence-2026-11-22.json` |

### Failed or skipped checks

* **One optional skip** in the suite (bootstrap/optional class). No critical
  skip; RC-001 records it explicitly (TZ §23.3: SKIPPED ≠ PASS).
* **The Docker offline gate is not executed locally** — no container runtime
  exists on the execution host (`docker`, `podman`, `buildah`, `nerdctl`, `ctr`,
  `runc`, `containerd` all absent). It stays **CI-authoritative**; the local
  namespace substitute is `tools/offline_local_check.py`, whose scope is
  recorded in `docs/EVIDENCE/offline-local-2026-11-22.json`. This is limitation
  L9 and is *not* counted as PASS here.
* **Organisational independence remains unevidenced** (`Q-ORG-01`,
  `Q-ORG-02`): a human decision, not a code change.

### Gates proven able to fail

The archive is a real gate, not a note:

* one edited byte in any tracked file → `evidence_freeze --verify` names that
  path;
* a new untracked file in the release surface → `untracked new file in release
  surface: …`;
* a changed gate verdict → `report verdict drift: …`;
* a tampered archive (`official_score_claimed: true`) → `release_evidence
  --verify` fails, and `C-ARCHIVE` fails;
* a frozen file touched → `tests/judge/test_release_freeze.py` fails.

---

## 5. Decisions and deviations

* `D-17-02` — the release surface is archived, and the archive must match the tree.
* `D-17-03` — a published reward contract is derived from the live constants,
  never re-typed.
* **Deviation (accepted):** the Phase 17 archive lives in `docs/EVIDENCE/`, not
  in `configs/`. Reason: any new file under `configs/` would drift the contract
  freeze, which must stay at 30 files / `0747baf0…`. The contract freeze is
  unchanged and still verified.
* **Deviation (accepted):** the two archive files are excluded from the hashed
  surface. Reason: an archive cannot contain its own digest. Their integrity is
  the commit, and the *release surface* they describe is hashed in full.
* **No frozen file was edited** (`D-14-02`), including
  `configs/scoring/default.json`, which still carries `eta: 0.05` and
  `provisional: true` as a historical record (`D-18-01`).

---

## 6. Risks and residual limitations

| Risk / limitation | Status |
|---|---|
| The evidence archive is **per-commit** (L8) | By design; a later patch release needs its own archive |
| The release evidence is a **snapshot** of the release run | Checked for honesty on every commit, for exact equality at release time (`--strict`) |
| Docker-offline gate is CI-authoritative (L9) | Recorded as UNVERIFIED locally, never as PASS |
| Organisational independence unevidenced (L10, `Q-ORG-01`) | Disclosed; needs a human owner |
| Narrative prose beyond the machine-checked axes | Needs human review; the structural detectors cover paths, data dictionary, demo, API, commands, reward, counts, evidence, archive, score honesty and open questions |

---

## 7. Next-phase readiness

Nothing blocks the release. The remaining item is a **human** decision
(`Q-ORG-01`): accept and disclose, or re-derive the verifier under a separate
owner. See `docs/CONTEXT/NEXT_AGENT.md`.

---

## 8. Owner sign-off

The factual status above is machine-verified (commands and artifacts are named
in §4). The organisational question in §6/L10 is **not** signed off and remains
OPEN — it is not an agent's to close.

---

```
STATUS: DONE
SCOPE: Phase 17 (TZ §24) — post-release evidence freeze; release v1.0.2.
IMPLEMENTED: tools/evidence_freeze.py, tools/release_evidence.py,
  docs/EVIDENCE/{evidence_freeze.json,phase-17-release-evidence-2026-11-22.json},
  make evidence-write/evidence-verify (wired into rc-check + CI), C-ARCHIVE,
  tests/judge/{test_evidence_freeze,test_release_evidence,test_release_freeze}.py,
  tests/scoring/test_formula_provenance.py, formula provenance in
  scoring/{official_scorer,reward,diagnostics}.py and judge/robustness_audit.py,
  docs: STATUS, CURRENT_STATE, NEXT_AGENT, LIMITATIONS (L8-L10), DECISIONS
  (D-17-02, D-17-03), CHANGELOG, RELEASE_NOTES, PHASE_REPORTS/PHASE-17,
  HANDOFF/phase-17-evidence-freeze.md, QUALITY_AUDIT/BUG_REGISTRY (0005-0007).
REQUIREMENTS: REQ-CONTRACT-001, REQ-CONTRACT-003, REQ-JUDGE-004 (carried),
  TZ §24 tasks 17.1-17.6 (closed).
TESTS RUN: python3 tools/freeze_release.py --verify; make verify;
  make docs-verify; make replay-all; make release-audit; make evidence-verify;
  python3 tools/release_evidence.py --verify; python3 -m unittest discover -s tests -t .
TEST RESULTS: PASS — 12/12 gates, 588 tests (1 optional skip), 22/22 doc checks,
  80/80 replays (567 steps), 6/6 audit checks, 30/30 frozen files, release
  surface + archive verified. SKIPPED: Docker offline build (no container
  runtime on this host; CI-authoritative, recorded UNVERIFIED, not PASS).
COMMIT: (merge commit of the Phase 17 PR; tag v1.0.2)
RISKS: see §6 — per-commit archive, CI-authoritative Docker gate, organisational
  independence unevidenced.
DECISIONS: D-17-02, D-17-03.
NEXT ACTION: human owner answers Q-ORG-01 (accept-and-disclose or re-derive).
```
