"""Independent verifier (Zone 3, Owner C). Public-only discovery and ProofGraph.

Depends ONLY on ``contracts`` and Python 3.11 stdlib. Never imports ``gen``.
Stage-2 truth crosscheck lives separately in ``scoring.crosscheck``.
"""

from verifier.discover import discover
from verifier.evidence import (
    BACKGROUND_CONTEXT_FILES,
    PUBLIC_TOOL_ROUTES,
    ReachabilityReport,
    check_evidence_reachability,
    tool_routes_for_typed_id,
    verify_ids_reachable,
)
from verifier.proof_graph import EDGE_TYPES, NODE_TYPES, ProofEdge, ProofGraph, ProofNode
from verifier.public_loader import (
    ALLOWED_PUBLIC_FILES,
    FORBIDDEN_PUBLIC_FILES,
    PublicEpisode,
    PublicEpisodeError,
    build_public_episode,
    fx_row_typed_id,
    load_public_episode,
    make_typed_id,
    subset_public_episode,
)
from verifier.result import (
    VERIFIER_VERSION,
    AblationFindingSummary,
    DiscoveryOutput,
    ValidationResult,
    VerifierConfig,
    VerifierFinding,
    VerifierReport,
)
from verifier.validate import validate_report

__all__ = [
    "ALLOWED_PUBLIC_FILES",
    "AblationFindingSummary",
    "BACKGROUND_CONTEXT_FILES",
    "DiscoveryOutput",
    "EDGE_TYPES",
    "FORBIDDEN_PUBLIC_FILES",
    "NODE_TYPES",
    "PUBLIC_TOOL_ROUTES",
    "ProofEdge",
    "ProofGraph",
    "ProofNode",
    "PublicEpisode",
    "PublicEpisodeError",
    "ReachabilityReport",
    "VERIFIER_VERSION",
    "ValidationResult",
    "VerifierConfig",
    "VerifierFinding",
    "VerifierReport",
    "build_public_episode",
    "check_evidence_reachability",
    "discover",
    "fx_row_typed_id",
    "load_public_episode",
    "make_typed_id",
    "subset_public_episode",
    "tool_routes_for_typed_id",
    "validate_report",
    "verify_ids_reachable",
]
