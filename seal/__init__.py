"""Commit-reveal, trajectory hash chain, Merkle tree, and offline receipts (Phase 9, Zone 2).

Imports ONLY ``contracts/`` and Python 3.11 stdlib.
"""

from seal.commitment import (
    COMMITMENT_INTEGRITY_NOTE,
    SALT_MODES,
    CommitmentBundle,
    RevealResult,
    compute_commitment,
    create_commitment_bundle,
    deterministic_fixture_salt,
    generate_secret_salt,
    verify_episode_commitment_from_disk,
    verify_reveal,
)
from seal.hashchain import (
    EVENT_DOMAIN,
    GENESIS_DOMAIN,
    ChainVerificationResult,
    HashChainBuilder,
    compute_event_hash,
    compute_initial_hash,
    compute_payload_digest,
    verify_hash_chain,
)
from seal.merkle import (
    EMPTY_TREE_ROOT,
    LEAF_DOMAIN_PREFIX,
    NODE_DOMAIN_PREFIX,
    MerkleProofStep,
    MerkleTree,
    internal_node_hash,
    leaf_hash,
    verify_inclusion_proof,
)
from seal.receipt import (
    RECEIPT_INTEGRITY_NOTE,
    ReceiptVerificationResult,
    build_lineage_digests,
    build_receipt,
    compute_code_version_hash,
    compute_manifest_hash,
    seal_receipt_batch,
    verify_receipt_offline,
)
from seal.rekey import (
    ProductionRekeyResult,
    rekey_episode_with_production_salt,
)

__all__ = [
    "COMMITMENT_INTEGRITY_NOTE",
    "EMPTY_TREE_ROOT",
    "EVENT_DOMAIN",
    "GENESIS_DOMAIN",
    "LEAF_DOMAIN_PREFIX",
    "NODE_DOMAIN_PREFIX",
    "RECEIPT_INTEGRITY_NOTE",
    "SALT_MODES",
    "ChainVerificationResult",
    "CommitmentBundle",
    "HashChainBuilder",
    "MerkleProofStep",
    "MerkleTree",
    "ProductionRekeyResult",
    "ReceiptVerificationResult",
    "RevealResult",
    "build_lineage_digests",
    "build_receipt",
    "compute_code_version_hash",
    "compute_commitment",
    "compute_event_hash",
    "compute_initial_hash",
    "compute_manifest_hash",
    "compute_payload_digest",
    "create_commitment_bundle",
    "deterministic_fixture_salt",
    "generate_secret_salt",
    "internal_node_hash",
    "leaf_hash",
    "rekey_episode_with_production_salt",
    "seal_receipt_batch",
    "verify_episode_commitment_from_disk",
    "verify_hash_chain",
    "verify_inclusion_proof",
    "verify_receipt_offline",
    "verify_reveal",
]
