# TwinLedger — Phase 5 work in progress

TwinLedger is a proposed synthetic ledger audit environment. This branch contains a **provisional, partial Phase 5 implementation**, not an organizer-compatible benchmark. Earlier phases are absent from this branch; Phase 1 and 2 pull requests are open but unmerged. The supplied Master TZ is a project specification, not an organizer-issued contract. See [phase report](docs/PHASE_REPORTS/PHASE-05.md).

Python 3.11, stdlib only:

```sh
make test
make smoke
python3 -m env.cli tests/fixtures/example/public
```

The last command reads provisional actions, one JSON object per line, e.g. `{"tool":"list_records","args":{"table":"invoices","limit":1}}` and `{"tool":"submit","args":{"findings":[]}}`. This is a local smoke CLI, **not** the official adapter. It uses a fixed demo cursor key and is not a security boundary. The in-process API is `Environment.reset(public_dir, config)` and `step(action)`; see [interface notes](contracts/PROVISIONAL_PHASE_05.md).

The loader reads only named public files and avoids symlinks; this does not isolate policy processes, guarantee content is non-sensitive, or protect secrets from Python code sharing the process. No scorer, evaluator, post-submit finalize, organizer adapter, complete schemas, generator, verifier, or full `make verify` exists here. The example fixture is hand-authored synthetic test input, not a generated or independently verified episode. Do not use this branch for closed evaluation of untrusted policy code.
