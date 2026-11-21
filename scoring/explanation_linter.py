"""Explanation consistency linter (Phase 10, Task 10.6 — Master TZ §17.6).

Diagnostic-only check verifying whether free-text ``explanation`` fields in
submitted findings stay grounded in declared ``affected_ids``, ``evidence_ids``,
``claimed_amount``, and ``currency``:
  1. Typed IDs mentioned in ``explanation`` (``INV:...``, ``PAY:...``, ``JE:...``,
     ``CN:...``, ``BANK:...``, ``FX:...``, ``CP:...``) must belong to
     ``affected_ids ∪ evidence_ids``;
  2. Raw IDs matching ``PREFIX/<hex>/<hex>`` mentioned in ``explanation`` must
     correspond to a declared ID in ``affected_ids ∪ evidence_ids``;
  3. ISO-4217 currency codes mentioned in ``explanation`` (``KZT``, ``USD``,
     ``EUR``, ``JPY``, ``KWD``) must match ``finding.currency`` (unless explaining
     an ``FX_RATE_MISMATCH`` pair where source + functional currencies appear);
  4. If integer amounts >= 100 are explicitly stated after ``amount``/``shortfall``/
     ``differs``/``exceed``/``by`` or equal ``claimed_amount``, contradictory
     hallucinated numbers are flagged when ``claimed_amount`` is absent and a
     conflicting amount is asserted;
  5. Result is **purely diagnostic** (TZ §15.9, §17.6): it NEVER alters matching,
     F1, or official/rational reward.

Zone 2 rule: imports ONLY ``contracts`` and Python 3.11 stdlib.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Sequence

from contracts.models import Finding

_TYPED_ID_RE = re.compile(r"\b(?:JE|INV|CN|PAY|BANK|FX|CP):[A-Za-z0-9_./-]+\b")
_SLASH_ID_RE = re.compile(r"\b(?:JE|INV|CN|PAY|BANK|FX|CP)/[0-9a-f]{6,16}/[0-9a-f]{8,32}\b")
_ISO_CURRENCIES = frozenset({"KZT", "USD", "EUR", "JPY", "KWD", "GBP", "CHF", "RUB", "CNY"})
_CURRENCY_TOKEN_RE = re.compile(r"\b(?:KZT|USD|EUR|JPY|KWD|GBP|CHF|RUB|CNY)\b")
_INTEGER_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_./:-])\d{2,15}(?![A-Za-z0-9_./:-])")


def lint_single_explanation(
    finding: Finding,
    *,
    accessible_public_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Lint one canonical ``Finding``'s ``explanation`` field diagnostically."""
    raw_text = unicodedata.normalize("NFC", finding.explanation or "").strip()
    declared_typed = set(finding.affected_ids) | set(finding.evidence_ids)
    declared_raw = {tid.split(":", 1)[1] if ":" in tid else tid for tid in declared_typed}

    if not raw_text:
        return {
            "consistent": True,
            "empty_explanation": True,
            "undeclared_ids": [],
            "unreachable_ids": [],
            "currency_mismatch": False,
            "amount_mentioned": False,
            "amount_consistent": True,
            "issues": [],
        }

    issues: list[str] = []
    undeclared_ids: list[str] = []
    unreachable_ids: list[str] = []

    for tid in sorted(set(_TYPED_ID_RE.findall(raw_text))):
        if tid not in declared_typed:
            undeclared_ids.append(tid)
            issues.append(f"mentioned typed ID {tid} not in affected_ids or evidence_ids")
        if accessible_public_ids is not None and tid not in accessible_public_ids:
            unreachable_ids.append(tid)
            issues.append(f"mentioned typed ID {tid} does not exist in public records")

    for sid in sorted(set(_SLASH_ID_RE.findall(raw_text))):
        # Skip if already matched as part of PREFIX:PREFIX/...
        if sid not in declared_raw:
            undeclared_ids.append(sid)
            issues.append(f"mentioned entity ID {sid} not in affected_ids or evidence_ids")

    mentioned_currencies = sorted(set(_CURRENCY_TOKEN_RE.findall(raw_text)))
    currency_mismatch = False
    if mentioned_currencies:
        if finding.type == "FX_RATE_MISMATCH":
            # FX explanations may mention both invoice currency and functional currency,
            # but must include the finding's currency if only one currency is cited
            if len(mentioned_currencies) == 1 and mentioned_currencies[0] != finding.currency:
                currency_mismatch = True
                issues.append(
                    f"explanation cites currency {mentioned_currencies[0]} != finding currency {finding.currency}"
                )
        else:
            bad_curs = [c for c in mentioned_currencies if c != finding.currency]
            if bad_curs:
                currency_mismatch = True
                issues.append(
                    f"explanation cites currency {bad_curs[0]} != finding currency {finding.currency}"
                )

    int_tokens = [int(tok) for tok in _INTEGER_TOKEN_RE.findall(raw_text)]
    # Exclude 4-digit calendar years 2020..2035 when checking amount mentions
    candidate_amounts = [n for n in int_tokens if not (2020 <= n <= 2035 and n != finding.claimed_amount)]
    amount_mentioned = len(candidate_amounts) > 0
    amount_consistent = True
    if amount_mentioned and finding.claimed_amount not in candidate_amounts:
        # Allow FX explanations that cite expected vs actual amounts whose abs diff == claimed_amount
        pairwise_diffs = {
            abs(a - b)
            for idx_a, a in enumerate(candidate_amounts)
            for b in candidate_amounts[idx_a + 1 :]
        }
        if finding.claimed_amount not in pairwise_diffs:
            amount_consistent = False
            issues.append(
                f"explanation mentions numbers {candidate_amounts[:4]} inconsistent with claimed_amount {finding.claimed_amount}"
            )

    return {
        "consistent": len(issues) == 0,
        "empty_explanation": False,
        "undeclared_ids": undeclared_ids,
        "unreachable_ids": unreachable_ids,
        "currency_mismatch": currency_mismatch,
        "amount_mentioned": amount_mentioned,
        "amount_consistent": amount_consistent,
        "issues": issues,
    }


def lint_findings_explanations(
    findings: Sequence[Finding],
    *,
    accessible_public_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Run explanation consistency linter across all submitted findings."""
    per_finding = [
        {
            "finding_index": idx,
            **lint_single_explanation(f, accessible_public_ids=accessible_public_ids),
        }
        for idx, f in enumerate(findings)
    ]
    consistent_count = sum(1 for item in per_finding if item["consistent"])
    total = len(per_finding)
    return {
        "status": "EVALUATED",
        "diagnostic_only": True,
        "affects_official_reward": False,
        "findings_checked": total,
        "consistent_count": consistent_count,
        "inconsistent_count": total - consistent_count,
        "all_consistent": consistent_count == total,
        "per_finding": per_finding,
    }


__all__ = [
    "lint_findings_explanations",
    "lint_single_explanation",
]
