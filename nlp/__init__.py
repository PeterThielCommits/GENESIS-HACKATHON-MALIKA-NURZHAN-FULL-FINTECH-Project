"""TwinLedger multilingual normalization, candidate matching, and evidence hierarchy (Phases 10–11).

Lazy facade (PEP 562): importing :mod:`nlp` itself loads NO submodules. Each
public name is resolved on first attribute access from its defining submodule,
so core consumers that need only the strict TZ §17.3 rule module
(:mod:`nlp.hierarchy`) never load the optional fuzzy helpers
(:mod:`nlp.matching`, :mod:`nlp.normalize`) — Phase 10 EXIT GATE:
the NLP layer is fully optional for core semantics.
"""

from __future__ import annotations

import importlib
from typing import Any

_EXPORTS: dict[str, str] = {
    "CandidateMatch": "nlp.matching",
    "EVIDENCE_TIERS": "nlp.hierarchy",
    "EvidenceSupportAssessment": "nlp.hierarchy",
    "LEGAL_FORM_SYNONYMS": "nlp.normalize",
    "TextOnlyProofRejectedError": "nlp.hierarchy",
    "UntrustedTextInspection": "nlp.injection_guard",
    "assess_evidence_reachability": "nlp.hierarchy",
    "assess_evidence_support": "nlp.hierarchy",
    "build_evidence_hierarchy_report": "nlp.hierarchy",
    "char_ngrams": "nlp.normalize",
    "extract_typed_id_mentions": "nlp.matching",
    "inspect_untrusted_text": "nlp.injection_guard",
    "normalize_accounting_text": "nlp.normalize",
    "normalize_nfc": "nlp.normalize",
    "rank_counterparty_candidates": "nlp.matching",
    "require_structural_proof": "nlp.hierarchy",
    "text_similarity_bps": "nlp.matching",
    "transliterate_to_ascii_skeleton": "nlp.normalize",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    mod_name = _EXPORTS.get(name)
    if mod_name is None:
        raise AttributeError(f"module 'nlp' has no attribute {name!r}")
    value = getattr(importlib.import_module(mod_name), name)
    globals()[name] = value  # cache for subsequent access
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))
