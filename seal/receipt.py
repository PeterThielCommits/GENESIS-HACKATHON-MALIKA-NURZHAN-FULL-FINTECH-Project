"""Offline-verifiable episode receipts and data lineage digests (Phase 9, Task 9.6).

Implements Master TZ v3.0.0 §16.5, §21.7, and REQ-SEAL-020..023:
  - Produces receipts strictly conforming to frozen ``contracts/receipt.schema.json``
    (v1.0.0) with namespaced ``x_twinledger_*`` extensions for Merkle root,
    inclusion proof, reveal reference, reward breakdown digest, isolation
    profile summary, and episode provenance lineage digests.
  - ``seal_receipt_batch`` computes the batch Merkle tree over ``trajectory_head``
    leaves and embeds inclusion proofs into every receipt.
  - ``verify_receipt_offline`` validates schema, manifest linkage, commit-reveal,
    trajectory hash chain, and Merkle inclusion completely offline (REQ-SEAL-020).

Imports ONLY ``contracts/``, ``seal.*``, and Python 3.11 stdlib.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from contracts.canonical import canonical_bytes, sha256_bytes, sha256_hex
from contracts.loader import validate_instance
from contracts.models import Receipt, TrajectoryEvent, TruthFinding
from contracts.version import PROTOCOL_VERSION
from seal.commitment import verify_reveal
from seal.hashchain import verify_hash_chain
from seal.merkle import MerkleTree, verify_inclusion_proof

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

REPO_ROOT = Path(__file__).resolve().parent.parent

RECEIPT_INTEGRITY_NOTE = (
    "Receipt, lineage digests, and Merkle root attest to cryptographic integrity "
    "and replay provenance; they do not by themselves certify finding quality "
    "(REQ-SEAL-023)."
)

_CODE_HASH_TARGETS: tuple[str, ...] = (
    "judge_adapter.py",
    "contracts",
    "core",
    "invariants",
    "gen",
    "verifier",
    "env",
    "harness",
    "scoring",
    "seal",
    "adapter",
)


def compute_code_version_hash(repo_root: Path | str | None = None) -> str:
    """Compute a deterministic offline SHA-256 over core source files (no git required)."""
    root = Path(repo_root).resolve() if repo_root is not None else REPO_ROOT
    hasher = hashlib.sha256()
    hasher.update(b"twinledger:code-version:v1\n")
    files: list[Path] = []
    for rel in _CODE_HASH_TARGETS:
        target = root / rel
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            for p in target.rglob("*"):
                if (
                    p.is_file()
                    and "__pycache__" not in p.parts
                    and p.suffix in (".py", ".json", ".yaml", ".md")
                ):
                    files.append(p)
    for p in sorted(set(files), key=lambda x: x.relative_to(root).as_posix()):
        rel_posix = p.relative_to(root).as_posix()
        hasher.update(rel_posix.encode("utf-8") + b"\x00")
        hasher.update(hashlib.sha256(p.read_bytes()).digest() + b"\n")
    return hasher.hexdigest()


def compute_manifest_hash(manifest: dict[str, Any] | bytes | Path) -> str:
    """Compute canonical SHA-256 digest of a public ``manifest.json``."""
    if isinstance(manifest, Path):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        return sha256_hex(data)
    if isinstance(manifest, bytes):
        data = json.loads(manifest.decode("utf-8"))
        return sha256_hex(data)
    if isinstance(manifest, dict):
        return sha256_hex(manifest)
    raise TypeError(f"unsupported manifest type: {type(manifest).__name__}")


def build_lineage_digests(
    *,
    generator_version: str,
    config_hash: str,
    public_manifest_hash: str,
    truth_commitment: str,
    trajectory_head: str,
    verifier_report_hash: str | None = None,
    scorer_report_hash: str | None = None,
    clean_twin_hash: str | None = None,
    mutation_diff_hash: str | None = None,
) -> dict[str, Any]:
    """Build episode provenance digest chain (Master TZ §21.7)."""
    lineage: dict[str, Any] = {
        "generator_version": generator_version,
        "config_hash": config_hash,
        "clean_twin_hash": clean_twin_hash,
        "mutation_diff_hash": mutation_diff_hash,
        "verifier_report_hash": verifier_report_hash,
        "truth_commitment": truth_commitment,
        "public_manifest_hash": public_manifest_hash,
        "trajectory_head": trajectory_head,
        "scorer_report_hash": scorer_report_hash,
    }
    lineage["lineage_chain_digest"] = sha256_hex(lineage)
    return lineage


def build_receipt(
    *,
    episode_id: str,
    code_version_hash: str,
    config_hash: str,
    public_manifest_hash: str,
    truth_commitment: str,
    trajectory_head: str,
    policy_identifier: str,
    merkle_leaf_index: int = 0,
    verification_status: str = "VERIFIED",
    protocol_version: str = PROTOCOL_VERSION,
    merkle_root: str | None = None,
    merkle_leaf_count: int | None = None,
    merkle_proof: Sequence[dict[str, str]] | None = None,
    salt_reveal_ref: str | dict[str, Any] = "SEALED",
    reward_breakdown_ref: str | None = None,
    isolation_profile: dict[str, Any] | None = None,
    lineage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a frozen-schema-validated ``Receipt`` dictionary."""
    base = Receipt(
        episode_id=episode_id,
        code_version_hash=code_version_hash,
        config_hash=config_hash,
        public_manifest_hash=public_manifest_hash,
        truth_commitment=truth_commitment,
        trajectory_head=trajectory_head,
        merkle_leaf_index=merkle_leaf_index,
        policy_identifier=policy_identifier,
        verification_status=verification_status,
        protocol_version=protocol_version,
    ).to_dict()

    if merkle_root is None:
        tree = MerkleTree.from_leaves([trajectory_head])
        merkle_root = tree.root
        merkle_leaf_count = 1
        merkle_proof = [s.to_dict() for s in tree.inclusion_proof(0)]

    base["x_twinledger_merkle_root"] = merkle_root
    base["x_twinledger_merkle_leaf_count"] = 1 if merkle_leaf_count is None else merkle_leaf_count
    base["x_twinledger_merkle_proof"] = list(merkle_proof or [])
    base["x_twinledger_salt_reveal_ref"] = salt_reveal_ref
    base["x_twinledger_integrity_note"] = RECEIPT_INTEGRITY_NOTE
    if reward_breakdown_ref is not None:
        base["x_twinledger_reward_breakdown_ref"] = reward_breakdown_ref
    if isolation_profile is not None:
        base["x_twinledger_isolation_profile"] = isolation_profile
    if lineage is not None:
        base["x_twinledger_lineage"] = lineage

    errs = validate_instance("receipt", base)
    if errs:
        raise ValueError(f"built receipt failed frozen schema validation: {errs}")
    return base


