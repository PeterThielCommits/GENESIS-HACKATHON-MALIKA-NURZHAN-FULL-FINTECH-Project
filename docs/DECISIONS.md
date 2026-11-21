# DECISIONS (append-only)

Entries are never edited or deleted; superseding a decision means appending a new entry that
references the old one. Each entry records the decision, the reason, and what would have gone
wrong otherwise.

---

## D-001 — `Book` lives in the public layer (`contracts/book_model.py`)

**Date:** 2026-11-21 (Phase 4)
**Status:** accepted

The immutable `Book` model (and its canonical public-file rendering) moved from
`gen/twins.py` to `contracts/book_model.py`; `gen/twins.py` re-exports it unchanged.

**Why:** `invariants/checks_clean.py` must read the book, and it previously imported
`gen.twins`. That made the invariant layer depend on the generator, which would have made the
Phase 8 independent verifier structurally unable to reuse the checks. The layering rule
(`contracts`/`core` ↛ `gen`) is now enforced by a test rather than by convention.

**Consequence:** the public API is unchanged; `props`/`Book` imports keep working.

---

## D-002 — Determinism keyed to the seed, not to attempt position

**Date:** 2026-11-21 (Phase 4)
**Status:** accepted

Operator selection is derived from `sha256(master_seed)`; the candidate *within* an operator
is chosen from a per-attempt RNG stream (`mutation/<operator>/<index>/<attempt>`), and
subtype proportions come from `subtype_weights_bps`.

**Why:** a positional pick (`candidates[(attempt + index) % len]`) made the first configured
subtype dominate the corpus (observed 27 / 23 / 1 across subtypes). Retries also repeated the
same rejection instead of exploring.

**Consequence:** seeds still reproduce exactly, and the corpus covers every declared subtype.

---

## D-003 — A retry may switch anomaly family

**Date:** 2026-11-21 (Phase 4)
**Status:** accepted

If the scheduled family has no viable target on a clean twin (for example an L1 book with no
credit note), the episode builder selects another configured family that does have candidates.
The episode is still rejected (`NO_CANDIDATE_PARAMS`) if no family is applicable.

**Why:** an inapplicable family is a property of the *book*, not of the attempt, so retrying
the same family cannot succeed and burns the rejection budget for no benefit.

**Consequence:** rejection rate for otherwise-valid seeds dropped to 0 in the 48-episode sweep
while the budget still bounds pathological configurations.

---

## D-004 — Credit notes are their own accounting event

**Date:** 2026-11-21 (Phase 4)
**Status:** accepted

A credit-note journal entry references the credit note (not the invoice) and books the
invoice's document-date rate so the receivable is relieved without an artificial FX
difference. INV-09 (CUTOFF) judges only recognition postings against the recognition policy;
INV-07 (FX_POLICY) applies the document-date basis to settlement and adjustment postings.

**Why:** the previous combination judged an adjustment posting against the invoice's
recognition period, which produced `INV-09` on books the generator considered clean — a
contradiction between two parts of our own specification.

**Consequence:** clean twins are genuinely clean (0/180 unclean over 60 seeds × L1/L2/L3), and
adjustment events remain auditable.

---

## D-005 — Invariant checks are total functions

**Date:** 2026-11-21 (Phase 4)
**Status:** accepted

Every check in `invariants/checks_clean.py` either reports a `Violation` or defers to the
invariant that owns the malformation; none raises on adversarial input.

**Why:** a verifier runs on documents it did not create. A `KeyError` on a dangling reference
would crash discovery instead of reporting a finding, and the crash would be indistinguishable
from a broken harness.

**Consequence:** INV-06 defers dangling references to INV-12, INV-10/INV-07 defer unparsable
timestamps to INV-14, INV-08 defers currency/rate problems to INV-07/INV-13.

---

## D-006 — Numeric ids carry a table namespace

**Date:** 2026-11-21 (Phase 4)
**Status:** accepted

Style-D identifiers (pure digits with a Luhn check digit) prefix two digits encoding the table
namespace; styles A/B/C already carry per-table prefixes.

