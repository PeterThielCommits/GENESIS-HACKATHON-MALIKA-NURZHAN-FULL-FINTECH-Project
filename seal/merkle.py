"""RFC-6962-style domain-separated SHA-256 Merkle tree over trajectory heads (Phase 9, Task 9.6).

Formal specification (Master TZ v3.0.0 §16.5, REQ-SEAL-022..023):
  1. Leaf order: deterministic sequence ``leaves[0 .. n-1]`` where each input
     leaf is a 64-char lowercase hex SHA-256 ``trajectory_head``.
  2. Empty tree (``n == 0``):
     ``EMPTY_TREE_ROOT = SHA256(b"twinledger:merkle:empty:v1")``.
  3. Leaf domain separation (``0x00`` prefix):
     ``L_i = SHA256(b"\\x00" + bytes.fromhex(leaves[i]))``.
  4. Internal node domain separation (``0x01`` prefix):
     ``Node(left, right) = SHA256(b"\\x01" + bytes.fromhex(left) + bytes.fromhex(right))``.
  5. Odd-node handling: RFC-6962 odd-node promotion (no self-duplication).
     When a tree level has ``2k + 1`` nodes, pairs ``(0,1), ..., (2k-2,2k-1)``
     are combined with ``Node(left, right)``, while the trailing odd node
     ``2k`` is promoted unchanged to the next level. Combined with ``0x00``/``0x01``
     domain separation and topology-aware proof verification, this eliminates
     both interior/leaf confusion and odd-leaf duplication second-preimage attacks.

Note (REQ-SEAL-023): A Merkle root proves batch integrity of recorded
trajectory heads; it is NOT a proof of finding semantic quality.

Imports ONLY ``contracts/`` and Python 3.11 stdlib (obeys ``seal/`` boundary).
"""

from __future__ import annotations

import hashlib
import hmac
import re
import struct
from dataclasses import dataclass
from typing import Any, Sequence

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

LEAF_DOMAIN_PREFIX = b"\x00"
NODE_DOMAIN_PREFIX = b"\x01"
ROOT_DOMAIN_PREFIX = b"\x02"
EMPTY_TREE_ROOT = hashlib.sha256(b"twinledger:merkle:empty:v1").hexdigest()


def _require_hex64(value: str, label: str) -> str:
    if not isinstance(value, str) or not _HEX64_RE.match(value):
        raise ValueError(f"{label} must be a 64-char lowercase hex SHA-256")
    return value


def leaf_hash(raw_leaf_hex: str) -> str:
    """Compute domain-separated leaf node hash ``SHA256(0x00 || raw_leaf_bytes)``."""
    _require_hex64(raw_leaf_hex, "raw_leaf_hex")
    return hashlib.sha256(LEAF_DOMAIN_PREFIX + bytes.fromhex(raw_leaf_hex)).hexdigest()


def internal_node_hash(left_hex: str, right_hex: str) -> str:
    """Compute domain-separated internal node hash ``SHA256(0x01 || left || right)``."""
    _require_hex64(left_hex, "left_hex")
    _require_hex64(right_hex, "right_hex")
    return hashlib.sha256(
        NODE_DOMAIN_PREFIX + bytes.fromhex(left_hex) + bytes.fromhex(right_hex)
    ).hexdigest()


def finalize_root_hash(top_node_hex: str, leaf_count: int) -> str:
    """Bind ``leaf_count`` into the root via ``SHA256(0x02 || uint64_be(leaf_count) || top_node)``."""
    _require_hex64(top_node_hex, "top_node_hex")
    if type(leaf_count) is not int or isinstance(leaf_count, bool) or leaf_count < 1:
        raise ValueError("leaf_count must be a positive integer")
    return hashlib.sha256(
        ROOT_DOMAIN_PREFIX + struct.pack(">Q", leaf_count) + bytes.fromhex(top_node_hex)
    ).hexdigest()


@dataclass(frozen=True)
class MerkleProofStep:
    """One sibling hash step along an inclusion path from leaf to root."""

    position: str  # "left" or "right" (position of the sibling relative to current node)
    sibling_hash: str

    def __post_init__(self) -> None:
        if self.position not in ("left", "right"):
            raise ValueError(f"position must be 'left' or 'right', got {self.position!r}")
        _require_hex64(self.sibling_hash, "sibling_hash")

    def to_dict(self) -> dict[str, str]:
        return {"position": self.position, "sibling_hash": self.sibling_hash}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MerkleProofStep":
        if not isinstance(data, dict):
            raise ValueError("MerkleProofStep must be a JSON object")
        return cls(
            position=str(data.get("position", "")),
            sibling_hash=str(data.get("sibling_hash", "")),
        )


