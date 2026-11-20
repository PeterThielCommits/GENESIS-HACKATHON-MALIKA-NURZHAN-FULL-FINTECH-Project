# DECISIONS — TwinLedger

Append-only decision log. Every entry is dated, owned and reversible only through a new
decision that explicitly supersedes it. Machine-checked fields: `Status`, `Date`, `Owner`,
`Refs` (see `tests/phase0/test_decisions.py`).

Hierarchy of sources (master spec §2.1): organizer contract → submission interface →
master specification → this file → convenience. A decision here can never override an
official organizer statement; when they conflict, the adapter is changed first and a CR
is opened.

---

## D-0001 — Phase 0 has no archived organizer contract; the contract set is provisional

- **Status:** Accepted
- **Date:** 2026-11-20
- **Owner:** A0 orchestrator
- **Refs:** REQ-ADAPTER-001, REQ-CONTRACT-004, §0.3, §2.2, Q-001..Q-014
- **Context:** Phase 0 task 0.1 requires the full official technical specification, rubric,
  sample inputs/outputs and starter code. None of these are available to this repository:
  the master specification itself states the Claude share link did not open, and no
  organizer document was supplied as a readable file. Public code search returns other
  participants' repositories, which are not authoritative.
- **Decision:** Treat the TwinLedger v3.0 master specification as the *internal normative
  source* and mark every external-facing element `provisional`. All sixteen open
  assumptions (A-001…A-016) are `UNRESOLVED` and each is isolated in `adapter/` and
  `configs/`; no core module may encode an external name, limit or formula directly.
- **Alternatives:** (a) Assume the Appendix H examples are official — rejected, the
  appendix explicitly says they are illustrative; (b) treat a third-party repository as
  the organizer contract — rejected, it is neither published by the organizers nor
  verifiable; (c) delay all work until the contract arrives — rejected, gate 0 allows a
  documented safe solution for an unresolved risk.
- **Consequences:** Positive: nothing can silently become "official". Negative: the
  adapter is unbound, so no end-to-end official run is possible yet — recorded as an open
  item in `docs/STATUS.md`, not as a pass.
- **Supersedes:** —

## D-0002 — No provisional formula or rubric weight may be presented as official

- **Status:** Accepted
- **Date:** 2026-11-20
- **Owner:** A0 orchestrator
- **Refs:** REQ-JUDGE-003, §0.3, §15.5, §23.4, §23.6
- **Context:** The reward formula (ETA=0.05, max_steps=100) and the 25/25/25/15/10 point
  distribution are marked preliminary in the master specification. Presenting either as
  official would be a false claim to the jury.
- **Decision:** Reward parameters live only in `configs/scoring/reward.json` with
  `provisional: true`; the rubric map carries `official_rubric_available: false` and
  `official: false` on every check (enforced by `contracts/rubric_check.schema.json`
  `const: false`). Reports show an *internal* suite pass rate and label it as such.
- **Alternatives:** Hardcode the weights and adjust later — rejected (R-01, R-20).
- **Consequences:** A human must confirm before any score is described as official.

## D-0003 — Python 3.11, stdlib-only mandatory core, optional extras never required

- **Status:** Accepted
- **Date:** 2026-11-20
- **Owner:** A0 orchestrator
- **Refs:** REQ-OPS-001, REQ-OPS-002, §22.1, §22.2, A-013
- **Context:** The judge machine is offline with a pinned Python. The mandatory path
  (contracts, generator, environment, scorer, replay, verify) must run without a single
  download.
- **Decision:** `requires-python = ">=3.11,<3.12"`, no runtime dependencies, optional
  extras (`pytest`, `hypothesis`, `jsonschema`, …) declared but never imported by
  mandatory code. Contract validation uses an in-repo validator
  (`tools/jsonschema_lite.py`) instead of the `jsonschema` package.
- **Alternatives:** Depend on `jsonschema`/`pytest` for correctness — rejected: R-15 and
  the offline release blocker.
- **Consequences:** We own a small validator; it is restricted to a documented keyword
  subset and fails the build if a schema leaves that subset.

## D-0004 — Money is integer minor units; floats are rejected by canonical JSON

- **Status:** Accepted
- **Date:** 2026-11-20
- **Owner:** A0 orchestrator
- **Refs:** REQ-MONEY-001, REQ-MONEY-002, REQ-MONEY-004, §9.1
- **Context:** Binary floating point cannot represent money exactly and silently breaks
  tolerance checks.
