"""Official Genesis FinTech (2026-11-20) public-only audit environment.

Implements the exact ``reset(seed, config) -> (obs, info)`` and
``step(action) -> (obs, reward, terminated, truncated, info)`` protocol
defined in ``spec/official_fintech_checks_2026-11-20.md``:

  - Canonical 5 actions: ``list_records``, ``get_record``, ``get_document``,
    ``calculator``, ``submit`` inside envelope ``{"name": ..., "args": ...}``;
  - Canonical 4 tables: ``ledger``, ``invoices``, ``payments``, ``fx`` (plus
    TwinLedger supporting tables ``credit_notes``, ``bank_lines``,
    ``counterparties``, ``accounts``, ``opening_balances``, ``period_calendar``);
  - Preserves file row order on load (supports paired permutation checks
    P01..P05 & P11..P20 without re-sorting);
  - Accepts arbitrary bijective-remapped string IDs (supports P06..P20) and
    semantic FX keys ``YYYY-MM-DD:SRC:DST``;
  - Enforces 100-action budget (99 inspection + submit on step 100 accepted;
    100 inspection without submit -> truncated with empty findings), 60-second
    wall-clock limit, and strict closed-mode ``reward == 0`` with zero leakage.

Strictly public-only: never imports ``gen/``, ``verifier/``, ``scoring/``,
or ``seal/`` and never reads ``sealed/``, ``truth.json``, or ``provenance.json``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from contracts.currency import exponent_of
from env.calc import evaluate_calc
from env.cursors import CursorCodec
from env.errors import EnvError

MAX_ACTIONS_DEFAULT = 100
MAX_PAGE_SIZE_DEFAULT = 50
TIME_LIMIT_SECONDS_DEFAULT = 60.0
MAX_FINDINGS_OFFICIAL = 30
MAX_EVIDENCE_IDS_OFFICIAL = 10
MAX_EXPLANATION_CODEPOINTS = 1000

TASK_DESCRIPTION = (
    "Audit the synthetic company's accounting records against the published "
    "policy using the provided read-only tools and calculator, then submit "
    "all verifiable accounting anomalies via submit."
)

# Canonical adapter table -> (candidate filenames, pk field candidates, typed prefix)
_TABLE_LOAD_SPECS: dict[str, tuple[tuple[str, ...], tuple[str, ...], str]] = {
    "ledger": (("journal_entries.jsonl", "ledger.jsonl", "ledger.json", "journal_entries.json"), ("je_id", "row_id", "id"), "JE"),
    "invoices": (("invoices.jsonl", "invoices.json"), ("doc_id", "invoice_id", "id"), "INV"),
    "payments": (("payments.jsonl", "payments.json"), ("pay_id", "payment_id", "id"), "PAY"),
    "fx": (("fx_rates.jsonl", "fx.jsonl", "fx.json", "fx_rates.json"), ("fx_id", "id"), "FX"),
    "credit_notes": (("credit_notes.jsonl", "credit_notes.json"), ("credit_note_id", "doc_id", "id"), "CN"),
    "bank_lines": (("bank_lines.jsonl", "bank_lines.json"), ("bank_line_id", "id"), "BANK"),
    "counterparties": (("counterparties.jsonl", "counterparties.json"), ("counterparty_id", "entity_id", "id"), "CP"),
    "accounts": (("accounts.json", "accounts.jsonl"), ("account_id", "id"), ""),
    "opening_balances": (("opening_balances.json", "opening_balances.jsonl"), ("account_id", "id"), ""),
    "period_calendar": (("period_calendar.json", "period_calendar.jsonl"), ("period_id", "id"), ""),
}

TABLE_ALIASES: dict[str, str] = {
    "ledger": "ledger",
    "journal_entries": "ledger",
    "invoices": "invoices",
    "payments": "payments",
    "fx": "fx",
    "fx_rates": "fx",
    "credit_notes": "credit_notes",
    "bank_lines": "bank_lines",
    "counterparties": "counterparties",
    "accounts": "accounts",
    "opening_balances": "opening_balances",
    "period_calendar": "period_calendar",
}

CANONICAL_TABLES: tuple[str, ...] = (
    "ledger",
    "invoices",
    "payments",
    "fx",
    "credit_notes",
    "bank_lines",
    "counterparties",
    "accounts",
    "opening_balances",
    "period_calendar",
)


@dataclass(frozen=True)
class OfficialPublicBook:
    """In-memory public episode data preserving exact file row order and remapped IDs."""

    episode_id: str
    manifest: dict[str, Any]
    policy: dict[str, Any]
    company: dict[str, Any]
    tables: dict[str, tuple[dict[str, Any], ...]]
    records_by_table_and_id: dict[str, dict[str, dict[str, Any]]]
    documents_by_id: dict[str, dict[str, Any]]
    cursor_fingerprint: str


def _safe_resolve_under(base: Path, target: Path) -> Path:
    resolved = target.resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise EnvError("BAD_ARGS", "path escapes public episode directory")
    return resolved


def _read_public_json(base: Path, candidates: tuple[str, ...]) -> Any | None:
    for name in candidates:
        p = base / name
        if p.is_file():
            resolved = _safe_resolve_under(base, p)
            return json.loads(resolved.read_text(encoding="utf-8"))
    return None


def _read_public_rows(base: Path, candidates: tuple[str, ...]) -> list[dict[str, Any]]:
    for name in candidates:
        p = base / name
        if not p.is_file():
            continue
        resolved = _safe_resolve_under(base, p)
        text = resolved.read_text(encoding="utf-8")
        if p.suffix == ".jsonl":
            rows: list[dict[str, Any]] = []
            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
            return rows
        obj = json.loads(text)
        if isinstance(obj, list):
            return [r for r in obj if isinstance(r, dict)]
    return []


def _extract_pk(row: Mapping[str, Any], candidates: tuple[str, ...]) -> str | None:
    for key in candidates:
        val = row.get(key)
        if isinstance(val, str) and val:
            return val
    return None


def load_official_public_book(episode_dir: Path | str) -> OfficialPublicBook:
    """Load public-only episode files preserving exact row order and arbitrary IDs."""
    root = Path(episode_dir)
    if not root.is_dir():
        raise EnvError("NOT_FOUND", "episode directory does not exist")
    pub = root / "public" if (root / "public").is_dir() else root
    pub_resolved = pub.resolve()

    company = _read_public_json(pub_resolved, ("company.json",)) or {}
    policy = _read_public_json(pub_resolved, ("policy.json",)) or {}
    disk_manifest = _read_public_json(root.resolve(), ("manifest.json",)) or _read_public_json(pub_resolved, ("manifest.json",)) or {}

    if not isinstance(company, dict):
        company = {}
    if not isinstance(policy, dict):
        policy = {}
    if not isinstance(disk_manifest, dict):
        disk_manifest = {}

    tables: dict[str, tuple[dict[str, Any], ...]] = {}
    records_by_table_and_id: dict[str, dict[str, dict[str, Any]]] = {}
    documents_by_id: dict[str, dict[str, Any]] = {}

    permitted_fx_sources = set(
        policy.get("fx_policy", {}).get("source_codes", [])
        if isinstance(policy.get("fx_policy"), dict)
        else []
    )

    for table_name, (fnames, pk_fields, prefix) in _TABLE_LOAD_SPECS.items():
        rows = _read_public_rows(pub_resolved, fnames)
        # Preserve EXACT file row order (required for paired permutation checks P01..P05/P11..P20)
        tables[table_name] = tuple(rows)
        idx_map: dict[str, dict[str, Any]] = {}
        for row in rows:
            pk = _extract_pk(row, pk_fields)
            if pk is not None:
                idx_map[pk] = row
                if prefix and ":" not in pk:
                    idx_map[f"{prefix}:{pk}"] = row
                if table_name in ("invoices", "credit_notes", "payments"):
                    documents_by_id[pk] = row
                    if prefix and ":" not in pk:
                        documents_by_id[f"{prefix}:{pk}"] = row
            # Semantic FX key: date:source_currency:target_currency
            if table_name == "fx":
                eff = row.get("effective_date") or row.get("date")
                pair = row.get("pair")
                src_code = row.get("source_code")
                if isinstance(eff, str) and isinstance(pair, str) and "/" in pair:
                    src_cur, dst_cur = pair.split("/", 1)
                    sem_key = f"{eff}:{src_cur}:{dst_cur}"
                    # Prefer policy-permitted source if multiple sources exist on the same date
                    is_perm = isinstance(src_code, str) and src_code in permitted_fx_sources
                    if sem_key not in idx_map or is_perm:
                        idx_map[sem_key] = row
                        idx_map[f"FX:{sem_key}"] = row
                    if isinstance(src_code, str) and src_code:
                        idx_map[f"{sem_key}:{src_code}"] = row
                        idx_map[f"FX:{sem_key}:{src_code}"] = row
        records_by_table_and_id[table_name] = idx_map

    # Standard public metadata documents
    documents_by_id["company"] = copy.deepcopy(company)
    documents_by_id["policy"] = copy.deepcopy(policy)
    documents_by_id["accounts"] = {"accounts": list(tables["accounts"])}
    documents_by_id["opening_balances"] = {"opening_balances": list(tables["opening_balances"])}
    documents_by_id["period_calendar"] = {"period_calendar": list(tables["period_calendar"])}

    # Optional public/documents/ subfolder (read-only preload; never accessed via FS on step)
    docs_dir = pub_resolved / "documents"
    if docs_dir.is_dir():
        for entry in sorted(docs_dir.iterdir(), key=lambda p: p.name):
            if entry.name.startswith(".") or not entry.is_file():
                continue
            resolved = _safe_resolve_under(pub_resolved, entry)
            try:
                content: Any = json.loads(resolved.read_text(encoding="utf-8"))
                if not isinstance(content, dict):
                    content = {"doc_id": entry.stem, "content": content}
            except json.JSONDecodeError:
                content = {"doc_id": entry.stem, "text": resolved.read_text(encoding="utf-8")}
            documents_by_id[entry.stem] = content
            documents_by_id[entry.name] = content

    # Compute exact period boundaries from period_calendar or manifest
    cal_rows = tables["period_calendar"]
    start_dates = [str(r["start_date"]) for r in cal_rows if isinstance(r.get("start_date"), str)]
    end_dates = [str(r["end_date"]) for r in cal_rows if isinstance(r.get("end_date"), str)]
    period_start = min(start_dates) if start_dates else str(disk_manifest.get("period_start", company.get("fiscal_year_start", "2025-01-01")))
    period_end = max(end_dates) if end_dates else str(disk_manifest.get("period_end", "2025-12-31"))

    base_currency = str(company.get("functional_currency", disk_manifest.get("base_currency", "KZT")))
    supported_currencies = list(company.get("supported_currencies", [base_currency]))
    tz_name = str(company.get("timezone", disk_manifest.get("timezone", "UTC")))
    episode_id = str(disk_manifest.get("episode_id", company.get("company_id", "episode")))

    record_counts = {tbl: len(rows) for tbl, rows in tables.items()}
    doc_count = len(tables["invoices"]) + len(tables["credit_notes"])
    if docs_dir.is_dir():
        doc_count += sum(1 for e in docs_dir.iterdir() if e.is_file() and not e.name.startswith("."))

    rounding_rules = {
        "rounding_mode": str(policy.get("rounding_mode", "half_even")),
        "fx_policy": copy.deepcopy(policy.get("fx_policy", {})),
        "cutoff_policy": copy.deepcopy(policy.get("cutoff_policy", {})),
        "allocation_policy": copy.deepcopy(policy.get("allocation_policy", {})),
        "minor_unit_exponents": {
            cur: (exponent_of(cur) if cur in ("KZT", "USD", "EUR", "JPY", "KWD") else 2)
            for cur in supported_currencies
        },
        "amount_tolerance_minor": 0,
    }

    # Public manifest strictly conforming to C02/C03/C20 (zero seed/truth/provenance/paths)
    public_manifest: dict[str, Any] = {
        "schema_version": str(disk_manifest.get("schema_version", "1.0.0")),
        "episode_id": episode_id,
        "base_currency": base_currency,
        "functional_currency": base_currency,
        "supported_currencies": supported_currencies,
        "period_start": period_start,
        "period_end": period_end,
        "timezone": tz_name,
        "record_counts": record_counts,
        "total_records": sum(record_counts.values()),
        "document_count": doc_count,
        "rounding_rules": rounding_rules,
    }

    # Sanitized public policy (never contains private data)
    public_policy = copy.deepcopy(policy)
    public_policy.setdefault("max_steps", MAX_ACTIONS_DEFAULT)
    public_policy.setdefault("max_page_size", MAX_PAGE_SIZE_DEFAULT)
    public_policy["max_findings"] = MAX_FINDINGS_OFFICIAL
    public_policy["max_evidence_ids"] = MAX_EVIDENCE_IDS_OFFICIAL
    public_policy["max_explanation_codepoints"] = MAX_EXPLANATION_CODEPOINTS
    public_policy["amount_tolerance_minor"] = 0

    fp_hash = hashlib.sha256(
        json.dumps(
            {"episode_id": episode_id, "record_counts": record_counts},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    return OfficialPublicBook(
        episode_id=episode_id,
        manifest=public_manifest,
        policy=public_policy,
        company=copy.deepcopy(company),
        tables=tables,
        records_by_table_and_id=records_by_table_and_id,
        documents_by_id=documents_by_id,
        cursor_fingerprint=fp_hash,
    )


def _validate_submit_structure(payload: Any) -> tuple[bool, str | None]:
    """Check official submit structural constraints BEFORE deduplication.

    Does NOT access truth, accessible IDs, or any closed information — error
    codes strictly reflect schema/size violations only.
    """
    if isinstance(payload, Mapping):
        if "findings" not in payload:
            return False, "findings payload object must contain 'findings' list"
        raw_list = payload["findings"]
    elif isinstance(payload, list):
        raw_list = payload
    else:
        return False, "findings payload must be a JSON object or list"

    if not isinstance(raw_list, list):
        return False, "'findings' must be a list"
    if len(raw_list) > MAX_FINDINGS_OFFICIAL:
        return False, f"findings count exceeds limit {MAX_FINDINGS_OFFICIAL}"

    for idx, item in enumerate(raw_list):
        if not isinstance(item, Mapping):
            return False, f"findings[{idx}] must be an object"
        ftype = item.get("type")
        if not isinstance(ftype, str) or not ftype:
            return False, f"findings[{idx}].type must be a non-empty string"

        aff = item.get("affected_ids")
        if not isinstance(aff, list) or len(aff) < 1 or not all(isinstance(x, str) and x for x in aff):
            return False, f"findings[{idx}].affected_ids must be a non-empty list of strings"

        ev = item.get("evidence_ids")
        if not isinstance(ev, list) or len(ev) < 1 or not all(isinstance(x, str) and x for x in ev):
            return False, f"findings[{idx}].evidence_ids must be a non-empty list of strings"
        if len(ev) > MAX_EVIDENCE_IDS_OFFICIAL:
            return False, f"findings[{idx}].evidence_ids exceeds limit {MAX_EVIDENCE_IDS_OFFICIAL}"

        has_minor = "claimed_amount_minor" in item
        has_plain = "claimed_amount" in item
        if not has_minor and not has_plain:
            return False, f"findings[{idx}] missing claimed_amount_minor"
        amt = item["claimed_amount_minor"] if has_minor else item["claimed_amount"]
        if has_minor and has_plain and item["claimed_amount"] != amt:
            return False, f"findings[{idx}] conflicting amount fields"
        if type(amt) is not int or isinstance(amt, bool):
            return False, f"findings[{idx}].claimed_amount_minor must be an integer"

        cur = item.get("currency")
        if not isinstance(cur, str) or not cur:
            return False, f"findings[{idx}].currency must be a non-empty string"

        expl = item.get("explanation", "")
        if expl is not None:
            if not isinstance(expl, str):
                return False, f"findings[{idx}].explanation must be a string"
            if len(expl) > MAX_EXPLANATION_CODEPOINTS:
                return False, f"findings[{idx}].explanation exceeds {MAX_EXPLANATION_CODEPOINTS} characters"

    return True, None


class OfficialJudgeEnv:
    """Official Genesis FinTech environment implementing ``reset`` and ``step``."""

    def __init__(
        self,
        *,
        episode_generator_fn: Callable[[int, dict[str, Any], str], None] | None = None,
        train_reward_fn: Callable[[str, Any, int], float] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._episode_generator_fn = episode_generator_fn
        self._train_reward_fn = train_reward_fn
        self._clock: Callable[[], float] = clock if clock is not None else time.monotonic

        self._book: OfficialPublicBook | None = None
        self._cursors: CursorCodec | None = None
        self._mode: str = "closed"
        self._max_actions: int = MAX_ACTIONS_DEFAULT
        self._max_page_size: int = MAX_PAGE_SIZE_DEFAULT
        self._time_limit_s: float = TIME_LIMIT_SECONDS_DEFAULT
        self._reset_time: float = 0.0

        self._actions_used: int = 0
        self._inspection_steps: int = 0
        self._terminated: bool = False
        self._truncated: bool = False
        self._final_findings: Any = {"findings": []}
        self._submitted: bool = False
        self._active_episode_dir: str | None = None
        self._owned_temp_dir: str | None = None

    @property
    def inspection_steps(self) -> int:
        return self._inspection_steps

    @property
    def actions_used(self) -> int:
        return self._actions_used

    @property
    def terminated(self) -> bool:
        return self._terminated

    @property
    def truncated(self) -> bool:
        return self._truncated

    @property
    def final_findings(self) -> Any:
        """Final frozen findings payload for external judge scoring."""
        return copy.deepcopy(self._final_findings)

    def close(self) -> None:
        if self._owned_temp_dir is not None:
            shutil.rmtree(self._owned_temp_dir, ignore_errors=True)
            self._owned_temp_dir = None

    def reset(
        self,
        seed: int | None = None,
        config: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Reset environment for one episode and return ``(observation, info)``."""
        self.close()
        cfg = dict(config or {})
        mode = str(cfg.get("mode", "closed")).lower()
        if mode not in ("closed", "train"):
            raise ValueError(f"unsupported mode: {mode!r}; expected 'closed' or 'train'")
        team_cfg = dict(cfg.get("team_config") or {})
        episode_dir = cfg.get("episode_dir")

        if episode_dir is not None:
            resolved_dir = str(Path(episode_dir))
            self._owned_temp_dir = None
        else:
            if self._episode_generator_fn is None:
                raise ValueError("episode_dir is required when no episode generator is attached")
            tmp_dir = tempfile.mkdtemp(prefix="twinledger_ep_")
            self._owned_temp_dir = tmp_dir
            gen_seed = 0 if seed is None else int(seed)
            self._episode_generator_fn(gen_seed, team_cfg, tmp_dir)
            resolved_dir = tmp_dir

        book = load_official_public_book(resolved_dir)
        self._book = book
        self._mode = mode
        self._active_episode_dir = resolved_dir if mode == "train" else None
        self._max_actions = int(team_cfg.get("max_steps", MAX_ACTIONS_DEFAULT))
        self._max_page_size = min(MAX_PAGE_SIZE_DEFAULT, int(team_cfg.get("max_page_size", MAX_PAGE_SIZE_DEFAULT)))
        self._time_limit_s = float(team_cfg.get("time_limit_s", TIME_LIMIT_SECONDS_DEFAULT))

        # Deterministic per-episode cursor key derived ONLY from public book fingerprint (zero seed leak)
        cursor_key = hashlib.sha256(
            f"official-cursor|{book.cursor_fingerprint}".encode("utf-8")
        ).digest()
        self._cursors = CursorCodec(cursor_key)

        self._actions_used = 0
        self._inspection_steps = 0
        self._terminated = False
        self._truncated = False
        self._submitted = False
        self._final_findings = {"findings": []}
        self._reset_time = self._clock()

        obs: dict[str, Any] = {
            "task": TASK_DESCRIPTION,
            "manifest": copy.deepcopy(book.manifest),
            "policy": copy.deepcopy(book.policy),
            "remaining_steps": self._max_actions,
        }
        info: dict[str, Any] = {
            "mode": self._mode,
            "step": 0,
            "tables": list(CANONICAL_TABLES),
        }
        return obs, info

    def _compute_terminal_reward(self) -> int | float:
        if self._mode == "closed":
            return 0
        if self._train_reward_fn is not None and self._active_episode_dir is not None:
            return float(
                self._train_reward_fn(
                    self._active_episode_dir,
                    self._final_findings,
                    self._inspection_steps,
                )
            )
        return 0

    def step(
        self,
        action: dict[str, Any],
    ) -> tuple[dict[str, Any], int | float, bool, bool, dict[str, Any]]:
        """Execute one action envelope ``{"name": ..., "args": ...}``."""
        if self._book is None or self._cursors is None:
            obs = {
                "result": None,
                "error": {"code": "NOT_RESET", "message": "environment must be reset before step"},
                "remaining_steps": 0,
            }
            return obs, 0, False, False, {"mode": self._mode}

        remaining_before = max(0, self._max_actions - self._actions_used)

        # Already ended (C15 / C17): freeze final findings and metrics forever
        if self._terminated or self._truncated:
            obs = {
                "result": None,
                "error": {"code": "ALREADY_TERMINATED", "message": "episode has already ended"},
                "remaining_steps": remaining_before,
            }
            return obs, 0, self._terminated, self._truncated, {
                "mode": self._mode,
                "step": self._actions_used,
            }

        # Wall-clock 60s timeout check (C18)
        elapsed = self._clock() - self._reset_time
        if elapsed >= self._time_limit_s:
            self._truncated = True
            self._final_findings = {"findings": []}
            reward = self._compute_terminal_reward()
            obs = {
                "result": None,
                "error": {"code": "TIME_LIMIT", "message": "episode time limit exceeded"},
                "remaining_steps": remaining_before,
            }
            return obs, reward, False, True, {
                "mode": self._mode,
                "step": self._actions_used,
            }

        # Validate outer action envelope
        if not isinstance(action, Mapping):
            return self._finish_inspection_error("BAD_ACTION", "action must be a JSON object")

        name = action.get("name")
        args = action.get("args", {})
        if not isinstance(name, str) or not name:
            return self._finish_inspection_error("BAD_ACTION", "action.name must be a non-empty string")
        if args is None:
            args = {}
        if not isinstance(args, Mapping):
            return self._finish_inspection_error("BAD_ARGS", "action.args must be a JSON object")

        # Handle submit (counts toward the 100-action limit, NOT toward inspection_steps — C16)
        if name == "submit":
            self._actions_used += 1
            remaining = max(0, self._max_actions - self._actions_used)
            if "findings" not in args:
                self._final_findings = None
                self._submitted = True
                self._terminated = True
                reward = self._compute_terminal_reward()
                obs = {
                    "result": None,
                    "error": {"code": "INVALID_SUBMIT", "message": "submit requires 'findings' argument"},
                    "remaining_steps": remaining,
                }
                return obs, reward, True, False, {
                    "mode": self._mode,
                    "step": self._actions_used,
                }

            payload = args["findings"]
            ok, err_msg = _validate_submit_structure(payload)
            self._submitted = True
            self._terminated = True
            self._final_findings = copy.deepcopy(payload)
            reward = self._compute_terminal_reward()
            if ok:
                obs = {
                    "result": {"accepted": True},
                    "error": None,
                    "remaining_steps": remaining,
                }
            else:
                obs = {
                    "result": None,
                    "error": {"code": "INVALID_SUBMIT", "message": err_msg or "invalid submit payload"},
                    "remaining_steps": remaining,
                }
            return obs, reward, True, False, {
                "mode": self._mode,
                "step": self._actions_used,
            }

        # Non-submit action: consumes 1 action AND 1 inspection step (even on error — C11..C14)
        if name not in ("list_records", "get_record", "get_document", "calculator"):
            return self._finish_inspection_error("UNKNOWN_ACTION", f"unknown action: {name}")

        try:
            if name == "list_records":
                result: Any = self._handle_list_records(args)
            elif name == "get_record":
                result = self._handle_get_record(args)
            elif name == "get_document":
                result = self._handle_get_document(args)
            elif name == "calculator":
                result = self._handle_calculator(args)
            else:
                raise EnvError("UNKNOWN_ACTION", f"unknown action: {name}")
        except EnvError as exc:
            return self._finish_inspection_error(exc.code, exc.message)

        self._actions_used += 1
        self._inspection_steps += 1
        remaining = max(0, self._max_actions - self._actions_used)
        truncated = self._actions_used >= self._max_actions
        if truncated:
            self._truncated = True
            self._final_findings = {"findings": []}
            reward = self._compute_terminal_reward()
        else:
            reward = 0

        obs = {
            "result": result,
            "error": None,
            "remaining_steps": remaining,
        }
        return obs, reward, False, truncated, {
            "mode": self._mode,
            "step": self._actions_used,
        }

    def _finish_inspection_error(
        self, code: str, message: str
    ) -> tuple[dict[str, Any], int | float, bool, bool, dict[str, Any]]:
        self._actions_used += 1
        self._inspection_steps += 1
        remaining = max(0, self._max_actions - self._actions_used)
        truncated = self._actions_used >= self._max_actions
        if truncated:
            self._truncated = True
            self._final_findings = {"findings": []}
            reward = self._compute_terminal_reward()
        else:
            reward = 0
        obs = {
            "result": None,
            "error": {"code": code, "message": message},
            "remaining_steps": remaining,
        }
        return obs, reward, False, truncated, {
            "mode": self._mode,
            "step": self._actions_used,
        }

    def _resolve_table(self, raw_table: Any) -> str:
        if not isinstance(raw_table, str) or raw_table not in TABLE_ALIASES:
            raise EnvError("BAD_ARGS", "unknown table")
        return TABLE_ALIASES[raw_table]

    def _handle_list_records(self, args: Mapping[str, Any]) -> dict[str, Any]:
        assert self._book is not None and self._cursors is not None
        table = self._resolve_table(args.get("table"))
        limit = args.get("limit", self._max_page_size)
        if limit is None:
            limit = self._max_page_size
        if type(limit) is not int or isinstance(limit, bool) or not 1 <= limit <= self._max_page_size:
            raise EnvError("BAD_ARGS", f"limit must be an integer in 1..{self._max_page_size}")

        cursor = args.get("cursor")
        if cursor is not None and not isinstance(cursor, str):
            raise EnvError("BAD_CURSOR", "cursor must be null or string")
        offset = 0 if cursor is None else self._cursors.decode(cursor, table, {})

        rows = self._book.tables[table]
        page = [copy.deepcopy(r) for r in rows[offset : offset + limit]]
        next_offset = offset + len(page)
        next_cursor = (
            self._cursors.encode(table, {}, next_offset)
            if next_offset < len(rows)
            else None
        )
        return {
            "records": page,
            "next_cursor": next_cursor,
        }

    def _handle_get_record(self, args: Mapping[str, Any]) -> dict[str, Any]:
        assert self._book is not None
        table = self._resolve_table(args.get("table"))
        rec_id = args.get("id")
        if not isinstance(rec_id, str) or not rec_id:
            raise EnvError("BAD_ARGS", "get_record requires non-empty string 'id'")
        row = self._book.records_by_table_and_id[table].get(rec_id)
        if row is None:
            raise EnvError("NOT_FOUND", "record not found")
        return copy.deepcopy(row)

    def _handle_get_document(self, args: Mapping[str, Any]) -> dict[str, Any]:
        assert self._book is not None
        doc_id = args.get("doc_id") if "doc_id" in args else args.get("id")
        if not isinstance(doc_id, str) or not doc_id:
            raise EnvError("BAD_ARGS", "get_document requires non-empty string 'doc_id'")
        doc = self._book.documents_by_id.get(doc_id)
        if doc is None:
            raise EnvError("NOT_FOUND", "document not found")
        return copy.deepcopy(doc)

    def _handle_calculator(self, args: Mapping[str, Any]) -> str:
        res = evaluate_calc(args.get("expression"))
        return res["result"]


__all__ = [
    "CANONICAL_TABLES",
    "MAX_ACTIONS_DEFAULT",
    "MAX_EVIDENCE_IDS_OFFICIAL",
    "MAX_EXPLANATION_CODEPOINTS",
    "MAX_FINDINGS_OFFICIAL",
    "MAX_PAGE_SIZE_DEFAULT",
    "OfficialJudgeEnv",
    "OfficialPublicBook",
    "TABLE_ALIASES",
    "TIME_LIMIT_SECONDS_DEFAULT",
    "load_official_public_book",
]
