# Pull request

## What changed and why

<!-- One paragraph. Link the task (docs/TASKS/T-…), the decision (D-…), the CR, and the
requirement ids from docs/REQUIREMENTS.json that this serves. -->

- Task:
- Requirements:
- Decision / CR:

## Contract impact

- [ ] No contract change
- [ ] Contract change **with** a `docs/CR/` entry and `python -m tools.check_golden --write`
      committed in the same PR
- [ ] Fixtures added/updated for every changed schema (valid **and** invalid case)

## Evidence (paste real command output, not a promise)

```text
$ python3 -m unittest discover -s tests -t . -p 'test_*.py'
$ python3 -m tools.verify --profile core
```

Exit code of `verify-core`: <!-- 0 -->

## Honesty checklist

- [ ] No item is described as official; `official: false` / `provisional: true` unchanged
      wherever the official contract is still missing.
- [ ] Nothing in `sealed/`, `episodes/hidden/`, `artifacts/` or a salt/seed value is added.
- [ ] A check that does not run is reported `SKIPPED`/`BLOCKED`/`NOT RUN`, never `PASS`.
- [ ] Numbers in the PR match `artifacts/reports/latest/verify_summary.json`.
- [ ] `docs/STATUS.md`, `docs/CURRENT_STATE.md` and the phase report are updated if a gate moved.

## Human actions created or closed

<!-- e.g. "creates: Reviewer 2 must re-sign CONTRACT_SUMMARY §3" -->
