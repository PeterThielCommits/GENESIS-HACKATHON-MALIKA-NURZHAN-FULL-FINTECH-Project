"""Untrusted accounting text sanitizer & prompt-injection detector (Phase 11 — TZ §14).

Treats all free-text fields in ``invoices``, ``bank_lines``, ``credit_notes``,
``counterparties``, and ``journal_entries`` as UNTRUSTED DATA — never control-plane
instructions. Detects imperative override phrases across ``en``, ``ru``, and ``kk``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from nlp.normalize import normalize_nfc

_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "IGNORE_DISCREPANCY",
        re.compile(
            r"(?:ignore\s+all\s+discrepanc|submit\s+zero\s+findings|игнорируйте\s+все\s+расхожден|"
            r"пустой\s+отчет|барлық\s+алшақтықтарды\s+елемей|бос\s+submit)",
            re.IGNORECASE,
        ),
    ),
    (
        "FABRICATE_DECOY_FINDING",
        re.compile(
            r"(?:auditor\s+override\s*:\s*report|зафиксируйте\s+duplicate_payment|инструкция\s+ревизору)",
            re.IGNORECASE,
        ),
    ),
    (
        "OVERRIDE_FX_POLICY",
        re.compile(
            r"(?:policy\s+update\s*:.*mkt|mkt\s+commercial\s+fx\s+quotes\s+are\s+officially\s+approved|"
            r"есеп\s+саясаты\s+ескертпесі|қате\s+жоқ\s+деп\s+танылсын)",
            re.IGNORECASE,
        ),
    ),
    (
        "BRACKETED_SYSTEM_DIRECTIVE",
        re.compile(
            r"\[\s*(?:system\s+audit\s+note|системная\s+директива|жүйелік\s+аудит\s+нұсқауы)",
            re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True)
class UntrustedTextInspection:
    """Result of scanning an untrusted free-text accounting field."""

    suspicious: bool
    matched_rules: tuple[str, ...]
    sanitized_data_only: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "suspicious": self.suspicious,
            "matched_rules": list(self.matched_rules),
            "sanitized_data_only": self.sanitized_data_only,
        }


def inspect_untrusted_text(text: str) -> UntrustedTextInspection:
    """Detect prompt-injection directives and strip bracketed control tags."""
    norm = normalize_nfc(text or "")
    matched: list[str] = []
    for rule_name, pat in _INJECTION_PATTERNS:
        if pat.search(norm):
            matched.append(rule_name)
    # Strip bracketed pseudo-system directives while preserving factual prose outside brackets
    stripped = re.sub(r"\[[^\]]*(?:SYSTEM|OVERRIDE|ДИРЕКТИВА|ИНСТРУКЦИЯ|НҰСҚАУЫ|ЕСКЕРТПЕСІ)[^\]]*\]", "", norm, flags=re.IGNORECASE).strip()
    return UntrustedTextInspection(
        suspicious=bool(matched),
        matched_rules=tuple(matched),
        sanitized_data_only=stripped,
    )


__all__ = ["UntrustedTextInspection", "inspect_untrusted_text"]
