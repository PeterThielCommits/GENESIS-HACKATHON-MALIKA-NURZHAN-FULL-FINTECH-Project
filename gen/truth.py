"""Phase 4 structural diff & sealed truth commitment helpers.

Compares ``clean_twin`` vs ``mutated_twin`` to produce an auditable structural
diff summary (strictly stored in ``sealed/provenance.json``) and computes the
salted canonical SHA-256 ``truth_commitment`` published in ``manifest.json``
without leaking whether truth is empty or non-empty (REQ-DATA-020).
"""

from __future__ import annotations

from typing import Any, Sequence

from contracts.canonical import sha256_hex as canonical_sha256
from contracts.loader import validate_instance
from gen.core.clean_twin import CleanTwin


def compute_structural_diff(clean: CleanTwin, mutated: CleanTwin) -> dict[str, Any]:
    """Return a deterministic structural diff summary between clean and mutated twins."""
    table_specs = [
        ("invoices", "doc_id", clean.invoices, mutated.invoices),
        ("payments", "pay_id", clean.payments, mutated.payments),
        ("credit_notes", "credit_note_id", clean.credit_notes, mutated.credit_notes),
        ("bank_lines", "bank_line_id", clean.bank_lines, mutated.bank_lines),
        ("journal_entries", "je_id", clean.journal_entries, mutated.journal_entries),
        ("fx_rates", "fx_id", clean.fx_rates, mutated.fx_rates),
    ]
    diff: dict[str, Any] = {}
    for name, pk, c_rows, m_rows in table_specs:
        c_map = {r[pk]: r for r in c_rows}
        m_map = {r[pk]: r for r in m_rows}
        added = sorted(set(m_map) - set(c_map))
        removed = sorted(set(c_map) - set(m_map))
        modified = sorted(k for k in (set(c_map) & set(m_map)) if c_map[k] != m_map[k])
        if added or removed or modified:
            diff[name] = {"added": added, "removed": removed, "modified": modified}
    return diff


def validate_truth_list(truths: Sequence[dict[str, Any]]) -> list[str]:
    """Validate every truth finding against frozen ``contracts/truth.schema.json``."""
    errors: list[str] = []
    seen_ids: set[str] = set()
    for i, item in enumerate(truths):
        for err in validate_instance("truth", item):
            errors.append(f"truth[{i}]: {err}")
        tid = item.get("truth_id")
        if tid in seen_ids:
            errors.append(f"truth[{i}]: duplicate truth_id {tid!r}")
        if isinstance(tid, str):
            seen_ids.add(tid)
    return errors


def compute_truth_commitment(truths: Sequence[dict[str, Any]], salt_hex: str) -> str:
    """Compute a salted SHA-256 commitment over canonical truth findings.

    Using a per-episode secret salt (stored only in ``sealed/``) ensures the
    public ``manifest.json`` cannot distinguish clean episodes (empty truth)
    from mutated episodes via hash lookup.
    """
    if not isinstance(salt_hex, str) or len(salt_hex) < 32:
        raise ValueError("salt_hex must be at least 32 hex chars")
    payload = {"salt": salt_hex, "truths": list(truths)}
    return canonical_sha256(payload)


__all__ = [
    "compute_structural_diff",
    "compute_truth_commitment",
    "validate_truth_list",
]
