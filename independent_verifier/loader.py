"""Independent public-episode loader (spec §1.1–§1.3).

Reads ONLY the allowlisted public files of an episode directory, never hidden
files, never anything outside ``public/``. Typed IDs and the public hash are
derived per the spec. No generator, scoring, or environment imports.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ALLOWED_PUBLIC_FILES: tuple[str, ...] = (
    "company.json",
    "policy.json",
    "accounts.json",
    "counterparties.jsonl",
    "journal_entries.jsonl",
    "invoices.jsonl",
    "credit_notes.jsonl",
    "payments.jsonl",
    "bank_lines.jsonl",
    "fx_rates.jsonl",
    "opening_balances.json",
    "period_calendar.json",
    "document_links.jsonl",
)
REQUIRED_PUBLIC_FILES: tuple[str, ...] = ("company.json", "policy.json")
FORBIDDEN_PUBLIC_FILES: tuple[str, ...] = ("index_hints.json",)


class PublicDataError(ValueError):
    """Public episode is malformed or violates the boundary rules."""


@dataclass
class PublicData:
    root: Path
    company: dict[str, Any]
    policy: dict[str, Any]
    accounts: list[dict[str, Any]]
    counterparties: list[dict[str, Any]]
    journal_entries: list[dict[str, Any]]
    invoices: list[dict[str, Any]]
    credit_notes: list[dict[str, Any]]
    payments: list[dict[str, Any]]
    bank_lines: list[dict[str, Any]]
    fx_rates: list[dict[str, Any]]
    opening_balances: list[dict[str, Any]]
    period_calendar: list[dict[str, Any]]
    document_links: list[dict[str, Any]]
    examined_public_sources: list[str]
    episode_public_hash: str
    typed_ids: dict[str, str] = field(default_factory=dict)  # typed id -> "<file>:<index>"

    # -- typed-id helpers ------------------------------------------------
    def typed_id(self, kind: str, raw_id: str) -> str:
        return f"{kind}:{raw_id}"

    def payment_id(self, p: dict) -> str:
        return f"PAY:{p['pay_id']}"

    def invoice_id(self, inv: dict) -> str:
        return f"INV:{inv['doc_id']}"

    def credit_note_id(self, cn: dict) -> str:
        return f"CN:{cn['credit_note_id']}"

    def je_id(self, je: dict) -> str:
        return f"JE:{je['je_id']}"

    def bank_id(self, b: dict) -> str:
        return f"BANK:{b['bank_line_id']}"

    def counterparty_id(self, cp: dict) -> str:
        return f"CP:{cp['counterparty_id']}"

    def fx_row_id(self, row: dict) -> str:
        if row.get("fx_id") or row.get("rate_id"):
            return f"FX:{row.get('fx_id') or row.get('rate_id')}"
        return f"FX:{row.get('pair')}/{row.get('effective_date')}/{row.get('source_code')}"

    def all_typed_ids(self) -> set[str]:
        out: set[str] = set()
        out.update(self.payment_id(p) for p in self.payments)
        out.update(self.invoice_id(i) for i in self.invoices)
        out.update(self.credit_note_id(c) for c in self.credit_notes)
        out.update(self.je_id(j) for j in self.journal_entries)
        out.update(self.bank_id(b) for b in self.bank_lines)
        out.update(self.counterparty_id(c) for c in self.counterparties)
        out.update(self.fx_row_id(r) for r in self.fx_rates)
        return out


def _read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PublicDataError(f"{path.name} is not valid JSON") from exc


def _read_jsonl_file(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PublicDataError(f"{path.name}:{lineno} is not valid JSON") from exc
        if not isinstance(row, dict):
            raise PublicDataError(f"{path.name}:{lineno} must be a JSON object")
        rows.append(row)
    return rows


def _load_allowlisted(public_dir: Path) -> tuple[dict[str, Any], list[str]]:
    """Parse every allowlisted file present. Returns (raw, examined filenames)."""
    resolved_root = public_dir.resolve()
    raw: dict[str, Any] = {}
    examined: list[str] = []
    for name in sorted(ALLOWED_PUBLIC_FILES):
        candidate = public_dir / name
        if candidate.name in FORBIDDEN_PUBLIC_FILES:
            raise PublicDataError(f"{candidate.name} is forbidden in public/")
        if not candidate.exists():
            if name in REQUIRED_PUBLIC_FILES:
                raise PublicDataError(f"required public file {name} is missing")
            continue
        if candidate.is_symlink():
            target = candidate.resolve()
            if resolved_root not in target.parents and target != resolved_root:
                raise PublicDataError(f"{name} is a symlink escaping public/")
        if not candidate.is_file():
            raise PublicDataError(f"{name} is not a regular file")
        examined.append(name)
        if name.endswith(".jsonl"):
            raw[name] = _read_jsonl_file(candidate)
        else:
            raw[name] = _read_json_file(candidate)
    # Hidden or non-allowlisted files are rejected outright.
    for child in public_dir.iterdir():
        if child.name.startswith("."):
            raise PublicDataError(f"hidden file {child.name!r} in public/")
        if child.name not in ALLOWED_PUBLIC_FILES:
            raise PublicDataError(f"non-allowlisted file {child.name!r} in public/")
    return raw, examined


def _canonical_hash(parsed: dict[str, Any], examined: list[str]) -> str:
    from contracts.canonical import canonical_bytes

    mapping = {name: parsed[name] for name in sorted(examined)}
    return hashlib.sha256(canonical_bytes(mapping)).hexdigest()


def load_public_dir(public_dir: str | Path) -> PublicData:
    """Load an on-disk episode ``public/`` directory into typed records."""
    public_path = Path(public_dir)
    if not public_path.is_dir():
        raise PublicDataError("public/ directory not found")
    raw, examined = _load_allowlisted(public_path)

    def as_list(name: str) -> list[dict[str, Any]]:
        value = raw.get(name, [])
        if value is None:
            return []
        if not isinstance(value, list):
            raise PublicDataError(f"{name} must be a JSON array")
        return value

    company = raw.get("company.json")
    policy = raw.get("policy.json")
    if not isinstance(company, dict) or not isinstance(policy, dict):
        raise PublicDataError("company.json and policy.json must be JSON objects")

    data = PublicData(
        root=public_path,
        company=company,
        policy=policy,
        accounts=as_list("accounts.json"),
        counterparties=as_list("counterparties.jsonl"),
        journal_entries=as_list("journal_entries.jsonl"),
        invoices=as_list("invoices.jsonl"),
        credit_notes=as_list("credit_notes.jsonl"),
        payments=as_list("payments.jsonl"),
        bank_lines=as_list("bank_lines.jsonl"),
        fx_rates=as_list("fx_rates.jsonl"),
        opening_balances=as_list("opening_balances.json"),
        period_calendar=as_list("period_calendar.json"),
        document_links=as_list("document_links.jsonl"),
        examined_public_sources=sorted(examined),
        episode_public_hash=_canonical_hash(raw, examined),
    )
    return data


def subset_public_data(data: PublicData, keep: set[str]) -> PublicData:
    """Public view containing ONLY subject records whose typed id ∈ ``keep``.

    Background context (company, policy, accounts, opening_balances,
    period_calendar) is always present, per spec §5. ``document_links`` are
    dropped (they are not evidence records); counterparties and bank_lines are
    filtered by their typed ids like everything else.
    """

    def filt(rows, id_fn):
        return [r for r in rows if id_fn(r) in keep]

    return PublicData(
        root=data.root,
        company=data.company,
        policy=data.policy,
        accounts=data.accounts,
        counterparties=filt(data.counterparties, data.counterparty_id),
        journal_entries=filt(data.journal_entries, data.je_id),
        invoices=filt(data.invoices, data.invoice_id),
        credit_notes=filt(data.credit_notes, data.credit_note_id),
        payments=filt(data.payments, data.payment_id),
        bank_lines=filt(data.bank_lines, data.bank_id),
        fx_rates=filt(data.fx_rates, data.fx_row_id),
        opening_balances=data.opening_balances,
        period_calendar=data.period_calendar,
        document_links=[],
        examined_public_sources=list(data.examined_public_sources),
        episode_public_hash=data.episode_public_hash,
    )
