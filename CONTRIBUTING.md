# Contributing to TwinLedger

Everything here is offline, stdlib-only, Python 3.11. No install step, no
network, no downloads (Master TZ §22.4).

```bash
make setup     # verifies Python 3.11; prints which optional extras are present
make verify    # the single command: lint + 12 gates + full suite
```

## Ground rules

1. **Never edit a frozen file.** `contracts/*.schema.json`, `configs/*`,
   `judge/rubric_map.json` and `docs/reference/TwinLedger_v3_Master_TZ_AI_Agents.txt`
   are locked by `configs/release_freeze.json`. Verify with:

   ```bash
   python3 tools/freeze_release.py --verify   # expect: 30 frozen files intact
   ```

   If a real contract change is needed, write a Change Request in
   `docs/DECISIONS.md` first (`D-14-02` is the precedent). Resolve genuine
   mismatches through validator tolerance, never by editing the contract.

2. **Money is integer minor units.** `Decimal` is constructed from strings.
   Binary float in monetary logic is a defect. Times are ISO-8601 with an offset;
   fiscal periods follow the company timezone, not the machine's.

3. **The sealed boundary is absolute.** No truth, provenance, salt, seed or
   hidden label may reach an observation, error message, policy log or public
   report (`REQ-ARENA-005`). `env/` must never import generator internals.

4. **The verifier is independent.** It uses public data only and must not import
   the generator or read provenance (`REQ-SEAL`). Never "prove independence" by
   writing two modules with the same algorithm.

5. **No unsupported claims.** Internal PASS is never an official jury score:
   reports carry `official_score_claimed: false` (TZ §23.6). Do not write
   "secure", "independent" or "reproducible" without the test that shows it.

## Before you open a PR

```bash
make lint            # compile check + import-boundary scan (REQ-ARC-001)
make test            # full suite
make verify          # 12 gates, writes artifacts/reports/latest/
make docs-verify     # every published number still matches its artifact
make rc-check        # verify + docs-verify + replay-all + release-audit
```

`make verify` must be **PASS 12/12** and `make rc-check` **PASS**. Do not open a
PR with a red gate; a red gate is the finding.

## Things that will bite you

- **Never hand-edit the README generated block** (between
  `<!-- BEGIN GENERATED:measured-facts -->` and `<!-- END GENERATED:measured-facts -->`).
  Regenerate it with `python3 tools/verify_doc_claims.py --write`.
- **Never gate a test on a gitignored artifact.** `artifacts/reports/latest/`,
  `doc_claims/`, `release/` and `evaluation/` are generated. Gate on the input,
  or drive the CLI into a temp directory (`D-15-01`, `D-16-01`).
- **Never assert a value produced by the run performing the check** — no gate
  pass-ratio, no self-measured test count.
- **Never add a report to `artifacts/reports/latest/`.** It is the frozen 20-file
  Judge Kit set. A 21st file makes documented counts false (`D-16-02`).
- **Every target must work in any order.** Run the whole §23.2 list before
  claiming a phase passes; `verify-core` after `build-episodes` is the case that
  used to break (`D-16-02`).
- **The container has no `git` and runs `LC_ALL=C`.** Console output must be
  ASCII-safe and file lists must not depend on Git metadata.

## Reporting

A phase is DONE only when scope, correctness, verification, documentation and
GitHub reporting are all closed. Record the result in
`docs/PHASE_REPORTS/PHASE-XX.md` / `.json` and
`docs/AGENT_REPORTS/YYYY-MM-DD/`. Report `FAIL`, `SKIPPED` and `NOT RUN` honestly;
a skipped mandatory check is never a pass.
