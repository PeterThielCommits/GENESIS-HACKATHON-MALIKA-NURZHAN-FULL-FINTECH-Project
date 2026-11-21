"""Deterministic, namespaced ID factory (Phase 2.5, 8.4 anti-shortcut).

Four ID families are supported and must be applied identically to clean and
mutated records:

  A: ``JE-000123`` / ``INV-2025-0042`` / ``PAY-7F3A91``
  B: ``2025/05/J/0123`` / ``S-0042-25`` / ``P0007F3A``
  C: ``je_ab12cd`` / ``in_9f2e`` / ``pm_77aa``
  D: numeric identifier with a Luhn-style check digit

Rules enforced:
  * an ID family never encodes seed, error type, operator index or record
    position (REQ-DATA / 8.4);
  * IDs are drawn from an injected ``random.Random`` stream only — no global
    randomness (REQ-GEN-001);
  * collisions inside one namespace raise instead of silently re-issuing.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Final, Literal

from contracts.errors import IdError

IdStyle = Literal["A", "B", "C", "D"]
ID_STYLES: Final[tuple[str, ...]] = ("A", "B", "C", "D")

_PREFIX_BY_TABLE: Final[dict[str, str]] = {
    "journal_entries": "JE",
    "invoices": "INV",
    "credit_notes": "CN",
    "payments": "PAY",
    "bank_lines": "BNK",
    "counterparties": "CP",
    "accounts": "ACC",
    "line_items": "LI",
    "journal_entry_lines": "JL",
    "allocations": "AL",
    "documents": "DOC",
}

# Style B needs a distinct single-letter prefix per table: a document reference is a
# *cross-table* pointer (``source_document_id`` may hold an invoice, payment or credit
# note id), so two tables must never mint the same string.
_STYLE_B_PREFIX: Final[dict[str, str]] = {
    "journal_entries": "J",
    "invoices": "S",
    "credit_notes": "C",
    "payments": "P",
    "bank_lines": "N",
    "counterparties": "R",
    "accounts": "K",
    "line_items": "L",
    "journal_entry_lines": "Y",
    "allocations": "A",
    "documents": "D",
}

# Style D is purely numeric, so the table namespace must live inside the digits.
# The two leading digits are the namespace index; the remaining six are the record
# counter. This mirrors the per-table prefixes of styles A/B/C and keeps document
# references unambiguous (``source_document_id`` points across tables).
_STYLE_D_NAMESPACE: Final[dict[str, int]] = {
    table: index
    for index, table in enumerate(
        (
            "journal_entries",
            "invoices",
            "credit_notes",
            "payments",
            "bank_lines",
            "counterparties",
            "accounts",
            "line_items",
            "journal_entry_lines",
            "allocations",
            "documents",
        )
    )
}

_SHORT_BY_TABLE: Final[dict[str, str]] = {
    "journal_entries": "je",
    "invoices": "in",
    "credit_notes": "cn",
    "payments": "pm",
    "bank_lines": "bn",
    "counterparties": "cp",
    "accounts": "ac",
    "line_items": "li",
    "journal_entry_lines": "jl",
    "allocations": "al",
    "documents": "dc",
}


def _luhn_check_digit(digits: str) -> int:
    """Mod-10 check digit where the check digit itself is appended."""
    total = 0
    for index, char in enumerate(reversed(digits)):
        digit = int(char)
        if index % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return (10 - total % 10) % 10


def validate_luhn(number: str) -> bool:
    """Validate a numeric identifier carrying a trailing Luhn check digit."""
    if not isinstance(number, str) or len(number) < 2 or not number.isdigit():
        raise IdError("numeric ID must be a digit string of length >= 2")
    return _luhn_check_digit(number[:-1]) == int(number[-1])


@dataclass
class IdFactory:
    """Per-namespace deterministic identifier generator.

    ``rng`` may be either ``random.Random`` or an ``RngStream`` from
    ``gen.core.rng``; both are seeded deterministically and never global.
    """

    style: IdStyle
    rng: object
    year: int
    _issued: dict[str, set[str]] = field(default_factory=dict, init=False)
    _counters: dict[str, int] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.style not in ID_STYLES:
            raise IdError("unknown ID style", style=self.style, allowed=list(ID_STYLES))
        if not isinstance(self.year, int) or not 1900 <= self.year <= 2999:
            raise IdError("year out of range", year=self.year)

    # ------------------------------------------------------------------ public
    def new(self, table: str, *, month: int | None = None, start_index: int = 1) -> str:
        """Issue a fresh unique ID for ``table``."""
        self._require_table(table)
        for _ in range(1000):
            candidate = self._build(table, month=month, start_index=start_index)
            issued = self._issued.setdefault(table, set())
            if candidate not in issued:
                issued.add(candidate)
                return candidate
        raise IdError("ID space exhausted for table", table=table)

    def _random_bits(self, bits: int) -> int:
        rng = self.rng
        getrandbits = getattr(rng, "getrandbits", None)
        if callable(getrandbits):
            return int(getrandbits(bits))
        inner = getattr(rng, "random", None)
        if inner is not None and hasattr(inner, "getrandbits"):
            return int(inner.getrandbits(bits))
        raise IdError("ID factory requires a deterministic random source")

    def peek_next(self, table: str) -> int:
        """Counter value the next ``new`` call will start from (deterministic)."""
        return self._counters.get(table, 1)

    def issued(self, table: str) -> tuple[str, ...]:
        return tuple(sorted(self._issued.get(table, set())))

    # ----------------------------------------------------------------- private
    def _require_table(self, table: str) -> None:
        if table not in _PREFIX_BY_TABLE:
            raise IdError("unknown id table", table=table)

    def _next_counter(self, table: str, start_index: int) -> int:
        current = self._counters.get(table, start_index)
        self._counters[table] = current + 1
        return current

    def _build(self, table: str, *, month: int | None, start_index: int) -> str:
        if self.style == "A":
            if table == "invoices":
                counter = self._next_counter(table, start_index)
                return f"INV-{self.year}-{counter:04d}"
            counter = self._next_counter(table, start_index)
            return f"{_PREFIX_BY_TABLE[table]}-{counter:06d}"
        if self.style == "B":
            if table == "journal_entries":
                counter = self._next_counter(table, start_index)
                month_value = month or 1
                return f"{self.year}/{month_value:02d}/J/{counter:04d}"
            if table == "invoices":
                counter = self._next_counter(table, start_index)
                return f"S-{counter:04d}-{str(self.year)[2:]}"
            counter = self._next_counter(table, start_index)
            return f"{_STYLE_B_PREFIX[table]}{counter:07X}"
        if self.style == "C":
            short = _SHORT_BY_TABLE[table]
            token = f"{self._random_bits(24):06x}"
            return f"{short}_{token}"
        # Style D: numeric with check digit, deterministic per-namespace sequence.
        counter = self._next_counter(table, start_index)
        body = f"{_STYLE_D_NAMESPACE[table]:02d}{(counter * 7919 + 100000) % 1000000:06d}"
        return body + str(_luhn_check_digit(body))


def style_for_config(id_style: str) -> IdStyle:
    if id_style not in ID_STYLES:
        raise IdError("unknown id_style in config", id_style=id_style, allowed=list(ID_STYLES))
    return id_style  # type: ignore[return-value]
