# TwinLedger — Decision Log (append-only)

Format: `D-<phase>-<nn>` + date + status. Never rewrite history; add a
new entry to supersede.

## D-00-01 (2026-11-20) — Official organiser contract status: UNKNOWN

The attached Master TZ v3.0.0 is preserved verbatim at
`docs/reference/TwinLedger_v3_Master_TZ_AI_Agents.txt` (SHA-256
`a46cdb63bb4b41aabb95a842406f5a4fff91e218ead1e4f97b22b60d1c748e36`).
No separate organizer-issued TZ, rubric, sample I/O or starter code was
present in the repository at Phase 0/1 start (repo contained only
`README.md` + initial commit `c961a00`). All Master TZ assumptions
A-001…A-016 about the competition are therefore **UNRESOLVED** and
isolated in `adapter/` + `configs/`. Owner: A0. Closure condition:
organizer contract published → copy to `docs/official/`, record
hash/date/source, update this log + `docs/QUESTIONS.md`.

## D-01-01 (2026-11-20) — Contract freeze v1.0.0 for MVP (Phase 1)

Schemas in `contracts/` frozen at `1.0.0` (`contracts/version.json`).
Further changes require an approved CR (`docs/CR/`). Owner: A0.
Rationale: TZ Phase 1 exit gate.

## D-01-02 (2026-11-20) — Flat package layout (no `twinledger/` prefix)

Top-level packages `gen/`, `verifier/`, `env/`, … per Master TZ 6, so
import-boundary rules map 1:1 to directories. Owner: A0.

## D-01-03 (2026-11-20) — Stdlib-only core; optional extras isolated

Core uses Python 3.11 stdlib only (`requirements-core.txt` empty).
`pytest`/`hypothesis`/`jsonschema` are dev-only; `gymnasium`/`numpy`/
`scikit-learn`/`matplotlib` are extras. Owner: A0. (TZ 22.1–22.2)

## D-01-04 (2026-11-20) — Sealed data git policy (provisional)

`episodes/*/sealed/` and `episodes/hidden/` are git-ignored by default
(`.gitignore`). Public episode fixtures may be committed. Revisit in
Phase 0 once organiser submission rules are known. Owner: A0.

## D-01-05 (2026-11-20) — Provisional reward/budget in configs, not code

`configs/scoring/default.json` (ETA=0.05, max_steps=100) and
`configs/environment/default.json` (CLOSED_EVAL, 100 steps, page 50)
hold provisional values (A-004/A-005). Code must read them; no hidden
defaults. Owner: A0.

## D-01-06 (2026-11-20) — Rubric map is provisional

`judge/rubric_map.json` has `provisional: true`. Internal test counts
must never be presented as official organiser checks (TZ 23.4/23.6).
Owner: A0/D.

## Assumptions register (A-001…A-016)

All UNRESOLVED pending D-00-01 closure. Isolated in `adapter/` +
`configs/`; not baked into core logic. See `docs/QUESTIONS.md` Q-001…Q-014.

## D-02-01 — local primitive conventions (provisional)
FX rate input is positive fixed-point text in target/source direction. Conversion
accepts signed int64 inputs/outputs and records one final rounding operation.
Monthly and quarterly periods use month-aligned fiscal calendars; quarters are
labelled by fiscal start year. Reject gaps; reject folds unless explicitly resolved.
A date without time is a company business date, not a machine-local instant.
Aging labels and open/partial/paid statuses are MVP group semantics, not organizer rules.

## D-06-00 (2026-11-21) — Phase 6 base line: frozen-contract stack of PR #1/#2

