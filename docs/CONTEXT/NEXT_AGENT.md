# Next agent — handoff after the Phase 18 container hardening (release v1.0.3)

Read `AGENTS.md`, `docs/CURRENT_STATE.md`, `docs/PHASE_REPORTS/PHASE-18.md`,
`docs/PHASE_REPORTS/PHASE-17.md`, `docs/HANDOFF/phase-17-evidence-freeze.md`,
`docs/QUESTIONS.md` (the process questions), and decisions `D-18-02`,
`D-18-03`, `D-18-04`, `D-17-02`, `D-17-03`, `D-16-02`, `D-16-03`, `D-18-01`,
`D-15-04..D-15-07` first. Then read `docs/INDEPENDENCE.md`
("Ownership — and an honest correction"), which is the most important
paragraph in the repository.

## Where the project stands

Phase 18 is `DONE`: the submission container is hardened against TZ §22.4 and
§16.2 (base image pinned by digest, Docker-correct build context, machine-
checked Compose profile, process/file-size limits) and the execution host
finally produces real container evidence - a container-equivalent run that
executes `make verify` as uid 10001 with no capabilities, `no_new_privs`, a
read-only tree and no network. Phases 0–18 are all `DONE` (see
`docs/STATUS.md`). The repository is feature-frozen; nothing in this handoff
authorises new features.

```
v1.0.3   -> annotated tag on the merge commit of the Phase 18 PR; the recommended artifact (same benchmark behaviour as v1.0.2 + the container hardening)
v1.0.2   -> retained for history (adds the Phase 17 evidence archive); tag unmoved
v1.0.1   -> retained for history (image no longer ships sealed truth, D-16-02); tag unmoved
v1.0.0   -> retained for history; superseded for submission; tag unmoved
make verify                                          -> 12/12 gates, 655 tests, 20 artifacts
make docs-verify                                     -> 22 measured facts, 22 checks
make replay-all                                      -> 80/80 runs, 567 steps byte-identical
make release-audit                                   -> 6/6 PASS
make container-local-check                           -> PASS (12/12 gates inside the sandbox; uid 10001, CapEff 0, no_new_privs, read-only tree, no network)
python3 tools/docker_build_info.py verify            -> base image pinned by digest; the recorded build info agrees
python3 tools/check_compose_profile.py               -> every Compose service keeps the hardening contract
python3 tools/freeze_release.py --verify             -> 30 frozen files intact, 0747baf0…
python3 tools/evidence_freeze.py --verify            -> release surface intact (one aggregate digest)
python3 tools/evidence_freeze.py --verify --require-reports -> + archived gate verdicts (CI gate)
python3 tools/release_evidence.py --verify           -> release archive honest and self-consistent
python3 tools/check_workflows.py                    -> every workflow parses AND masks nothing (no continue-on-error, no `|| true`)
```

### The CI close-out (read this before trusting a green CI run)

A green CI run used to be able to hide a failed step. The `docker-offline` job
reported **success** while the container-equivalent step had failed with exit
code 1; the only trace was a `Process completed with exit code 1` annotation on
a *successful* job. Three defects were behind it (`BUG-TL-0015..0017`,
`D-18-04`):

* the workflow masked the exit status twice (`continue-on-error: true` and
  `|| true`), and `tools/check_workflows.py` had no rule against either;
* `tools/container_local_check.py` reported a host that *forbids* unprivileged
  user namespaces (Ubuntu 24.04 AppArmor) as a generic FAIL;
* the `publish` subcommand of `tools/docker_build_info.py` was unreachable
  dead code, so the CI step named "Publish the image build provenance" had
  never published anything.

All three are fixed: a failing step now fails the job, an environment that
cannot provide the isolation is an explicit **skip** (exit code 2, with a
reason), and the static guard enforces both. If you add a workflow step,
**do not** hide a failure — handle it explicitly and report it.

One more trap, found by that very CI run: the suite also runs inside the
hardened image, whose `/tmp` is mounted **`noexec`**. A test that writes a
fake executable into a temporary directory and runs it fails there
(`BUG-TL-0018`). Replace the *call* (the tools expose `_run_command()` as a
seam) rather than the *binary*; `test_no_test_makes_a_temporary_file_executable`
guards this.

### What is still not provable here (read this before claiming anything)

The **image build** is CI-authoritative: the execution host has no container
runtime and no registry access, so `docker build` cannot run there. The local
`make container-local-check` is a *container-equivalent* run - it materialises
the image from the build context and applies the same hardening, but it does
**not** pull or build the base image. Do not describe it as a Docker build
(see `docs/LIMITATIONS.md`, L9, and `D-18-03`).

## Reconstruct the release from the repository alone

This is the point of Phase 17, so it comes first. From a clean checkout of the
release tag:

```bash
python3 tools/freeze_release.py --verify
make verify && make docs-verify && make replay-all && make release-audit
python3 tools/evidence_freeze.py --verify --require-reports
python3 tools/release_evidence.py --verify --strict
```

