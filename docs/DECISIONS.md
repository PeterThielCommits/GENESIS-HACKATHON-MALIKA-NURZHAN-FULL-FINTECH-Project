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
