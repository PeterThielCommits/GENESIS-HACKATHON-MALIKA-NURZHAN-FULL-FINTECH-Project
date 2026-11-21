"""Deterministic candidate entity & document ranker (Phase 10, Task 10.4 — Master TZ §17.4).

Strictly emits HYPOTHESIS-TIER candidates (``requires_structured_verification=True``).
Never auto-confirms an anomaly or substitutes for structured foreign-key / amount /
policy verification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from nlp.normalize import (
    char_ngrams,
    normalize_accounting_text,
    transliterate_to_ascii_skeleton,
)

_TYPED_ID_MENTION_RE = re.compile(r"\b(?:INV|PAY|BANK|JE|CN|CP|FX|AL):[A-Za-z0-9_-]{2,48}\b")


@dataclass(frozen=True)
class CandidateMatch:
    """Hypothesis-only candidate match ranked using integer basis points [0..10000]."""

    entity_id: str
    score_bps: int
    matched_surface: str
    tier: str = "TIER_4_TEXT_SIMILARITY_ONLY"
    requires_structured_verification: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "score_bps": self.score_bps,
            "matched_surface": self.matched_surface,
            "tier": self.tier,
            "requires_structured_verification": self.requires_structured_verification,
        }


def _jaccard_bps(a: frozenset[str], b: frozenset[str]) -> int:
    if not a or not b:
        return 0
    inter = len(a & b)
    union = len(a | b)
    return (inter * 10000) // union if union else 0


def text_similarity_bps(query: str, candidate: str) -> int:
    """Compute integer basis-point [0..10000] cross-script similarity without floats."""
    q_norm = normalize_accounting_text(query)
    c_norm = normalize_accounting_text(candidate)
    if not q_norm or not c_norm:
        return 0
    if q_norm == c_norm:
        return 10000

    # Combine native-script 3-gram Jaccard and cross-script ASCII phonetic skeleton 3-gram Jaccard
    native_bps = _jaccard_bps(char_ngrams(q_norm, 3), char_ngrams(c_norm, 3))
    q_skel = transliterate_to_ascii_skeleton(query)
    c_skel = transliterate_to_ascii_skeleton(candidate)
    if q_skel and q_skel == c_skel:
        return 9600
    skel_bps = _jaccard_bps(char_ngrams(q_skel, 3), char_ngrams(c_skel, 3))
    tok_bps = _jaccard_bps(frozenset(q_skel.split()), frozenset(c_skel.split()))
    # Deterministic integer weighted blend: max(native, (6 * skel + 4 * tok) // 10)
    cross_bps = (6 * skel_bps + 4 * tok_bps) // 10
    return max(native_bps, cross_bps)


def rank_counterparty_candidates(
    counterparty_text: str,
    counterparties: Sequence[Mapping[str, Any]],
    *,
    min_score_bps: int = 2500,
    top_k: int = 5,
) -> tuple[CandidateMatch, ...]:
    """Rank candidate ``counterparty_id`` entries against noisy/multilingual text."""
    scored: list[CandidateMatch] = []
    q_norm = normalize_accounting_text(counterparty_text)
    for cp in counterparties:
        cp_id = str(cp.get("counterparty_id", ""))
        if not cp_id:
            continue
        surfaces = [str(cp.get("name", ""))]
        for alias in cp.get("aliases") or ():
            surfaces.append(str(alias))
        best_bps = -1
        best_surface = ""
        best_tier = "TIER_4_TEXT_SIMILARITY_ONLY"
        for s in surfaces:
            if not s:
                continue
            s_norm = normalize_accounting_text(s)
            if q_norm and q_norm == s_norm:
                bps = 10000
                tier = "TIER_3_VERIFIED_ALIAS_SURFACE"
            else:
                bps = text_similarity_bps(counterparty_text, s)
                tier = "TIER_4_TEXT_SIMILARITY_ONLY"
            if bps > best_bps:
                best_bps = bps
                best_surface = s
                best_tier = tier
        if best_bps >= min_score_bps:
            scored.append(
                CandidateMatch(
                    entity_id=cp_id,
                    score_bps=best_bps,
                    matched_surface=best_surface,
                    tier=best_tier,
                    requires_structured_verification=True,
                )
            )
    scored.sort(key=lambda m: (-m.score_bps, m.entity_id))
    return tuple(scored[: max(0, top_k)])


def extract_typed_id_mentions(text: str) -> tuple[str, ...]:
    """Extract canonical typed ID mentions from untrusted free-text narratives."""
    if not isinstance(text, str) or not text:
        return ()
    seen: dict[str, None] = {}
    for m in _TYPED_ID_MENTION_RE.finditer(text):
        seen[m.group(0)] = None
    return tuple(seen.keys())


__all__ = [
    "CandidateMatch",
    "extract_typed_id_mentions",
    "rank_counterparty_candidates",
    "text_similarity_bps",
]