def _expected_positions_for_index(leaf_index: int, leaf_count: int) -> list[str]:
    """Compute exact sibling positions implied by ``(leaf_index, leaf_count)`` topology."""
    positions: list[str] = []
    idx = leaf_index
    width = leaf_count
    while width > 1:
        if idx % 2 == 0:
            if idx + 1 < width:
                positions.append("right")
            # else: odd trailing node promoted without a sibling at this level
        else:
            positions.append("left")
        idx //= 2
        width = (width + 1) // 2
    return positions


class MerkleTree:
    """Immutable SHA-256 Merkle tree with inclusion proof generation."""

    def __init__(self, raw_leaves: Sequence[str]) -> None:
        validated = tuple(_require_hex64(h, f"leaves[{i}]") for i, h in enumerate(raw_leaves))
        self._raw_leaves = validated
        if not validated:
            self._levels: tuple[tuple[str, ...], ...] = ()
            self._root = EMPTY_TREE_ROOT
            return

        levels: list[tuple[str, ...]] = [tuple(leaf_hash(h) for h in validated)]
        current = levels[0]
        while len(current) > 1:
            next_level: list[str] = []
            i = 0
            while i < len(current):
                if i + 1 < len(current):
                    next_level.append(internal_node_hash(current[i], current[i + 1]))
                    i += 2
                else:
                    # RFC-6962 odd-node promotion (no self-duplication)
                    next_level.append(current[i])
                    i += 1
            current = tuple(next_level)
            levels.append(current)
        self._levels = tuple(levels)
        self._root = finalize_root_hash(levels[-1][0], len(validated))

    @classmethod
    def from_leaves(cls, raw_leaves: Sequence[str]) -> "MerkleTree":
        return cls(raw_leaves)

    @property
    def leaf_count(self) -> int:
        return len(self._raw_leaves)

    @property
    def leaves(self) -> tuple[str, ...]:
        return self._raw_leaves

    @property
    def root(self) -> str:
        return self._root

    def inclusion_proof(self, leaf_index: int) -> tuple[MerkleProofStep, ...]:
        """Build an inclusion proof for ``leaves[leaf_index]``."""
        if type(leaf_index) is not int or isinstance(leaf_index, bool):
            raise ValueError("leaf_index must be an int")
        if not (0 <= leaf_index < len(self._raw_leaves)):
            raise IndexError(f"leaf_index {leaf_index} out of range for {len(self._raw_leaves)} leaves")

        steps: list[MerkleProofStep] = []
        idx = leaf_index
        for level in self._levels[:-1]:
            if idx % 2 == 0:
                if idx + 1 < len(level):
                    steps.append(MerkleProofStep(position="right", sibling_hash=level[idx + 1]))
            else:
                steps.append(MerkleProofStep(position="left", sibling_hash=level[idx - 1]))
            idx //= 2
        return tuple(steps)


def verify_inclusion_proof(
    raw_leaf_hex: str,
    leaf_index: int,
    leaf_count: int,
    proof: Sequence[MerkleProofStep | dict[str, Any]],
    expected_root: str,
) -> bool:
    """Verify an inclusion proof offline against ``expected_root`` and tree topology."""
    try:
        _require_hex64(raw_leaf_hex, "raw_leaf_hex")
        _require_hex64(expected_root, "expected_root")
    except ValueError:
        return False

    if (
        type(leaf_index) is not int
        or isinstance(leaf_index, bool)
        or type(leaf_count) is not int
        or isinstance(leaf_count, bool)
        or leaf_count < 1
        or not (0 <= leaf_index < leaf_count)
    ):
        return False

    expected_positions = _expected_positions_for_index(leaf_index, leaf_count)
    if len(proof) != len(expected_positions):
        return False

    curr = leaf_hash(raw_leaf_hex)
    for step_raw, expected_pos in zip(proof, expected_positions):
        try:
            step = step_raw if isinstance(step_raw, MerkleProofStep) else MerkleProofStep.from_dict(step_raw)
        except ValueError:
            return False
        if step.position != expected_pos:
            return False
        if step.position == "left":
            curr = internal_node_hash(step.sibling_hash, curr)
        else:
            curr = internal_node_hash(curr, step.sibling_hash)

    final_root = finalize_root_hash(curr, leaf_count)
    return hmac.compare_digest(final_root, expected_root)


__all__ = [
    "EMPTY_TREE_ROOT",
    "LEAF_DOMAIN_PREFIX",
    "NODE_DOMAIN_PREFIX",
    "ROOT_DOMAIN_PREFIX",
    "MerkleProofStep",
    "MerkleTree",
    "finalize_root_hash",
    "internal_node_hash",
    "leaf_hash",
    "verify_inclusion_proof",
]