**Why:** per-table counters starting at 1 minted identical strings for different tables, and
`source_document_id` / allocation targets are *cross-table* pointers. Duplicate ids made
references ambiguous and tripped INV-11 on clean books.

**Consequence:** ids remain shortcut-free (no seed/type/position) and are now globally
unambiguous across document tables.

---

## D-007 — The exit gate is executable

**Date:** 2026-11-21 (Phase 4)
**Status:** accepted

`tools/phase4_sweep.py` encodes the Phase 4 gate as six named checks (both families generate,
clean twin clean everywhere, findings diff-backed, no forbidden invariant, rejection a
minority, determinism) and exits non-zero if any fails; `make verify` runs tests plus sweep.

**Why:** a gate described only in prose can be "passed" by assertion. An executable gate makes
the verdict reproducible and makes regressions visible in CI terms.

**Consequence:** `make verify` is the canonical evidence command for Phase 4.

---

## D-008 — Documentation is generated where it can drift, written where it must be argued

**Date:** 2026-11-21 (documentation consolidation)
**Status:** accepted

Facts that mirror code (invariant list, operator registry, schema inventory, public file set,
commands, difficulty profiles) are exported by `tools/export_context.py` into
`docs/CONTEXT/PROJECT_CONTEXT.json`, and a test fails when the committed copy is stale.
Prose that requires judgement (architecture rationale, invariant semantics, decisions, traps)
stays hand-written.

**Why:** prose duplication is the main way AI-agent context rots. Mechanical facts should be
derived, not retyped; reasoning should be written, not generated.

**Consequence:** `make test` includes `tests/docs/test_docs_consistency.py`, so documentation
rot is a test failure rather than a slow-burning inconsistency.

---

## D-009 — Documentation set is organised by *question*, not by phase history

**Date:** 2026-11-21 (documentation consolidation)
**Status:** accepted

`docs/` is organised so a fresh agent can answer one question per file
(`ARCHITECTURE`, `INVARIANTS`, `ERROR_MATRIX`, `DATA_CONTRACTS`, `DETERMINISM`, `TESTING`,
`CLEAN_TWIN_MODEL`, `OPERATIONS`, `GLOSSARY`, `AI_HANDOFF_PROTOCOL`), with `docs/README.md` as
the map. Phase history lives separately in `docs/PHASE_REPORTS/` and `docs/AGENT_REPORTS/`.

**Why:** new agents arrive with a task, not with a timeline. Searching by question beats
reconstructing history. History is still preserved, just not mixed into the reference path.

**Consequence:** adding a new topic means adding a question-shaped document and one line in
`docs/README.md`, not appending to an ever-growing single file.

---

## D-010 — Layer rule is `contracts`/`core`/`invariants` ↛ `gen`; declared in one place

**Date:** 2026-11-21 (documentation consolidation)
**Status:** accepted, supersedes the informal statement in D-001

The dependency rule is stated once, in `docs/CONTEXT/ARCHITECTURE.md` §2 and mirrored in
`tools/export_context.py::LAYERS`, and enforced by `LayeringTests`. The verifier entry
(`verifier/` may import `contracts`/`core`, never `gen`/`invariants`) is declared now so the
Phase 8 boundary cannot be quietly relaxed.

**Why:** an architectural rule that exists in three slightly different forms is not a rule.

**Consequence:** changing the allowed import direction requires editing the doc, the exporter
and the test together — which is exactly the friction such a change deserves.

---

## D-011 — Documentation tests check docs against code, never docs against docs

**Date:** 2026-11-21 (documentation consolidation)
**Status:** accepted

`tests/docs/test_docs_consistency.py` verifies: required documents exist and are non-trivial,
internal links resolve, the generated snapshot is current, every `INV-NN` named in prose
exists in the checker, the documented schema count equals the schemas on disk, the documented
public-file count equals `PUBLIC_FILE_ORDER`, and phase reports contain the required evidence
sections and executed-command tables.

**Why:** docs-to-docs consistency proves only that the documents agree with each other, which
is what stale documentation always does.

**Consequence:** a documentation test failing means the code and the docs disagree — and the
code is the authority.