- **Decision:** Stored amounts are `int` minor units per `contracts/currency.json`
  exponents; rates and intermediate values are `Decimal` parsed from strings;
  `tools/canonical_json.py` raises on any `float`, so a float cannot reach a hash or a
  contract-validated document. Currency exponents are explicit configuration data.
- **Alternatives:** `Decimal` everywhere — rejected: JSON has no decimal type and the
  official protocol shows integer amounts; `float` — rejected outright.
- **Consequences:** Callers must convert at the boundary; the boundary is tested.

## D-0005 — One canonical JSON implementation defines all hashes

- **Status:** Accepted
- **Date:** 2026-11-20
- **Owner:** A0 orchestrator
- **Refs:** REQ-CONTRACT-010, REQ-CONTRACT-011, REQ-CONTRACT-012, §7.2
- **Context:** Commitments, manifest hashes, trajectory chains and replay comparisons are
  meaningless if two components serialize the same object differently.
- **Decision:** `tools/canonical_json.py` is the single definition: UTF-8,
  `sort_keys=True`, `separators=(",",":")`, `ensure_ascii=False`, no NaN/Infinity, floats
  rejected, `Decimal` as plain decimal text, duplicate object keys rejected on parse.
  Phase 1 promotes this file into the core package with the same golden tests.
- **Alternatives:** `json.dumps` at each call site — rejected (REQ-CONTRACT-010).
- **Consequences:** Key-order independence is a tested property, not an assumption.

## D-0006 — Import direction and the adapter boundary are enforced by AST scan

- **Status:** Accepted
- **Date:** 2026-11-20
- **Owner:** A0 orchestrator
- **Refs:** REQ-ARC-001, REQ-ARC-002, REQ-ARC-003, REQ-ADAPTER-002, §6
- **Context:** The independence claims (env ↛ truth, verifier ↛ generator, policy ↛
  scorer) are only credible if a machine rejects violations on every build.
- **Decision:** `tools/check_import_boundaries.py` parses every `.py` file with `ast` and
  applies the layer rules from §6. `adapter/` may import only stdlib and `contracts`
  data; nothing imports `adapter/` except the harness and tests.
- **Alternatives:** Code review only — rejected, not verifiable by the jury.
- **Consequences:** A forbidden import fails `make lint` with the file, line and rule id.

## D-0007 — Contract versioning, unknown-field policy and the CR requirement

- **Status:** Accepted
- **Date:** 2026-11-20
- **Owner:** A0 orchestrator
- **Refs:** REQ-CONTRACT-003, REQ-CONTRACT-004, §7.1, §7.3
- **Context:** Without a rule, "just add a field" breaks the matcher, replay and the
  official adapter at once.
- **Decision:** `contracts/version.json` declares the set version (`0.1.0`), the payload
  version (`1.0.0`) and semver rules. Unknown fields are rejected; extensions must use the
  `x_twinledger_` prefix. Any behavioral change needs a CR in `docs/CR/` plus a decision
  entry, and the contract digest printed by `make verify` must change in the same commit.
- **Alternatives:** Lenient parsing — rejected: REQ-ADAPTER-003 forbids silent fallback.
- **Consequences:** The digest acts as the freeze marker (gate 1 will lock it).

## D-0008 — Sealed, hidden and generated data are never committed

- **Status:** Accepted
- **Date:** 2026-11-20
- **Owner:** A0 orchestrator
- **Refs:** REQ-DATA-022, REQ-SEAL-012, REQ-GH-007, §5, §8.6, A-012, A-015
- **Context:** Phase 0 must decide the Git rule for sealed data. Committing truth,
  provenance or held-out episodes would destroy the benchmark and could leak answers.
- **Decision:** `episodes/**/sealed/`, `episodes/hidden/`, `episodes/train/`,
  `episodes/dev/`, salts, artifacts and reports are git-ignored. What *is* committed:
  episode manifests (hashes only), golden digest files (hashes only) and tiny hand-authored
  fixtures whose salt is explicitly labelled `TEST_FIXTURE` (REQ-SEAL-013). The full rule
  and the reasons are in `docs/GIT_AND_DATA_POLICY.md`; a test asserts the ignore rules.
- **Alternatives:** Commit dev episodes for reproducibility — rejected for now; the golden
  digests give reproducibility without publishing the answer key.
- **Consequences:** Regeneration is required to inspect an episode locally; the digests
  make that verifiable offline.

## D-0009 — Reward, step accounting and tolerance are configuration, not code

