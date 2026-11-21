"""Public-only allowlisted episode loader for the TwinLedger environment.

Reads ONLY the 12 allowlisted public files inside ``public/``. Rejects hidden
dotfiles, ``index_hints.json``, unrecognised files, and symlinks escaping the
public directory boundary (REQ-ARC-002, REQ-ENV-001).

Row order contract (README "Canonical Tables"): **file row order is preserved
verbatim on load** — pagination cursors page over records exactly as stored,
which is what the paired permutation checks (``P01..P05``, ``P11..P20``)
require. All reads are bounded by ``contracts.loader`` byte/row caps so an
oversized or hostile episode file can never exhaust memory (D-10-03).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from contracts.loader import check_row_cap, read_text_bounded, validate_instance
from env.errors import EnvError

PUBLIC_JSON_FILES = frozenset(
    {
        "company.json",
        "policy.json",
        "accounts.json",
        "opening_balances.json",
        "period_calendar.json",
    }
)

PUBLIC_JSONL_FILES = frozenset(
    {
        "counterparties.jsonl",
        "fx_rates.jsonl",
        "invoices.jsonl",
        "payments.jsonl",
        "credit_notes.jsonl",
        "bank_lines.jsonl",
        "journal_entries.jsonl",
    }
)

ALLOWED_PUBLIC_FILES = PUBLIC_JSON_FILES | PUBLIC_JSONL_FILES

TABLE_SPECS: dict[str, tuple[str, str]] = {
    # table_name -> (primary_key_field, typed_id_prefix_or_empty)
    "accounts": ("account_id", ""),
    "opening_balances": ("account_id", ""),
    "period_calendar": ("period_id", ""),
    "counterparties": ("counterparty_id", "CP"),
    "fx_rates": ("fx_id", "FX"),
    "invoices": ("doc_id", "INV"),
    "payments": ("pay_id", "PAY"),
    "credit_notes": ("credit_note_id", "CN"),
    "bank_lines": ("bank_line_id", "BANK"),
    "journal_entries": ("je_id", "JE"),
}

PREFIX_TO_TABLE: dict[str, str] = {
    prefix: table for table, (_, prefix) in TABLE_SPECS.items() if prefix
}


@dataclass(frozen=True)
class LoadedPublicBook:
    """Immutable public accounting book indexed for read-only tool queries."""

    public_dir: Path
    company: dict[str, Any]
    policy: dict[str, Any]
    tables: dict[str, tuple[dict[str, Any], ...]]
    records_by_typed_id: dict[str, tuple[str, dict[str, Any]]]
    documents_by_id: dict[str, dict[str, Any]]


def _assert_inside_public(root_resolved: Path, entry: Path) -> Path:
    if entry.name.startswith("."):
        raise EnvError("BAD_ARGS", f"hidden entry forbidden in public directory: {entry.name}")
    if entry.name == "index_hints.json":
        raise EnvError("BAD_ARGS", "index_hints.json is forbidden in public directory")
    if entry.name not in ALLOWED_PUBLIC_FILES:
        raise EnvError("BAD_ARGS", f"non-allowlisted entry in public directory: {entry.name}")
    resolved = entry.resolve()
    if not resolved.is_relative_to(root_resolved):
        raise EnvError("BAD_ARGS", f"symlink escapes public directory boundary: {entry.name}")
    if not resolved.is_file():
        raise EnvError("BAD_ARGS", f"expected regular file: {entry.name}")
    return resolved


def _read_json(path: Path) -> Any:
    try:
        return json.loads(read_text_bounded(path))
    except json.JSONDecodeError as exc:
        raise EnvError("INTERNAL", f"failed reading {path.name}: {exc}") from exc
    except OSError as exc:
        raise EnvError("INTERNAL", f"failed reading {path.name}: {exc}") from exc
    except ValueError as exc:
        raise EnvError("LIMIT", f"failed reading {path.name}: {exc}") from exc


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        text = read_text_bounded(path)
    except OSError as exc:
        raise EnvError("INTERNAL", f"failed reading {path.name}: {exc}") from exc
    except ValueError as exc:
        raise EnvError("LIMIT", f"failed reading {path.name}: {exc}") from exc
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EnvError("INTERNAL", f"{path.name}:{lineno} invalid JSON: {exc}") from exc
        if not isinstance(item, dict):
            raise EnvError("INTERNAL", f"{path.name}:{lineno} expected JSON object")
        rows.append(item)
        try:
            check_row_cap(len(rows), path.name)
        except ValueError as exc:
            raise EnvError("LIMIT", str(exc)) from exc
    return rows


def load_public_book(public_dir: Path | str) -> LoadedPublicBook:
    """Strictly load and index an episode's ``public/`` directory."""
    root = Path(public_dir)
    if not root.is_dir():
        raise EnvError("NOT_FOUND", f"public directory does not exist: {root}")
    root_resolved = root.resolve()

    present: dict[str, Path] = {}
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        present[entry.name] = _assert_inside_public(root_resolved, entry)

    for required in ("company.json", "policy.json", "accounts.json"):
        if required not in present:
            raise EnvError("BAD_ARGS", f"missing required public file: {required}")

    company = _read_json(present["company.json"])
    policy = _read_json(present["policy.json"])
    c_errs = validate_instance("company", company)
    if c_errs:
        raise EnvError("BAD_ARGS", f"invalid company.json: {c_errs[0]}")
    p_errs = validate_instance("policy", policy)
    if p_errs:
        raise EnvError("BAD_ARGS", f"invalid policy.json: {p_errs[0]}")

    raw_tables: dict[str, list[dict[str, Any]]] = {
        "accounts": _read_json(present["accounts.json"]),
        "opening_balances": _read_json(present["opening_balances.json"]) if "opening_balances.json" in present else [],
        "period_calendar": _read_json(present["period_calendar.json"]) if "period_calendar.json" in present else [],
        "counterparties": _read_jsonl(present["counterparties.jsonl"]) if "counterparties.jsonl" in present else [],
        "fx_rates": _read_jsonl(present["fx_rates.jsonl"]) if "fx_rates.jsonl" in present else [],
        "invoices": _read_jsonl(present["invoices.jsonl"]) if "invoices.jsonl" in present else [],
        "payments": _read_jsonl(present["payments.jsonl"]) if "payments.jsonl" in present else [],
        "credit_notes": _read_jsonl(present["credit_notes.jsonl"]) if "credit_notes.jsonl" in present else [],
        "bank_lines": _read_jsonl(present["bank_lines.jsonl"]) if "bank_lines.jsonl" in present else [],
        "journal_entries": _read_jsonl(present["journal_entries.jsonl"]) if "journal_entries.jsonl" in present else [],
    }

    tables: dict[str, tuple[dict[str, Any], ...]] = {}
    records_by_typed_id: dict[str, tuple[str, dict[str, Any]]] = {}
    documents_by_id: dict[str, dict[str, Any]] = {
        "company": company,
        "policy": policy,
        "accounts": {"accounts": raw_tables["accounts"]},
        "opening_balances": {"opening_balances": raw_tables["opening_balances"]},
        "period_calendar": {"period_calendar": raw_tables["period_calendar"]},
    }

    for table_name, (pk_field, prefix) in TABLE_SPECS.items():
        rows = raw_tables[table_name]
        if not isinstance(rows, list):
            raise EnvError("BAD_ARGS", f"table {table_name} must be a list")
        # File row order is preserved verbatim (README "Canonical Tables"):
        # never re-sort here — pagination cursors must page over records
        # exactly as stored (paired permutation checks P01..P05, P11..P20).
        tables[table_name] = tuple(rows)
        if prefix:
            for row in rows:
                raw_id = str(row.get(pk_field, ""))
                if not raw_id:
                    continue
                tid = f"{prefix}:{raw_id}"
                records_by_typed_id[tid] = (table_name, row)
                if prefix in ("INV", "CN"):
                    documents_by_id[tid] = row

    return LoadedPublicBook(
        public_dir=root_resolved,
        company=company,
        policy=policy,
        tables=tables,
        records_by_typed_id=records_by_typed_id,
        documents_by_id=documents_by_id,
    )


__all__ = [
    "ALLOWED_PUBLIC_FILES",
    "LoadedPublicBook",
    "PREFIX_TO_TABLE",
    "TABLE_SPECS",
    "load_public_book",
]
