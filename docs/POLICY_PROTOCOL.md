# Policy Protocol (JSONL v1.0) — Task 15.3

The wire contract between an untrusted **policy** process and the TwinLedger
**environment**. This is the only channel a policy has; it never imports
`env`, `scoring`, `gen`, `verifier` or `seal` (`tools/check_import_boundaries.py`
enforces this statically).

- Protocol version: `1.0` (`contracts/version.py::PROTOCOL_VERSION`)
- Transport: **one canonical JSON object per line** over the child process's
  stdin/stdout. Nothing else is written to stdout.
- Authoritative schemas: `contracts/tool_request.schema.json`,
  `contracts/tool_response.schema.json` (both **frozen**; see
  `configs/release_freeze.json`).
- Server: `python3 -m env.jsonl_server <public_dir> [--config <env_config.json>] [--cursor-seed <label>]`

A policy that speaks JSONL but nothing else can be written in any language.
Two reference implementations ship in this repo: `harness/reference_policies.py`
(Python) and `arena/policies/worker.py` (subprocess-isolated baselines).

---

## 1. Session start

On startup the environment writes exactly one unsolicited line:

```json
{"event": "ready", "observation": {"task": "...", "manifest": {...}, "policy": {...}, "remaining_steps": 100}}
```

`policy` is the frozen public accounting policy (`contracts/policy.schema.json`)
every finding must be judged against. `remaining_steps` is the remaining action
budget. No truth, seed, salt or scoring field is ever present.

## 2. Request envelope

```json
{"protocol_version": "1.0", "request_id": "<1..128 chars>", "action": {"tool": "list_records", "args": {...}}}
```

| Field | Type | Notes |
|---|---|---|
| `protocol_version` | string, const `"1.0"` | mismatched versions are rejected |
| `request_id` | string, 1–128 chars | echoed back verbatim so responses can be correlated |
| `action.tool` | string enum | see §3 |
| `action.args` | object | tool-specific, see §3 |

`additionalProperties: false` — unknown top-level fields are rejected.
Extensions must be namespaced `x_twinledger_*`.

## 3. Tools

The authoritative core tool enum, as accepted by `env/jsonl_server.py` and
`contracts/tool_request.schema.json`, is:

`list_records`, `get_record`, `get_document`, `calc`, `submit`

> **Vocabulary note (important for adapter authors).** The *core* environment
> and this JSONL protocol use the tool name **`calc`**. The *official
> competition adapter* (`judge_adapter.py`, `adapter/official_env.py`) exposes
> the **same capability** under the name **`calculator`**, matching the wording
> of the official task statement. They are different front doors to one
> implementation (`env/calc.py`, the AST-only exact `Decimal` evaluator), and
> each rejects the other's name:
>
> | Front door | Accepted name | Rejection of the other |
> |---|---|---|
> | `env/jsonl_server.py` (this protocol) | `calc` | `{"code": "UNKNOWN_TOOL"}` |
> | `judge_adapter.make_env()` | `calculator` | `{"code": "UNKNOWN_ACTION"}` |
>
> Both behaviours are verified live by `tests/…` and by
> `python3 tools/verify_doc_claims.py` (`C-PROTOCOL-TOOLS`), which reads the
> enum straight from the frozen schema so the documentation cannot drift.

| Tool | Args | Result payload |
|---|---|---|
| `list_records` | `table`, `cursor` (`null` = first page), `limit` (`1..max_page_size`, default 50) | `{"records": [...], "next_cursor": str \| null}` |
| `get_record` | `table`, `id` — raw PK, typed `PREFIX:id`, or FX semantic key `YYYY-MM-DD:SRC:DST[:SRC_CODE]` | record object |
| `get_document` | `doc_id` — raw or typed `PREFIX:id` | document object (preloaded; zero filesystem access at request time) |
| `calc` | `expression` — exact decimal arithmetic, AST-validated, ≤ `max_calc_expression_length` and ≤ `max_calc_ast_nodes` | exact decimal **string**, e.g. `"0.1+0.2"` → `"0.3"` |
| `submit` | `findings` — `{"findings": [...]}` per the official finding schema | `{"accepted": true}` or a bounded structural error |

Tables (`table` argument): `ledger`, `invoices`, `payments`, `fx` are the
required adapter tables; `credit_notes`, `bank_lines`, `counterparties`,
`accounts`, `opening_balances`, `period_calendar` are supporting tables.

## 4. Response envelope

```json
{"protocol_version": "1.0", "request_id": "...", "ok": true, "result": {...}, "error": null}
```

