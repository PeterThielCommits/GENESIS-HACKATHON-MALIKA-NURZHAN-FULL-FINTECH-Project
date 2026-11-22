# TwinLedger — Proof-Carrying FinTech Audit Environment

TwinLedger is a deterministic, synthetic-accounting benchmark environment for AI
audit agents featuring counterfactual twins, a zero-common-mode independent
verifier, sealed evaluation, OS-isolated baseline policies, and full compliance
with the official **Genesis FinTech Check Definitions (2026-11-20)**
(`spec/official_fintech_checks_2026-11-20.md`).

> **Scope notice:** TwinLedger is a research/competition benchmark environment.
> It is **not** a real accounting system, audit service, or financial product.
> All companies, banks, counterparties, documents, and transactions are 100%
> synthetic and generated deterministically from seed.

---

## Single-Command Verification (Offline, Python 3.11, stdlib-only)

Working directory inside the container: `/app`. Zero external `pip` packages or
network access are required.

```bash
make verify            # lint + full 12-gate Judge Kit (RC-001..RC-012) + the whole test suite + 20 evidence artifacts
make verify-core       # fast critical core & release-blocker gates (RC-001..005, RC-009)
make test-official     # official Genesis FinTech 2026-11-20 mirror suite (Blocks 1..5: C01..C20, D01..D20, Block 3 #1..20 + M01..M12, P01..P20, Baselines) — 55 official mirror tests
make replay            # fresh-process CLOSED_EVAL trajectory & Merkle receipt replay + paired P01..P20
make audit-shortcuts   # metadata-only L2 logistic regression audit (AUC <= 0.55) + 10-channel canary fuzzer + C20 non-leakage
make mutation-test     # 26/26 mutants killed matcher/reward suite + Official Block 3 M01..M12
make report            # synthesize self-contained offline artifacts/reports/latest/report.html + report_index.json
make official-eval     # run all 4 baseline policies across D01..D20 -> artifacts/trajectories/trajectories.jsonl + summary
make replay-all        # replay ALL 80 published trajectories and compare every step (TZ 16.4)
make release-audit     # release audit: secrets, file list, size, deps, official entrypoint (TZ 16.5/16.6)
make rc-check          # release candidate gate: verify + docs-verify + replay-all + release-audit
make docker-check      # build and run inside hardened offline container (--network=none --read-only --cap-drop ALL)
make container-local-check # the same container command, hardened, on a host WITHOUT a container runtime
make base-image-verify # the Docker base image is pinned by digest and the recorded build info agrees
python3 tools/demo_walkthrough.py        # deterministic 3-minute jury walkthrough (seed=2025)
python3 tools/freeze_release.py --verify # cryptographic SHA-256 verification of frozen contracts & configs
python3 tools/verify_doc_claims.py       # re-measure every number published in this README
```

Pinned versions and reproduction parameters are locked in
`configs/official_eval_manifest.json`. The **container** is pinned too: the base
image is fixed by digest (`python:3.11-slim-bookworm@sha256:a36c24f9…`, CPython
3.11.16 on Debian bookworm) and the image records its own provenance - see
`docs/EVIDENCE/docker-build-info.json`.

---

## Judge Adapter (`judge_adapter.py`)

Root-level entrypoint `/app/judge_adapter.py` exposes the exact three functions
required by the official evaluation harness:

```python
import judge_adapter

# 1. Deterministic episode generator (writes public/, manifest.json, sealed/truth.json, sealed/provenance.json)
judge_adapter.generate_episode(seed: int, config: dict, output_dir: str) -> None

# 2. Public-only stateful environment (reset/step)
env = judge_adapter.make_env()
obs, info = env.reset(seed=2026, config={"mode": "closed", "episode_dir": "...", "team_config": {}})
obs, reward, terminated, truncated, info = env.step({"name": "list_records", "args": {"table": "invoices", "cursor": None, "limit": 50}})

# 3. Closed judge-side scorer (never exposed to policies)
metrics = judge_adapter.score_episode(episode_dir: str, findings: dict, inspection_steps: int) -> dict
```

### Canonical Actions & Result Schema

Every `step(action)` accepts `{"name": "<action>", "args": {...}}`:

