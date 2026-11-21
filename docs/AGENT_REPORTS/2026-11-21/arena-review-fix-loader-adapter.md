# Arena agent — review remediation: loader row order + bounded reads (2026-11-21)

**SCOPE:** Code-review remediation (2 findings on `main` @ `7f47638`), branch
`arena/794acafe-genesis-hackathon-malika-nurzh` (PR #12).
**STATUS:** DONE
**Decision:** `D-10-03` · **Limitation:** `L7`

## 1. Findings and root causes

| # | Finding | Root cause | Risk assessment |
| --- | --- | --- | --- |
| 1 | `env/loader.py` (former line 166) sorted table rows by `(pk, currency)` although README "Canonical Tables" requires verbatim row-order preservation (paired checks `P01..P05`, `P11..P20`) | `load_public_book` re-ordered rows for "stable" pagination | **Not exploitable on the jury path** — official checks run through `adapter/official_env.py::load_official_public_book`, which already preserved order. Empirically the sort was an identity operation on all generator-produced episodes (files are written pk-sorted by `gen/serialize.py`), so no existing trajectory/replay changed. Real impact: any externally-authored or permutation-shuffled episode file would be silently re-ordered in the core env (wrong rows per page, order-dependent policy behavior). |
| 2 | `adapter/official_env.py` (records at former line ~127, metadata, and `public/documents/` — which read each file **twice**) plus `env/loader.py`, `scoring/official_scorer.py`, `verifier/public_loader.py` read whole files into memory unbounded | No size/count caps on episode-supplied reads | **DoS-class only, not a data-integrity hole:** with trusted synthetic episodes (the shippable configuration) practical risk is negligible (largest generated public file ≈ 27 KiB). If an episode path ever receives untrusted/external files, one huge file could exhaust RAM or stall startup. Fixed unconditionally with cheap bounds. |

## 2. Implementation

- `contracts/loader.py`: shared guards — `read_text_bounded()` (hard byte cap
  `MAX_INPUT_FILE_BYTES = 16 MiB`, enforced at `cap + 1` bytes, UTF-8 check,
  never echoes content) and `check_row_cap()` (`MAX_INPUT_ROWS = 100_000`,
  resolved at call time so tests/operators can tighten it).
- `env/loader.py`: bounded reads (`EnvError("LIMIT")` on overflow,
  `EnvError("INTERNAL")` on I/O/JSON failures — note `JSONDecodeError` is a
  `ValueError` subclass, handler order preserved for correct codes);
  **file row order preserved verbatim** (sort removed, contract documented in
  the module docstring).
- `adapter/official_env.py`: bounded reads for metadata, records (jsonl row
  caps both parse paths), and `public/documents/` — now a **single** bounded
  read per document (fixes a double-read), JSON-or-text fallback preserved.
- `scoring/official_scorer.py`: bounded reads in
  `collect_accessible_ids_from_episode_dir._read_rows` and
  `load_truths_from_episode_dir`.
- `verifier/public_loader.py`: bounded read in `load_public_episode` +
  row cap in `_parse_jsonl` (`PublicEpisodeError` on overflow). No algorithm
  changes — robustness guard only, imports `contracts.loader` (already a
  dependency).
- `tests/env/test_loader_order_and_bounds.py` (new, 11 tests): loader order
  preservation (env + adapter), `list_records` pagination follows file order,
  generated-episode order regression guard, byte/row-cap boundary unit test,
  `LIMIT`-error tests for env/adapter, documents-subfolder bound, scorer and
  verifier bounds.

## 3. Verification (exact commands & exit codes)

| Command | Exit | Status | Result |
| --- | --- | --- | --- |
| `python3 -m unittest discover -s tests -t .` | 0 | PASS | **354 tests OK** (343 before session + 11 new) |
| `python3 -m unittest tests.env.test_loader_order_and_bounds -v` | 0 | PASS | 11/11 |
| `make lint` | 0 | PASS | `import boundary scan: CLEAN (REQ-ARC-001..007)` |
| `make test-official` | 0 | PASS | 55/55 (incl. `P01..P20` paired invariance matrix) |
| `make replay` | 0 | PASS | byte-identical replay + paired invariance `P01..P20` |
| `make test-property` | 0 | PASS | 8/8 property suites |
| CI (`core`, `docker-offline`) on PR #12 | 0 | PASS | see PR checks |

Failed/skipped/not-run: none. Behavior-neutrality on generated episodes proven
by the pre-change probe (file order == loaded order for all 10 tables) plus
`test_generated_episode_order_matches_file_order_regression`.

## 4. Files changed

- Modified: `contracts/loader.py`, `env/loader.py`, `adapter/official_env.py`,
  `scoring/official_scorer.py`, `verifier/public_loader.py`,
  `docs/DECISIONS.md`, `docs/LIMITATIONS.md`, `docs/CURRENT_STATE.md`,
  `docs/CONTEXT/NEXT_AGENT.md`
- Created: `tests/env/test_loader_order_and_bounds.py`,
  `docs/AGENT_REPORTS/2026-11-21/arena-review-fix-loader-adapter.md`
- Contracts/API: **none** (no frozen schema change; `LIMIT` is a pre-existing
  fixed error code in `contracts/tool_response.schema.json`).

## 5. Residual notes

- Caps (`16 MiB` / `100 000 rows`) are documented as limitation `L7`; if an
  official task ever ships bigger fixtures, raise the two constants in
  `contracts/loader.py` and re-run `tests/env/test_loader_order_and_bounds.py`.
- The reviewer's practical assessment was correct: for the shippable trusted-
  synthetic configuration the memory issue was a hardening opportunity, not a
  live vulnerability; it is now closed unconditionally anyway.

## 6. Next action

Merge PR #12 (Phase 10 audit + this remediation) after CI green — owner: team
lead. Then proceed per `docs/CONTEXT/NEXT_AGENT.md`.
