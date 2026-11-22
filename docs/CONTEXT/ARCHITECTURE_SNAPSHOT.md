# Architecture Snapshot — as built (v1.0.0)

Rewritten 2026-11-22 from the real module tree. The previous version of this
page was written as a *plan* and never reconciled with the code: it named seven
modules that were never built, a test count of 295, and a gate range of
`RC-001..RC-005`. Every path on this page is now asserted by
`tools/verify_doc_claims.py::C-PATHS`, so it cannot silently rot again.

## Runtime constraints

- **Python 3.11, standard library only** across `contracts`, `core`,
  `invariants`, `gen`, `verifier`, `env`, `adapter`, `scoring`, `seal`,
  `harness`, `arena`, `nlp`, `metamorphic`, `judge`, `tools`.
- Offline by construction: no network call, no model download, no `pip install`.
  Enforced by `tools/release_audit.py` (0 undeclared external imports across 109
  runtime modules) and by the `docker-offline` CI job.
- Determinism: namespaced RNG streams, canonical JSON as the only hashing input,
  exact `Fraction`/`Decimal` arithmetic, and integer minor units everywhere.

## Zone map (AST-enforced by `tools/check_import_boundaries.py`)

Dependencies point downward only. Violating this fails `make lint`, which is part
of `make verify` (`RC-002`, release blocker).

### Shared frozen boundary — `contracts/`

JSON Schema draft-07 documents plus stdlib-only helpers:
`contracts/canonical.py` (canonical JSON + SHA-256), `contracts/currency.py`
(ISO-4217 exponents), `contracts/validate.py` (schema validation without
`jsonschema`), `contracts/models.py` (typed domain models),
`contracts/loader.py` (bounded episode-file reads), `contracts/version.py`,
and the `*.schema.json` family. Contains **zero** accounting or detection logic:
it is a wire contract only, which is why sharing it with the verifier does not
create a common-mode failure (`docs/INDEPENDENCE.md`).

### Primitives — `core/` and `invariants/`

- `core/money.py` — integer minor units, `Decimal`-from-string parsing, rounding
  policies, exponent lookup.
- `core/time_rules.py` — IANA timezone and fiscal-period calendar arithmetic.
- `core/ids.py` — deterministic, namespace-keyed ID factory with four families.
- `invariants/checks.py` — the machine-readable invariant catalogue
  (`INV-01..INV-17`) that mutation operators must perturb and must not exceed.

These are deliberately **not** shared with `verifier/`, which implements its own
`verifier/money_time.py` on `fractions.Fraction` (zero common mode).

### Zone 1 — generator `gen/`

- `gen/core/clean_twin.py` — chart of accounts, counterparties, invoices,
  payments, bank lines, journal entries; produces a balanced book by
  construction. `gen/core/rng.py` — namespaced RNG service.
  `gen/core/text.py` — deterministic `ru`/`kk`/`en` templates.
- `gen/distractors/catalog.py` — the 16 clean distractor families
  (`D-DUP-01..04`, `D-PART-01..04`, `D-FX-01..04`, `D-CUT-01..04`): legitimate
  transactions that *resemble* each anomaly type and must not be flagged.
- `gen/errors/operators.py` — `DUPLICATE_PAYMENT` and
  `PARTIAL_PAYMENT_ALLOCATION`; `gen/errors/fx_cutoff.py` —
  `FX_RATE_MISMATCH` and `PERIOD_CUTOFF`.
- `gen/truth.py` — candidate truth from a structural clean→mutated diff, with
  invariant signatures; `gen/serialize.py` — canonical episode serialisation;
  `gen/pipeline.py` — recipes, rejection sampling, and the release build.

`diff(C, M)` proves *what changed*, never *that it is wrong*; semantic wrongness
comes from the invariant catalogue plus the independent verifier
(`docs/DESIGN.md` §3).

### Zone 2 — environment, scoring, sealing, harness

- `env/` — `env/loader.py` (public-only, bounded), `env/cursors.py` (opaque
  HMAC cursors), `env/calc.py` (AST-only exact `Decimal` calculator),
  `env/environment.py` (`TwinLedgerEnv` reset/step), `env/jsonl_server.py`
  (JSONL stdio server, `--require-closed-eval`), `env/errors.py`.
- `adapter/` — `adapter/official_env.py` (`TwinLedgerOfficialEnv`: the four
  canonical tables `ledger`/`invoices`/`payments`/`fx` plus aliases, the official
  action names), `adapter/organizer.py`.
