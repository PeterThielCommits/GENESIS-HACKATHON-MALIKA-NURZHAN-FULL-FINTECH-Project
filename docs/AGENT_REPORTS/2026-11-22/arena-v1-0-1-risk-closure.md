# Agent report — Phase 16 §7 risk-closure round (v1.0.1 follow-up)

Date: 2026-11-22 · Branch: `arena/d0407793-genesis-hackathon-malika-nurzh` (base `main` @ `3b83864`) · Operator: AI-agent-assisted, one session

## Trigger

Final Phase-16 report listed four risks (§7). The owner directed: fix **all**
errors/bugs/risks so the jury has no questions, without rewriting history.

## What was done

1. **Independent re-derivation verifier (`independent_verifier/`)** — a
   from-scratch Stage-1 implementation written from `spec/verifier_algorithm.md`
   and `contracts/` only. Own money/FX (`Fraction`), own `zoneinfo` fiscal
   periods, own discovery for the four anomaly types, own ProofGraph
   (acyclicity, finding-paths, FactNode invariants), own evidence
   minimal-set reduction with full-deletion ablation. Never imports
   `verifier/`, `gen/`, `scoring/`, `seal/`, `nlp/`, `harness/`, `env/`,
   `arena/`, `judge/` (enforced by `tools/check_import_boundaries.py` §
   `independent_verifier`, by `tests/independent_verifier/` AST + fresh-process
   import + runtime file-open spy tests).
   - Result: 10/10 committed on-disk episodes (6 dev + 4 train) re-derive to
     signature-identical findings with identical `episode_public_hash`.
   - Official `D01..D20` matrix (`master_seed=2026`, rebuilt via the public
     recipe matrix by `tools/verify_independent_rederivation.py`):
     **F1 = 1 exact, FP = 0, FN = 0** on all 20; evidence enumeration complete;
     zero ProofGraph invariant errors; full-deletion ablation holds.
   - Evidence artifact: `docs/EVIDENCE/independent-rederivation-2026-11-22.json`.
   - Honesty: both implementations were written in one session. This is
     **technical zero-common-mode evidence**, not organisational separation.
     `Q-ORG-01` stays OPEN for a human owner. `docs/INDEPENDENCE.md` and
     `docs/QUESTIONS.md` updated accordingly (not "fixed away").
2. **Docker-offline evidence without a local container runtime.**
   - Probed and recorded: no `docker`/`podman`/`buildah`/`nerdctl`/`ctr`/`runc`/
     `containerd` on the host.
   - New `tools/offline_local_check.py`: user+net+mount namespace
     (`unshare -rmn`), repo bind-mounted **read-only**, `artifacts/` overlaid
     tmpfs, preflight refuses to run if any network route exists or the tree is
     writable; runs the full stdlib `unittest` suite with
     `PYTHONDONTWRITEBYTECODE=1`. Result: exit 0 (540→548 tests, skipped=26).
   - Static audit of `Dockerfile`/`.dockerignore`/`Makefile docker-check-container`
     (10/10 PASS: pinned base, `PIP_NO_INDEX=1`, `--network=none`, `--read-only`,
     `--cap-drop ALL`, non-root `USER 10001`, depth-2 `.dockerignore` exclusions,
     key material excluded).
   - **The Docker image build remains CI-authoritative**; `docker-offline`
     success on `main` @ `3b83864` (run `45021422570`) and on the `v1.0.1` tag
     commit (`45020669250`). Local approximation scope/limits recorded in
     `docs/EVIDENCE/offline-local-2026-11-22.json` (incl. `scope_statement`).
3. **Documentation gate extended** (`tools/verify_doc_claims.py`): new structural
   detectors `C-EVIDENCE` (the two evidence artifacts exist, carry a full git
   SHA, and record PASS), `C-SCORE-HONEST` (every `official_score_claimed`
   asserts `false`; ≥1 occurrence required), `C-QORG-OPEN` (`Q-ORG-01`/`Q-ORG-02`
   not presented as RESOLVED). Gate: 18 → **21 checks, all PASS**.
4. **`v1.0.0` release notes supersession pointer.** GitHub release `v1.0.0` body
   now opens with a SUPERSEDED banner → `v1.0.1` (`D-16-02`, `D-16-03`). The tag
   is untouched (`v1.0.0` = object `3b1e6be` → `8da0af2`). Repo docs already
   pointed at v1.0.1.
5. **Hygiene:** `independent_verifier/` added to `LOCAL_PACKAGES`
   (release-audit DEPS fix found by the suite going red on a clean tree),
   to `check_import_boundaries.py` (new rules incl. sealed-path literals),
   `Makefile` lint roots, `Dockerfile` compileall; suite now **548 tests**
   (8 new, incl. runtime file-open spy, fresh-subprocess import,
   signature/hash equality across all committed episodes, official-matrix
   F1=1 crosscheck).

## Defects found and fixed in this round

- Independent implementation initially derived over-allocation findings from a
  `{PAY}`-only set — valid for its own discovery, but failing the Stage-2
  superset-of-truth predicate on official `D11` (fp=1/fn=1). Fixed principledly:
  allocations referencing documents absent from the (sub)episode are
  unverifiable and derive nothing (REQ-VER-005/014-aligned). Not truth-informed;
  full episodes unaffected. After the fix: all 20 official scenarios
  F1=1/FP=0/FN=0.
- ProofGraph data-flow direction created a `rule→calc→rule` cycle via
  `governed_by`. Direction unified (evidence flows toward the finding);
  invariant check reports zero errors.
- `currency_exponents()` initially assumed a mapping layout; the registry is a
  list of `{code, exponent}` rows — now parsed accordingly, pinned by test.

## What remains (honest)

- `Q-ORG-01`, `Q-ORG-02` — **OPEN** (human owner; do not "fix").
- `Q-DOC-01` — OPEN.
- Docker image build locally — impossible on this host (no container runtime);
  a maintainer with Docker should run `make docker-check` once.
- No new tag cut from this round. `v1.0.2` would be a separate, explicit
  decision. `make official-eval` was not run; committed `trajectories.jsonl`
  untouched. `code_version` stays `twinledger@1.0.0`.
- CI run `45021422570` was observed **success** (core + docker-offline) on
  `3b83864` — recorded here; PR CI for this branch is the merge gate.

## Verification commands (all executed, this tree)

```
make verify                                    # 12/12 PASS (~86 s)
python3 tools/verify_doc_claims.py             # 21/21 PASS, 22 facts
python3 -m unittest discover -s tests -t .     # 548 tests OK (26 skipped)
python3 tools/offline_local_check.py           # exit 0
python3 tools/check_import_boundaries.py       # CLEAN (covers independent_verifier/)
python3 tools/freeze_release.py --verify       # 30 files, 0747baf0…
python3 tools/verify_independent_rederivation.py  # pass: true
```
