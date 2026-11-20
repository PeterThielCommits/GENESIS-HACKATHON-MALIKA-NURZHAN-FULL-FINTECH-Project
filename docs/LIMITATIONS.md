# LIMITATIONS — what this project does not guarantee

Written to be uncomfortable to read. If a claim is not on this page and not backed by a
test/artifact, it is not claimed.

## 1. Official contract and rubric are unknown

* No organizer technical specification, rubric, starter code or sample I/O exists in this
  repository (`docs/official/MANIFEST.json`, `docs/official/SOURCE_SEARCH_LOG.md`).
* All external names, limits and formulas are `PROVISIONAL` and isolated in `adapter/` and
  `configs/`. The adapter profile is `UNBOUND`: an official run is **not** possible today.
* The 25/25/25/15/10 rubric split and the ~20 checks per block are **unconfirmed**. No
  report in this repository claims the official score, and an internal pass rate is never
  presented as one.
* The reward formula `max(0, F1 - 0.05·steps/100)` is our provisional reading; the official
  formula may differ in tolerance, matching or step accounting.

## 2. Sandbox and isolation

* Process separation is **not** a sandbox. In the current environment there is no separate
  uid, no namespace isolation, no seccomp/cgroup profile and no enforced network namespace.
* What is real: separate working directories, stdin/stdout-only JSONL, allowlisted
  environment variables, fixed argv without a shell, sealed data absent from policy/env
  paths, and Git rules that keep sealed data out of the repository.
* The security profile is recorded per platform in `docs/THREAT_MODEL.md` §3; "not enabled"
  rows are never described as enabled.

## 3. Determinism

* Determinism is claimed **within one Python patch version** (3.11.x) on the same platform.
  Cross-platform byte identity is not claimed: `zoneinfo` data and iteration order of
  `os.scandir` can differ. Golden digests are therefore version-tagged.
* Wall-clock time is excluded from all deterministic hashes. A watchdog timeout is a run
  error, not a truncation.
* Any nondeterministic field must be documented; none is currently known, because no runtime
  exists yet.

## 4. Accounting realism

* Only four anomaly types and the accounting policies listed in `spec/anomaly_catalog.json`
  and `contracts/policy.schema.json` are modelled. Real accounting has far more nuance
  (revenue recognition standards, tax, consolidation, multi-entity eliminations).
* The synthetic universe is fictional by construction: jurisdiction codes `XA`–`XZ` are
  internal placeholders, **not** ISO-3166 codes, and no real company, bank or person appears.
* Distractor pairs are designed to differ by one accessible fact; they are not an exhaustive
  enumeration of legitimate business cases.

## 5. Evidence and verifier independence

* Independence is organisational and structural, not provable: the verifier is written from
  the specification without importing the generator, with its own test vectors. A single
  author still means correlated mistakes are possible (R-03).
* A shared low-level money/FX helper would be a common-mode risk. It is either absent or
  explicitly listed in `docs/INDEPENDENCE.md` with hand-authored reference vectors.
* Minimal evidence sets are minimal *with respect to the verifier's own rules and the
  declared context files*, not in an absolute logical sense.

## 6. Statistics and experiments

* Any learnability or arena comparison is a statement about a fixed experiment (seeds,
  tuning budget, split), not about "the model improving".
* Bootstrap confidence intervals are computed with a deterministic RNG; they quantify
  sampling noise only.
* Shortcut detection uses thresholds (`p`-values, classifier accuracy). With finite samples
  these are evidence, not proof of absence.

## 7. Engineering and reporting

* `make verify` currently implements the Phase 0 subset of checks. Planned checks appear as
  `BLOCKED` with a reason; they are never silently omitted and never counted as passing.
* Optional dependency absence produces `SKIPPED`, not `PASS`. `make setup` shows which
  extras exist.
* Docker/offline packaging, the full rubricator, HTML report and replay are **not
  implemented yet** (Phases 8–16); the corresponding Make targets exit `5` and say so.
* Performance targets (p99 step < 5 ms, L4 < 50 MB, verify < 10 min) are targets, not
  measurements. They will be reported with host, OS and Python version once measured.

## 8. Legal / licensing

* The repository currently has no chosen licence: licence review is an open item
  (`docs/STATUS.md`). Do not redistribute before that is resolved.
* No third-party code or data is vendored. Schemas are written for this project.
