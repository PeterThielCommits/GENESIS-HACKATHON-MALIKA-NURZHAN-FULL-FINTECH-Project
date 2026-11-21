# Glossary

Terms are listed as the code uses them. If a term here and a term in code disagree, the code
wins — and you should fix this file.

---

| Term | Meaning in this project |
|---|---|
| **Episode** | One unit of evaluation: a public book, a sealed truth, a manifest, and the provenance that explains how the mutated twin was produced. Identified by `EP-{difficulty}-{16 hex}`. |
| **Twin / twin pair** | The **clean** book (C) and the **mutated** book (M) generated from the same history. Only M is published as the episode's public book; C exists to prove the mutation caused the difference. |
| **Clean twin** | A generated book that passes all of INV-01..17. Refused at build time otherwise. |
| **Mutated twin** | The clean twin after one or more operators have been applied, producing exactly the intended invariant violations. |
| **Sealed** | Material only the scorer may see: `truth.json`, `provenance.json`, `verifier_crosscheck.json`, `reject_log.json`. Never referenced by public output. |
| **Public surface** | The 12 book files in `public/` plus `manifest.json`. The only thing a solver may read. |
| **Manifest** | Public metadata: file hashes, `public_digest`, config hash, commitment. Contains no answer. |
| **Commitment** | `sha256(salt ‖ truth_digest)` published before the truth is revealed; the salt is sealed and derived from `(config_hash, episode_id)`. |
| **Canary** | A derived marker embedded nowhere in public output, used to *detect* leakage. A hit is a release blocker, not a warning. |
| **Operator** | A mutation: a class with `preconditions`, `apply_book`, `affected_ids`, `candidate_params` (and optionally `selection_table`). Never mutates the clean book. |
| **Operator registry** | `gen/errors/registry.py` — the single place an operator becomes selectable, validated against the frozen catalogue. |
| **Anomaly type / family** | The kind of error (`DUPLICATE_PAYMENT`, `PARTIAL_PAYMENT_ALLOCATION`). Declared in `contracts/anomaly_catalog.json`. |
| **Subtype** | A documented variant inside a family, e.g. `OVER_ALLOCATE_TO_ONE_INVOICE`. Recorded in sealed provenance. |
| **Invariant** | A rule the books must satisfy (`INV-01`..`INV-17`). The backbone of both correctness and truth. |
| **Violation** | One invariant breach with a deterministic signature: id, entity key, delta, currency, direction, tolerance, detail. |
| **Signature** | The *shape* of a violation set for an anomaly: which invariants are intended, allowed, forbidden. Frozen in `gen/errors/signatures.py`. |
| **Intended invariant** | Must fire for this anomaly; defines what the anomaly *is*. |
| **Allowed side effect** | May fire as a documented consequence; acceptable but not required. |
| **Forbidden invariant** | Must never fire; a hit means the operator is broken. |
| **Diff** | Structural comparison C→M: added / modified / removed rows, per-row changed fields. |
| **Diff-backed** | A finding whose claims are traceable to specific diff facts. Truth cannot exist without this. |
| **Evidence set** | A set of public ids sufficient to prove a finding. Findings carry alternative sets; the smallest is `minimal_evidence_size`. |
| **Reachable evidence** | Evidence that actually resolves in the public book (an id you can look up). Unreachable evidence → reject. |
| **Candidate truth** | Truth constructed from diff + violations + provenance, before it is accepted. |
| **Distractor** | A near-miss that looks like the anomaly but is fully explained by legitimate documents (e.g. a credit note that explains an apparent overpayment). Reported as a finding = false positive. |
| **Rejection sampling** | Bounded retry loop: if the attempt cannot satisfy every gate, record a frozen reason and retry, up to `reject_attempt_limit`. |
| **Reject reason code** | Frozen enum in `gen/reject.py` (`NO_CANDIDATE_PARAMS`, `SIGNATURE_MISMATCH`, `UNREACHABLE_EVIDENCE`, …). Never contains ids or seeds. |
| **`config_hash`** | Digest of the canonical generator config. Part of every episode's identity and commitment salt. |
| **`public_digest`** | Digest over the per-file hashes of the public surface. |
| **Difficulty (L1/L2/L3)** | Profile controlling anomaly count, distractor pairs and invoice volume. |
| **Minor units** | Integer representation of money (cents/tiyin). The only money representation allowed. |
| **Functional currency** | The company's reporting currency (`KZT` by default). Foreign amounts are converted at the policy rate. |
| **Document-date basis** | Policy rule: the FX rate of the invoice's document date governs its settlement and adjustment postings. |
| **Posting period** | Period label (`2025-M03`) an entry lands in, per the calendar and cutoff offset. |
| **Reporting date (aging)** | Last day of the last period the book posts in; the as-of date for INV-05. |
| **Layering rule** | `contracts`/`core` never import `gen`; `invariants` never import `gen`; the verifier may import neither. Enforced by AST test. |
| **Verifier (independent)** | Phase 8 component that discovers findings from public data alone. Must not import `gen` or `invariants`. |
| **Clean episode** | An episode with `anomaly_count=0`: no finding, mode `CLEAN`. Detects over-reporting. |
| **Gate** | A check whose verdict is machine-readable and whose failure stops the work (G1–G6 in the sweep; exit gates per phase). |
| **Exit gate** | The phase's acceptance criterion, expressed as executed commands with exit codes. |