| Action | Arguments | `obs["result"]` |
|---|---|---|
| `list_records` | `table`, `cursor` (`null` for page 1), `limit` (`1..50`) | `{"records": [...], "next_cursor": str \| null}` |
| `get_record` | `table`, `id` (raw PK, typed `PREFIX:id`, or FX semantic key `YYYY-MM-DD:SRC:DST[:SRC_CODE]`) | Record JSON object |
| `get_document` | `doc_id` (raw ID or typed `PREFIX:id`) | Document JSON object (strictly preloaded; zero filesystem access) |
| `calculator` | `expression` (AST-only exact `Decimal` arithmetic) | Exact decimal string (e.g. `"0.1+0.2"` -> `"0.3"`) |
| `submit` | `findings` (`{"findings": [...]}` per §05) | `{"accepted": true}` or bounded structural error (never leaks truth) |

> **Adapter vs core tool names.** The adapter above (and the official harness)
> spells the calculator **`calculator`**. The *core* JSONL protocol
> (`env/jsonl_server.py`, `contracts/tool_request.schema.json`) spells the same
> capability **`calc`**, and the two front doors each reject the other's name
> (`UNKNOWN_ACTION` / `UNKNOWN_TOOL`). This asymmetry is intentional
> compatibility with the official task statement and is documented in
> [`docs/POLICY_PROTOCOL.md`](docs/POLICY_PROTOCOL.md).

- **Initial observation:** `{"task": str, "manifest": object, "policy": object, "remaining_steps": 100}`
- **Subsequent observations:** `{"result": value_or_null, "error": null_or_object, "remaining_steps": int}`
- **Budget & timeout:** 100 total actions (`submit` on action 100 after 99 inspection steps is accepted and `terminated=True`; 100 inspection actions without `submit` ends as `truncated=True` with empty findings). `submit` is excluded from `inspection_steps`; errored inspection steps are included. 60-second wall-clock episode limit ends as `truncated=True` with empty findings.
- **Closed vs. train mode:** In `mode="closed"`, `reward` is numeric `0` on every step including terminal, and `info` contains zero truth/metric fields. In `mode="train"`, terminal reward is returned to the policy.

### Canonical Tables

- **Required adapter tables:** `ledger` (journal entries), `invoices`, `payments`, `fx` (FX quotes).
- **Supporting accounting tables:** `credit_notes`, `bank_lines`, `counterparties`, `accounts`, `opening_balances`, `period_calendar`.
- File row order is preserved verbatim on load (for paired permutation checks `P01..P05`, `P11..P20`), and arbitrary bijective-remapped string IDs are accepted without prefix regex restrictions (for `P06..P20`).

### Supported Anomaly Types & Interaction Scenarios

| Anomaly Type | Description | Canonical `affected_ids` |
|---|---|---|
| `DUPLICATE_PAYMENT` | Duplicate payment & settlement journal entry on an already-settled invoice (excluding valid refunds/credit notes & recurring invoices) | `["JE:<dup_je>", "PAY:<dup_pay>"]` |
| `PARTIAL_PAYMENT_ALLOCATION` | Missing payment allocation (`allow_advances=false`), premature `paid` invoice status with unpaid shortfall, or over-allocated payment | `["PAY:<pay>"]` (missing alloc) or `["INV:<inv>", "PAY:<pay>"]` |
| `FX_RATE_MISMATCH` | Foreign-currency journal entry converted using non-policy rate/date/source/quote convention | `["JE:<je>"]` |
| `PERIOD_CUTOFF` | Invoice recognition journal entry posted to the wrong fiscal period under company timezone & calendar policy | `["JE:<je>"]` |

Two documented multi-anomaly interaction scenarios (`D16..D20`):
1. **Interaction #1 (`FX_PERIOD_INTERACTION`, `D16..D18`):** `FX_RATE_MISMATCH` + `PERIOD_CUTOFF` on cross-border invoices spanning period boundaries across multiple currencies, rounding modes, quote conventions, and timezones.
2. **Interaction #2 (`PAYMENT_ALLOCATION_INTERACTION`, `D19..D20`):** `DUPLICATE_PAYMENT` + `PARTIAL_PAYMENT_ALLOCATION` (`missing_allocation` and `premature_paid`) woven alongside legitimate split, refund, and credit-note distractors.

### Official Matcher & Reward Specification (`scoring/official_scorer.py`)