Phase 6 (matcher + base reward) is implemented on top of the Phase 1 +
Phase 2 stack (branch `arena/2a69516d-...`, commits ae5650e..ef15218,
fast-forwarded into the session branch), which carries the first
contract freeze v1.0.0 (D-01-01). Parallel session branches (`arena/
6e3d45bc-...` Phase 0/1 alternative, `arena/280879b6-...` Phase 3,
`arena/d94e8b76-...` Phase 4, `arena/eb1e0f8a-...` Phase 5) claim
incompatible v1.0.0 schema sets (see CR-05-01 follow-up and issue #3).
Per the priority rules, the earliest frozen contract (D-01-01) wins
until A0 issues an approved CR; Phase 6 consumes domain models only and
does not touch any disputed wire format. Owner: A0. Closure: issue #3
disposition + merged contract line. Draft CR: `docs/CR/CR-06-01.md`.

## D-06-01 (2026-11-21) — Finding/truth schemas adopted as scoring boundary

Task 6.1: `contracts/finding.schema.json` v1.0.0 (schema_version,
type, typed affected_ids, claimed_amount int minor units, currency,
evidence_ids) and `contracts/truth.schema.json` v1.0.0 (amount_minor,
tolerance_minor, evidence_sets) are confirmed as the scoring input
boundary. No schema file was modified. Status: PROVISIONAL pending the
official organiser contract (Q-003). Scoring validates every input at
its module boundary (REQ-CONTRACT-002) and re-validates canonicalised
round-trips.

## D-06-02 (2026-11-21) — Empty-denominator conventions for precision/recall/F1

TZ 15.4 requires explicitly established special rules. Conventions
(kept in `scoring/reward.py`, all executable in tests): clean book +
empty submission => F1 = 1; precision = 1 for an empty submission;
recall = 1 for an empty truth; otherwise F1 = 2TP/(2TP+FP+FN). These
match every sanity example A-J of TZ 15.6. PROVISIONAL until the
official rubric is published (Q-005).

## D-06-03 (2026-11-21) — Exact rational reward, display-only decimals

Reward, F1, precision, recall and penalty are computed as exact
`fractions.Fraction` values; eta is parsed from the config literal text
(Decimal-from-string, never binary float). Decimal strings are
rendered only for display (ROUND_HALF_EVEN, 7 places); raw values are
stored exactly (TZ 15.5). `steps_used` must satisfy
0 <= steps_used <= max_steps (bounded error otherwise).

## D-06-04 (2026-11-21) — Formalised tie-break of the matcher

Among all matchings with maximum cardinality and minimum total absolute
amount error, `scoring/matcher.py` selects the lexicographically
smallest sorted pair tuple ``(finding_index, truth_index)``. Implemented
as greedy pair locking with exact min-cost-flow feasibility checks on
top of a min-cost max-flow solve; the original input index is used only
as this final tie-break (REQ-SCORE-002). Bounded error above 4096
candidate edges instead of a silent determinism downgrade.

## D-06-05 (2026-11-21) — Match predicate scope and experimental column

The match predicate is exactly the six conditions of TZ 15.2
(PROVISIONAL pending Q-005); explanation/confidence never influence
matching or reward. `experimental_grounded_score` (TZ 15.8) is computed
only from caller-supplied requested evidence IDs, is labelled
EXPERIMENTAL and lives in a separate diagnostics column that never
feeds the reward. Explanation-consistency (Phase 10) and verifier
quality (Phase 8) diagnostics are explicit NOT_AVAILABLE markers.

## D-07-01 — Provisional normalized operator boundary

Implement FX and cutoff against normalized journal inputs without introducing
an episode schema or affected-ID translation. For FX select the latest allowed
quote date only under the declared fallback policy; reject distinct permitted
booked amounts rather than guessing a source-priority rule. Keep official
semantics open under Q-004/Q-006; integrate only after A0 resolves CR-06-01.

## D-08-01 (2026-11-21) — Zero common-mode verifier implementation

`verifier/` imports only Python 3.11 stdlib and `contracts/` (schemas,
canonical JSON, ISO-4217 currency exponents). It deliberately does **not**
import `core/`, `invariants/`, `gen/`, or `scoring/`. FX conversion is
independently implemented in `verifier/money_time.py` using exact
`fractions.Fraction` intermediate arithmetic with a single final rounding step
(`half_even`/`half_up`) and inverse-pair support; company-local date and fiscal
period mapping is independently implemented via `zoneinfo.ZoneInfo`. This
eliminates common-mode helper bugs between generator/invariants and the
independent verifier (TZ §12.4, §13.1).

## D-08-02 (2026-11-21) — Stage-1/Stage-2 crosscheck separation & digest lock

To satisfy REQ-ORG-003, REQ-ARC-001, and REQ-VER-020..022 without letting
`verifier/` see sealed truth or letting `scoring/` import `verifier/`, Stage-1
discovery (`verifier.discover`) outputs a schema-valid `verifier_report` and
pre-committed SHA-256 `report_digest` from `public/` alone, while Stage-2
crosscheck (`scoring/crosscheck.py`) consumes the serialized `verifier_report`
dict, verifies `expected_report_digest`, delegates TP/FP/FN to
`scoring.matcher.optimal_matching` with strict per-set (non-union) evidence
sufficiency checks, and sets `release_blocked=True` on any mismatch,
ambiguity, insufficiency, or ablation failure. `scoring/diagnostics.py` retains
its explicit `verifier_quality: NOT_AVAILABLE` marker for agent scoring until
episode pipeline integration.

## D-08-03 (2026-11-21) — Frozen independent verifier spec & provisional semantics

`spec/verifier_algorithm.md` (v1.0.0) freezes the independent verifier
algorithm, ProofGraph DAG contract, minimal-evidence ablation protocol, and
16-distractor exclusion rules without reading `gen/` (Task 8.1). Provisional
public-episode `affected_ids` and amount conventions follow
`spec/anomaly_catalog.yaml` and `docs/DATA_DICTIONARY.md` (pending external
organiser clarifications `Q-004/Q-006`).

## D-08-04 (2026-11-21) — Resolution of CR-06-01 & Phases 3–5/7–8 full integration

Resolved `docs/CR/CR-06-01.md` on the frozen Phase 1 v1.0.0 contract line
(`D-01-01`, zero frozen schema edits):
- Integrated deterministic Clean Twin generator (`gen/core/clean_twin.py`,
  `gen/core/rng.py`, `gen/distractors/catalog.py`) and all 4 anomaly operators
  + structural diff + salted truth commitment + manifest serializer
  (`gen/errors/operators.py`, `gen/truth.py`, `gen/serialize.py`,
  `gen/pipeline.py`), reusing Phase 7's `gen/errors/fx_cutoff.py`.
- Integrated frozen-contract-compliant public-only `env/` (`list_records`,
  `get_record`, `get_document`, safe AST `calc`, `submit`, opaque HMAC cursors,
  `CLOSED_EVAL`, JSONL stdio server) and provisional `adapter/organizer.py`.
- Added `episodes/*/*/sealed/` to `.gitignore` so sealed truth/provenance
  directories under `episodes/dev/<ep_id>/` and `episodes/train/<ep_id>/` are
  never committed to Git while remaining deterministically regenerable via
  `tools/make_dataset.py --split all`.
- Generated 10 episodes (6 `dev` + 4 `train`) and verified 100% (10/10) through
  manifest SHA-256 checks, Stage-1 public-only `verifier.discover`, Stage-2
  `scoring.crosscheck` (`release_blocked=False`), and `TwinLedgerEnv` public
  tool reachability — promoting EXIT GATE 8 to **DONE** (internal provisional
  contract line; external organiser items `Q-003..Q-006` and `make docker-check`
  remain explicitly documented).

## D-09-01 (2026-11-21) — Three-subprocess `CLOSED_EVAL` barrier & Zone-2 import discipline

`harness/` imports ONLY `contracts` and Python 3.11 stdlib (enforced by
`tools/check_import_boundaries.py`). During `CLOSED_EVAL`, `harness/runner.py`
spawns `env` (`python3 -m env.jsonl_server --require-closed-eval`) over a staged
read-only copy of the 12 allowlisted `public/` files (`0o444`/`0o555`, zero
`sealed/`) and `policy` in an empty read-only temporary directory (`0o555`).
Only after BOTH `policy` and `env` subprocesses exit (`env_alive=False`,
`policy_alive=False`, monotonic `env_exited_ns <= scorer_started_ns`) may
`harness/scorer_process.py` spawn `python3 -m scoring.scorer_cli`. Preserves
`harness/isolated_runner.py` intact for Official 2026-11-20 evaluation.

## D-09-02 (2026-11-21) — Normative trajectory hash chain without wall-clock fields

Every episode trajectory is anchored at
`h_0 = SHA256("twinledger:h0:v1|" + truth_commitment + "|" + episode_id)` and
chained via
`h_{i+1} = SHA256(b"twinledger:event:v1|" + h_i + b"|" + canonical_bytes(event_i))`
over frozen `contracts/trajectory_event.schema.json` v1.0.0 (`reset`,
`tool_call`, `submit`, `terminate`, `error`). Diagnostic nanosecond timings
(`elapsed_ns`) live only in the outer JSONL wrapper and are excluded from
`TrajectoryEvent` so `trajectory_head` is 100% deterministic across fresh
processes (`REQ-SEAL-021`, `REQ-SEAL-030`).

## D-09-03 (2026-11-21) — Size-bound RFC-6962 domain-separated Merkle tree

`seal/merkle.py` uses `0x00` leaf prefix, `0x01` internal node prefix, odd-leaf
promotion without self-duplication, and a size-bound root envelope
`SHA256(0x02 || uint64_be(leaf_count) || top_node)` (with
`EMPTY_TREE_ROOT = SHA256(b"twinledger:merkle:empty:v1")`). This prevents both
leaf-duplication second-preimage collisions (`[A, B, C]` vs `[A, B, C, C]`) and
subtree-truncation size ambiguity (`leaf_index=0` across `leaf_count=3` vs `4`),
satisfying `REQ-SEAL-022..023`.

## D-09-04 (2026-11-21) — Explicit non-MAC `SecurityProfile` honesty contract

`harness/sandbox.py` sets `SecurityProfile.is_full_os_sandbox = False`
(`host-posix-subprocess-v1` / `container-posix-subprocess-v1`), enumerating both
enforced controls (separate OS subprocesses, post-termination scorer barrier,
staged read-only `public/`, empty scratch `cwd`, `close_fds=True`, sanitized env
allowlist, `shell=False`, POSIX soft `rlimit`s) and unavailable kernel controls
(`container_mount_namespace`, `container_network_disabled_flag`,
`seccomp_bpf_syscall_filter`) per Master TZ Principle P-012 and Risk R-09.

## D-09-05 (2026-11-21) — Linux kernel namespace + seccomp-BPF sandbox & CSPRNG production rekey (supersedes D-09-04 on Linux)

Remediates `R-09` and `L4`:
- On Linux kernels where `probe_kernel_sandbox_capabilities()` succeeds, `harness/sandbox.py` + `harness/ns_launcher.py` wrap `policy` and `env` inside `unshare --user --map-root-user --net --mount` with `MS_REC|MS_PRIVATE` `tmpfs` path masking over `episodes/` and `episode_dir`, read-only `tmpfs` `cwd` (`EROFS`), `PR_SET_NO_NEW_PRIVS`, and `x86_64`/`aarch64` `seccomp-BPF` blocking `socket`, `mount`, `umount2`, `pivot_root`, `ptrace`, `process_vm_readv`, and `process_vm_writev` (`profile_id = "linux-kernel-ns-seccomp-v1"`, `is_full_os_sandbox = True`), with automatic honest fallback to `posix-subprocess-isolated-v1` on non-Linux hosts.
- `seal/rekey.py` (`python3 -m seal.cli rekey-production`) re-keys episodes with 256-bit `secrets.token_hex(32)` `PRODUCTION_SECRET` salts, and `scoring/scorer_cli.py` performs Stage-2 `scoring/crosscheck.py` `semantic_truth_verification` whenever `verifier_report.json` is supplied.

## D-10-01 (2026-11-21) — Isolated multilingual (`ru`/`kk`/`en`) & prompt-injection RNG streams + diagnostic explanation linter

`gen/core/text.py` renders `en`, `ru`, `kk`, and `mixed` narrative layers and benign prompt-injection strings solely via derived RNG streams (`"text_layer"` and `"injection_layer"`), guaranteeing byte-identical accounting numbers, dates, IDs, `TruthFinding` digests, and Stage-1 `verifier_report` findings across language variants (`REQ-NLP-001..005`). `scoring/explanation_linter.py` populates `diagnostics.explanation_consistency` strictly as a diagnostic column without influencing official `F1` or `reward` (preserving `D-06-05`).

## D-12-01 (2026-11-21) — Privilege-separated oracle, 22-attack Arena, seed-grouped AutoHacker & within-table shortcut audit

- `oracle_test_only` is forbidden in public runs (`ValueError` unless `allow_privileged_oracle=True`, `REQ-ARENA-005`).
- `arena/attacks/catalog.py` executes all 22 TZ §18.3 red-team attacks (`AT-01..AT-22`), and `arena/autohacker.py` optimizes `AuditorParams` strictly on seed-grouped `TRAIN`/`DEV` splits before single-shot `HELDOUT` evaluation with 95% bootstrap CIs (`REQ-AUTO-001..004`).
- `judge/shortcut_audit.py` orthogonalizes `(anomaly_class, id_style, timezone)` and trains per-table L2 Logistic Regression classifiers on public metadata features (`macro_ROC_AUC <= 0.55`, `REQ-SHORTCUT-001..003`).

## D-14-01 (2026-11-21) — Complete 12-Gate Judge Kit & Offline Self-Contained HTML Report

`judge/verify.py` executes all 12 provisional Master TZ §23 rubricator gates (`RC-001..RC-012`) while preserving `official_score_claimed: false` (`D-01-06`). `judge/report.py` synthesizes a 100% offline self-contained `artifacts/reports/latest/report.html` (zero external `http://` or `https://` links, zero canary/salt leaks) indexing all 21 JSON/CSV/MD/HTML evidence artifacts.

## D-14-02 (2026-11-21) — Frozen rubric map validated tolerantly; TZ §23.5 envelope enforced as a contract gate

Phase 14 re-audit. `judge/rubric_map.json` is frozen by `configs/release_freeze.json`, but its per-check objects omit `schema_version` (the version appears once, at top level as `rubric_version`), while `contracts/rubric_check.schema.json` lists `schema_version` among the required fields for a standalone check. Editing either the frozen map or the frozen contract to reconcile this would require a CR, and the discrepancy is representation-only.

Decision: `judge/schemas.py::validate_rubric_map` requires the seven semantic fields (`check_id`, `rubric_item`, `req_id`, `test_id`, `command`, `evidence_artifact`, `provisional`) and validates `schema_version` **only when present**. Locked by `tests/judge/test_judge_kit.py::TestRubricMapConsistency::test_rubric_map_validates` running against the real frozen file.

In the same pass, TZ §23.5 ("every report must contain code version, config hash, run timestamp, target platform, Python version and launch command") is now machine-enforced: `validate_report_envelope` / `validate_report_dir_envelopes` audit every `*.json` in `artifacts/reports/latest/`, and `judge/verify.py --full` treats a violation as a configuration/contract error (exit 2). `harness/replay.py` and `tests/scoring/test_reward_properties.py` were extended with the envelope (additive metadata only — no change to replay, reward, or scoring semantics).

## D-14-03 (2026-11-21) — EXIT GATE 14 is defined by clean-checkout reproduction, and report synthesis is ordered around it

The earlier Phase 14 claim of `PASS` was measured in a working tree that already contained 21 artifacts. TZ §24 defines EXIT GATE 14 as *clean checkout + documented command → complete verification outputs*, so that claim was untested for the only condition that matters to a judge.

Decision: the gate is only accepted when the documented command runs in a tree built from `git ls-files` (no `__pycache__`, `artifacts/reports/latest/` holding only `.gitkeep`) and exits 0 with complete outputs. This standard immediately exposed two real defects, both fixed: an f-string `x or {{}}` set-literal `TypeError` that only fires when an optional report is absent, and a synthesis-order bug where `judge/report.py` consumed `verify_summary.json` before `judge/verify.py` wrote it (exit 5 on a clean clone). `judge/verify.py` now emits the summary in two phases — before the report step (its input) and after (final status/artifacts) — and the advisory pre-report completeness check can no longer decide the exit code; only the post-report completeness pass sets exit 5. Locked by `test_build_report_survives_empty_artifact_dir`.

Consequence for future phases: any "VERIFIED" claim about the judge path must name the clean-tree reproduction, not a dirty run.

## D-15-01 (2026-11-21) — Documentation claims are generated and machine-checked, never hand-maintained

Phase 15 re-audit. TZ §24 Task 15.6 ("validate no unsupported claims or fake metrics") cannot be met by careful editing: the README had drifted to a 317-test claim against 410 measured, and `docs/THREAT_MODEL.md` published a 9-item "encoding transform" list containing 8 names, four of which were not real identifiers.

Decision: every quantitative claim published to the jury is derived from an artifact.
- `README.md` carries a delimited block (`<!-- BEGIN GENERATED:measured-facts -->`) rendered by `tools/verify_doc_claims.py` from `artifacts/reports/latest/*.json`, `report_index.json` and `artifacts/trajectories/trajectories.jsonl`. Check mode compares it byte-for-byte; only `--write` may change it.
- Counts appearing in prose are asserted separately; a stale sentence fails the gate.
- A stale-literal denylist rejects values previously proven wrong (`317 tests`, `Replay Suite: 0/0`, `15 invariants`, …) anywhere in 10 jury-facing docs.
- Cited decision IDs must exist in this file (referential integrity) — added after this phase accidentally cited a non-existent `D-03-01`.
- `tests/judge/test_doc_claims.py` (18 tests) proves the checker's mechanisms inside RC-001, but the **authoritative** claim check runs in `judge/verify.py::_run_doc_claims()` *after* artifact synthesis. Inside RC-001 no artifact exists yet, so a check placed there is a chicken-and-egg failure on clean checkouts (it crashed with `FileNotFoundError` until this was found by a clean-tree run). The tests therefore skip explicitly in that bootstrap position, and the skip reason is classified as positional/optional, never as a critical skip that can be hidden.
- No asserted value may be produced by the run performing the check. Asserting the gate pass-ratio ("12/12 PASS") in the byte-compared block was self-poisoning: one run failing due to doc drift persisted a failing summary, which changed the next run's expected wording — an unrecoverable deadlock. Only outcome-independent facts are asserted; the verdict lives in the exit code and `verify_summary.json`.

Two self-inflicted design bugs were found and fixed under this rule, and are the reason for the stable-only policy: (a) sampled timings (p99 latency, peak RSS, max episode duration) must never enter a byte-compared block, because they change every run and made the gate fail on the next `verify`; only budgets, verdicts, counts and contract enums are asserted. (b) The doc-claims report is written to `artifacts/reports/doc_claims/`, **not** `artifacts/reports/latest/`, because the latter is the frozen 21-artifact Judge Kit evidence set and a conditional extra file would make artifact counts depend on target execution order.

New targets: `make docs-verify`, `make demo`, `make demo-backup` (TZ 15.4 technical backup demo).

## D-15-02 (2026-11-21) — Two tool vocabularies are intentional and documented, not unified

The core JSONL protocol (`env/jsonl_server.py`, `contracts/tool_request.schema.json`) exposes the calculator as **`calc`**; the official adapter (`judge_adapter.py`, `adapter/official_env.py`) exposes the same implementation as **`calculator`**, matching the official task statement. Each front door rejects the other's name (`UNKNOWN_TOOL` / `UNKNOWN_ACTION`).

Decision: keep both and document the asymmetry rather than renaming either surface. Renaming the protocol would break the frozen `tool_request` schema; renaming the adapter would break the official harness contract. Both spellings are verified empirically, printed in the README adapter section and `docs/POLICY_PROTOCOL.md` §3, and pinned by the `C-PROTOCOL-TOOLS` claim check which reads the enum from the frozen schema, so the documentation cannot drift from the contract. No frozen file was modified.

## D-15-03 (2026-11-22) — Evidence count excludes placeholder files (20, not 21)

`artifacts/reports/latest/.gitkeep` exists only so Git can track an otherwise
empty directory. `judge/report.py` counted every regular file in the evidence
directory, so the published artifact count depended on **where the code ran**:
21 in a checkout (which has `.gitkeep`) versus 20 inside the offline image
(where it does not exist). The documentation gate compares the committed count
against the measured one, so this environment difference surfaced as a real
`docker-offline` CI failure:

```
[DRIFT] G-BLOCK (line 13: committed '| Evidence artifacts indexed | **21** |'
                       != measured '| Evidence artifacts indexed | **20** |')
```

Decision: evidence is defined as *non-placeholder* files — `_is_artifact()`
excludes dotfiles — so the count is **20** everywhere and is a genuine
measurement rather than an accident of the filesystem. This matches the TZ
§23.5 contract: 16 required reports + `report.html` (optional) + `report_index.json`
+ `robustness_report.json` (added in Phase 9) = 20, `missing: []`.

The placeholder is kept (Git needs it); it is simply never counted. Locked by
`TestArtifactPlaceholders` (4 tests), which also asserts that
`report_index.json` and the directory contents agree exactly.

## D-16-01 (2026-11-22) — Release gates measure, they do not describe

Phase 16 added two gates whose authority comes from measurement, and whose value
comes from being demonstrably able to fail:

- `tools/replay_all_trajectories.py` (TZ 16.4) replays the **recorded actions** of
  all 80 published runs against freshly rebuilt episodes and compares every
  observation, reward and score. It deliberately does **not** re-run the baseline
  policies: the claim under test is that the generator, environment and scorer are
  deterministic, and mixing policy execution into it would make a policy change
  look like a determinism failure.
- `tools/release_audit.py` (TZ 16.5/16.6) measures secrets, forbidden paths,
  package size, runtime imports, the official entrypoint and the submission
  format. The entrypoint is verified **behaviourally** (each documented tool is
  dispatched in a fresh environment) rather than by introspecting attributes,
  because the adapter exposes no tool registry and an unknown action is answered
  inside the observation, where an attribute check cannot see it.

Three operating rules, each paid for with a real bug:

1. **A gate must be shown to fail.** Every detector has a negative test with a
   deliberately injected violation. The secrets audit even reported four
   credential shapes in its own fixtures; they were removed rather than the audit
   being exempted.
2. **Never read a gitignored artefact inside a test.** `artifacts/reports/release/`
   is generated, so tests drive the real CLI into a temporary directory instead.
   This is `D-15-01` restated after it was reintroduced one directory over.
3. **Gates must run where the artefact runs.** `.dockerignore` excludes `.git`, so
   the submission image has no Git metadata; a `git ls-files`-only audit errored
   there. `tracked_files()` falls back to a filesystem walk mirroring
   `.dockerignore`. Verified in a Git checkout, a clean clone and a `git archive`
   tarball.

`artifacts/reports/release/` is gitignored for the same reason as
`artifacts/reports/doc_claims/`: `artifacts/reports/latest/` is the frozen
Judge Kit evidence set (D-15-03), and extra files there make counts depend on
execution order.

## D-16-02 (2026-11-22) — Mandatory targets must be runnable in any order

An audit against the Universal Phase Execution Prompt and TZ §23.2 found that
three of the required `make` targets were never actually executed by previous
phases, only assumed to work, and that running them exposed three real defects:

1. **`make verify-core` FAILED after `make build-episodes`.** The filesystem
   fallback in `tools/release_audit.py` scanned *untracked* files, so sealed
   truth generated by a legitimate build target produced 20 false `FILELIST`
   violations. Sealed truth is `git`ignored *by design*: it is distributed
   deterministically rather than committed. The walk now honours ignore rules
   (`_is_ignored`), matching `git ls-files` plus a known generated-path set.
2. **The Docker build context shipped sealed truth.** `.dockerignore` listed
   `episodes/*/sealed/`, but Docker matches patterns per path element, so the
   real depth-2 layout `episodes/dev/ep_x/sealed/` was **not** excluded. A
   default `make docker-check` would have baked `truth.json` into the image — a
   `REQ-ARENA-005` release blocker. Both depths are now listed.
3. **`make official-eval` wrote a 21st file into the frozen evidence dir.** The
   documented "20 evidence artifacts" became 21 after a legitimate command.
   `official_eval_summary.json` now lives in `artifacts/reports/evaluation/`.

A fourth, subtler defect: the published gate count came from
`verify_summary.json`, which lists only the gates of the *most recent* run. After
`make verify-core` (6 gates) the README said "6 gates" and the next full run
reported `DRIFT`. The count now comes from the frozen `judge/rubric_map.json`
(12), which is the contract, not a measurement — the same class of error as
`D-15-01`.

Rule adopted: **every target in TZ §23.2 must be executed, in sequence, on a
dirty-but-legitimate tree, before a phase may claim its gates pass.** A target
that only works in a pristine checkout is broken, because reviewers do not work
in pristine checkouts.

## D-17-01 (2026-11-21) — Post-release cryptographic contract & config freeze manifest

`tools/freeze_release.py` locks SHA-256 digests over all 30 frozen contract schemas (`contracts/*.schema.json`, `contracts/version.json`), operational configs (`configs/*`), provisional rubricator (`judge/rubric_map.json`), official check spec (`spec/official_fintech_checks_2026-11-20.md`), and Master TZ v3.0.0 (`docs/reference/TwinLedger_v3_Master_TZ_AI_Agents.txt`) in `configs/release_freeze.json`.


## D-10-02 (2026-11-21) — Phase 10 quality audit: pinned text dictionaries, scorer-side evidence-hierarchy enforcement, lazy NLP facade, explanation report artifact

Follow-up to `D-10-01` after a full Phase 10 re-execution (Universal Phase Execution Prompt, `PHASE_NUMBER=10`, branch `arena/794acafe-genesis-hackathon-malika-nurzh`):

- **Module vs package deviation:** Master §24 lists the deliverable as `gen/core/text/`; the implementation keeps `gen/core/text.py` (single module). Functionally equivalent for every requirement; no import churn. Recorded as an accepted deviation rather than restructuring.
- **Pinned dictionary versions (TZ §17.2):** `gen/core/text.py` now exposes `TEXT_LAYER_VERSION = "text-layer@1.0.0"` and `TEMPLATE_DICTIONARY_VERSION = "ru-kk-en-dicts@1.0.0"`, recorded in generation provenance so text dictionaries are version-frozen.
- **Evidence hierarchy enforcement (Task 10.5, TZ §17.3):** `nlp/hierarchy.py` gains `assess_evidence_reachability` + `build_evidence_hierarchy_report`; `scoring/scorer_cli.py` emits `diagnostics.evidence_hierarchy` on every scored submission. Strictly diagnostic (TZ §15.9): matching/F1/official reward semantics unchanged (`D-06-05` preserved). Scorer imports ONLY `nlp.hierarchy` from the `nlp` package — never the optional fuzzy helpers.
- **Lazy `nlp` facade:** `nlp/__init__.py` uses PEP-562 lazy exports so that importing the strict rule module never loads `nlp.matching`/`nlp.normalize`. Subprocess tests prove `gen`, `env`, `verifier`, `scoring.{matcher,reward,diagnostics}`, `seal`, `harness` load zero `nlp` submodules (EXIT GATE 10: NLP layer optional for core).
- **Import-boundary hardening:** `tools/check_import_boundaries.py` forbids `nlp` entirely in `core/`, `invariants/`, `env/`, `gen/`, `seal/`, `harness/` (and `verifier/` as before), and restricts `scoring/` to `nlp.hierarchy` only — machine-enforcing "verifier does not rely on unsupported fuzzy matches".
- **Explanation consistency report (Task 10.6 deliverable):** `tools/explanation_report.py` produces `artifacts/reports/latest/explanation_consistency_report.json` (rules EC-01..EC-05 per TZ §17.6, deterministic, diagnostic-only).
- **REQ-ID correction:** `REQ-SCORE-020` cited in earlier Phase 10 artifacts is a phantom ID (Master TZ defines `REQ-SCORE-001..005` only); Phase 10 traceability now lists `REQ-NLP-001..005`, `REQ-PROD-020`, `REQ-ARC-001`, `REQ-VER-002`.
## D-10-03 (2026-11-21) — Review remediation: verbatim row-order loading + bounded episode-input reads

Remediates two code-review findings on `main` @ `7f47638`:

- **Row order (defect):** `env/loader.py::load_public_book` re-sorted table rows by `(primary_key, currency)`, contradicting the README "Canonical Tables" claim *«File row order is preserved verbatim on load»* (needed by the paired permutation checks `P01..P05`, `P11..P20`). Fixed: rows are kept in file order exactly as stored; `list_records` cursors page over file order. Empirically the removed sort was an identity operation on every generator-produced episode (`gen/serialize.py::_write_jsonl_canonical` already writes pk-sorted JSONL), so the change is behavior-neutral for all project-generated data and only corrects externally-authored/permutation-shuffled inputs. Jury path unaffected either way: official checks run through `adapter/official_env.py::load_official_public_book`, which already preserved order. Locked by `tests/env/test_loader_order_and_bounds.py::TestLoaderRowOrderPreserved` (incl. a `list_records` end-to-end pagination test).
- **Unbounded reads (robustness gap):** `adapter/official_env.py` (records, metadata, `public/documents/` — which also double-read files), `env/loader.py`, `scoring/official_scorer.py`, and `verifier/public_loader.py` read whole episode files into memory without size/count limits. Fixed with shared guards in `contracts/loader.py`: `read_text_bounded()` (`MAX_INPUT_FILE_BYTES = 16 MiB`, read cap enforced at `cap + 1` bytes) and `check_row_cap()` (`MAX_INPUT_ROWS = 100_000`), translated into each zone's bounded error type (`EnvError("LIMIT", ...)` / `PublicEpisodeError` / `ValueError`). Caps chosen against measured workloads (largest generated public file ~27 KiB; largest table 292 rows; README documents a 4 950-row scan ceiling) with >20x–500x headroom; documented as limitation `L7`. Locked by `tests/env/test_loader_order_and_bounds.py::TestBoundedEpisodeReads`.

No frozen schema, reward formula, or public tool contract changed; `make test-official` (55/55, incl. `P01..P20` paired invariance), `make replay`, `make test-property`, `make lint` all PASS.

## D-11-01 (2026-11-21) — Measured, fail-closed Phase 11 robustness evidence
Retain frozen v1 config and generator/policy/scorer behavior. Runner validates
exact supported coverage lists/version/invariance settings and integer seed;
unsupported custom suites fail rather than silently ignoring config. Expand to
24 neutral/injected pairs including clean and partial-allocation cases. Compare
all accounting fields except the three explicitly permitted text leaves, truth
bytes, verifier finding lists, honest action digests, findings and step counts.
The legacy follow-rate field is a measured behavioral-change proxy, not a
semantic intent detector. Report labels internal provisional score separately
from official scoring and explicitly disclaims OS-isolation/LLM conclusions.
Master traceability uses REQ-NLP-004/REQ-UNIQUE-001, not phantom REQ-INJ IDs.
Frozen release mismatch from earlier loader change is NOT silently re-frozen.

## D-12-02 (2026-11-21) — Maintainer-authorized release-freeze re-synchronization (Phase 12 closure)

`configs/release_freeze.json` was out of date since `D-10-03` (2026-11-21): `contracts/loader.py` grew from 1717 B (`610f07…`) to 4244 B (`4dbb8b…`) with `read_text_bounded`/`check_row_cap` guards, but the manifest was not updated per `D-11-01` policy ("NOT silently re-frozen").

On this branch (`arena/3f693c20`, base `2dc365a`), `env/loader.py` was restored to its D-10-03 bounded-read form (missing after squash). With full verification passing (`make verify` 12/12, `make lint` CLEAN, 360 tests, 55 official, 5/5 replay, 26/26 mutants, 7/7 metamorphic), maintainer explicitly authorizes `python3 tools/freeze_release.py --write` to re-synchronize the manifest:

- `contracts/loader.py`: 1717 B `610f07…` → 4244 B `4dbb8b…`
- `aggregate_sha256`: `caf9405e…` → `0747baf0…`
- No other frozen file changed; 30 files still tracked.

Clean-clone verification (`git clone --branch arena/3f693c20 … && make verify && make lint && python3 tools/freeze_release.py --verify`) and offline Docker (`make docker-check`) are then run. This is the final unblock for Phases 16–17 tagging.

## D-13-01 (2026-11-21) — Phase 13 finite test evidence
Expand the metamorphic sample from three to four scenarios and require changed public bytes, while checking verifier equivariance and policy reward equality. Capture pipeline clean twins for multiple operator plans; extend deterministic property loops and exercise optional Hypothesis separately. Use a reproducible repeat-sensitive tie-break mutant rather than a probabilistic kill. These tests are representative, not universal proofs; serialization difference alone does not prove a causal accounting change. No production behavior or release freeze is changed.

## D-18-01 (2026-11-21) — One reward implementation; official formula supersedes provisional A-005

`spec/official_fintech_checks_2026-11-20.md` (vendored verbatim from the
organisers; byte-identical to the copy circulated to the team) fixes the
reward as `return = clip([-1, 1], 2*F1 - 1 - 0.2*inspection_steps/100)` and
publishes 20 exact matcher/reward vectors plus 12 worked examples.

The repo held **two** implementations:

- `scoring/official_scorer.compute_official_metrics` — official formula, used
  by `judge_adapter.score_episode` and covered by `tests/official/`;
- `scoring/reward.compute_reward` — the provisional
  `R = max(0, F1 - eta*steps/max_steps)` with `eta = 0.05` (assumption A-005),
  consumed by `arena/autohacker.py`, `judge/mutation_suite.py`,
  `judge/robustness_audit.py` and the reward-property matrix.

The second one failed 10 of the 11 published reward vectors, so every
internal artifact derived from it published numbers the jury would never
reproduce (BUG-TL-0001).

Decision:

1. `compute_official_metrics` is the **single** implementation. No second
   reward formula may exist (TZ §23.2 "no duplicate competing
   implementations").
2. `scoring/reward.py` becomes a thin view: it keeps `RewardBreakdown`, the
   config loader and the exact-decimal helpers, and obtains
   `(precision, recall, f1, return)` from `reward_metrics()`, which delegates
   to `compute_official_metrics`. `reward_metrics` exists only as a named
   seam so fault-injection suites can patch the live path.
3. `RewardBreakdown.eta` now reports the **applied** weight (0.2), not the
   stale config value, so no consumer can read a 0.05 bound off a breakdown.
4. `configs/scoring/default.json` is a **frozen contract** and is *not*
   edited (D-14-02): it still contains `eta: 0.05` and
   `provisional: true`. Those keys no longer influence the reward; the
   discrepancy is documented here instead of silently re-frozen.
5. `precision_score` / `recall_score` deliberately keep the vacuous-truth
   convention (`1` when the denominator is empty), because the generator
   cross-check (`scoring/crosscheck.py`, EXIT GATE 8) needs "nothing asserted,
   nothing wrong" to read as perfect precision on clean episodes. The
   official `P = R = 0` convention applies **only** to the reward breakdown
   and the jury-facing scorer. Both conventions are documented in the
   docstrings.

Regression evidence: `tests/env/test_cursor_codec.py`,
`tests/scoring/test_reward_sanity.py`, `tests/scoring/test_diagnostics.py`,
`tests/scoring/test_reward_properties.py`, `tests/unit/test_property.py`,
`tests/official/test_block1_contracts.py::test_C05_pagination_over_large_fixture_L_three_pages`,
and mutation suite MUT-07/08/13 re-pointed at the live reward path.

## D-15-04 (2026-11-22) — Documentation claims are checked on two axes: numbers *and* shapes

The Phase 15 gate verified one thing well: every published **number** is
re-measured from the artifact that produced it. Re-auditing against the literal
EXIT GATE text ("the jury can deploy from the README and verify the key claims")
found that all the numbers were right while the prose around them described files,
fields, routes and a demo that did not exist — 19 defects, none of which the
numeric gate could see. A number can be re-measured; a sentence cannot, so the
sentence must be pinned to something that defines it.

Decision: six **structural** detectors are added to `tools/verify_doc_claims.py`,
each with a negative test proving it fires, and each pinned to a source rather
than to a second copy of the truth:

| Check | Pinned to |
|---|---|
| `C-PATHS` | the filesystem (with generated artifacts resolved against `judge/verify.py::REQUIRED_FULL_ARTIFACTS`) |
| `C-DATADICT` | a real generated episode, compared **both ways** |
| `C-DEMO` | `tools/demo_walkthrough.py::SEGMENTS` |
| `C-WORKBENCH-API` | `tools/demo_server.py`'s real dispatchers |
| `C-COMMANDS` | the filesystem and the Makefile |
| `C-REWARD` | `scoring/official_scorer.py`'s live constants |

Three sub-rules were forced by the work and are part of the decision:

1. **Single source, not agreement.** The demo's clock and titles live in one
   `SEGMENTS` tuple that the program prints *and* the checker compares. Two copies
   of a clock is one copy too many.
2. **Assert the contract, not the file.** A bare `replay_report.json` is legitimate
   prose on a bare checkout; it is resolved against the gate's own artifact list so
   the check means something before any artifact exists.
3. **Absence must be documentable.** "`gen/diff.py` does not exist" is a true
   sentence. Lines carrying a negation cue (`does not exist`, `forbidden`,
   `renamed`) are exempt; incident reports and limitation disclosures need to be
   able to say what is *not* there.

Consequence: 19 defects fixed. The most serious was not a path but a claim —
`docs/INDEPENDENCE.md` asserted a "different human owner" for the verifier, which
this repository cannot evidence (see `D-15-05`).

## D-15-05 (2026-11-22) — Organisational independence is disclosed as *unevidenced*, not asserted

Master TZ §4 (REQ-ORG-001/002) requires the independent verifier to be built under
a different human owner or agent context from the generator. `docs/INDEPENDENCE.md`
stated this as accomplished fact, and `.github/CODEOWNERS` named four handles
(`@twinledger-owner-a..d`) that do not exist. The repository was produced by AI
agents in one shared session context.

Decision: split the claim into its two halves and state each at its true strength.

- **Technical zero-common-mode separation — proven and continuously tested.**
  `verifier/` imports neither `gen/` nor `core/` nor `invariants/` nor `nlp/`
  (AST scan + fresh-subprocess import test, `RC-002`, release blocker); a runtime
  `io.open`/`Path.open` spy over an episode that *has* `sealed/truth.json` proves
  discovery never leaves `public/`; Stage-1 output is committed as a canonical
  SHA-256 digest before truth is visible and Stage 2 rejects post-hoc tampering.
- **Organisational separation — not evidenced.** Stated as such in
  `docs/INDEPENDENCE.md` ("Ownership — and an honest correction"), in `AGENTS.md`
  and in the `CODEOWNERS` header, and raised as `Q-ORG-01` / `Q-ORG-02` in
  `docs/QUESTIONS.md` as **OPEN**, answerable only by a human owner.

Rationale: a judge can verify the first half themselves in one command. Overstating
the second half would put the project's central architectural argument at risk the
moment anyone opened the CODEOWNERS file.

## D-15-06 (2026-11-22) — A published fact may not depend on which target ran last

Third occurrence of one bug class (after `D-15-01` and `D-15-03`), so it is now a
named rule with a test rather than a lesson.

`make verify-core` writes a six-gate summary into the same directory as the
twelve-gate full run. Two published facts were read *out of that summary*:

- `F-TESTS` / `F-TESTS-OFFICIAL` — the test counts. Under `--core` these reported
  524/524 while a full run reported 522/524, because two tests skip on core-mode
  evidence. `make verify-core && make docs-verify` therefore failed on a correct
  tree.
- `test_check_mode_passes_on_repository` re-litigated the whole documentation gate
  inside RC-001 against whatever summary happened to be there.

Decision:

1. Test counts are measured by `unittest` **discovery** over `tests/` and
   `tests/official/`, never read from a run's summary. Discovery is the same set
   every time, so the number is state-independent (`F-TESTS` now cites
   "unittest discovery over tests/ (state-independent)").
2. `test_checker_runs_under_ascii_stdout` asserts the *locale* contract only
   (no `UnicodeEncodeError`, ASCII-clean stream, a well-formed exit code). It no
   longer asserts `rc == 0`, which belongs to the authoritative check in
   `judge/verify.py`.
3. `test_check_mode_passes_on_repository` requires **full-mode** evidence and
   skips explicitly otherwise; that skip reason is registered in
   `judge/verify.py::_OPTIONAL_SKIP_RE` as a positional skip, in the same way as
   the existing bootstrap skip.

Proven order-independent by running three sequences, all green: `verify-core` →
`docs-verify`; `report` → `docs-verify`; `docs-verify` twice.


## D-15-07 (2026-11-22) — Locale-safe verdicts and discovery-backed prose totals

Follow-up to `D-15-06`, under REQ-DOC-001/002 and Phase 15 Task 15.6.

1. A clean full verifier run under `LC_ALL=C PYTHONIOENCODING=ascii` completed
   its gates but crashed while printing a Unicode success message. All console
   writes in `judge/verify.py::main` now use `_say`: readable transliteration of
   known glyphs, then ASCII replacement for arbitrary interpolated diagnostics
   when a narrow stream cannot encode them. JSON verdicts are unchanged. Three
   state-independent regression tests guard the output path, including narrow
   stdout and explicit streams. Mutation checks reject reverting the helper or
   restoring a raw Unicode print.
2. README's prose still claimed **522-test** coverage and DEMO claimed **490
   tests**, despite a current generated facts block. Add `C-COUNTS`, comparing
   recognised prose totals with unittest discovery; `--write` repairs only the
   numeric spans. Official/mirror counts are measured separately. Tests exercise
   positive/negative cases, adjacent clauses, subset exemptions, preservation,
   and idempotence. The detector caught the real stale claims before repair.
3. This is a bounded recogniser, not a natural-language verifier: it scans the
   existing jury-facing `DOC_SCAN`, recognises integer + test/tests with optional
   official/mirror qualifiers, and excludes named-file counts and unqualified
   counts below 100 unless explicitly introduced as full/total/suite. Historical
   phase reports are not current-claim inputs. Other phrasing still needs review.

No frozen contract, release tag, scoring formula, ownership assertion, or
organiser-score claim changed. Organisational independence remains unevidenced.


## D-16-03 (2026-11-22) — Cut `v1.0.1`; tag `v1.0.0` is superseded for submission

Under Phase 16 (Tasks 16.7/16.8) and the documented recommendation in `docs/QUESTIONS.md`
(`Q-REL-01`), the release authority (repository owner) directed that the Phase 16
release candidate be executed fully, which includes the tag and the GitHub release.

Finding that makes this necessary rather than cosmetic: tag `v1.0.0` (`8da0af2`)
contains the `.dockerignore` defect documented in `D-16-02` — the default
`make docker-check` image would have included `episodes/dev/*/sealed/truth.json`
(a `REQ-ARENA-005` violation). The fix, the forensic audit (PR #24), the
mandatory-target audit (PR #23) and the Phase 15 structural hardening (PR #25)
were all merged after the tag. Cutting `v1.0.1` from the reviewed merge commit is
the documented remedy; the alternative (re-tagging `v1.0.0`) was rejected because
moving a published tag rewrites history for everyone who fetched it.

Scope and constraints honoured:
- `v1.0.0` remains published and unchanged; `v1.0.1` is additive.
- The tag is annotated and is placed **after** re-verification of the merge
  commit, not before; `make rc-check` PASS from clean-clone conditions is the
  precondition, matching the precedent set for `v1.0.0`.
- No frozen file changes: the frozen surface remains 30 files,
  `aggregate_sha256 = 0747baf0…`; `schema_version` stays `1.0.0` (`D-01-01`);
  `code_version` stays `twinledger@1.0.0` (it names the frozen contract line, not
  the release tag).
- `pyproject.toml`'s unreferenced `version` field is aligned to `1.0.1` (it was
  stale at `0.1.0` and is read by nothing in the tree).
- `official_score_claimed: false` (TZ §23.6). No jury-score claim is made.
- `Q-ORG-01` / `Q-ORG-02` remain OPEN: this decision does not, and cannot, fix
  the organisational-independence disclosure.

Supersedes: the recommendation recorded in `Q-REL-01` (now RESOLVED by this
decision). Refs: `D-16-02`, `D-15-07`, Phase 16 (`docs/PHASE_REPORTS/PHASE-16.md`,
v1.0.1 addendum), release notes `docs/RELEASE_NOTES.md`.

## D-16-04 (2026-11-22) — Phase 16 §7 risk-closure round: evidence, not assertions

Phase 16's final report listed four risks (§7). This decision records how each
was closed (or honestly not closed) without moving tags, editing frozen files,
or self-approving a process decision.

1. **Organisational independence unevidenced (`Q-ORG-01`) — strengthened
   technically, NOT closed.** A second, from-scratch Stage-1 implementation
   (`independent_verifier/`) was authored from `spec/verifier_algorithm.md` and
   `contracts/` alone: own `Fraction`-based money/FX, own `zoneinfo` fiscal
   periods, own discovery algorithms, own ProofGraph DAG with acyclicity and
   finding-path checks, own minimal-evidence ablation. Measured agreement:
   all 10 committed dev/train episodes re-derive signature-identically with
   identical `episode_public_hash`; the official `D01..D20` matrix
   (`master_seed=2026`) re-derives to sealed truth at F1 = 1 exact, FP = 0,
   FN = 0 (harness: `tools/verify_independent_rederivation.py`; evidence:
   `docs/EVIDENCE/independent-rederivation-2026-11-22.json`; regression-locked
   by `tests/independent_verifier/`). Both implementations were written in one
   AI-agent-assisted session, so this is **zero-common-mode technical evidence,
   not organisational separation**. `Q-ORG-01` / `Q-ORG-02` stay OPEN.
2. **Docker offline verification was CI-only.** No container runtime exists on
   the execution host (probed 2026-11-22: `docker`, `podman`, `buildah`,
   `nerdctl`, `ctr`, `runc`, `containerd` — none). Added
   `tools/offline_local_check.py`: user+net+mount namespace, read-only bind of
   the tree, tmpfs `artifacts/`, refused if any network route exists, full suite
   PASS. Static Dockerfile/`.dockerignore` hardening audit 10/10 PASS. The
   Docker image build remains **CI-authoritative** (`docker-offline` green on
   `main` @ `3b83864`, run `45021422570`; also `45020669250` on the `v1.0.1` tag
   commit `640c585`). Exact local scope recorded in
   `docs/EVIDENCE/offline-local-2026-11-22.json`. A maintainer with Docker
   should run `make docker-check` once locally to retire this entirely.
3. **Prose only partly machine-checkable.** `tools/verify_doc_claims.py` gains
   `C-EVIDENCE` (evidence artifacts exist, carry full git SHA, record PASS),
   `C-SCORE-HONEST` (every `official_score_claimed` in the scan set asserts
   `false`), and `C-QORG-OPEN` (`Q-ORG-01`/`Q-ORG-02` not presented as
   RESOLVED). 18 → 21 checks, all PASS; new tests raise the suite to 548.
4. **`v1.0.0` release notes lacked a supersession pointer.** The GitHub release
   `v1.0.0` body now opens with a SUPERSEDED banner pointing to `v1.0.1`
   (`D-16-02`, `D-16-03`). The tag itself is unchanged — published tags do not
   move. Repository docs (`docs/RELEASE_NOTES.md`, `docs/CHANGELOG.md`) already
   carried the pointer.

Constraints honoured: no frozen file changed (`freeze_release --verify` → 30
files, `0747baf0…`); no tag moved (`v1.0.0`, `v1.0.1`); `code_version` stays
`twinledger@1.0.0`; `schema_version` stays `1.0.0`;
`official_score_claimed: false`; `Q-ORG-01` / `Q-ORG-02` / `Q-DOC-01` remain
OPEN; Phase 17 not restarted; `make official-eval` not run (the committed
`trajectories.jsonl` untouched).

Refs: Phase 16 report §10/§11 (`docs/PHASE_REPORTS/PHASE-16.md`),
`docs/EVIDENCE/`, `docs/INDEPENDENCE.md` ("Re-derivation evidence"),
`docs/AGENT_REPORTS/2026-11-22/`.
