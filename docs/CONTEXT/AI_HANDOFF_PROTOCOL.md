# AI Handoff Protocol

How context survives between agents. Written because the usual failure mode is not missing
information — it is **stale, duplicated and unverified** information that a new agent trusts.

---

## 1. Single source of truth

| Kind of fact | Authority | Never |
|---|---|---|
| What the code does | **the code** | trust a doc that disagrees |
| Scope and acceptance criteria | `docs/official/` (master TZ + universal prompt) | paraphrase the TZ from memory |
| Invariant catalogue, error matrix, registry | `gen/errors/signatures.py`, `contracts/anomaly_catalog.json`, `gen/errors/registry.py` | hand-maintain a second copy |
| Test counts, gates, digests | a command run in this session | copy numbers from an older report |
| Decisions and their reasons | `docs/DECISIONS.md` (append-only) | edit or delete an entry |
| Machine-readable snapshot | `docs/CONTEXT/PROJECT_CONTEXT.json` (**generated**) | hand-edit it |

`PROJECT_CONTEXT.json` is produced by `tools/export_context.py` from live code, and
`tests/docs/test_docs_consistency.py` fails if the committed copy is stale. That is how this
documentation stays honest instead of aspirational.

## 2. Required reading order for a fresh agent

1. `docs/README.md` — 4-minute orientation (you are here if you came from there).
2. `docs/STATUS.md` — phase, gates, gaps, one screen.
3. `docs/CONTEXT/NEXT_AGENT.md` — handover brief, traps, extension recipe.
4. `docs/PHASE_REPORTS/PHASE-04.md` §2 (traceability) and §6 (deviations).
5. `docs/DECISIONS.md` — thirteen accepted decisions with reasons.
6. `docs/CONTEXT/ARCHITECTURE.md` and `INVARIANTS.md` before touching generation code.

Then run `make verify` **before** your first edit. Never start from a state you have not
verified.

## 3. Handoff artefact: the session record

Every agent session that changes the project leaves three things:

| Artefact | Location | Content |
|---|---|---|
| Phase report | `docs/PHASE_REPORTS/PHASE-NN.md` + `.json` | scope traceability, command→exit→result table, deviations, known issues |
| Agent report | `docs/AGENT_REPORTS/<date>/<agent>-phase-NN.md` | what was attempted, what broke, what was learned |
| Decision entries | `docs/DECISIONS.md` | each non-obvious choice, its reason, its consequence |

The agent report is deliberately candid: defects found by gates, dead ends, and near-misses are
the most valuable part of the record, because they prevent a successor from repeating them.

## 4. Writing rules (these are the ones that actually prevent drift)

1. **Every claim carries evidence.** A number without a command, an exit code and a result is
   not allowed in a report.
2. **State the negative.** "Both families generate and pass all current gates" is weaker than
   "both generate; 0 forbidden-invariant hits; 0 rejects in 48 attempts".
3. **Never write a verdict you did not execute.** `SKIPPED` is not `PASS`. `PASS` requires a
   run.
4. **No secret-adjacent claims.** Do not describe the boundary as "secure"; describe exactly
   what was tested (no leak in produced artifacts, layering enforced), and leave it there.
5. **Append, don't rewrite, history.** Decisions and phase reports are append-only. A change of
   mind is a new entry referencing the old one.
6. **Record traps where they bit.** Each entry in `NEXT_AGENT.md` §4 came from a real failure.

## 5. Updating documentation in the same change

| You changed | Update |
|---|---|
| an invariant | `docs/CONTEXT/INVARIANTS.md`, `tools/export_context.py` catalogue, then regenerate |
| an operator or family | `docs/CONTEXT/ERROR_MATRIX.md`, `docs/CURRENT_STATE.md`, regenerate |
| a public file or schema | `docs/CONTEXT/DATA_CONTRACTS.md`, regenerate |
| a test suite | `docs/CONTEXT/TESTING.md` counts, regenerate |
| a decision | append `docs/DECISIONS.md` |
| phase completion | `docs/STATUS.md`, `docs/CURRENT_STATE.md`, phase report, agent report |

Then:

```bash
python3 tools/export_context.py            # regenerate the snapshot
make docs-check                            # fail fast if it is stale
make test-docs                             # documentation <-> code checks
make verify                                # tests + gate sweep
```

## 6. Conflict resolution

If two documents disagree:

1. **Code wins** over prose; fix the prose.
2. **`docs/official/` wins** over any summary of scope.
3. **A newer decision wins** over an older one, but the old entry stays and is referenced.
4. If the disagreement is about *intent* rather than fact, it is a decision to be made and
   recorded — not a documentation bug to be quietly patched.

## 7. What "context is unified" means here

A new agent should be able to answer these questions **without opening the code**, and then
verify each answer by running one command:

| Question | Fast answer lives in |
|---|---|
| What phase are we in and did it pass? | `docs/STATUS.md` |
| What are the rules the books obey? | `docs/CONTEXT/INVARIANTS.md` |
| What may each anomaly break? | `docs/CONTEXT/ERROR_MATRIX.md` |
| What is public vs sealed? | `docs/CONTEXT/DATA_CONTRACTS.md` |
| Why is this deterministic? | `docs/CONTEXT/DETERMINISM.md` |
| What does each test prove? | `docs/CONTEXT/TESTING.md` |
| Why is the code shaped this way? | `docs/CONTEXT/ARCHITECTURE.md` |
| Why was decision X taken? | `docs/DECISIONS.md` |
| What will bite me? | `docs/CONTEXT/NEXT_AGENT.md` §4 |
| What exactly exists right now? | `docs/CONTEXT/PROJECT_CONTEXT.json` |

If any answer is missing or stale, that is the highest-value thing you can fix in your first
hour — it compounds for every agent after you.
