"""Independent Stage-1 runner: discovery, evidence minimality, report.

Second derivation of the verification pipeline. Public data only; never reads
``hidden/``; never imports the generator. Output conforms to
``contracts/verifier_report.schema.json`` plus ``x_twinledger_*`` diagnostic
purposes are confined to ``deterministic_diagnostics``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from independent_verifier import algos_fx_cutoff
from independent_verifier.algos import (
    discover_duplicates,
    discover_partial_allocation,
)
from independent_verifier.loader import load_public_dir, subset_public_data
from independent_verifier.proof_graph import ProofGraph

VERIFIER_VERSION = "independent-1.0.0"
MAX_EVIDENCE_SETS = 32
MAX_EVIDENCE_IDS = 20


@dataclass
class IndependentRun:
    report: dict[str, Any]
    graph: ProofGraph
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _discovery(data):
    findings = []
    findings.extend(discover_duplicates(data))
    findings.extend(discover_partial_allocation(data))
    fx_findings, fx_amb = algos_fx_cutoff.discover_fx_rate_mismatch(data)
    findings.extend(fx_findings)
    cut_findings, cut_amb = algos_fx_cutoff.discover_period_cutoff(data)
    findings.extend(cut_findings)
    return findings, [*fx_amb, *cut_amb]


def _signature(f) -> tuple[str, tuple[str, ...], int, str]:
    return (f.type, tuple(sorted(f.affected_ids)), int(f.claimed_amount_minor), f.currency)


def _rederives(public_dir: Path, allowed_ids, target_signature) -> bool:
    data = load_public_dir(public_dir)
    subset = subset_public_data(data, set(allowed_ids))
    found, _ = _discovery(subset)
    return any(_signature(f) == target_signature for f in found)


def _minimize(public_dir: Path, candidate: list[str], target_signature) -> list[str] | None:
    current = sorted(set(candidate))
    if not current or len(current) > MAX_EVIDENCE_IDS:
        return None
    if not _rederives(public_dir, current, target_signature):
        return None
    changed = True
    while changed:
        changed = False
        for elem in list(current):
            trial = [x for x in current if x != elem]
            if not trial:
                continue
            if _rederives(public_dir, trial, target_signature):
                current = trial
                changed = True
                break
    return current


def run_episode(public_dir: str | Path) -> IndependentRun:
    public_path = Path(public_dir)
    data = load_public_dir(public_path)
    findings, ambiguities = _discovery(data)

    report_findings: list[dict[str, Any]] = []
    enumeration_complete = True
    diagnostics: dict[str, Any] = {"ablation": {}, "evidence_failures": []}
    graph_inputs: list[tuple[Any, list[list[str]]]] = []

    for finding in findings:
        sig = _signature(finding)
        min_sets: list[list[str]] = []
        seen: set[tuple[str, ...]] = set()
        for candidate in finding.evidence_candidates:
            if len(min_sets) >= MAX_EVIDENCE_SETS:
                enumeration_complete = False
                break
            reduced = _minimize(public_path, candidate, sig)
            if reduced is None:
                continue
            key = tuple(reduced)
            if key not in seen:
                seen.add(key)
                min_sets.append(reduced)
        min_sets.sort(key=lambda s: (len(s), s))
        # Drop any non-minimal superset of an already-kept set.
        strict: list[list[str]] = []
        for cand in min_sets:
            candfs = frozenset(cand)
            if any(frozenset(prev).issubset(candfs) and len(prev) < len(candfs) for prev in strict):
                continue
            strict.append(cand)
        min_sets = strict[:MAX_EVIDENCE_SETS]
        if not min_sets:
            diagnostics["evidence_failures"].append(
                f"{finding.type}:{sorted(finding.affected_ids)}:no minimal sufficient evidence set found"
            )
            ambiguities = [*ambiguities, f"{finding.type}:no minimal sufficient evidence set"]
            # Without evidence the finding cannot be published (REQ-VER-013).
            continue
        if len(min_sets) >= MAX_EVIDENCE_SETS:
            enumeration_complete = False
        # Full-deletion ablation: S removed from the full episode must break re-derivation.
        full_deletion_breaks = False
        if min_sets:
            best = set(min_sets[0])
            remaining = sorted(data.all_typed_ids() - best)
            data_remaining = subset_public_data(data, set(remaining))
            found, _ = _discovery(data_remaining)
            full_deletion_breaks = not any(_signature(f) == sig for f in found)
        diagnostics["ablation"][f"{finding.type}:{sig[1][0] if sig[1] else ''}"] = {
            "evidence_sets": len(min_sets),
            "full_deletion_breaks_proof": bool(full_deletion_breaks),
        }
        graph_inputs.append((finding, min_sets))
        report_findings.append(
            {
                "type": finding.type,
                "affected_ids": sorted(finding.affected_ids),
                "claimed_amount_minor": int(finding.claimed_amount_minor),
                "currency": finding.currency,
                "evidence_sets": min_sets,
                "explanation_code": finding.explanation_code,
            }
        )

    graph = _build_graph(graph_inputs)
    inv_errors = graph.check_invariants()
    graph_ref = graph.ref()
    for rf in report_findings:
        rf["proof_graph_ref"] = graph_ref
    if inv_errors:
        diagnostics["proof_graph_invariant_errors"] = inv_errors

    report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "episode_public_hash": data.episode_public_hash,
        "findings": report_findings,
        "examined_public_sources": data.examined_public_sources,
        "unresolved_ambiguities": sorted(set(ambiguities)),
        "verifier_version": VERIFIER_VERSION,
        "deterministic_diagnostics": {
            "ablation": diagnostics["ablation"],
            "evidence_failures": diagnostics["evidence_failures"],
            "proof_graph_invariant_errors": diagnostics.get("proof_graph_invariant_errors", []),
            "evidence_enumeration_complete": enumeration_complete,
            "independent_implementation": True,
        },
    }
    return IndependentRun(report=report, graph=graph, diagnostics=diagnostics)


def _build_graph(graph_inputs) -> ProofGraph:
    graph = ProofGraph()
    for finding, evidence_sets in graph_inputs:
        rule_node = graph.add_node(
            "RuleNode",
            [finding.rule_id],
            finding.rule_id,
            [],
            value_note=f"rule:{finding.rule_id}",
        )
        calc_node = graph.add_node(
            "CalculationNode",
            list(finding.affected_ids),
            finding.rule_id,
            [rule_node],
            value_note=f"calc:{finding.claimed_amount_minor}:{finding.currency}",
        )
        for tid in finding.affected_ids:
            record = graph.add_node("RecordNode", [tid], finding.rule_id, [], value_note=f"rec:{tid}")
            graph.add_supports(record, calc_node)
        finding_node = graph.add_node(
            "FindingNode",
            list(finding.affected_ids),
            finding.rule_id,
            [calc_node],
            value_note=f"find:{finding.type}:{finding.claimed_amount_minor}:{finding.currency}",
        )
        # Data-flow direction (evidence flows toward the finding), so the
        # graph stays a strict DAG: rule -> finding governs edge.
        graph.add_governed_by(rule_node, finding_node)
    return graph


def compare_to_committed(report: dict[str, Any], committed_path: str | Path) -> dict[str, Any]:
    """Signature-level comparison against a committed verifier_report.json."""
    committed = json.loads(Path(committed_path).read_text(encoding="utf-8"))

    def sigs(d):
        return {
            (f["type"], tuple(sorted(f["affected_ids"])), int(f["claimed_amount_minor"]), f["currency"])
            for f in d.get("findings", [])
        }

    mine = sigs(report)
    theirs = sigs(committed)
    return {
        "independent_findings": len(mine),
        "committed_findings": len(theirs),
        "matching": len(mine & theirs),
        "only_independent": sorted(
            {"|".join([t, ",".join(a), str(m), c]) for t, a, m, c in mine - theirs}
        ),
        "only_committed": sorted(
            {"|".join([t, ",".join(a), str(m), c]) for t, a, m, c in theirs - mine}
        ),
        "episode_public_hash_match": report.get("episode_public_hash")
        == committed.get("episode_public_hash"),
    }