- **Status:** Accepted
- **Date:** 2026-11-20
- **Owner:** A0 orchestrator
- **Refs:** A-004, A-005, A-006, A-007, A-011, A-014, REQ-SCORE-001, §15.5
- **Context:** The official formula, ETA, max_steps, submit accounting and tolerance model
  are all unconfirmed. If they are literals in the scorer, a contract change becomes a
  rewrite and old episodes silently reinterpret.
- **Decision:** `configs/scoring/reward.json`, `configs/scoring/tolerance.json` and
  `configs/environment/limits.json` hold every such value with `config_version`. The
  config hash is recorded in every episode manifest (REQ-CONTRACT-020).
- **Alternatives:** Constants in `scoring/reward.py` — rejected.
- **Consequences:** Phase 9 and Phase 13 read the config; no magic numbers are allowed
  outside configs (checked in Phase 1 when `scoring/` exists).

## D-0010 — Tolerance model `ROUNDING_OPERATIONS_V1` is provisional until proven per type

- **Status:** Accepted
- **Date:** 2026-11-20
- **Owner:** A0 orchestrator
- **Refs:** A-014, REQ-MONEY-005, §9.2
- **Context:** `tolerance_minor = n_round * 1` is only valid if the maximal error really is
  bounded by the number of rounding operations, which depends on the anomaly type.
- **Decision:** Ship the rule as configuration with an explicit proof obligation per
  anomaly type. Widening tolerance after observing policy results is forbidden and stated
  in the config file. Where the proof fails, the rule is versioned up before data release.
- **Alternatives:** Use a "safe" generous tolerance — rejected: it would accept wrong
  answers and violate the reward contract.
- **Consequences:** Phase 4 must produce a per-type rounding trace before release.

## D-0011 — `CLOSED_EVAL` is the default mode; `OPEN_DEV` is never evidence of isolation

- **Status:** Accepted
- **Date:** 2026-11-20
- **Owner:** A0 orchestrator
- **Refs:** A-008, REQ-ENV-030, REQ-ENV-031, REQ-ENV-032, §14.9
- **Context:** A development convenience can quietly become the mode used for the jury.
- **Decision:** The harness selects the mode explicitly and `CLOSED_EVAL` is the default
  in config and code. In closed mode the step reward is literally `0` and `info` is
  restricted to `steps_used`/`steps_remaining`. An environment variable can never flip the
  mode; all mode differences are tested.
- **Alternatives:** "Closed unless `DEV=1`" — rejected: REQ-ENV-031.
- **Consequences:** Local debugging is slightly less convenient and requires an explicit
  mode argument, which is visible in every report.

## D-0012 — Process separation is not a sandbox; controls are described honestly

- **Status:** Accepted
- **Date:** 2026-11-20
- **Owner:** A0 orchestrator
- **Refs:** REQ-SEAL-001..005, §3 «ГРАНИЦЫ ПРОЦЕССОВ», §16.2, R-09
- **Context:** A subprocess without OS controls can still read files and open sockets.
  Claiming "sandbox" would be a false isolation claim.
- **Decision:** The evidence we may claim is limited to what is actually enabled
  (separate working directory, stdin/stdout only, allowlisted environment, no sealed path
  mounted for env/policy, fixed argv without a shell). `docs/THREAT_MODEL.md` lists each
  control with its status, and `docs/LIMITATIONS.md` names what is *not* enforced on this
  platform.
- **Alternatives:** Say "we use subprocesses, therefore isolated" — rejected.
- **Consequences:** Phase 8/16 must measure and record the actual profile per platform.

## D-0013 — Synthetic universe: reserved codes, no real entities, no personal data

- **Status:** Accepted
- **Date:** 2026-11-20
- **Owner:** A0 orchestrator
- **Refs:** REQ-DATA-005, §8.1
- **Context:** A benchmark that accidentally embeds real companies, IBANs or people is a
  legal and ethical defect, not a cosmetic one.
- **Decision:** Jurisdiction codes are `XA`…`XZ` and are documented as *internal
  placeholders, not ISO-3166 assignments*. Company, counterparty and bank names are
  generated from invented phrases; contract fixtures use obviously fictional entities.
  Company schema enforces the code pattern, so a real country code cannot be introduced.
- **Alternatives:** Use real ISO codes for realism — rejected.
- **Consequences:** Some realism is lost; the constraint is visible in the schema.

## D-0014 — ID namespaces are fixed to seven prefixes

- **Status:** Accepted
- **Date:** 2026-11-20
- **Owner:** A0 orchestrator
- **Refs:** A-002, A-003, REQ-DATA-001, REQ-DATA-002, §8.4, §15.1
- **Context:** Canonicalization must be able to tell record kinds apart without guessing,
  and must not strip prefixes in a way that creates collisions.
