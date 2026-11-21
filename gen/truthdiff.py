"""Structural diff between the clean and mutated twins (Phase 4.4, 10.3).

The diff is *structural evidence*, not proof of error: it reports exactly which
rows were added, removed or modified, with field-level before/after values, in a
deterministic order. Candidate truth is then built from this diff plus the
operator declaration — never from a hand-written label (P-002, REQ-GEN-010).

Diff kinds distinguished (10.3):
  * ``added``      — a row present only in the mutated twin;
  * ``removed``    — a row present only in the clean twin;
  * ``modified``   — a row present in both with changed fields (including links
                     such as ``allocations`` and periods).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from contracts.canonical import digest_of
from contracts.errors import ContractError
from contracts.models import TABLES, BookRow
from gen.twins import Book

TABLE_KEY_FIELDS: dict[str, tuple[str, ...]] = {
    "accounts": ("account_id",),
    "counterparties": ("counterparty_id",),
    "journal_entries": ("je_id",),
    "invoices": ("doc_id",),
    "credit_notes": ("credit_note_id",),
    "payments": ("pay_id",),
    "bank_lines": ("bank_line_id",),
    "fx_rates": ("pair", "effective_date"),
}


@dataclass(frozen=True)
class RowChange:
    table: str
    kind: str  # added | removed | modified
    key: str
    changed_fields: tuple[str, ...] = ()
    before: Mapping[str, Any] | None = None
    after: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "kind": self.kind,
            "key": self.key,
            "changed_fields": list(self.changed_fields),
            "before": dict(self.before) if self.before is not None else None,
            "after": dict(self.after) if self.after is not None else None,
        }

    def sort_key(self) -> tuple:
        return (self.table, self.kind, self.key)


@dataclass(frozen=True)
class TwinDiff:
    changes: tuple[RowChange, ...]
    clean_digest: str
    mutated_digest: str

    def added(self, table: str | None = None) -> tuple[RowChange, ...]:
        return tuple(
            change
            for change in self.changes
            if change.kind == "added" and (table is None or change.table == table)
        )

    def removed(self, table: str | None = None) -> tuple[RowChange, ...]:
        return tuple(
            change
            for change in self.changes
            if change.kind == "removed" and (table is None or change.table == table)
        )

    def modified(self, table: str | None = None) -> tuple[RowChange, ...]:
        return tuple(
            change
            for change in self.changes
            if change.kind == "modified" and (table is None or change.table == table)
        )

    def by_table(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for change in self.changes:
            key = f"{change.table}:{change.kind}"
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))

    def new_ids(self, table: str) -> tuple[str, ...]:
        """Primary keys added to ``table`` (documented affected-id rule input)."""
        key_fields = TABLE_KEY_FIELDS[table]
        ids: list[str] = []
        for change in self.added(table):
            row = change.after or {}
            ids.append("/".join(str(row[field_name]) for field_name in key_fields))
        return tuple(sorted(ids))

    def is_empty(self) -> bool:
        return not self.changes

    def summary(self) -> dict[str, Any]:
        return {
            "added": len(self.added()),
            "removed": len(self.removed()),
            "modified": len(self.modified()),
            "by_table": self.by_table(),
            "clean_digest": self.clean_digest,
            "mutated_digest": self.mutated_digest,
        }

    def digest(self) -> str:
        return digest_of([change.to_dict() for change in self.changes])


def structural_diff(clean: Book, mutated: Book) -> TwinDiff:
    """Deterministic structural diff of two books over all public tables."""
    changes: list[RowChange] = []
    for table in TABLES:
        key_fields = TABLE_KEY_FIELDS[table]
        before = {_row_key(table, row, key_fields): row for row in clean.rows(table)}
        after = {_row_key(table, row, key_fields): row for row in mutated.rows(table)}
        for key in sorted(set(after) - set(before)):
            changes.append(
                RowChange(table=table, kind="added", key=key, after=after[key].to_row())
            )
        for key in sorted(set(before) - set(after)):
            changes.append(
                RowChange(table=table, kind="removed", key=key, before=before[key].to_row())
            )
        for key in sorted(set(before) & set(after)):
            before_row = before[key].to_row()
            after_row = after[key].to_row()
            changed = tuple(
                sorted(
                    field_name
                    for field_name in set(before_row) | set(after_row)
                    if before_row.get(field_name) != after_row.get(field_name)
                )
            )
            if changed:
                changes.append(
                    RowChange(
                        table=table,
                        kind="modified",
                        key=key,
                        changed_fields=changed,
                        before=before_row,
                        after=after_row,
                    )
                )
    changes.sort(key=lambda change: change.sort_key())
    return TwinDiff(
        changes=tuple(changes),
        clean_digest=clean.public_digest(),
        mutated_digest=mutated.public_digest(),
    )


def _row_key(table: str, row: BookRow, key_fields: Sequence[str]) -> str:
    return "/".join(str(getattr(row, field_name)) for field_name in key_fields)


def assert_clean_untouched(clean_before: Book, clean_after: Book) -> None:
    """Guard used by tests and the episode builder: mutations never edit the clean twin."""
    if clean_before.public_digest() != clean_after.public_digest():
        raise ContractError(
            "clean twin changed during mutation",
            before=clean_before.public_digest(),
            after=clean_after.public_digest(),
        )


def touched_entities(diff: TwinDiff) -> dict[str, tuple[str, ...]]:
    """All entity ids touched by the diff, grouped by table (public evidence map)."""
    touched: dict[str, set[str]] = {}
    for change in diff.changes:
        row = change.after or change.before or {}
        for value in row.values():
            if isinstance(value, str) and _looks_like_id(value):
                touched.setdefault(change.table, set()).add(value)
    return {table: tuple(sorted(ids)) for table, ids in sorted(touched.items())}


def _looks_like_id(value: str) -> bool:
    if not 2 <= len(value) <= 48:
        return False
    return "-" in value or "_" in value or "/" in value
