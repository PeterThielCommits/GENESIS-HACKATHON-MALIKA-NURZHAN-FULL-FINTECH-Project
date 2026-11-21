"""Minimal evidence set reduction and ablation verification (TZ 13.5, 21.3).

Formal minimality criterion (REQ-VER-012, REQ-VER-013):
  - Background context (``company.json``, ``policy.json``, ``accounts.json``,
    ``opening_balances.json``, ``period_calendar.json``) is always present.
  - A subject evidence set ``S`` is **sufficient** for finding signature
    ``sig = (type, affected_ids, claimed_amount_minor, currency)`` iff
    re-running the independent detector on ``subset_public_episode(ep, S)``
    re-derives ``sig``.
  - ``S`` is **minimal** iff it is sufficient AND for every ``e in S``,
    re-running the detector on ``subset_public_episode(ep, S - {e})`` fails
    to derive ``sig``.
  - Full-set deletion ablation (TZ 21.3): removing all elements of ``S`` from
    the full episode eliminates the proof path relying on ``S``.

Dependencies: ``contracts`` + ``verifier`` stdlib helpers only (never ``gen``).
"""

from __future__ import annotations

from typing import Callable

from verifier.proof_graph import ProofGraph
from verifier.public_loader import PublicEpisode, subset_public_episode
from verifier.result import (
    MAX_SCHEMA_EVIDENCE_IDS,
    MAX_SCHEMA_EVIDENCE_SETS,
    AblationFindingSummary,
    VerifierFinding,
)

DetectorFn = Callable[[PublicEpisode, ProofGraph], tuple[VerifierFinding, ...]]


def _re_derives_signature(
    episode: PublicEpisode,
    allowed_ids: tuple[str, ...] | frozenset[str],
    target_signature: tuple[str, tuple[str, ...], int, str],
    detector_fn: DetectorFn,
) -> bool:
    """Return True iff running ``detector_fn`` on ``allowed_ids`` derives ``target_signature``."""
    sub_ep = subset_public_episode(episode, allowed_ids)
    scratch = ProofGraph(sub_ep.episode_public_hash)
    found = detector_fn(sub_ep, scratch)
    return any(f.signature == target_signature for f in found)


def minimize_evidence_set(
    episode: PublicEpisode,
    evidence_set: tuple[str, ...],
    target_signature: tuple[str, tuple[str, ...], int, str],
    detector_fn: DetectorFn,
) -> tuple[str, ...] | None:
    """Deterministically shrink a sufficient evidence set until strictly minimal.

    Returns ``None`` if the initial set is not sufficient.
    """
    current = list(sorted(set(evidence_set)))
    if not current:
        return None
    if not _re_derives_signature(episode, tuple(current), target_signature, detector_fn):
        return None

    # Greedy deterministic pruning in sorted order until no single element is removable
    changed = True
    while changed:
        changed = False
        for elem in list(current):
            candidate = tuple(x for x in current if x != elem)
            if not candidate:
                continue
            if _re_derives_signature(episode, candidate, target_signature, detector_fn):
                current = list(candidate)
                changed = True
                break
    return tuple(current)


def refine_and_ablate_finding(
    episode: PublicEpisode,
    finding: VerifierFinding,
    detector_fn: DetectorFn,
    *,
    max_evidence_sets: int = MAX_SCHEMA_EVIDENCE_SETS,
) -> tuple[VerifierFinding, AblationFindingSummary]:
    """Minimize candidate evidence sets and run full ablation proof checks.

    Returns ``(updated_finding, ablation_summary)``.
    """
    policy_cap = min(
        int(episode.policy.get("max_evidence_ids", MAX_SCHEMA_EVIDENCE_IDS)),
        MAX_SCHEMA_EVIDENCE_IDS,
    )
    sig = finding.signature
    failures: list[str] = []

    minimized: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    complete = finding.evidence_enumeration_complete

    for raw_set in finding.evidence_sets:
        reduced = minimize_evidence_set(episode, raw_set, sig, detector_fn)
        if reduced is None:
            failures.append(f"candidate set {list(raw_set)} is NOT sufficient (REQ-VER-013)")
            continue
        if len(reduced) > policy_cap:
            failures.append(
                f"minimal set {list(reduced)} size {len(reduced)} exceeds cap {policy_cap} (REQ-VER-011)"
            )
            continue
        if reduced not in seen:
            seen.add(reduced)
            minimized.append(reduced)

    # Remove any non-minimal superset if a strictly smaller set is also present
    minimized.sort(key=lambda s: (len(s), s))
    strict_sets: list[tuple[str, ...]] = []
    for cand in minimized:
        cand_fs = frozenset(cand)
        if any(frozenset(prev).issubset(cand_fs) for prev in strict_sets):
            continue
        strict_sets.append(cand)

    if len(strict_sets) > max_evidence_sets:
        strict_sets = strict_sets[:max_evidence_sets]
        complete = False

    if not strict_sets:
        failures.append("no sufficient minimal evidence set survived reduction")
        summary = AblationFindingSummary(
            finding_signature=sig,
            evidence_sets_checked=0,
            all_sufficient=False,
            all_minimal=False,
            full_deletion_breaks_proof=False,
            evidence_enumeration_complete=complete,
            failures=tuple(failures),
        )
        return finding, summary

    # Independent verification pass on every retained set:
    # 1. Sufficiency (REQ-VER-013)
    # 2. Single-element ablation minimality (REQ-VER-012)
    # 3. Full-set deletion ablation against full episode (TZ 21.3)
    all_sufficient = True
    all_minimal = True
    full_deletion_breaks = True
    full_ids = episode.all_reachable_typed_ids()

    for ev_set in strict_sets:
        if not _re_derives_signature(episode, ev_set, sig, detector_fn):
            all_sufficient = False
            failures.append(f"sufficiency failed for {list(ev_set)}")
            continue
        for elem in ev_set:
            ablated = tuple(x for x in ev_set if x != elem)
            if ablated and _re_derives_signature(episode, ablated, sig, detector_fn):
                all_minimal = False
                failures.append(
                    f"minimality failed: removing {elem!r} from {list(ev_set)} still proves finding"
                )
        remaining_ids = full_ids - frozenset(ev_set)
        if _re_derives_signature(episode, remaining_ids, sig, detector_fn):
            full_deletion_breaks = False
            failures.append(
                f"full-set deletion of {list(ev_set)} did not break finding proof"
            )

    updated = VerifierFinding(
        type=finding.type,
        affected_ids=finding.affected_ids,
        claimed_amount_minor=finding.claimed_amount_minor,
        currency=finding.currency,
        evidence_sets=tuple(strict_sets),
        explanation_code=finding.explanation_code,
        proof_graph_ref=finding.proof_graph_ref,
        evidence_enumeration_complete=complete,
    )
    summary = AblationFindingSummary(
        finding_signature=sig,
        evidence_sets_checked=len(strict_sets),
        all_sufficient=all_sufficient,
        all_minimal=all_minimal,
        full_deletion_breaks_proof=full_deletion_breaks,
        evidence_enumeration_complete=complete,
        failures=tuple(failures),
    )
    return updated, summary


__all__ = [
    "DetectorFn",
    "minimize_evidence_set",
    "refine_and_ablate_finding",
]