- **Decision:** The contract allows `JE, INV, CN, PAY, BANK, FX, CP`. Adding a namespace
  is a minor contract change plus CR. ID *styles* (A/B/C/D) vary, namespaces do not.
- **Alternatives:** Free-form IDs — rejected: the matcher cannot canonicalize them.
- **Consequences:** New entity families must reuse an existing namespace or trigger a CR.

## D-0015 — The verification harness reports PASS/FAIL/SKIPPED/BLOCKED with artifacts

- **Status:** Accepted
- **Date:** 2026-11-20
- **Owner:** A0 orchestrator
- **Refs:** REQ-JUDGE-001..005, §23.3, §29
- **Context:** A green build that hides skipped checks is worse than a red one.
- **Decision:** `tools/verify.py` emits `artifacts/reports/latest/verify_summary.json` and
  `.txt` with check id, REQ ids, block, status, reason, artifact and duration, and exits
  with the documented codes (0/1/2/3/4/5). Required checks that were not executed are
  `BLOCKED`/`SKIPPED` with a reason, never `PASS`.
- **Alternatives:** Print "all good" — rejected.
- **Consequences:** Later phases add checks to the same runner rather than new scripts.

## D-0016 — Phase gate 0 is closed with an explicit open-items list

- **Status:** Accepted
- **Date:** 2026-11-20
- **Owner:** A0 orchestrator
- **Refs:** §24 Phase 0, §29, REQ-TEST-004
- **Context:** Gate 0 asks for "known interfaces" and "critical risk removed or documented
  safe decision". Reasonable people could read "known interfaces" as "contract confirmed".
- **Decision:** Gate 0 is reported as `PASS_WITH_OPEN_ITEMS`: every architectural blocker
  has a documented safe decision (adapter-bound isolation), while the organizer-specific
  facts remain `OPEN` in `docs/QUESTIONS.md`. `docs/STATUS.md` shows both, and no item is
  marked `DONE` that is only mitigated.
- **Alternatives:** Declare gate 0 fully green — rejected as a false claim.
- **Consequences:** Phase 1 may start; Phase 5's official-compatibility statement may not.

## D-0017 — Two-person review of the contract summary is recorded, not implied

- **Status:** Accepted
- **Date:** 2026-11-20
- **Owner:** A0 orchestrator (human owner D for the second signature)
- **Refs:** §24 Phase 0 tests, REQ-ORG-016
- **Context:** Phase 0 requires the contract summary to be reviewed by two people. An AI
  agent cannot sign for a human, and a missing signature must not be hidden.
- **Decision:** `docs/official/CONTRACT_SIGNOFF.md` holds two named signature slots with
  scope, date and evidence. Reviewer 1 (AI orchestrator) signs the *internal* summary
  against the archived master specification. Reviewer 2 (human owner) remains `PENDING`
  until a person signs; the verification runner reports this as
  `HUMAN_ACTION_REQUIRED`, which is not a failure and not a pass.
- **Alternatives:** Sign both slots ourselves — rejected as fabrication.
- **Consequences:** One open item stays visible in every report until a human signs.

## D-0018 — The master specification is archived as a derived, not official, source

- **Status:** Accepted
- **Date:** 2026-11-20
- **Owner:** A0 orchestrator
- **Refs:** §0 preamble, REQ-ADAPTER-001, D-0001
- **Context:** Reproducibility needs a byte-stable copy of the text every decision cites.
- **Decision:** `docs/official/master_tz/TwinLedger_v3_Master_TZ_AI_Agents.txt` is stored
  unmodified with SHA-256
  `a46cdb63bb4b41aabb95a842406f5a4fff91e218ead1e4f97b22b60d1c748e36`, 4062 lines, and is
  labelled `DERIVED_INTERNAL`. A test recomputes the hash. If the organizers publish a
  different document, it is archived alongside and the hash list grows.
- **Alternatives:** Link instead of archiving — rejected: links rot and the judge is offline.
- **Consequences:** The archive is immutable; edits require a new file plus a decision.

## D-0019 — A stdlib JSON-Schema subset validator owns contract validation

- **Status:** Accepted
- **Date:** 2026-11-20
- **Owner:** A0 orchestrator
- **Refs:** REQ-CONTRACT-002, REQ-OPS-001, D-0003
- **Context:** The contracts must be executable agreements, but the mandatory path may not
  depend on `jsonschema`.