- **Pre-deduplication structural limits:** max `30` findings, max `10` `evidence_ids` per finding (checked before dedup — M05), max `1000` Unicode code points for `explanation`, strict JSON integer `claimed_amount_minor` (rejects `bool`/`str`/`float` — M09). Structural violations return `return=-1.0` and `null` for `tp/fp/fn/precision/recall/f1`.
- **Exact matching:** exact case/whitespace ID, type, and currency equality; exact `affected_ids` set equality; `evidence_ids` must cover at least one valid evidence set AND every listed `evidence_id` must exist in the episode's accessible public IDs (M04); default amount tolerance `tau = 0` (`abs(claimed - expected) <= tau`).
- **Matching & tie-break:** maximum-cardinality bipartite matching (duplicate findings kept as separate vertices — M12), breaking ties by sorting truth `issue_id` by Unicode code points and selecting the lexicographically smallest sorted list of `(issue_id, finding_index)` pairs (M10/M11).
- **Reward formula (exact `Fraction` arithmetic):**
  - Clean book + empty findings (`TP=FP=FN=0`): `precision=0`, `recall=0`, `f1=1`.
  - `return = clip([-1, 1], 2 * F1 - 1 - 0.2 * inspection_steps / 100)`.

---

## Measured Baseline Results (`D01..D20`, `seed=2026`)

Public policies (`random`, `simple_reconciliation`, `mass_flagging`) execute in
separate OS child processes (`python3 -m arena.policies.worker`) with sanitized
environment variables and zero access to `episode_dir`, `sealed/`, or scoring
modules. The `oracle` policy runs strictly on the judge side (`judge/oracle_policy.py`).