The same list, with the measured outcome of each command, is archived in
`docs/EVIDENCE/phase-17-release-evidence-2026-11-22.json`
(`reconstruct.commands`, `gates`).

## Rules this project established (do not break them)

### Carried over, still binding
- **Never hand-edit the README generated block.** Regenerate with
  `python3 tools/verify_doc_claims.py --write`.
- **Never gate a test on a gitignored or generated output**, and **never read an
  artifact that does not exist yet in RC-001's bootstrap position**. Use
  `@unittest.skipUnless(ARTIFACTS_READY, NOT_READY_REASON)`. This has bitten the
  project **five** times.
- **Never assert a value produced by the run that is performing the check.**
- **Never put a sampled value in the generated block.**
- **Never write reports into `artifacts/reports/latest/`.**
- **Never cite a decision ID that is not in `docs/DECISIONS.md`.**
- **`calc` vs `calculator` is intentional** (`D-15-02`).
- **Checked-in `episodes/dev/*` have no `sealed/truth.json`** (`D-01-04`).
- **Every gate must be shown to fail.** Keep the injected-fault standard.
- **Do not move a published tag.** Fix-forward on a new branch; next patch tag.
- **Do not run `make official-eval` casually** — it rewrites the committed
  `artifacts/trajectories/trajectories.jsonl`. If a sweep runs it, restore with
  `git checkout -- artifacts/trajectories/trajectories.jsonl`.
- **Do not "fix" the frozen `configs/scoring/default.json`** (`eta: 0.05`,
  `provisional: true`): it is a historical record that no longer influences the
  reward (`D-18-01`, `D-14-02`). Changing it needs an approved CR.

### New in Phase 17
- **A published reward contract is derived, never re-typed** (`D-17-03`).
  `scoring/official_scorer.official_formula_text()` is the only place the
  formula string is written; `scoring.reward.FORMULA` and the reward-property
  matrix publish *that*. `C-REWARD` audits the generated artifacts too — a
  report that quotes a formula nobody implements fails the gate.
- **The committed evidence archive must match the committed tree.** After
  changing any tracked file, run `make evidence-write` in the same commit, or
  CI fails with the exact path that drifted (`D-17-02`).
- **A re-freeze of the contract surface needs an approved CR.**
  `tests/judge/test_release_freeze.py` fails if a frozen file moves, so
  "silently re-freeze" is no longer possible.
- **An archive cannot contain its own digest.** The two files under
  `docs/EVIDENCE/` are excluded from the hashed surface; their integrity is
  the commit.

### Console and docs
- **Console verdicts must survive an ASCII-only locale** (`D-15-07`). Use `_say`
  for every console write in `judge/verify.py::main`.
- **Recognised prose totals track discovery** through `C-COUNTS`. Adding a test
  requires `python3 tools/verify_doc_claims.py --write` to update the facts block
  and recognised prose copies.
- **A published fact must not depend on which target ran last** (`D-15-06`).
  Test counts come from `unittest` **discovery**, never from `verify_summary.json`.
- **Pin a sentence to a source, not to a second copy** (demo clock, `C-DEMO`).
- **Absence must be documentable.** `C-PATHS` negation-cue exemption: keep it.
- **Do not "fix" the honest ownership disclosure.** `Q-ORG-01` and `Q-ORG-02` are
  OPEN on purpose. The technical zero-common-mode separation is proven; the
  organisational separation is not.

## Known open items

| ID | Item | Owner |
|---|---|---|
| `Q-ORG-01` | Verifier was not built by a separate human/agent context. Technical re-derivation now exists (`independent_verifier/`, 10/10 committed episodes signature-identical, `D01..D20` F1=1 exact, FP=FN=0; `docs/EVIDENCE/independent-rederivation-2026-11-22.json`) — organisational separation still does not. Accept and disclose, or re-derive under a separate owner. | Human owner |
| `Q-ORG-02` | CODEOWNERS personas are intended, not real accounts (already disclosed in the file header). | Human owner |
| `Q-DOC-01` | Should the 16-family distractor catalogue appear in narration? Not published today. | Next agent / owner |
| — | Narrative behavioural claims are only partly mechanical; prose needs review (`C-ARCHIVE` added 2026-11-22). | Next agent |
| — | The evidence freeze is per-commit (L8): a later patch release needs its own archive. | Next agent |

`Q-REL-01` is **RESOLVED** (`v1.0.1` cut, `D-16-03`, 2026-11-22).

## Single next action

Get a human answer to `Q-ORG-01`. If the answer is "accept and disclose", record it
in `docs/DECISIONS.md` as a new `D-xx-xx` and close the question. If the answer is
"re-derive", `independent_verifier/` already provides the second implementation —
what remains is *who authors it next and under what review*. Note the 2026-11-22
re-derivation was authored in the same session as everything else, so it
strengthens the technical evidence but does not by itself close the organisational
question. Do not attempt both.
