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
make verify            # lint + full 12-gate Judge Kit (RC-001..RC-012) + all 317 unit/official/security tests + 21 JSON/CSV/HTML artifacts
make verify-core       # fast critical core & release-blocker gates (RC-001..005, RC-009)
make test-official     # official Genesis FinTech 2026-11-20 mirror suite (Blocks 1..5: C01..C20, D01..D20, Block 3 #1..20 + M01..M12, P01..P20, Baselines)
make replay            # fresh-process CLOSED_EVAL trajectory & Merkle receipt replay + paired P01..P20
make audit-shortcuts   # metadata-only L2 logistic regression audit (AUC <= 0.55) + 10-channel canary fuzzer + C20 non-leakage
make mutation-test     # 26-mutant matcher/reward kill suite (100% killed) + Official Block 3 M01..M12
make report            # synthesize self-contained offline artifacts/reports/latest/report.html + report_index.json
make official-eval     # run all 4 baseline policies across D01..D20 -> artifacts/trajectories/trajectories.jsonl + summary
make docker-check      # build and run inside hardened offline container (--network=none --read-only --cap-drop ALL)
python3 tools/demo_walkthrough.py        # deterministic 3-minute jury walkthrough (seed=2025)
python3 tools/freeze_release.py --verify # cryptographic SHA-256 verification of frozen contracts & configs
```

Pinned versions and reproduction parameters are locked in
`configs/official_eval_manifest.json`.

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

| Policy | Isolation | Mean F1 | Mean Return | Mean Steps | Max Episode Time |
|---|---|---:|---:|---:|---:|
| `oracle` | Judge-side reference | `1.0000` | `+0.9920` | `4.0` | `0.004s` |
| `simple_reconciliation` | OS subprocess worker | `1.0000` | `+0.9853` | `7.3` | `0.065s` |
| `random` | OS subprocess worker | `0.2500` | `-0.5060` | `12.0` | `0.084s` |
| `mass_flagging` | OS subprocess worker | `0.0000` | `-1.0000` | `1.0` | `0.079s` |

Full 80-episode trajectory log (zero truth leakage in observations):
`artifacts/trajectories/trajectories.jsonl`.

---

## Documentation & Traceability

- `spec/official_fintech_checks_2026-11-20.md` — Official Genesis FinTech check definitions (verbatim reference)
- `docs/OFFICIAL_COMPLIANCE_MATRIX.md` — Line-by-line mapping of all 100 points (`C01..C20`, `D01..D20`, Block 3 #1..20 + M01..M12, `P01..P20`, Engineering 0/1/2)
- `docs/FAILURE_ANALYSIS.md` — Measured failure analysis, root causes, and re-verification
- `docs/LIMITATIONS.md` — Honest scenario-linked limitations
- `docs/INDEPENDENCE.md` — Zero-common-mode verifier independence & import-boundary rules
- `tools/demo_server.py` — Optional zero-dependency interactive local workbench (`python3 tools/demo_server.py`)