def seal_receipt_batch(
    receipts: Sequence[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Compute a batch Merkle tree over ``receipts`` and embed inclusion proofs.

    Returns ``(merkle_root, updated_receipts)`` preserving the input sequence
    order as ``merkle_leaf_index = 0 .. len(receipts) - 1``.
    """
    leaves = [str(r["trajectory_head"]) for r in receipts]
    tree = MerkleTree.from_leaves(leaves)
    sealed: list[dict[str, Any]] = []
    for idx, orig in enumerate(receipts):
        updated = dict(orig)
        updated["merkle_leaf_index"] = idx
        updated["x_twinledger_merkle_root"] = tree.root
        updated["x_twinledger_merkle_leaf_count"] = tree.leaf_count
        updated["x_twinledger_merkle_proof"] = [s.to_dict() for s in tree.inclusion_proof(idx)]
        errs = validate_instance("receipt", updated)
        if errs:
            raise ValueError(f"batch receipt[{idx}] failed frozen schema validation: {errs}")
        sealed.append(updated)
    return tree.root, sealed


@dataclass(frozen=True)
class ReceiptVerificationResult:
    """Offline verification result for an episode receipt (REQ-SEAL-020)."""

    valid: bool
    schema_ok: bool
    manifest_ok: bool | None
    commitment_ok: bool | None
    trajectory_ok: bool | None
    merkle_ok: bool | None
    receipt_digest: str
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "schema_ok": self.schema_ok,
            "manifest_ok": self.manifest_ok,
            "commitment_ok": self.commitment_ok,
            "trajectory_ok": self.trajectory_ok,
            "merkle_ok": self.merkle_ok,
            "receipt_digest": self.receipt_digest,
            "errors": list(self.errors),
        }


def verify_receipt_offline(
    receipt: dict[str, Any],
    *,
    manifest: dict[str, Any] | None = None,
    trajectory_events: Sequence[TrajectoryEvent | dict[str, Any]] | None = None,
    revealed_truths: Sequence[TruthFinding | dict[str, Any]] | None = None,
    revealed_salt_hex: str | None = None,
    salt_mode: str = "PRODUCTION_SECRET",
    expected_merkle_root: str | None = None,
) -> ReceiptVerificationResult:
    """Verify a TwinLedger receipt completely offline (REQ-SEAL-020)."""
    errors: list[str] = []
    if not isinstance(receipt, dict):
        return ReceiptVerificationResult(
            valid=False,
            schema_ok=False,
            manifest_ok=None,
            commitment_ok=None,
            trajectory_ok=None,
            merkle_ok=None,
            receipt_digest="",
            errors=("receipt must be a JSON object",),
        )

    schema_errs = validate_instance("receipt", receipt)
    schema_ok = len(schema_errs) == 0
    errors.extend(schema_errs)
    receipt_digest = sha256_bytes(canonical_bytes(receipt)) if schema_ok else ""
    if not schema_ok:
        return ReceiptVerificationResult(
            valid=False,
            schema_ok=False,
            manifest_ok=None,
            commitment_ok=None,
            trajectory_ok=None,
            merkle_ok=None,
            receipt_digest=receipt_digest,
            errors=tuple(errors),
        )

    if receipt.get("verification_status") != "VERIFIED":
        errors.append(
            f"receipt verification_status is {receipt.get('verification_status')!r}, expected 'VERIFIED'"
        )

    # 1. Manifest linkage check
    manifest_ok: bool | None = None
    if manifest is not None:
        m_errs = validate_instance("episode_manifest", manifest)
        if m_errs:
            manifest_ok = False
            errors.append(f"invalid manifest: {m_errs[0]}")
        else:
            computed_m_hash = compute_manifest_hash(manifest)
            manifest_ok = (
                hmac.compare_digest(computed_m_hash, receipt["public_manifest_hash"])
                and manifest["episode_id"] == receipt["episode_id"]
                and hmac.compare_digest(manifest["truth_commitment"], receipt["truth_commitment"])
            )
            if not manifest_ok:
                errors.append("receipt fields do not match supplied manifest.json")

    # 2. Commit-reveal check (if salt/truths provided or embedded in judge reveal)
    commitment_ok: bool | None = None
    salt_to_check = revealed_salt_hex
    effective_salt_mode = salt_mode
    embedded_ref = receipt.get("x_twinledger_salt_reveal_ref")
    if salt_to_check is None and isinstance(embedded_ref, dict) and "salt_hex" in embedded_ref:
        salt_to_check = str(embedded_ref["salt_hex"])
        effective_salt_mode = str(embedded_ref.get("mode", salt_mode))

    if revealed_truths is not None or salt_to_check is not None:
        if revealed_truths is None or salt_to_check is None:
            commitment_ok = False
            errors.append("both revealed_truths and revealed_salt_hex are required for reveal verification")
        else:
            rev = verify_reveal(
                receipt["truth_commitment"],
                revealed_truths,
                salt_to_check,
                salt_mode=effective_salt_mode,
            )
            commitment_ok = rev.verified
            if not commitment_ok:
                errors.extend(rev.errors)

    # 3. Trajectory hash-chain check
    trajectory_ok: bool | None = None
    if trajectory_events is not None:
        chain_res = verify_hash_chain(
            receipt["truth_commitment"],
            receipt["episode_id"],
            trajectory_events,
            expected_head=receipt["trajectory_head"],
        )
        trajectory_ok = chain_res.valid
        if not trajectory_ok:
            errors.extend(chain_res.errors)

    # 4. Merkle inclusion check
    merkle_ok: bool | None = None
    root_to_check = expected_merkle_root or receipt.get("x_twinledger_merkle_root")
    if root_to_check is not None:
        proof_raw = receipt.get("x_twinledger_merkle_proof", [])
        leaf_count = receipt.get("x_twinledger_merkle_leaf_count", 1)
        if not isinstance(root_to_check, str) or not _HEX64_RE.match(root_to_check):
            merkle_ok = False
            errors.append("invalid Merkle root format in receipt")
        elif not isinstance(proof_raw, list) or type(leaf_count) is not int or isinstance(leaf_count, bool):
            merkle_ok = False
            errors.append("invalid Merkle proof metadata in receipt")
        else:
            merkle_ok = verify_inclusion_proof(
                receipt["trajectory_head"],
                receipt["merkle_leaf_index"],
                leaf_count,
                proof_raw,
                root_to_check,
            )
            if not merkle_ok:
                errors.append("Merkle inclusion proof failed verification")

    return ReceiptVerificationResult(
        valid=len(errors) == 0,
        schema_ok=schema_ok,
        manifest_ok=manifest_ok,
        commitment_ok=commitment_ok,
        trajectory_ok=trajectory_ok,
        merkle_ok=merkle_ok,
        receipt_digest=receipt_digest,
        errors=tuple(errors),
    )


__all__ = [
    "RECEIPT_INTEGRITY_NOTE",
    "ReceiptVerificationResult",
    "build_lineage_digests",
    "build_receipt",
    "compute_code_version_hash",
    "compute_manifest_hash",
    "seal_receipt_batch",
    "verify_receipt_offline",
]
