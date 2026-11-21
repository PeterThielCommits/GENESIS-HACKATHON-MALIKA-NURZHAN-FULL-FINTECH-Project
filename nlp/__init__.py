"""TwinLedger multilingual normalization, candidate matching, and evidence hierarchy (Phases 10–11)."""

from nlp.hierarchy import (
    EVIDENCE_TIERS,
    EvidenceSupportAssessment,
    TextOnlyProofRejectedError,
    assess_evidence_support,
    require_structural_proof,
)
from nlp.injection_guard import UntrustedTextInspection, inspect_untrusted_text
from nlp.matching import (
    CandidateMatch,
    extract_typed_id_mentions,
    rank_counterparty_candidates,
    text_similarity_bps,
)
from nlp.normalize import (
    LEGAL_FORM_SYNONYMS,
    char_ngrams,
    normalize_accounting_text,
    normalize_nfc,
    transliterate_to_ascii_skeleton,
)

__all__ = [
    "CandidateMatch",
    "EVIDENCE_TIERS",
    "EvidenceSupportAssessment",
    "LEGAL_FORM_SYNONYMS",
    "TextOnlyProofRejectedError",
    "UntrustedTextInspection",
    "assess_evidence_support",
    "char_ngrams",
    "extract_typed_id_mentions",
    "inspect_untrusted_text",
    "normalize_accounting_text",
    "normalize_nfc",
    "rank_counterparty_candidates",
    "require_structural_proof",
    "text_similarity_bps",
    "transliterate_to_ascii_skeleton",
]
