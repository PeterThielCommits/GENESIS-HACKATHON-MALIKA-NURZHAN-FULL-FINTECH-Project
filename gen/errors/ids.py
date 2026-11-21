"""Identifier issuance for mutated records (8.4, REQ-ERR-003).

A mutated record must look exactly like a normal record: same ID family, same
formatting, no ``BUG``/``DUP``/``ERROR`` markers and no positional disclosure. The
helper below detects the book's next free counter per table, so a duplicate payment
takes the next ordinary payment id of that company.
"""

from __future__ import annotations

import re
from typing import Any

from contracts.errors import OperatorError
from core.ids import IdFactory, style_for_config
from gen.core.rng import RngStream
from gen.twins import Book

_TRAILING_NUMBER = re.compile(r"(\d{3,8})(?!.*\d)")
_HEX_SUFFIX = re.compile(r"([0-9A-F]{4,8})$")


def _next_index(book: Book, table: str) -> int:
    """Smallest counter that is still free for ``table``."""
    key_field = {
        "payments": "pay_id",
        "bank_lines": "bank_line_id",
        "allocations": "allocation_id",
        "journal_entries": "je_id",
        "journal_entry_lines": "line_id",
        "invoices": "doc_id",
    }[table]
    highest = 0
    if table not in ("allocations", "journal_entry_lines"):
        for row in book.rows(table):
            highest = max(highest, _extract_index(str(getattr(row, key_field))))
    if table == "journal_entry_lines":
        for entry in book.journal_entries:
            for line in entry.lines:
                highest = max(highest, _extract_index(line.line_id))
    if table == "allocations":
        for payment in book.payments:
            for allocation in payment.allocations:
                highest = max(highest, _extract_index(allocation.allocation_id))
    return highest + 1


def _extract_index(identifier: str) -> int:
    match = _TRAILING_NUMBER.search(identifier)
    if match:
        return int(match.group(1))
    match = _HEX_SUFFIX.search(identifier.upper())
    if match:
        return int(match.group(1), 16) % 1_000_000
    return 0


def issue_unique_ids(
    book: Book,
    rng: RngStream,
    table: str,
    count: int = 1,
    *,
    month: int | None = None,
) -> tuple[str, ...]:
    """Issue ``count`` fresh ids for ``table`` in the book's own ID style.

    All ids come from **one** factory instance so counters advance monotonically and
    two calls inside a single mutation cannot produce the same identifier.
    """
    if count < 1:
        raise OperatorError("count must be >= 1", count=count)
    style = style_for_config(str(book.company["id_style"]))
    year = int(str(book.period_calendar.get("periods", ["2025"])[0])[:4] or 2025)
    start = _next_index(book, table)
    factory = IdFactory(style=style, rng=rng, year=year)
    existing = set(_existing_ids(book, table))
    issued: list[str] = []
    for offset in range(count):
        for attempt in range(500):
            candidate = factory.new(table, month=month, start_index=start + offset + attempt * 97)
            if candidate not in existing:
                existing.add(candidate)
                issued.append(candidate)
                break
        else:  # pragma: no cover - defensive
            raise OperatorError("could not issue a unique id", table=table, style=style)
    if len(set(issued)) != count:  # pragma: no cover - defensive
        raise OperatorError("issued duplicate ids", table=table)
    return tuple(issued)


def issue_unique_id(
    book: Book,
    rng: RngStream,
    table: str,
    *,
    month: int | None = None,
) -> str:
    """Issue exactly one fresh id for ``table``."""
    return issue_unique_ids(book, rng, table, 1, month=month)[0]


def _existing_ids(book: Book, table: str) -> set[str]:
    key_field = {
        "payments": "pay_id",
        "bank_lines": "bank_line_id",
        "journal_entries": "je_id",
        "invoices": "doc_id",
    }.get(table)
    identifiers: set[str] = set()
    if key_field is not None:
        identifiers |= {str(getattr(row, key_field)) for row in book.rows(table)}
    if table == "journal_entry_lines":
        for entry in book.journal_entries:
            identifiers |= {line.line_id for line in entry.lines}
    if table == "allocations":
        for payment in book.payments:
            identifiers |= {allocation.allocation_id for allocation in payment.allocations}
    return identifiers
