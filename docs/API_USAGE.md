# API Usage — TwinLedger (Task 15.3)

Three public entry points, in the order a judge is likely to need them:

1. **Official adapter** (`judge_adapter.py`) — the three functions the
   competition harness calls.
2. **JSONL policy protocol** (`env/jsonl_server.py`) — the wire contract for
   writing a policy in any language. Full specification:
   [`docs/POLICY_PROTOCOL.md`](POLICY_PROTOCOL.md).
3. **Local workbench** (`tools/demo_server.py`) — zero-dependency HTTP UI/API for
   exploring episodes interactively.

All three are stdlib-only, offline, and deterministic.

---

## 1. Official adapter — `judge_adapter.py`

The only module the official harness needs. It never requires arguments beyond
those documented here.

```python
import judge_adapter

# (1) Generate one deterministic episode
judge_adapter.generate_episode(seed: int, config: dict, output_dir: str) -> None
#   writes output_dir/public/, manifest.json, sealed/truth.json, sealed/provenance.json

# (2) Public-only stateful environment (identical to the official interaction model)
env = judge_adapter.make_env()
obs, info = env.reset(seed=2026, config={"mode": "closed", "episode_dir": "...", "team_config": {}})
obs, reward, terminated, truncated, info = env.step({"name": "list_records", "args": {...}})

# (3) Closed judge-side scorer (never exposed to a policy)
metrics = judge_adapter.score_episode(episode_dir: str, findings: dict, inspection_steps: int) -> dict
```

**Adapter tool names** (note: `calculator`, not `calc` — see the vocabulary
table in `docs/POLICY_PROTOCOL.md` §3):

| Tool | Args | Result |
|---|---|---|
| `list_records` | `table`, `cursor`, `limit` | `{"records": [...], "next_cursor": …}` |
| `get_record` | `table`, `id` | record object |
| `get_document` | `doc_id` | document object |
| `calculator` | `expression` | exact decimal string (`"0.1+0.2"` → `"0.3"`) |
| `submit` | `findings` | `{"accepted": true}` |

Observations in `mode="closed"`: initial
`{"task", "manifest", "policy", "remaining_steps"}`; subsequent
`{"result", "error", "remaining_steps"}`. Reward is `0` on every step and `info`
holds no truth or metric fields.

### Verified example

```console
$ python3 -c "import judge_adapter, json; \
env=judge_adapter.make_env(); \
o,i=env.reset(seed=2026, config={'mode':'closed','episode_dir':'episodes/dev/ep_dev_001_clean_distractors','team_config':{}}); \
print(json.dumps(env.step({'name':'calculator','args':{'expression':'0.1+0.2'}})[0]['result']))"
"0.3"
```

### Scoring contract

`score_episode` returns precision / recall / F1 / TP / FP / FN and the official
reward. The reward is exact `Fraction` arithmetic:

```text
clean book + no findings  -> precision=0, recall=0, f1=1
otherwise                 -> return = clip([-1, 1], 2 * F1 - 1 - 0.2 * inspection_steps / 100)
```

Structural violations (more than 30 findings, more than 10 `evidence_ids`,
`explanation` over 1000 code points, non-integer `claimed_amount_minor`) return
`return = -1.0` with `null` for `tp/fp/fn/precision/recall/f1`.

The formula above is the **organisers' official formula**, fixed on 2026-11-20
(`spec/official_fintech_checks_2026-11-20.md`, decision `D-18-01`) and reproduced
by the 20 published reward vectors plus the 12 worked examples. There is exactly
one implementation, `scoring/official_scorer.compute_official_metrics`;
`scoring/reward.py` is a thin view over it. `configs/scoring/default.json` still
carries `eta: 0.05` and `provisional: true` as a frozen historical record, but
those keys no longer influence the computed reward — the applied penalty weight
is `0.2` over a budget of `100` steps. What remains *internal* is the claim, not
the formula: a `return` from this module is an internal measurement and is never
presented as an organiser jury score (`official_score_claimed: false`).

---

## 2. Policy over JSONL

```bash
python3 -m env.jsonl_server episodes/dev/ep_dev_001_clean_distractors/public \
    --config configs/environment/default.json \
    --cursor-seed episode
```

Then write one `tool_request` JSON object per line to stdin and read one
`tool_response` per line from stdout. The first line is always
`{"event": "ready", "observation": {...}}`. See
[`docs/POLICY_PROTOCOL.md`](POLICY_PROTOCOL.md) for the full request/response
envelopes, the authoritative tool and error enums, budget semantics and limits.

Reference policies you can copy from:

```bash
python3 -m harness.reference_policies --policy rule_auditor_v1   # honest auditor
python3 -m harness.reference_policies --policy silent_v1         # says nothing
python3 -m harness.reference_policies --policy truncate_exhaust_v1
```

---

## 3. Local workbench (optional, no dependencies)

```bash
python3 tools/demo_server.py          # UI at http://127.0.0.1:8000
```

Relative `/api/...` endpoints (all local, no network egress):

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/episodes` | list episodes in `episodes/dev` and `episodes/train` |
| GET | `/api/episode/<split>/<id>/overview` | public metadata, manifest check, table counts |
| POST | `/api/episode/<split>/<id>/verify` | run Stage-1 `verifier.discover` + ProofGraph + Stage-2 crosscheck |
| POST | `/api/env/reset` | reset an interactive environment session |
| POST | `/api/env/step` | execute one frozen-contract tool request |
| POST | `/api/env/score` | score submitted findings via `scoring.reward` |
| POST | `/api/generate` | generate and fully verify a fresh episode |
| POST | `/api/run_checks` | run the import-boundary scan and a unittest summary |

---

## 4. Command-line surface

| Command | What it proves |
|---|---|
| `make verify` | full 12-gate Judge Kit + evidence artifacts |
| `make verify-core` | fast critical gates only |
| `make test-official` | official mirror suite (Blocks 1–5) |
| `make replay` | fresh-process replay + Merkle receipts |
| `make audit-shortcuts` | metadata shortcut audit + canary fuzzer |
| `make mutation-test` | mutant kill suite |
| `make official-eval` | 4 baselines × D01..D20 → `artifacts/trajectories/trajectories.jsonl` |
| `python3 tools/demo_walkthrough.py` | deterministic 3-minute jury walkthrough |
| `python3 tools/verify_doc_claims.py` | every documented number vs its artifact |
| `python3 tools/freeze_release.py --verify` | frozen contract/config digests |

---

## 5. Error handling expectations

Callers must treat a `tool_response` as authoritative on `ok`:

```python
resp = call(request)
if not resp["ok"]:
    code = resp["error"]["code"]          # stable enum, see POLICY_PROTOCOL.md §4
    # recoverable: UNKNOWN_TOOL, BAD_ARGS, BAD_FILTER, BAD_CURSOR, NOT_FOUND, CALC_ERROR, LIMIT, INTERNAL
    # final:       BAD_FINDING, TERMINATED, ALREADY_SUBMITTED
```

Never branch on `error["message"]` text — only on `code`. Messages are for humans
and intentionally contain no paths, seeds, salts or truth.