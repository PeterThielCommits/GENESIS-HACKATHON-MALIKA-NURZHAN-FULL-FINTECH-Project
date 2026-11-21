"""Evidence reachability and public-tool coverage verification (TZ 13.5).

Verifies:
  - REQ-VER-010: every typed ID in ``affected_ids`` and ``evidence_sets`` is
    reachable through supported public tools (``list_records``, ``get_record``,
    ``get_document``) over the public tables of ``PublicEpisode``;
  - REQ-VER-011: every evidence set satisfies ``1 <= len(set) <= min(policy.max_evidence_ids, 20)``;
  - REQ-VER-014: unreachable facts/IDs produce explicit reachability errors so
    an episode cannot be published with unprovable findings.

Dependencies: ``contracts`` + ``verifier`` stdlib helpers only (never ``gen``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from verifier.public_loader import PublicEpisode
from verifier.result import MAX_SCHEMA_EVIDENCE_IDS, VerifierFinding

#: Mapping from typed-ID namespace to supported public tool access paths (TZ 14.2).
PUBLIC_TOOL_ROUTES: dict[str, tuple[str, ...]] = {
    "JE": ("list_records:journal_entries", "get_record:journal_entries"),
    "INV": ("list_records:invoices", "get_record:invoices", "get_document"),
    "CN": ("list_records:credit_notes", "get_record:credit_notes"),
    "PAY": ("list_records:payments", "get_record:payments"),
    "BANK": ("list_records:bank_lines", "get_record:bank_lines"),
    "FX": ("list_records:fx_rates", "get_record:fx_rates"),
    "CP": ("list_records:counterparties", "get_record:counterparties"),
}

#: Background context files available to every policy without consuming evidence_ids slots.
BACKGROUND_CONTEXT_FILES: tuple[str, ...] = (
    "company.json",
    "policy.json",
    "accounts.json",
    "opening_balances.json",
    "period_calendar.json",
)


@dataclass(frozen=True)
class ReachabilityReport:
    """Result of checking reachability and evidence-set size limits."""

    all_reachable: bool
    unreachable_ids: tuple[str, ...]
    oversized_sets: tuple[str, ...]
    errors: tuple[str, ...]


def tool_routes_for_typed_id(typed_id: str) -> tuple[str, ...]:
    """Return the public tool routes that can retrieve ``typed_id``."""
    namespace, _, _ = typed_id.partition(":")
    return PUBLIC_TOOL_ROUTES.get(namespace, ())


def check_evidence_reachability(
    episode: PublicEpisode,
    findings: Sequence[VerifierFinding],
) -> ReachabilityReport:
    """Verify every affected/evidence ID is reachable and within policy limits."""
    reachable = episode.all_reachable_typed_ids()
    policy_cap = int(episode.policy.get("max_evidence_ids", MAX_SCHEMA_EVIDENCE_IDS))
    effective_cap = min(policy_cap, MAX_SCHEMA_EVIDENCE_IDS)

    unreachable: set[str] = set()
    oversized: list[str] = []
    errors: list[str] = []

    for idx, finding in enumerate(findings):
        for aid in finding.affected_ids:
            if aid not in reachable or not tool_routes_for_typed_id(aid):
                unreachable.add(aid)
                errors.append(
                    f"finding[{idx}]: affected_id {aid!r} is not reachable via public tools (REQ-VER-010)"
                )
        if not finding.evidence_sets:
            errors.append(f"finding[{idx}]: evidence_sets must be non-empty")
            continue
        for s_idx, ev_set in enumerate(finding.evidence_sets):
            if len(ev_set) < 1:
                errors.append(f"finding[{idx}].evidence_sets[{s_idx}]: empty evidence set")
            if len(ev_set) > effective_cap:
                msg = (
                    f"finding[{idx}].evidence_sets[{s_idx}]: size {len(ev_set)} "
                    f"exceeds limit {effective_cap} (REQ-VER-011)"
                )
                oversized.append(msg)
                errors.append(msg)
            for eid in ev_set:
                if eid not in reachable or not tool_routes_for_typed_id(eid):
                    unreachable.add(eid)
                    errors.append(
                        f"finding[{idx}].evidence_sets[{s_idx}]: evidence_id {eid!r} "
                        "is not reachable via public tools (REQ-VER-010/REQ-VER-014)"
                    )

    return ReachabilityReport(
        all_reachable=not errors,
        unreachable_ids=tuple(sorted(unreachable)),
        oversized_sets=tuple(oversized),
        errors=tuple(errors),
    )


def verify_ids_reachable(
    episode: PublicEpisode,
    typed_ids: Iterable[str],
) -> tuple[bool, tuple[str, ...]]:
    """Return ``(all_ok, missing_ids)`` for an arbitrary collection of typed IDs."""
    reachable = episode.all_reachable_typed_ids()
    missing = sorted(
        tid for tid in set(typed_ids)
        if tid not in reachable or not tool_routes_for_typed_id(tid)
    )
    return (not missing), tuple(missing)


__all__ = [
    "BACKGROUND_CONTEXT_FILES",
    "PUBLIC_TOOL_ROUTES",
    "ReachabilityReport",
    "check_evidence_reachability",
    "tool_routes_for_typed_id",
    "verify_ids_reachable",
]
