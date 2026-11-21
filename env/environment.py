"""Phase 5 public-only TwinLedger interactive environment (REQ-ENV-001..032).

Strictly conforms to frozen v1.0.0 contracts:
  - ``contracts/tool_request.schema.json`` (`protocol_version: "1.0"`)
  - ``contracts/tool_response.schema.json``
  - ``contracts/finding.schema.json``
  - ``configs/environment/default.json``

Imports ONLY ``contracts/`` and Python 3.11 stdlib. Never accesses private
directories or scoring/verifier/generator modules.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from contracts.loader import validate_instance
from contracts.version import PROTOCOL_VERSION
from env.calc import evaluate_calc
from env.cursors import CursorCodec
from env.errors import EnvError
from env.loader import LoadedPublicBook, TABLE_SPECS, load_public_book

DEFAULT_ENV_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "configs" / "environment" / "default.json"
)

ALLOWED_FILTERS: dict[str, frozenset[str]] = {
    "accounts": frozenset({"account_id", "account_type", "normal_side"}),
    "opening_balances": frozenset({"account_id", "currency"}),
    "period_calendar": frozenset({"period_id", "status"}),
    "counterparties": frozenset({"counterparty_id", "role", "country"}),
    "fx_rates": frozenset({"fx_id", "pair", "effective_date", "source_code", "date_from", "date_to"}),
    "invoices": frozenset({"doc_id", "counterparty_id", "currency", "status", "min_amount_minor", "max_amount_minor"}),
    "payments": frozenset({"pay_id", "counterparty_id", "currency", "payment_channel", "min_amount_minor", "max_amount_minor"}),
    "credit_notes": frozenset({"credit_note_id", "invoice_id", "counterparty_id", "currency", "reason_code"}),
    "bank_lines": frozenset({"bank_line_id", "currency", "direction", "min_amount_minor", "max_amount_minor"}),
    "journal_entries": frozenset({"je_id", "posting_period", "source_document_id", "currency", "account_id", "counterparty_id"}),
}


@dataclass(frozen=True)
class EnvConfig:
    """Validated runtime limits loaded from ``configs/environment/default.json``."""

    mode: str = "CLOSED_EVAL"
    max_steps: int = 100
    max_page_size: int = 50
    max_findings: int = 20
    max_evidence_ids: int = 20
    max_request_bytes: int = 65536
    max_calc_expression_length: int = 500
    max_calc_ast_nodes: int = 100
    submit_counts_as_step: bool = False

    @classmethod
    def from_file(cls, path: Path | str | None = None) -> EnvConfig:
        p = Path(path) if path is not None else DEFAULT_ENV_CONFIG_PATH
        raw = json.loads(p.read_text(encoding="utf-8"))
        return cls(
            mode=str(raw.get("mode", "CLOSED_EVAL")),
            max_steps=int(raw.get("max_steps", 100)),
            max_page_size=int(raw.get("max_page_size", 50)),
            max_findings=int(raw.get("max_findings", 20)),
            max_evidence_ids=int(raw.get("max_evidence_ids", 20)),
            max_request_bytes=int(raw.get("max_request_bytes", 65536)),
            max_calc_expression_length=int(raw.get("max_calc_expression_length", 500)),
            max_calc_ast_nodes=int(raw.get("max_calc_ast_nodes", 100)),
            submit_counts_as_step=bool(raw.get("submit_counts_as_step", False)),
        )


def _match_row(table: str, row: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, val in filters.items():
        if key == "date_from":
            if str(row.get("effective_date", "")) < str(val):
                return False
        elif key == "date_to":
            if str(row.get("effective_date", "")) > str(val):
                return False
        elif key == "min_amount_minor":
            amt = row.get("total_minor", row.get("amount_minor"))
            if not isinstance(amt, int) or amt < int(val):
                return False
        elif key == "max_amount_minor":
            amt = row.get("total_minor", row.get("amount_minor"))
            if not isinstance(amt, int) or amt > int(val):
                return False
        elif table == "journal_entries" and key in ("currency", "account_id", "counterparty_id"):
            if not any(ln.get(key) == val for ln in row.get("lines", [])):
                return False
        else:
            if row.get(key) != val:
                return False
    return True


def _validate_filters(table: str, filters: Any) -> dict[str, Any]:
    if filters is None:
        return {}
    if not isinstance(filters, dict):
        raise EnvError("BAD_FILTER", "filters must be a JSON object")
    allowed = ALLOWED_FILTERS.get(table, frozenset())
    clean: dict[str, Any] = {}
    for k, v in filters.items():
        if k not in allowed:
            raise EnvError("BAD_FILTER", f"unsupported filter {k!r} for table {table!r}")
        if k in ("min_amount_minor", "max_amount_minor"):
            if type(v) is not int or isinstance(v, bool):
                raise EnvError("BAD_FILTER", f"{k} must be an integer")
        elif not isinstance(v, str):
            raise EnvError("BAD_FILTER", f"filter {k!r} value must be a string")
        clean[k] = v
    return clean


class TwinLedgerEnv:
    """Stateful public-only audit environment for one episode."""

    def __init__(self, config: EnvConfig | None = None) -> None:
        self._base_config = config if config is not None else EnvConfig.from_file()
        self._config = self._base_config
        self._book: LoadedPublicBook | None = None
        self._cursors: CursorCodec | None = None
        self._steps_used: int = 0
        self._submitted: bool = False
        self._terminated: bool = False
        self._submitted_findings: list[dict[str, Any]] | None = None
        self._requested_evidence_ids: set[str] = set()

    @property
    def steps_used(self) -> int:
        return self._steps_used

    @property
    def terminated(self) -> bool:
        return self._terminated

    @property
    def submitted_findings(self) -> list[dict[str, Any]] | None:
        return list(self._submitted_findings) if self._submitted_findings is not None else None

    @property
    def requested_evidence_ids(self) -> frozenset[str]:
        return frozenset(self._requested_evidence_ids)

    def reset(self, public_dir: Path | str, *, cursor_seed: str = "episode") -> dict[str, Any]:
        """Load a public episode directory and return the initial public observation."""
        book = load_public_book(public_dir)
        pol = book.policy
        self._config = EnvConfig(
            mode=self._base_config.mode,
            max_steps=min(self._base_config.max_steps, int(pol["max_steps"])),
            max_page_size=min(self._base_config.max_page_size, int(pol["max_page_size"])),
            max_findings=min(self._base_config.max_findings, int(pol["max_findings"])),
            max_evidence_ids=min(self._base_config.max_evidence_ids, int(pol["max_evidence_ids"])),
            max_request_bytes=self._base_config.max_request_bytes,
            max_calc_expression_length=self._base_config.max_calc_expression_length,
            max_calc_ast_nodes=self._base_config.max_calc_ast_nodes,
            submit_counts_as_step=self._base_config.submit_counts_as_step,
        )
        self._book = book
        key = hashlib.sha256(
            f"env-cursor|{book.company['company_id']}|{cursor_seed}".encode("utf-8")
        ).digest()
        self._cursors = CursorCodec(key)
        self._steps_used = 0
        self._submitted = False
        self._terminated = False
        self._submitted_findings = None
        self._requested_evidence_ids = set()

        return {
            "protocol_version": PROTOCOL_VERSION,
            "mode": self._config.mode,
            "company": book.company,
            "policy": book.policy,
            "limits": {
                "max_steps": self._config.max_steps,
                "max_page_size": self._config.max_page_size,
                "max_findings": self._config.max_findings,
                "max_evidence_ids": self._config.max_evidence_ids,
                "submit_counts_as_step": self._config.submit_counts_as_step,
            },
            "tables": sorted(TABLE_SPECS.keys()),
            "remaining_steps": self._config.max_steps,
        }

    def _ok_response(self, request_id: str, result: dict[str, Any]) -> dict[str, Any]:
        resp = {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": result,
            "error": None,
        }
        errs = validate_instance("tool_response", resp)
        if errs:
            raise RuntimeError(f"internal tool_response schema failure: {errs}")
        return resp

    def _err_response(self, request_id: str, err: EnvError) -> dict[str, Any]:
        resp = {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": False,
            "result": None,
            "error": err.to_dict(),
        }
        errs = validate_instance("tool_response", resp)
        if errs:
            raise RuntimeError(f"internal tool_response schema failure: {errs}")
        return resp

    def step(self, request: dict[str, Any] | str | bytes) -> dict[str, Any]:
        """Process one versioned tool request and return a frozen-schema-valid response."""
        if self._book is None or self._cursors is None:
            return self._err_response("uninitialized", EnvError("TERMINATED", "environment not reset"))

        # Enforce max_request_bytes before parsing if raw payload supplied
        if isinstance(request, bytes):
            if len(request) > self._config.max_request_bytes:
                return self._err_response("oversized", EnvError("LIMIT", "request exceeds max_request_bytes"))
            try:
                req_obj = json.loads(request.decode("utf-8"))
            except Exception:
                return self._err_response("malformed", EnvError("BAD_ARGS", "malformed UTF-8/JSON request"))
        elif isinstance(request, str):
            raw_b = request.encode("utf-8")
            if len(raw_b) > self._config.max_request_bytes:
                return self._err_response("oversized", EnvError("LIMIT", "request exceeds max_request_bytes"))
            try:
                req_obj = json.loads(request)
            except Exception:
                return self._err_response("malformed", EnvError("BAD_ARGS", "malformed JSON request"))
        elif isinstance(request, dict):
            req_obj = request
        else:
            return self._err_response("malformed", EnvError("BAD_ARGS", "request must be dict/str/bytes"))

        req_id = (
            req_obj.get("request_id")
            if isinstance(req_obj, dict) and isinstance(req_obj.get("request_id"), str) and 1 <= len(req_obj["request_id"]) <= 128
            else "invalid-request-id"
        )

        # Check tool name first so unknown tool returns UNKNOWN_TOOL cleanly
        if isinstance(req_obj, dict) and isinstance(req_obj.get("action"), dict):
            raw_tool = req_obj["action"].get("tool")
            if isinstance(raw_tool, str) and raw_tool not in ("list_records", "get_record", "get_document", "calc", "submit"):
                if not self._terminated:
                    self._consume_step_or_terminate()
                return self._err_response(req_id, EnvError("UNKNOWN_TOOL", f"unknown tool: {raw_tool}"))

        schema_errs = validate_instance("tool_request", req_obj)
        if schema_errs:
            if not self._terminated:
                self._consume_step_or_terminate()
            return self._err_response(req_id, EnvError("BAD_ARGS", f"invalid tool_request: {schema_errs[0]}"))

        tool: str = req_obj["action"]["tool"]
        args: dict[str, Any] = req_obj["action"]["args"]

        if self._terminated:
            code = "ALREADY_SUBMITTED" if (self._submitted and tool == "submit") else "TERMINATED"
            return self._err_response(req_id, EnvError(code, "episode has already terminated"))

        if tool == "submit":
            if self._config.submit_counts_as_step:
                if self._steps_used >= self._config.max_steps:
                    self._terminated = True
                    return self._err_response(req_id, EnvError("LIMIT", "step budget exhausted"))
                self._steps_used += 1
            try:
                res = self._handle_submit(args)
            except EnvError as exc:
                return self._err_response(req_id, exc)
            return self._ok_response(req_id, res)

        # Non-submit inspection/calc call consumes 1 step (even if arguments fail!)
        if self._steps_used >= self._config.max_steps:
            self._terminated = True
            return self._err_response(req_id, EnvError("LIMIT", "step budget exhausted"))
        self._steps_used += 1
        if self._steps_used >= self._config.max_steps:
            # Allow this final call to complete; next non-submit call will hit LIMIT
            pass

        try:
            if tool == "list_records":
                res = self._handle_list_records(args)
            elif tool == "get_record":
                res = self._handle_get_record(args)
            elif tool == "get_document":
                res = self._handle_get_document(args)
            elif tool == "calc":
                res = self._handle_calc(args)
            else:
                raise EnvError("UNKNOWN_TOOL", f"unknown tool: {tool}")
        except EnvError as exc:
            return self._err_response(req_id, exc)

        res["remaining_steps"] = max(0, self._config.max_steps - self._steps_used)
        return self._ok_response(req_id, res)

    def _consume_step_or_terminate(self) -> None:
        if self._steps_used < self._config.max_steps:
            self._steps_used += 1
        else:
            self._terminated = True

    def _handle_list_records(self, args: dict[str, Any]) -> dict[str, Any]:
        assert self._book is not None and self._cursors is not None
        table = args.get("table")
        if not isinstance(table, str) or table not in TABLE_SPECS:
            raise EnvError("BAD_ARGS", f"unknown table: {table!r}")

        filters = _validate_filters(table, args.get("filters"))
        page_size = args.get("page_size", self._config.max_page_size)
        if type(page_size) is not int or isinstance(page_size, bool) or not 1 <= page_size <= self._config.max_page_size:
            raise EnvError("BAD_ARGS", f"page_size must be in 1..{self._config.max_page_size}")

        cursor = args.get("cursor")
        offset = 0 if cursor is None else self._cursors.decode(cursor, table, filters)

        rows = [r for r in self._book.tables[table] if _match_row(table, r, filters)]
        page = rows[offset : offset + page_size]
        next_offset = offset + len(page)
        next_cursor = (
            self._cursors.encode(table, filters, next_offset)
            if next_offset < len(rows)
            else None
        )

        pk_field, prefix = TABLE_SPECS[table]
        if prefix:
            for r in page:
                if r.get(pk_field):
                    self._requested_evidence_ids.add(f"{prefix}:{r[pk_field]}")

        return {
            "table": table,
            "records": page,
            "count": len(page),
            "total_matching": len(rows),
            "next_cursor": next_cursor,
        }

    def _handle_get_record(self, args: dict[str, Any]) -> dict[str, Any]:
        assert self._book is not None
        raw_id = args.get("id")
        table_hint = args.get("table")
        if not isinstance(raw_id, str) or not raw_id:
            raise EnvError("BAD_ARGS", "get_record requires non-empty string 'id'")

        if ":" in raw_id:
            found = self._book.records_by_typed_id.get(raw_id)
            if found is None:
                raise EnvError("NOT_FOUND", f"record not found: {raw_id}")
            tbl, row = found
            if table_hint is not None and table_hint != tbl:
                raise EnvError("NOT_FOUND", f"record {raw_id} is not in table {table_hint}")
            self._requested_evidence_ids.add(raw_id)
            return {"table": tbl, "typed_id": raw_id, "record": row}

        if isinstance(table_hint, str) and table_hint in TABLE_SPECS:
            _, prefix = TABLE_SPECS[table_hint]
            if prefix:
                tid = f"{prefix}:{raw_id}"
                found = self._book.records_by_typed_id.get(tid)
                if found is not None:
                    self._requested_evidence_ids.add(tid)
                    return {"table": table_hint, "typed_id": tid, "record": found[1]}
        raise EnvError("NOT_FOUND", f"record not found: {raw_id}")

    def _handle_get_document(self, args: dict[str, Any]) -> dict[str, Any]:
        assert self._book is not None
        doc_id = args.get("id") or args.get("doc_id")
        if not isinstance(doc_id, str) or not doc_id:
            raise EnvError("BAD_ARGS", "get_document requires non-empty string 'id'")
        doc = self._book.documents_by_id.get(doc_id)
        if doc is None:
            raise EnvError("NOT_FOUND", f"document not found: {doc_id}")
        if ":" in doc_id:
            self._requested_evidence_ids.add(doc_id)
        return {"id": doc_id, "document": doc}

    def _handle_calc(self, args: dict[str, Any]) -> dict[str, Any]:
        return evaluate_calc(
            args.get("expression"),
            max_length=self._config.max_calc_expression_length,
            max_ast_nodes=self._config.max_calc_ast_nodes,
        )

    def _handle_submit(self, args: dict[str, Any]) -> dict[str, Any]:
        findings = args.get("findings")
        if not isinstance(findings, list):
            raise EnvError("BAD_FINDING", "submit requires 'findings' list")
        if len(findings) > self._config.max_findings:
            raise EnvError("BAD_FINDING", f"findings count exceeds max_findings ({self._config.max_findings})")

        validated: list[dict[str, Any]] = []
        for idx, item in enumerate(findings):
            if not isinstance(item, dict):
                raise EnvError("BAD_FINDING", f"findings[{idx}] must be an object")
            errs = validate_instance("finding", item)
            if errs:
                raise EnvError("BAD_FINDING", f"findings[{idx}]: {errs[0]}")
            ev = item.get("evidence_ids", [])
            if len(ev) > self._config.max_evidence_ids:
                raise EnvError(
                    "BAD_FINDING",
                    f"findings[{idx}] evidence_ids exceeds max_evidence_ids ({self._config.max_evidence_ids})",
                )
            validated.append(item)

        self._submitted = True
        self._terminated = True
        self._submitted_findings = validated
        return {
            "accepted": True,
            "submitted_count": len(validated),
            "steps_used": self._steps_used,
            "terminated": True,
            "mode": self._config.mode,
            "reward": None,
        }


__all__ = ["ALLOWED_FILTERS", "EnvConfig", "TwinLedgerEnv"]
