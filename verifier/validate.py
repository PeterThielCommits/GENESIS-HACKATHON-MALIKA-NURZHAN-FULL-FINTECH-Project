"""Validation of VerifierReport against frozen public contracts (TZ 13.3).

Checks:
  1. JSON schema conformance against ``contracts/verifier_report.schema.json``;
  2. When ``public_episode`` is provided: ``episode_public_hash`` match and
     public-tool reachability + size bounds (REQ-VER-010, REQ-VER-011, REQ-VER-014);
  3. When ``proof_graph`` is provided: DAG acyclicity, REQ-VER-003/004 path
     invariants, and every finding's ``proof_graph_ref`` resolves to a valid
     ``FindingNode``.

Dependencies: ``contracts`` + ``verifier`` stdlib helpers only (never ``gen``).
"""

from __future__ import annotations

from typing import Any

from contracts.loader import validate_instance
from verifier.evidence import check_evidence_reachability
from verifier.proof_graph import ProofGraph
from verifier.public_loader import PublicEpisode
from verifier.result import ValidationResult, VerifierFinding, VerifierReport


def _finding_from_dict(item: dict[str, Any]) -> VerifierFinding:
    return VerifierFinding(
        type=str(item["type"]),
        affected_ids=tuple(str(x) for x in item["affected_ids"]),
        claimed_amount_minor=int(item["claimed_amount_minor"]),
        currency=str(item["currency"]),
        evidence_sets=tuple(tuple(str(x) for x in s) for s in item["evidence_sets"]),
        explanation_code=str(item["explanation_code"]),
        proof_graph_ref=str(item.get("proof_graph_ref", "")),
    )


def validate_report(
    report: VerifierReport | dict[str, Any],
    public_episode: PublicEpisode | None = None,
    proof_graph: ProofGraph | None = None,
) -> ValidationResult:
    """Validate a verifier report against frozen schemas and public contracts."""
    report_dict = report.to_dict() if isinstance(report, VerifierReport) else report
    errors: list[str] = []

    if not isinstance(report_dict, dict):
        return ValidationResult(valid=False, errors=("report must be a VerifierReport or dict",))

    schema_errors = validate_instance("verifier_report", report_dict)
    errors.extend(schema_errors)
    if schema_errors:
        return ValidationResult(valid=False, errors=tuple(errors))

    findings = tuple(_finding_from_dict(f) for f in report_dict.get("findings", ()))

    if public_episode is not None:
        if report_dict["episode_public_hash"] != public_episode.episode_public_hash:
            errors.append(
                "episode_public_hash mismatch between report and public episode"
            )
        reach = check_evidence_reachability(public_episode, findings)
        errors.extend(reach.errors)

    if proof_graph is not None:
        reachable = (
            public_episode.all_reachable_typed_ids()
            if public_episode is not None
            else None
        )
        errors.extend(proof_graph.validate(reachable_typed_ids=reachable))
        for idx, finding in enumerate(findings):
            ref = finding.proof_graph_ref
            if not ref.startswith("proof:"):
                errors.append(
                    f"finding[{idx}]: missing or invalid proof_graph_ref {ref!r} (REQ-VER-003)"
                )
                continue
            node_id = ref[len("proof:"):]
            node = proof_graph.get_node(node_id)
            if node is None or node.node_type != "FindingNode":
                errors.append(
                    f"finding[{idx}]: proof_graph_ref {ref!r} does not resolve to a FindingNode"
                )

    return ValidationResult(valid=not errors, errors=tuple(errors))


__all__ = ["validate_report"]