The exact table is **generated** from `artifacts/trajectories/trajectories.jsonl` and
appears in [Measured Facts](#measured-facts-auto-generated) below, with the rest of
this README's numbers. It is never transcribed by hand.

Full 80-episode trajectory log (zero truth leakage in observations):
`artifacts/trajectories/trajectories.jsonl`. Reproduce with
`python3 tools/run_official_eval.py` (or `make official-eval`).

---

## Verify Every Claim Yourself (Tasks 15.5 & 15.6)

No number in this README is maintained by hand. The block below is rendered from
measured artifacts by `tools/verify_doc_claims.py --write`; **check mode** (used
by `make verify` and CI) fails if it disagrees with the artifacts, if a prose
count goes stale, or if a superseded value reappears anywhere in the docs.

```bash
make verify                          # regenerates every artifact
python3 tools/verify_doc_claims.py   # re-measures and diffs this documentation
```

Current measured state of this release (see the generated block for the full set):
**12/12 PASS** verification gates, the full **653-test** suite, **5/5 byte-identical replays**,
**0 canary hits**, `official_score_claimed: false`.

### Verify the release archive itself (Phase 17, TZ §24)

The release is archived in the repository, so it can be restored **and** checked
without any explanation from the team:

```bash
python3 tools/freeze_release.py --verify     # 30 frozen contract surfaces
python3 tools/evidence_freeze.py --verify    # every tracked release file + the gate verdicts
python3 tools/release_evidence.py --verify   # the reconstructable release archive
python3 tools/check_workflows.py             # the CI workflow files are well formed
```

`docs/EVIDENCE/evidence_freeze.json` pins the SHA-256 of every tracked release
file; `docs/EVIDENCE/phase-17-release-evidence-2026-11-22.json` states the
frozen digest, the twelve rubric gates, the decision register and the exact
command list to rebuild and re-verify the release. The committed archive must
match the committed tree (`make evidence-verify`, also run by CI).

The manifest separates the two things a checkout can prove:

| Command | Needs the generated artifacts? | What it proves |
|---|---|---|
| `python3 tools/evidence_freeze.py --verify` | no | the release **surface** (every tracked file) is byte-identical to the archived release — works on a bare clone |
| `python3 tools/evidence_freeze.py --verify --require-reports` | yes | additionally, the archived gate **verdicts** match a fresh `make verify` run — the release gate used by CI and `make rc-check` |

The full reconstruct-and-verify sequence (also stored in the archive under
`reconstruct.commands`) is:

```bash
python3 tools/freeze_release.py --verify
make verify && make docs-verify && make replay-all && make release-audit
python3 tools/evidence_freeze.py --verify --require-reports
python3 tools/release_evidence.py --verify --strict
```

<!-- BEGIN GENERATED:measured-facts -->
<!-- Generated by `python3 tools/verify_doc_claims.py --write`. Do not edit by hand:
     `make verify` / CI fails if this block disagrees with the measured artifacts. -->

### Measured Facts (auto-generated)

| Fact | Value | Source artifact |
|---|---|---|
| Verification gates defined (RC-001..RC-012) | **12** | `judge/rubric_map.json (frozen contract)` |
| Official organiser score claimed | **false** | `verify_summary.json` |
| Total tests in the verification suite | **653** | `unittest discovery over tests/ (state-independent)` |
| Official mirror tests (Blocks 1–5) | **55** | `unittest discovery over tests/official/ (state-independent)` |
| Evidence artifacts indexed | **20** | `report_index.json` |
| Required artifacts missing | **0** | `report_index.json` |
| Byte-identical fresh-process replays | **5/5** | `replay_report.json` |
| Mutants killed | **26/26** | `mutation_test_report.json` |
| Metamorphic transforms passed | **7/7** | `metamorphic_report.json` |
| Prompt-injection twin pairs evaluated | **24** | `robustness_report.json` |
| Invariant catalog (TZ §12.1) | **INV-01..INV-17** | `invariants_report.json` |
| Canary leakage hits | **0** | `canary_fuzz_report.json` |
| Policy-visible canary channels | **10** | `judge/canary_fuzzer.py` |
| Canary encoding transforms | **9** | `judge/canary_fuzzer.py` |
| Shortcut macro ROC AUC (limit 0.55) | **0.5389** | `shortcut_audit.json` |
| Performance budgets (step p99 / RSS / episode disk) | **< 5.0 ms / < 300.0 MB / < 50.0 MB** | `performance_report.json` |
| Performance & dependency gate | **PASS** | `performance_report.json` |
| Core stdlib-only | **true** | `dependency_report.json` |
| Runtime network required | **false** | `dependency_report.json` |
| Core JSONL protocol tools | **`list_records`, `get_record`, `get_document`, `calc`, `submit`** | `contracts/tool_request.schema.json` |
| Bounded tool error codes | **11** | `contracts/tool_response.schema.json` |
| Demo walkthrough seed | **2025** | `tools/demo_walkthrough.py` |

### Measured Baselines — D01..D20, seed 2026 (auto-generated)

| Policy | Isolation | Mean F1 | Mean Return | Mean Steps | Episodes |
|---|---|---:|---:|---:|---:|
| `oracle` | Judge-side reference | 1.0000 | +0.9920 | 4.0 | 20 |
| `simple_reconciliation` | OS subprocess worker | 1.0000 | +0.9853 | 7.3 | 20 |
| `random` | OS subprocess worker | 0.2500 | -0.5060 | 12.0 | 20 |
| `mass_flagging` | OS subprocess worker | 0.0000 | -1.0000 | 1.0 | 20 |

Source: `artifacts/trajectories/trajectories.jsonl` (80 episode rows). Reproduce with `make official-eval`.
<!-- END GENERATED:measured-facts -->

## Documentation & Traceability

- `spec/official_fintech_checks_2026-11-20.md` — Official Genesis FinTech check definitions (verbatim reference)
- `docs/OFFICIAL_COMPLIANCE_MATRIX.md` — Line-by-line mapping of all 100 points (`C01..C20`, `D01..D20`, Block 3 #1..20 + M01..M12, `P01..P20`, Engineering 0/1/2)
- `docs/FAILURE_ANALYSIS.md` — Measured failure analysis, root causes, and re-verification
- `docs/LIMITATIONS.md` — Honest scenario-linked limitations
- `docs/INDEPENDENCE.md` — Zero-common-mode verifier independence & import-boundary rules
- `docs/API_USAGE.md` — Official adapter API, policy client, local workbench, CLI surface (Task 15.3)
- `docs/POLICY_PROTOCOL.md` — JSONL v1.0 wire contract: envelopes, tool/error enums, budgets, limits (Task 15.3)
- `docs/DEMO.md` — 3-minute jury demo + technical backup demo (`make demo-backup`, Task 15.4)
- `docs/DESIGN.md` — as-built design: layering, frozen contracts, truth lifecycle, process boundaries
- `docs/DATA_DICTIONARY.md` — every public episode file and field, checked against a real episode
- `docs/THREAT_MODEL.md` — assets, trust boundaries, and the controls enforced at each one
- `docs/STATUS.md` · `docs/CURRENT_STATE.md` · `docs/DECISIONS.md` — phase status, live state, and the append-only decision log
- `docs/QUESTIONS.md` — protocol questions (resolved) plus the open process questions from the 2026-11-22 audit
- `docs/RUBRIC_TRACEABILITY.md` · `docs/OFFICIAL_COMPLIANCE_MATRIX.md` — requirement-to-evidence mapping
- `docs/RELEASE_NOTES.md` · `docs/CHANGELOG.md` — what shipped and when
- `tools/demo_server.py` — Optional zero-dependency interactive local workbench (`python3 tools/demo_server.py`)
