# REPRODUCIBILITY_AUDIT — TwinLedger v3.0

Every claim below has the command that produced it. Anything that could not be
executed here is marked **UNVERIFIED**, never PASS.

## R-1 Clean-extraction verification (container-equivalent)

Recipe: extract a commit with `git archive` (no `.git`), empty
`artifacts/reports/latest` **and** remove `.gitkeep`, empty
`artifacts/trajectories`, drop `git` from `PATH`, force C locale and a fixed
hash seed.

```
$ git archive 0afdbd8 | tar -x -C /tmp/repro
$ rm -rf artifacts/reports/latest artifacts/reports/latest/.gitkeep artifacts/trajectories/*
$ PATH=<no git> LC_ALL=C LANG=C PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 make verify
...
verify: documentation claims PASS (docs match measured artifacts)
verify: PASS (65.836s) — artifacts/reports/latest/verify_summary.json
```

**Result: 12/12 PASS from a pristine tree with no artifacts and no git.**
This is the strongest reproducibility evidence in the audit: it proves the
gate set does not depend on leftover state or on version control.

## R-2 Determinism

| Check | Result |
|---|---|
| `make replay-all` | **PASS (80/80 runs, 567 steps byte-identical)** |
| `make replay` (`--verify-suite` + Block 4) | PASS |
| Regenerated `trajectories.jsonl` vs previous | 80 rows; **only cursor tokens differ**; `metrics`, `final_findings`, `initial_observation` identical |
| Published baselines after regeneration | oracle 1.0000/+0.9920/4.0 · simple 1.0000/+0.9853/7.3 · random 0.2500/−0.5060/12.0 · mass 0.0000/−1.0000/1.0 — **unchanged** |

The only field that legitimately varies between runs is `duration_s` (wall
clock), which is excluded from comparison by design and was already documented.

## R-3 Pinned versions

| Item | Where |
|---|---|
| 30 frozen contract/config files | `configs/release_freeze.json`, `aggregate_sha256=0747baf0…` — verified intact after all changes |
| Scoring config hash | embedded as `config_hash` in every scoring artifact |
| Python version | recorded in `performance_report.json` (3.11.2) |
| Platform | recorded (`Linux-6.1.158+-x86_64-with-glibc2.36`) |
| Episode seeds | fixed and recorded per trajectory row (`seed: 2026`) |

`Frozen files were NOT modified` — the freeze manifest hash is byte-identical
before and after this audit, which is what makes the claim checkable.

## R-4 Single documented start command

`make verify` runs lint + the full 12-gate Judge Kit + the whole test suite +
docs verification + artifact synthesis, with no manual step. `make help`
lists 19 targets. This satisfies the engineering anchor "one command, no
undocumented action".

## R-5 What could NOT be verified here

| Item | Status | Why |
|---|---|---|
| `make docker-check` / `make docker-build` | **UNVERIFIED** | No `docker` binary in this sandbox (`make[1]: docker: No such file or directory`) |
| Docker image hardening flags (`--read-only`, `--cap-drop ALL`, `--network=none`, non-root `uid=10001`) | **UNVERIFIED** | reviewed in `Dockerfile`/`Makefile`, not executed |
| GitHub Actions CI on this branch | **UNVERIFIED at audit time** | run after push; see `FINAL_GITHUB_REPORT.md` |
| Jury hardware timing | **UNVERIFIED** | machine characteristics are the organisers'; the harness caveat says so |
| tzdata version stability across machines | **UNVERIFIED** | residual risk listed in `DEPENDENCY_AUDIT.md` |

None of these is reported as PASS anywhere in this audit.
