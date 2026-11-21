"""Deterministic ID factories per contract 8.4.

ID families supported (A-D):
  A: JE-000123, INV-2025-0042, PAY-7F3A91
  B: 2025/05/J/0123, S-0042-25, P0007F3A
  C: je_ab12cd, in_9f2e, pm_77aa
  D: synthetic numeric identifier with a check digit

Rules:
  - REQ-DATA-001: uniqueness within each table and namespace;
  - anti-shortcut rules: no BUG/DUP/ERROR/SYNTHETIC markers, no sequential
    blocks of "suspicious" IDs, no seed/operator/position encoding
    (clean generation uses random-looking IDs from namespaced RNG);
  - REQ-DATA-005: synthetic data only (no real data);
  - every generator id is registered in a per-table uniqueness set so
    duplicates cannot be emitted.
"""
from __future__ import annotations

from gen.rng import NamespacedRNG

_ALPHA_NUM = "0123456789ABCDEF"


class IDFactory:
    """Factory of unique synthetic IDs with configurable ID families."""

    def __init__(self, rng: NamespacedRNG, fiscal_year: int):
        if not isinstance(fiscal_year, int):
            raise ValueError("fiscal_year must be an int")
        self._rng = rng
        self._fiscal_year = fiscal_year
        self._used: dict[str, set[str]] = {}

    # -- uniqueness -------------------------------------------------------
    def _next_unique(self, table: str, make) -> str:
        seen = self._used.setdefault(table, set())
        while True:
            candidate = make()
            if candidate not in seen:
                seen.add(candidate)
                return candidate

    def _hex(self, length: int) -> str:
        return "".join(self._rng.choice(_ALPHA_NUM) for _ in range(length))

    def _num(self, low: int, high: int) -> int:
        return self._rng.randint(low, high)

    # -- factories --------------------------------------------------------
    def next_je_id(self) -> str:
        return self._next_unique("je_ids", lambda: f"JE-{self._num(100000, 999999):06d}")

    def next_je_id_b(self, year: int, month: int) -> str:
        return self._next_unique(
            "je_ids",
            lambda: f"{year}/{month:02d}/J/{self._num(1, 9999):04d}",
        )

    def next_inv_id(self, year: int | None = None) -> str:
        y = year if year is not None else self._fiscal_year
        return self._next_unique(
            "invoice_ids",
            lambda: f"INV-{y:04d}-{self._num(1, 9999):04d}",
        )

    def next_inv_id_c(self) -> str:
        return self._next_unique("invoice_ids", lambda: f"in_{self._hex(6)}")

    def next_pay_id(self) -> str:
        return self._next_unique("pay_ids", lambda: f"PAY-{self._hex(6)}")

    def next_pay_id_b(self) -> str:
        return self._next_unique("pay_ids", lambda: f"S-{self._num(1000, 9999):04d}-{self._num(20, 29):02d}")

    def next_pay_id_c(self) -> str:
        return self._next_unique("pay_ids", lambda: f"pm_{self._hex(8)}")

    def next_cp_id(self) -> str:
        return self._next_unique("counterparty_ids", lambda: f"CP-{self._num(100000, 999999):06d}")

    def next_ba_id(self) -> str:
        return self._next_unique("bank_account_ids", lambda: f"BA-{self._num(1, 9999):04d}")

    def next_allocation_id(self) -> str:
        return self._next_unique("allocation_ids", lambda: f"AL-{self._num(100000, 999999):06d}")

    def next_journal_line_id(self) -> str:
        return self._next_unique("journal_line_ids", lambda: f"JL-{self._num(100000, 999999):06d}")

    def next_invoice_line_id(self) -> str:
        return self._next_unique("invoice_line_ids", lambda: f"IL-{self._num(100000, 999999):06d}")

    def next_credit_note_id(self) -> str:
        return self._next_unique("credit_note_ids", lambda: f"CN-{self._num(100000, 999999):06d}")

    def next_bank_line_id(self) -> str:
        return self._next_unique("bank_line_ids", lambda: f"BL-{self._num(100000, 999999):06d}")

    # -- check digit family (D) ------------------------------------------
    @staticmethod
    def _check_digit(digits: str) -> str:
        """Simple weighted check digit: sum * 7 mod 11 as single char."""
        total = sum(int(ch) * (i + 1) for i, ch in enumerate(digits))
        return str((total * 7) % 11)

    def next_numeric_id(self, table: str, digits: int = 7) -> str:
        """Synthetic numeric identifier with a check digit."""
        def make() -> str:
            raw = str(self._num(10 ** (digits - 1), 10**digits - 1))
            return raw + self._check_digit(raw)
        return self._next_unique(table, make)