`ok` is `false` exactly when `error` is non-null, and then `result` is `null`.
Errors are **bounded**: they carry a stable machine code and a short message,
never a traceback, file path, salted value, or truth fragment. An unexpected
internal failure is reported as `INTERNAL` with the fixed message
`"bounded internal environment error"` (the real exception is never serialised).

The authoritative error-code enum (`contracts/tool_response.schema.json`) is:

`UNKNOWN_TOOL`, `BAD_ARGS`, `BAD_FILTER`, `BAD_CURSOR`, `NOT_FOUND`, `BAD_FINDING`, `CALC_ERROR`, `LIMIT`, `TERMINATED`, `ALREADY_SUBMITTED`, `INTERNAL`

| Code | Meaning | Recoverable? |
|---|---|---|
| `UNKNOWN_TOOL` | tool name not in the enum above | yes — correct the name |
| `BAD_ARGS` | missing / wrong-typed / extra argument | yes |
| `BAD_FILTER` | unsupported table or filter combination | yes |
| `BAD_CURSOR` | malformed, expired, or foreign cursor | yes — restart pagination with `null` |
| `NOT_FOUND` | record/document id does not exist in public data | yes |
| `BAD_FINDING` | structurally invalid finding on `submit` | no (submission is final) |
| `CALC_ERROR` | non-arithmetic or invalid expression | yes |
| `LIMIT` | page size, expression length/AST nodes, request bytes, or file row/size cap exceeded | yes |
| `TERMINATED` | episode budget exhausted | no |
| `ALREADY_SUBMITTED` | any request after a successful `submit` | no |
| `INTERNAL` | bounded internal failure | yes |

## 5. Termination, budget and determinism

- **Budget:** `max_steps` actions (default 100, `configs/environment/default.json`).
  `submit` does **not** consume an inspection step (`submit_counts_as_step: false`)
  but does consume an action. Errored inspection steps *do* count.
- **Terminal states:** a successful `submit` ends the episode; exhausting the
  budget without submitting ends it with empty findings; a 60-second wall-clock
  limit ends it as truncated.
- **CLOSED_EVAL mode:** the reward returned to the policy is always numeric `0`,
  and `info` carries no truth or metric fields. Truth-bearing rewards exist only
  in `train` mode and in the judge-side scorer.
- **Determinism:** identical public inputs + identical request sequence produce
  byte-identical canonical responses. This is what the fresh-process replay gate
  (`RC-005`, `5/5 byte-identical replays`) checks.

## 6. Limits enforced on every request

| Limit | Value | Config key |
|---|---|---|
| actions per episode | 100 | `max_steps` |
| page size | ≤ 50 | `max_page_size` |
| findings per submission | ≤ 20 (env) / ≤ 30 (official scorer, pre-dedup) | `max_findings` |
| `evidence_ids` per finding | ≤ 20 (env) / ≤ 10 (official scorer, pre-dedup) | `max_evidence_ids` |
| request line size | 65 536 bytes | `max_request_bytes` |
| calc expression | 500 chars, 100 AST nodes | `max_calc_expression_length`, `max_calc_ast_nodes` |
| episode wall clock | 60 s | (harness) |
| per-file episode input | 16 MiB / 100 000 rows | `contracts/loader.py` (`L7`) |

## 7. Minimal worked session

```text
S->P  {"event": "ready", "observation": {...}}
P->S  {"protocol_version": "1.0", "request_id": "1", "action": {"tool": "list_records", "args": {"table": "invoices", "cursor": null, "limit": 2}}}
S->P  {"protocol_version": "1.0", "request_id": "1", "ok": true, "result": {"records": [...], "next_cursor": "..."}, "error": null}
P->S  {"protocol_version": "1.0", "request_id": "2", "action": {"tool": "calc", "args": {"expression": "0.1+0.2"}}}
S->P  {"protocol_version": "1.0", "request_id": "2", "ok": true, "result": {"result": "0.3", "remaining_steps": 98}, "error": null}
P->S  {"protocol_version": "1.0", "request_id": "3", "action": {"tool": "submit", "args": {"findings": []}}}
S->P  {"protocol_version": "1.0", "request_id": "3", "ok": true, "result": {"accepted": true}, "error": null}
```

## 8. Conformance checks

| Property | Enforced by |
|---|---|
| Request/response satisfy the frozen schemas | `contracts/validate.py`, `tests/contracts/` |
| Error responses leak nothing | `tests/security/`, 10-channel canary audit (0 hits) |
| Byte-identical replay of a recorded session | `RC-005` → `replay_report.json` |
| Tool vocabulary matches this page | `tools/verify_doc_claims.py` claim `C-PROTOCOL-TOOLS` |
| Error vocabulary matches this page | `tools/verify_doc_claims.py` claim `C-PROTOCOL-ERRORS` |
