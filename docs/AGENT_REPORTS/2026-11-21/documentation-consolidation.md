# Agent Report — Documentation Consolidation (2026-11-21)

**Agent:** Arena coding agent (Agent Mode)
**Scope:** build the complete documentation and context layer for the repository so that
knowledge transfers between AI agents without loss or drift
**Status:** DONE — verified by tests, not by assertion

---

## 1. Problem being solved

Phase 4 produced a working generator plus four documents. That is enough for the agent that
wrote the code and not enough for the next one. Three specific risks:

1. **Drift.** Facts duplicated in prose (test counts, invariant lists, schema counts) silently
   diverge from code. A new agent then trusts the wrong number.
2. **Missing reasoning.** The code shows *what*, not *why*: why settlement uses the
   document-date rate, why credit notes are excluded from CUTOFF, why numeric ids carry a
   namespace. Without that, a successor "simplifies" the design and breaks the benchmark.
3. **Undiscoverable failures.** Seven defects were found by gates in Phase 4. Unless they are
   written down as traps, they will be rediscovered the hard way.

## 2. What was built

### 2.1 Generated context (anti-drift)

`tools/export_context.py` derives the machine-readable snapshot
`docs/CONTEXT/PROJECT_CONTEXT.json` from live code: layers and their import rules, book tables,
the 12 public files, sealed file names, the 16 schemas, the 17 invariants, the operator registry
with its three-set signatures, difficulty profiles, reject reason codes, canonical commands,
and an index of every document.

`tests/docs/test_docs_consistency.py` regenerates it and fails when the committed copy is stale
(`D-008`). Documentation rot is now a red test, not a slow inconsistency.

### 2.2 Reference documents, organised by question (anti-loss)

| Document | Question it answers |
|---|---|
| `docs/README.md` | "where do I start and what is this?" |
| `docs/CONTEXT/ARCHITECTURE.md` | "how is it structured and why are the boundaries where they are?" |
| `docs/CONTEXT/INVARIANTS.md` | "what rules must the books obey?" (scope, key, metric, tolerance, null semantics, ownership) |
| `docs/CONTEXT/ERROR_MATRIX.md` | "what may each anomaly break?" |
| `docs/CONTEXT/DATA_CONTRACTS.md` | "what is public, what is sealed, what shape is each document?" |
| `docs/CONTEXT/DETERMINISM.md` | "how is reproducibility actually guaranteed?" |
| `docs/CONTEXT/TESTING.md` | "what does each test prove, and how do I add one?" |
| `docs/CONTEXT/CLEAN_TWIN_MODEL.md` | "how is a clean book built, and why is it clean?" |
| `docs/CONTEXT/OPERATIONS.md` | "how do I run things, and what do these errors mean?" |
| `docs/CONTEXT/AI_HANDOFF_PROTOCOL.md` | "how do we exchange context without losing it?" |
| `docs/GLOSSARY.md` | "what does this domain term mean here?" |

### 2.3 History, kept out of the reference path (anti-ambiguity)

`docs/PHASE_REPORTS/` (evidence with command → exit → result), `docs/AGENT_REPORTS/` (what was
attempted, what broke), `docs/DECISIONS.md` (append-only, D-001…D-011). Reference documents
describe the present; reports describe how it got there.

## 3. Findings while documenting

Documentation work surfaced two real inconsistencies in the existing artefacts:

| Finding | Resolution |
|---|---|
| `INVARIANTS.md` would have referenced a glossary that did not exist at the documented path | glossary created at `docs/GLOSSARY.md`, exporter path corrected, link test added |
| Test counts in prose (254) became wrong as soon as doc tests were added | counts updated; a test now asserts the documentation-consistency count matches the module, so the same class of drift fails |

Additionally, the prose claimed "17 schemas" while the repository contains **16**. The
authoritative count is the file system, exposed by the exporter and asserted against the docs.

## 4. Verification

| Command | Exit | Result |
|---|---|---|
| `python3 -m unittest tests.docs.test_docs_consistency` | 0 | 19 tests OK |
| `python3 tools/export_context.py --check` | 0 | `OK: … is current` |
| `python3 -m unittest discover -s tests -t .` | 0 | **273 tests OK, 0 skipped** |
| `make sweep` | 0 | 6/6 gates, unchanged by documentation work |

The documentation tests check documents **against code**: required files exist and are
non-trivial, internal links resolve, the snapshot is current, every documented `INV-NN` exists
in the checker, the documented schema count equals the schemas on disk, the documented
public-file count equals `PUBLIC_FILE_ORDER`, phase reports contain their required evidence
sections, and no report claims a "GitHub update" without a URL.

## 5. Judgement calls

* **Generated vs written.** Only mechanical facts are generated. Rationale, trade-offs and
  traps stay hand-written — generated prose reads plausible and says nothing.
* **One question per file.** A single growing `CONTEXT.md` was rejected: agents search by
  question, and long files hide the answer that matters.
* **The docs tests deliberately do not compare docs to docs.** Agreement between documents is
  what stale documentation already has.
* **Counts are stated with their provenance** ("254 at gate time; 273 now") instead of being
  retroactively rewritten, so the phase report stays a truthful historical record.

## 6. What the next agent gets

A cold start now looks like: read `docs/README.md` (4 min) → `docs/STATUS.md` (1 min) →
`docs/CONTEXT/NEXT_AGENT.md` (3 min) → run `make verify` (~50 s) → start work with the layer
rule, the invariant ownership table, the error matrix and the trap list already in context.
