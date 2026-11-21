"""Public-only discovery entry point for the independent verifier (Zone 3).

Implements Stage 1 of Master TZ sections 13.2-13.6:
  - Accepts ONLY a public episode directory or :class:`PublicEpisode`;
  - Runs the four independent detectors (DUPLICATE_PAYMENT,
    PARTIAL_PAYMENT_ALLOCATION, FX_RATE_MISMATCH, PERIOD_CUTOFF);
  - Builds a deterministic :class:`ProofGraph` DAG with explicit distractor
    exclusion edges;
  - Enforces public-tool reachability and runs minimal-evidence ablation;
  - Emits a schema-validated :class:`VerifierReport` and its canonical
    ``report_digest`` BEFORE any Stage-2 truth comparison can occur
    (REQ-ORG-003, REQ-VER-001, REQ-VER-021).

Dependencies: ``contracts`` + ``verifier`` stdlib helpers only (never ``gen``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from verifier.duplicate_payment import detect_duplicate_payments
from verifier.evidence import check_evidence_reachability
from verifier.fx_mismatch import detect_fx_mismatches
from verifier.minimal_sets import refine_and_ablate_finding
from verifier.partial_allocation import detect_partial_allocations
from verifier.period_cutoff import detect_period_cutoffs
from verifier.proof_graph import ProofGraph
from verifier.public_loader import PublicEpisode, load_public_episode
from verifier.result import (
    VERIFIER_VERSION,
    AblationFindingSummary,
    DiscoveryOutput,
    VerifierConfig,
    VerifierFinding,
    VerifierReport,
)
from verifier.validate import validate_report


def _run_detector_for_type(
    anomaly_type: str,
    episode: PublicEpisode,
    graph: ProofGraph,
    max_evidence_sets: int,
) -> tuple[VerifierFinding, ...]:
    if anomaly_type == "DUPLICATE_PAYMENT":
        return detect_duplicate_payments(
            episode, graph, max_evidence_sets=max_evidence_sets
        ).findings
    if anomaly_type == "PARTIAL_PAYMENT_ALLOCATION":
        return detect_partial_allocations(episode, graph).findings
    if anomaly_type == "FX_RATE_MISMATCH":
        return detect_fx_mismatches(
            episode, graph, max_evidence_sets=max_evidence_sets
        ).findings
    if anomaly_type == "PERIOD_CUTOFF":
        return detect_period_cutoffs(episode, graph).findings
    raise ValueError(f"unknown anomaly type: {anomaly_type!r}")


def _sort_findings(findings: list[VerifierFinding]) -> tuple[VerifierFinding, ...]:
    return tuple(
        sorted(
            findings,
            key=lambda f: (
                f.type,
                f.affected_ids,
                f.currency,
                f.claimed_amount_minor,
                f.explanation_code,
            ),
        )
    )


def discover(
    public_episode: PublicEpisode | str | Path,
    verifier_config: VerifierConfig | None = None,
) -> DiscoveryOutput:
    """Run independent public-only discovery and return report + ProofGraph.

    Never reads private directories or non-public artifacts.
    """
    config = verifier_config or VerifierConfig()
    episode = (
        public_episode
        if isinstance(public_episode, PublicEpisode)
        else load_public_episode(public_episode)
    )

    graph = ProofGraph(episode.episode_public_hash)
    raw_findings: list[VerifierFinding] = []
    ambiguities: list[str] = []

    dup_res = detect_duplicate_payments(
        episode, graph, max_evidence_sets=config.max_evidence_sets
    )
    raw_findings.extend(dup_res.findings)
    ambiguities.extend(dup_res.ambiguities)

    part_res = detect_partial_allocations(episode, graph)
    raw_findings.extend(part_res.findings)
    ambiguities.extend(part_res.ambiguities)

    fx_res = detect_fx_mismatches(
        episode, graph, max_evidence_sets=config.max_evidence_sets
    )
    raw_findings.extend(fx_res.findings)
    ambiguities.extend(fx_res.ambiguities)

    cut_res = detect_period_cutoffs(episode, graph)
    raw_findings.extend(cut_res.findings)
    ambiguities.extend(cut_res.ambiguities)

    ordered = _sort_findings(raw_findings)

    # Minimal evidence reduction and ablation proof checks (Task 8.4)
    final_findings: list[VerifierFinding] = []
    ablation_summaries: list[AblationFindingSummary] = []

    if config.run_ablation:
        for finding in ordered:
            def _det(ep: PublicEpisode, g: ProofGraph, _t: str = finding.type) -> tuple[VerifierFinding, ...]:
                return _run_detector_for_type(_t, ep, g, config.max_evidence_sets)

            updated, summary = refine_and_ablate_finding(
                episode,
                finding,
                _det,
                max_evidence_sets=config.max_evidence_sets,
            )
            final_findings.append(updated)
            ablation_summaries.append(summary)
    else:
        final_findings.extend(ordered)

    sorted_final = _sort_findings(final_findings)
    sorted_ambiguities = tuple(sorted(set(ambiguities)))

    reach = check_evidence_reachability(episode, sorted_final)
    graph_errors = graph.validate(reachable_typed_ids=episode.all_reachable_typed_ids())
    if not reach.all_reachable:
        sorted_ambiguities = tuple(
            sorted(set(sorted_ambiguities) | {f"UNREACHABLE_EVIDENCE:{e}" for e in reach.errors})
        )

    diagnostics: dict[str, Any] = {}
    if config.include_diagnostics:
        diagnostics = {
            "proof_graph_digest": graph.digest(),
            "proof_graph_nodes": len(graph.nodes),
            "proof_graph_edges": len(graph.edges),
            "proof_graph_exclusions": len(graph.exclusion_edges()),
            "proof_graph_valid": not graph_errors,
            "all_evidence_reachable": reach.all_reachable,
            "evidence_enumeration_complete_all": all(
                f.evidence_enumeration_complete for f in sorted_final
            ),
            "ablation_run": config.run_ablation,
            "ablation_summary": {
                "findings_checked": len(ablation_summaries),
                "all_sufficient": all(s.all_sufficient for s in ablation_summaries),
                "all_minimal": all(s.all_minimal for s in ablation_summaries),
                "all_full_deletion_breaks_proof": all(
                    s.full_deletion_breaks_proof for s in ablation_summaries
                ),
                "details": [s.to_dict() for s in ablation_summaries],
            },
        }

    report = VerifierReport(
        episode_public_hash=episode.episode_public_hash,
        findings=sorted_final,
        examined_public_sources=episode.examined_public_sources,
        unresolved_ambiguities=sorted_ambiguities,
        verifier_version=VERIFIER_VERSION,
        deterministic_diagnostics=diagnostics,
    )

    validation = validate_report(report, public_episode=episode, proof_graph=graph)
    if not validation.valid:
        raise ValueError(
            f"verifier produced invalid report: {'; '.join(validation.errors)}"
        )

    return DiscoveryOutput(
        report=report,
        proof_graph=graph,
        report_digest=report.digest(),
        ablation_results=tuple(ablation_summaries),
    )


__all__ = ["discover"]