- `scoring/` — `scoring/matcher.py` (exact predicate + deterministic
  maximum-cardinality bipartite matching), `scoring/official_scorer.py` (the
  **single** reward implementation, `D-18-01`), `scoring/reward.py` (thin view
  over it), `scoring/crosscheck.py` (Stage-2 truth crosscheck),
  `scoring/diagnostics.py`, `scoring/exhaustive.py` (brute-force differential
  matcher), `scoring/explanation_linter.py`, `scoring/scorer_cli.py`
  (post-termination isolated scorer), `scoring/canon.py`.
- `seal/` — `seal/commitment.py` (commit-reveal), `seal/hashchain.py`
  (trajectory hash chain), `seal/merkle.py` (RFC-6962 Merkle tree),
  `seal/receipt.py`, `seal/rekey.py` (`PRODUCTION_SECRET` rekey), `seal/cli.py`.
- `harness/` — `harness/runner.py` (3-subprocess `CLOSED_EVAL` orchestrator),
  `harness/sandbox.py` (staged read-only public + scratch workspaces, honest
  `SecurityProfile`), `harness/ns_launcher.py` (Linux user/mount/net namespaces +
  `seccomp-BPF`), `harness/protocol.py` (JSONL v1.0 + outbound leakage guard),
  `harness/trajectory.py`, `harness/env_process.py`, `harness/policy_process.py`,
  `harness/scorer_process.py` (post-termination barrier),
  `harness/reference_policies.py`, `harness/replay.py`,
  `harness/isolated_runner.py`.

### Zone 3 — independent verifier and red team

- `verifier/` — `verifier/discover.py` (entry point), one detector per anomaly
  type: `verifier/duplicate_payment.py`, `verifier/partial_allocation.py`,
  `verifier/fx_mismatch.py`, `verifier/period_cutoff.py`;
  `verifier/proof_graph.py` (DAG), `verifier/minimal_sets.py` (minimal and
  alternative evidence sets), `verifier/evidence.py` (reachability),
  `verifier/money_time.py` (its own `Fraction` FX and `zoneinfo` period logic),
  `verifier/public_loader.py` (12-file allowlist), `verifier/validate.py`,
  `verifier/result.py`, `verifier/__main__.py`.
  Imports neither `gen/` nor `nlp/` nor `scoring/` — asserted by AST scan and by
  a runtime file-open spy (`docs/INDEPENDENCE.md`).
- `arena/` — `arena/policies/` (baselines), `arena/attacks/catalog.py`
  (`AT-01..AT-22`), `arena/autohacker.py` (heldout sensitivity probe).
- `nlp/` — `nlp/hierarchy.py` (4-tier evidence hierarchy, rejects text-only
  proof), `nlp/injection_guard.py`, `nlp/matching.py`, `nlp/normalize.py`.
- `metamorphic/` — `metamorphic/paired_transform.py` (7 paired transforms),
  `metamorphic/suite.py`.

### Zone 4 — judge kit and evidence

`judge/verify.py` (the 12-gate runner and exit-code contract),
`judge/rubric_map.json` (frozen gate→requirement map),
`judge/report.py` (offline `report.html` + `report_index.json`),
`judge/schemas.py` (TZ §23.5 envelope validation),
`judge/performance_and_deps.py`, `judge/mutation_suite.py`,
`judge/shortcut_audit.py`, `judge/canary_fuzzer.py`,
`judge/robustness_audit.py`, `judge/oracle_policy.py`.

`tools/` holds the reviewer-facing entry points: `verify_doc_claims.py`,
`release_audit.py`, `replay_all_trajectories.py`, `freeze_release.py`,
`demo_walkthrough.py`, `demo_server.py`, `make_dataset.py`,
`run_official_eval.py`, `check_import_boundaries.py`, `inspect_episode.py`,
`verify_manifest.py`, `explanation_report.py`.

## Entrypoints

| Entrypoint | Purpose |
|---|---|
| `judge_adapter.py` (repo root) | The three official functions: `generate_episode`, `make_env`, `score_episode` |
| `python3 -m env.jsonl_server` | JSONL policy protocol (core vocabulary: `list_records`, `get_record`, `get_document`, `calc`, `submit`) |
| `python3 -m harness.replay` | Fresh-process deterministic replay |
| `make verify` | 12-gate Judge Kit + 20 evidence artifacts |
| `python3 tools/demo_server.py` | Optional zero-dependency workbench UI/API |

The adapter spells the calculator `calculator` and the core protocol spells it
`calc`; each rejects the other's name. That asymmetry is intentional
(`D-15-02`) and is pinned by `C-PROTOCOL-TOOLS`.

## Verification surface

`make verify` runs 12 gates (`RC-001..RC-012`) defined in the frozen
`judge/rubric_map.json`, writes 20 evidence artifacts into
`artifacts/reports/latest/`, and then runs the documentation gate
(`tools/verify_doc_claims.py`) once every artifact exists. Optional extras
(`hypothesis`) skip explicitly; a critical skip can never yield exit 0.