- **Decision:** `tools/jsonschema_lite.py` implements the keyword subset the contracts use
  (`$ref`, `type`, `const`, `enum`, `required`, `properties`, `patternProperties`,
  `additionalProperties`, `propertyNames`, `items`, `minItems`, `maxItems`, `uniqueItems`,
  `minLength`, `maxLength`, `pattern`, `minimum`, `maximum`, `allOf`, `anyOf`, `oneOf`,
  `not`, `if/then/else`) and raises `SchemaError` on any unsupported keyword, so the subset
  cannot silently widen. Optional `jsonschema` may be used in development as a cross-check.
- **Alternatives:** Vendor `jsonschema` — rejected (wheel/licence review, R-15).
- **Consequences:** Schemas must stay inside the subset; a test enforces this.

## D-0020 — Root-level package layout (no `src/`), matching master spec §6

- **Status:** Accepted
- **Date:** 2026-11-20
- **Owner:** A0 orchestrator
- **Refs:** §6 «СТРУКТУРА РЕПОЗИТОРИЯ»
- **Context:** The specification draws the repository with `contracts/`, `gen/`, `env/`,
  `scoring/` … at the root, and the judge kit expects those paths.
- **Decision:** Use the root-level layout exactly; tooling modules live in `tools/`,
  tests in `tests/`. Import boundaries make root-level packages safe (D-0006).
- **Alternatives:** `src/twinledger/` — rejected: it would diverge from every path in the
  specification and in the phase reports.
- **Consequences:** `python -m tools.…` and `python -m unittest` run from the repo root.

---

## Assumption status register (mirror of `docs/ASSUMPTIONS.json`)

Phase 0 requires an explicit `CONFIRMED / CHANGED / OPEN` status for every `A-*`. This
table is the human view; the JSON is the machine view and the two must agree
(`tests/phase0/test_assumption_registry.py`).

| ID | Assumption (short) | Master-TZ status | Our status | Question | Isolated in |
|----|--------------------|-----------------|------------|----------|-------------|
| A-001 | Tool names `list_records/get_record/get_document/calc/submit` | preliminary | UNRESOLVED | Q-001 | `adapter/`, `configs/adapter/compatibility.json` |
| A-002 | Four anomaly types | preliminary | UNRESOLVED | Q-004 | `spec/anomaly_catalog.json`, `contracts/common.defs.json` |
| A-003 | Finding schema fields | preliminary | UNRESOLVED | Q-003 | `contracts/finding.schema.json` |
| A-004 | 100 steps, page size ≤ 50 | preliminary | UNRESOLVED | Q-002 | `configs/environment/limits.json` |
| A-005 | Reward `F1 - 0.05·steps/100` | provisional | UNRESOLVED | Q-005 | `configs/scoring/reward.json` |
| A-006 | `submit` not an inspection step | preliminary | UNRESOLVED | Q-005 | `configs/environment/limits.json` |
| A-007 | Truncation scored normally | preliminary | UNRESOLVED | Q-013 | `configs/scoring/reward.json` |
| A-008 | Closed mode hides reward | preliminary | UNRESOLVED | Q-013 | `configs/environment/mode.json` |
| A-009 | Opaque snapshot-bound cursor | preliminary | UNRESOLVED | Q-002 | `configs/environment/cursor.json` |
| A-010 | Bounded post-terminal errors | preliminary | UNRESOLVED | Q-002 | `contracts/tool_response.schema.json`, `configs/environment/mode.json` |
| A-011 | 60 s watchdog, steps are the limit | preliminary | UNRESOLVED | Q-009 | `configs/environment/limits.json` |
| A-012 | train/dev public, hidden held out | preliminary | UNRESOLVED | Q-008 | `configs/generator/default.json`, `.gitignore` |
| A-013 | Python 3.11, offline, 2 CPU / 4 GB / 1 GB | preliminary | UNRESOLVED | Q-009 | `pyproject.toml`, `configs/environment/resources.json` |
| A-014 | Tolerance from rounding count | preliminary | UNRESOLVED | Q-005 | `configs/scoring/tolerance.json` |
| A-015 | Seed never in observation/info | preliminary | UNRESOLVED | Q-010 | `configs/generator/default.json`, `configs/environment/mode.json` |
| A-016 | 20 checks × 4 blocks + 5 criteria | preliminary | UNRESOLVED | Q-012 | `configs/rubric/provisional.json`, `judge/rubric_map.json` |

No assumption is `CONFIRMED`. A `CONFIRMED` row requires an archived official file with a
hash and a cited section, which is exactly what Phase 0 could not obtain (D-0001).
