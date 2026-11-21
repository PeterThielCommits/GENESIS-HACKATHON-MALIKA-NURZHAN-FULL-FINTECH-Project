"""Public-only episode loader for the independent verifier (Zone 3).

Loads ONLY allowlisted public accounting tables from a public episode
directory or in-memory mapping, validates company and policy against the
frozen contracts, rejects hidden files, symlinks escaping the public root,
and forbidden hint files, and computes a deterministic canonical
``episode_public_hash``.

Dependencies: ``contracts`` + Python 3.11 stdlib only.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from contracts.canonical import canonicalize, sha256_hex
from contracts.loader import check_row_cap, read_text_bounded, validate_instance

#: Allowlisted public filenames (Master TZ section 8.2).
REQUIRED_PUBLIC_FILES: tuple[str, ...] = (
    "company.json",
    "policy.json",
)

JSON_OBJECT_OR_LIST_FILES: tuple[str, ...] = (
    "company.json",
    "policy.json",
    "accounts.json",
    "opening_balances.json",
    "period_calendar.json",
)

JSONL_TABLE_FILES: tuple[str, ...] = (
    "counterparties.jsonl",
    "journal_entries.jsonl",
    "invoices.jsonl",
    "credit_notes.jsonl",
    "payments.jsonl",
    "bank_lines.jsonl",
    "fx_rates.jsonl",
    "document_links.jsonl",
)

ALLOWED_PUBLIC_FILES: frozenset[str] = frozenset(
    JSON_OBJECT_OR_LIST_FILES + JSONL_TABLE_FILES
)

#: Explicitly forbidden files inside a public episode directory (TZ 8.2).
FORBIDDEN_PUBLIC_FILES: frozenset[str] = frozenset(
    {"index_hints.json"}
)

_TYPED_ID_RE = re.compile(r"^(JE|INV|CN|PAY|BANK|FX|CP):([A-Za-z0-9._/-]+)$")
_LOCAL_ID_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


class PublicEpisodeError(ValueError):
    """Raised when public episode inputs violate boundaries or contracts."""


def make_typed_id(namespace: str, raw_id: str) -> str:
    """Build a canonical typed ID ``<NAMESPACE>:<local>`` (NFC-normalised)."""
    if not isinstance(raw_id, str) or not raw_id:
        raise PublicEpisodeError(f"{namespace} record has missing/non-string ID: {raw_id!r}")
    norm = unicodedata.normalize("NFC", raw_id)
    prefix = f"{namespace}:"
    if norm.startswith(prefix):
        local = norm[len(prefix):]
    else:
        local = norm
    if not _LOCAL_ID_RE.fullmatch(local):
        raise PublicEpisodeError(
            f"invalid {namespace} local ID {raw_id!r}: must match [A-Za-z0-9._/-]+"
        )
    typed = f"{namespace}:{local}"
    if _TYPED_ID_RE.fullmatch(typed) is None:
        raise PublicEpisodeError(f"invalid typed ID {typed!r}")
    return typed


def fx_row_raw_id(row: Mapping[str, Any]) -> str:
    """Return the canonical local identifier for an FX rate row."""
    explicit = row.get("fx_id") or row.get("rate_id")
    if isinstance(explicit, str) and explicit:
        return explicit
    pair = str(row.get("pair", ""))
    effective_date = str(row.get("effective_date", ""))
    source_code = str(row.get("source_code", ""))
    return f"{pair}/{effective_date}/{source_code}"


def fx_row_typed_id(row: Mapping[str, Any]) -> str:
    """Return the typed ID ``FX:<local>`` for an FX rate row."""
    return make_typed_id("FX", fx_row_raw_id(row))


def _parse_jsonl(text: str, source_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PublicEpisodeError(
                f"{source_name}:{lineno}: malformed JSONL ({exc})"
            ) from exc
        if not isinstance(parsed, dict):
            raise PublicEpisodeError(
                f"{source_name}:{lineno}: JSONL record must be a JSON object"
            )
        rows.append(parsed)
        try:
            check_row_cap(len(rows), source_name)
        except ValueError as exc:
            raise PublicEpisodeError(str(exc)) from exc
    return rows


def _parse_json(text: str, source_name: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise PublicEpisodeError(f"{source_name}: malformed JSON ({exc})") from exc


def _normalize_records(records: Iterable[Mapping[str, Any]], pk_field: str | None = None) -> tuple[dict[str, Any], ...]:
    out = [canonicalize(dict(r)) for r in records]
    if pk_field is not None:
        seen: set[str] = set()
        for r in out:
            pk = r.get(pk_field)
            if not isinstance(pk, str) or not pk:
                raise PublicEpisodeError(f"missing or invalid primary key {pk_field!r}")
            if pk in seen:
                raise PublicEpisodeError(f"duplicate primary key {pk_field}={pk!r}")
            seen.add(pk)
    return tuple(out)


@dataclass(frozen=True)
class PublicEpisode:
    """Immutable in-memory representation of a public accounting episode.

    Contains ONLY public records and metadata. Provides deterministic
    indexes built strictly from public tables.
    """

    company: dict[str, Any]
    policy: dict[str, Any]
    accounts: tuple[dict[str, Any], ...] = ()
    counterparties: tuple[dict[str, Any], ...] = ()
    journal_entries: tuple[dict[str, Any], ...] = ()
    invoices: tuple[dict[str, Any], ...] = ()
    credit_notes: tuple[dict[str, Any], ...] = ()
    payments: tuple[dict[str, Any], ...] = ()
    bank_lines: tuple[dict[str, Any], ...] = ()
    fx_rates: tuple[dict[str, Any], ...] = ()
    opening_balances: Any = field(default_factory=list)
    period_calendar: Any = field(default_factory=list)
    document_links: tuple[dict[str, Any], ...] = ()
    examined_public_sources: tuple[str, ...] = ()
    episode_public_hash: str = ""

    @property
    def accounts_by_id(self) -> dict[str, dict[str, Any]]:
        return {
            str(acc["account_id"]): acc
            for acc in self.accounts
            if isinstance(acc, dict) and "account_id" in acc
        }

    @property
    def invoices_by_id(self) -> dict[str, dict[str, Any]]:
        return {str(inv["doc_id"]): inv for inv in self.invoices}

    @property
    def payments_by_id(self) -> dict[str, dict[str, Any]]:
        return {str(pay["pay_id"]): pay for pay in self.payments}

    @property
    def credit_notes_by_id(self) -> dict[str, dict[str, Any]]:
        return {str(cn["credit_note_id"]): cn for cn in self.credit_notes}

    @property
    def journal_entries_by_id(self) -> dict[str, dict[str, Any]]:
        return {str(je["je_id"]): je for je in self.journal_entries}

    @property
    def bank_lines_by_id(self) -> dict[str, dict[str, Any]]:
        return {str(bl["bank_line_id"]): bl for bl in self.bank_lines}

    @property
    def counterparties_by_id(self) -> dict[str, dict[str, Any]]:
        return {str(cp["counterparty_id"]): cp for cp in self.counterparties}

    @property
    def fx_rates_by_typed_id(self) -> dict[str, dict[str, Any]]:
        return {fx_row_typed_id(row): row for row in self.fx_rates}

    def all_reachable_typed_ids(self) -> frozenset[str]:
        """Return every subject record typed ID reachable via public tools."""
        ids: set[str] = set()
        for je in self.journal_entries:
            ids.add(make_typed_id("JE", str(je["je_id"])))
        for inv in self.invoices:
            ids.add(make_typed_id("INV", str(inv["doc_id"])))
        for cn in self.credit_notes:
            ids.add(make_typed_id("CN", str(cn["credit_note_id"])))
        for pay in self.payments:
            ids.add(make_typed_id("PAY", str(pay["pay_id"])))
        for bl in self.bank_lines:
            ids.add(make_typed_id("BANK", str(bl["bank_line_id"])))
        for row in self.fx_rates:
            ids.add(fx_row_typed_id(row))
        for cp in self.counterparties:
            ids.add(make_typed_id("CP", str(cp["counterparty_id"])))
        return frozenset(ids)


def _compute_public_hash(sources_payload: Mapping[str, Any]) -> str:
    """Compute canonical SHA-256 over the sorted public file payload."""
    canonical_map = {k: canonicalize(sources_payload[k]) for k in sorted(sources_payload)}
    return sha256_hex(canonical_map)


def build_public_episode(
    company: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    accounts: Iterable[Mapping[str, Any]] = (),
    counterparties: Iterable[Mapping[str, Any]] = (),
    journal_entries: Iterable[Mapping[str, Any]] = (),
    invoices: Iterable[Mapping[str, Any]] = (),
    credit_notes: Iterable[Mapping[str, Any]] = (),
    payments: Iterable[Mapping[str, Any]] = (),
    bank_lines: Iterable[Mapping[str, Any]] = (),
    fx_rates: Iterable[Mapping[str, Any]] = (),
    opening_balances: Any = None,
    period_calendar: Any = None,
    document_links: Iterable[Mapping[str, Any]] = (),
    examined_public_sources: Iterable[str] | None = None,
) -> PublicEpisode:
    """Construct and validate an in-memory :class:`PublicEpisode`."""
    company_d = canonicalize(dict(company))
    policy_d = canonicalize(dict(policy))

    comp_errors = validate_instance("company", company_d)
    if comp_errors:
        raise PublicEpisodeError(f"invalid company.json: {'; '.join(comp_errors)}")
    pol_errors = validate_instance("policy", policy_d)
    if pol_errors:
        raise PublicEpisodeError(f"invalid policy.json: {'; '.join(pol_errors)}")

    accounts_t = tuple(canonicalize(dict(a)) for a in accounts)
    counterparties_t = _normalize_records(counterparties, "counterparty_id")
    journal_entries_t = _normalize_records(journal_entries, "je_id")
    invoices_t = _normalize_records(invoices, "doc_id")
    credit_notes_t = _normalize_records(credit_notes, "credit_note_id")
    payments_t = _normalize_records(payments, "pay_id")
    bank_lines_t = _normalize_records(bank_lines, "bank_line_id")
    fx_rates_t = tuple(canonicalize(dict(r)) for r in fx_rates)
    # Verify FX typed IDs are unique
    seen_fx: set[str] = set()
    for row in fx_rates_t:
        tid = fx_row_typed_id(row)
        if tid in seen_fx:
            raise PublicEpisodeError(f"duplicate FX rate identifier {tid!r}")
        seen_fx.add(tid)

    opening_b = canonicalize([] if opening_balances is None else opening_balances)
    period_cal = canonicalize([] if period_calendar is None else period_calendar)
    doc_links_t = tuple(canonicalize(dict(d)) for d in document_links)

    table_map: dict[str, Any] = {
        "company.json": company_d,
        "policy.json": policy_d,
        "accounts.json": list(accounts_t),
        "counterparties.jsonl": list(counterparties_t),
        "journal_entries.jsonl": list(journal_entries_t),
        "invoices.jsonl": list(invoices_t),
        "credit_notes.jsonl": list(credit_notes_t),
        "payments.jsonl": list(payments_t),
        "bank_lines.jsonl": list(bank_lines_t),
        "fx_rates.jsonl": list(fx_rates_t),
        "opening_balances.json": opening_b,
        "period_calendar.json": period_cal,
        "document_links.jsonl": list(doc_links_t),
    }

    if examined_public_sources is not None:
        sources = tuple(sorted(set(examined_public_sources)))
        for s in sources:
            if s not in ALLOWED_PUBLIC_FILES:
                raise PublicEpisodeError(f"non-public source {s!r} is forbidden")
    else:
        sources = tuple(
            sorted(
                name
                for name, val in table_map.items()
                if name in REQUIRED_PUBLIC_FILES or bool(val)
            )
        )

    hash_payload = {name: table_map[name] for name in sources}
    pub_hash = _compute_public_hash(hash_payload)

    return PublicEpisode(
        company=company_d,
        policy=policy_d,
        accounts=accounts_t,
        counterparties=counterparties_t,
        journal_entries=journal_entries_t,
        invoices=invoices_t,
        credit_notes=credit_notes_t,
        payments=payments_t,
        bank_lines=bank_lines_t,
        fx_rates=fx_rates_t,
        opening_balances=opening_b,
        period_calendar=period_cal,
        document_links=doc_links_t,
        examined_public_sources=sources,
        episode_public_hash=pub_hash,
    )


def load_public_episode(public_dir: str | Path) -> PublicEpisode:
    """Load a :class:`PublicEpisode` strictly from a ``public/`` directory.

    Enforces:
      - ``public_dir`` must be an existing directory;
      - hidden files (starting with ``.``) are forbidden (TZ 8.6);
      - ``index_hints.json`` is forbidden (TZ 8.2);
      - any non-allowlisted file or subdirectory inside ``public_dir`` is
        rejected so private artifacts can never be silently ingested;
      - symlinks pointing outside ``public_dir`` are rejected.
    """
    root = Path(public_dir)
    if not root.exists() or not root.is_dir():
        raise PublicEpisodeError(f"public directory does not exist: {root}")
    resolved_root = root.resolve()

    present_files: list[str] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        name = entry.name
        if name.startswith("."):
            raise PublicEpisodeError(f"hidden file forbidden in public directory: {name!r}")
        if name in FORBIDDEN_PUBLIC_FILES:
            raise PublicEpisodeError(f"forbidden file in public directory: {name!r}")
        if entry.is_dir():
            raise PublicEpisodeError(f"unexpected subdirectory in public directory: {name!r}")
        if name not in ALLOWED_PUBLIC_FILES:
            raise PublicEpisodeError(f"unrecognised non-public file in public directory: {name!r}")
        resolved_entry = entry.resolve()
        try:
            resolved_entry.relative_to(resolved_root)
        except ValueError as exc:
            raise PublicEpisodeError(
                f"symlink escapes public directory boundary: {name!r}"
            ) from exc
        present_files.append(name)

    for req in REQUIRED_PUBLIC_FILES:
        if req not in present_files:
            raise PublicEpisodeError(f"missing required public file: {req!r}")

    loaded: dict[str, Any] = {}
    for name in present_files:
        # Bounded read (D-10-03): public episode inputs may be oversized/hostile.
        try:
            text = read_text_bounded(root / name)
        except (OSError, ValueError) as exc:
            raise PublicEpisodeError(f"failed reading {name!r}: {exc}") from exc
        if name.endswith(".jsonl"):
            loaded[name] = _parse_jsonl(text, name)
        else:
            loaded[name] = _parse_json(text, name)

    accounts_raw = loaded.get("accounts.json", [])
    if isinstance(accounts_raw, dict) and "accounts" in accounts_raw:
        accounts_list = accounts_raw["accounts"]
    elif isinstance(accounts_raw, list):
        accounts_list = accounts_raw
    else:
        raise PublicEpisodeError("accounts.json must be a list or {\"accounts\": [...]}")

    return build_public_episode(
        company=loaded["company.json"],
        policy=loaded["policy.json"],
        accounts=accounts_list,
        counterparties=loaded.get("counterparties.jsonl", ()),
        journal_entries=loaded.get("journal_entries.jsonl", ()),
        invoices=loaded.get("invoices.jsonl", ()),
        credit_notes=loaded.get("credit_notes.jsonl", ()),
        payments=loaded.get("payments.jsonl", ()),
        bank_lines=loaded.get("bank_lines.jsonl", ()),
        fx_rates=loaded.get("fx_rates.jsonl", ()),
        opening_balances=loaded.get("opening_balances.json", []),
        period_calendar=loaded.get("period_calendar.json", []),
        document_links=loaded.get("document_links.jsonl", ()),
        examined_public_sources=present_files,
    )


def subset_public_episode(
    episode: PublicEpisode,
    allowed_typed_ids: Iterable[str],
) -> PublicEpisode:
    """Restrict an episode to background context + ``allowed_typed_ids``.

    Background context (``company.json``, ``policy.json``, ``accounts.json``,
    ``opening_balances.json``, ``period_calendar.json``) is preserved per
    TZ 13.5 so minimality ablation tests subject evidence records only.
    """
    allowed = frozenset(allowed_typed_ids)
    return build_public_episode(
        company=episode.company,
        policy=episode.policy,
        accounts=episode.accounts,
        counterparties=[
            r for r in episode.counterparties
            if make_typed_id("CP", str(r["counterparty_id"])) in allowed
        ],
        journal_entries=[
            r for r in episode.journal_entries
            if make_typed_id("JE", str(r["je_id"])) in allowed
        ],
        invoices=[
            r for r in episode.invoices
            if make_typed_id("INV", str(r["doc_id"])) in allowed
        ],
        credit_notes=[
            r for r in episode.credit_notes
            if make_typed_id("CN", str(r["credit_note_id"])) in allowed
        ],
        payments=[
            r for r in episode.payments
            if make_typed_id("PAY", str(r["pay_id"])) in allowed
        ],
        bank_lines=[
            r for r in episode.bank_lines
            if make_typed_id("BANK", str(r["bank_line_id"])) in allowed
        ],
        fx_rates=[
            r for r in episode.fx_rates
            if fx_row_typed_id(r) in allowed
        ],
        opening_balances=episode.opening_balances,
        period_calendar=episode.period_calendar,
        document_links=episode.document_links,
    )


__all__ = [
    "ALLOWED_PUBLIC_FILES",
    "FORBIDDEN_PUBLIC_FILES",
    "PublicEpisode",
    "PublicEpisodeError",
    "REQUIRED_PUBLIC_FILES",
    "build_public_episode",
    "fx_row_raw_id",
    "fx_row_typed_id",
    "load_public_episode",
    "make_typed_id",
    "subset_public_episode",
]
