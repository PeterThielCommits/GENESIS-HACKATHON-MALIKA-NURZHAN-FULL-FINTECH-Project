"""Commit-reveal cryptographic primitives for sealed truth (Phase 9, Task 9.4).

Implements Master TZ v3.0.0 §16.3 and REQ-SEAL-010..013:
  - ``commitment = canonical_sha256({"salt": salt_hex, "truths": list(truths)})``
    (byte-identical to ``gen/truth.py::compute_truth_commitment``);
  - ``generate_secret_salt`` uses Python's OS CSPRNG (``secrets.token_hex``);
  - ``deterministic_fixture_salt`` explicitly tags reproducible test salts with
    ``mode="TEST_FIXTURE"`` so they are never presented as production secrets
    (REQ-SEAL-013);
  - ``verify_reveal`` checks frozen ``truth.schema.json`` compliance and
    constant-time digest equality (``hmac.compare_digest``).

Important architectural boundary (TZ §16.3, R-10):
  A valid commitment reveal proves ONLY that canonical truth bytes were not
  modified after the commitment was published in ``manifest.json``. Semantic
  correctness of the truth itself is established separately via counterfactual
  twin diff, accounting invariants, and the independent public-only verifier.

Imports ONLY ``contracts/`` and Python 3.11 stdlib (obeys ``seal/`` boundary).
"""

from __future__ import annotations

import hmac
import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from contracts.canonical import sha256_hex as canonical_sha256
from contracts.loader import validate_instance
from contracts.models import TruthFinding

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_SALT_HEX_RE = re.compile(r"^[0-9a-f]{32,256}$")

SALT_MODES = ("PRODUCTION_SECRET", "TEST_FIXTURE")

COMMITMENT_INTEGRITY_NOTE = (
    "Commit-reveal proves immutability of canonical truth bytes after "
    "commitment publication; it does not by itself prove semantic validity "
    "of initial truth (verified separately by diff, invariants, and verifier)."
)


def generate_secret_salt(num_bytes: int = 32) -> str:
    """Generate a fresh CSPRNG hex salt (>= 16 bytes / 32 hex chars, REQ-SEAL-012)."""
    if type(num_bytes) is not int or isinstance(num_bytes, bool) or num_bytes < 16:
        raise ValueError("num_bytes must be an integer >= 16")
    return secrets.token_hex(num_bytes)


def deterministic_fixture_salt(fixture_label: str) -> tuple[str, str]:
    """Derive a reproducible test-fixture salt explicitly tagged ``TEST_FIXTURE`` (REQ-SEAL-013)."""
    if not isinstance(fixture_label, str) or not fixture_label.strip():
        raise ValueError("fixture_label must be a non-empty string")
    digest = hashlib.sha256(
        f"twinledger:test-fixture-salt:v1|{fixture_label}".encode("utf-8")
    ).hexdigest()
    return digest, "TEST_FIXTURE"


def _normalize_truth_items(
    truths: Sequence[dict[str, Any] | TruthFinding],
) -> tuple[list[dict[str, Any]], list[str]]:
    normalized: list[dict[str, Any]] = []
    errors: list[str] = []
    seen_ids: set[str] = set()
    for idx, item in enumerate(truths):
        raw = item.to_dict() if isinstance(item, TruthFinding) else item
        if not isinstance(raw, dict):
            errors.append(f"truth[{idx}]: expected object, got {type(raw).__name__}")
            continue
        schema_errs = validate_instance("truth", raw)
        for err in schema_errs:
            errors.append(f"truth[{idx}]: {err}")
        tid = raw.get("truth_id")
        if isinstance(tid, str):
            if tid in seen_ids:
                errors.append(f"truth[{idx}]: duplicate truth_id")
            seen_ids.add(tid)
        normalized.append(raw)
    return normalized, errors


def compute_commitment(
    truths: Sequence[dict[str, Any] | TruthFinding],
    salt_hex: str,
) -> str:
    """Compute salted SHA-256 commitment over canonical truth findings (REQ-SEAL-010).

    Uses the exact canonical payload ``{"salt": salt_hex, "truths": list(truths)}``
    established in ``gen/truth.py`` so all generated episode manifests verify
    identically.
    """
    if not isinstance(salt_hex, str) or not _SALT_HEX_RE.match(salt_hex):
        raise ValueError("salt_hex must be 32..256 lowercase hex characters")
    items, errors = _normalize_truth_items(truths)
    if errors:
        raise ValueError(f"invalid truth findings for commitment: {errors[0]}")
    return canonical_sha256({"salt": salt_hex, "truths": items})


@dataclass(frozen=True)
class CommitmentBundle:
    """Pre-episode public commitment metadata (never exposes salt or truth)."""

    episode_id: str
    truth_commitment: str
    salt_mode: str = "PRODUCTION_SECRET"
    created_before_policy: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.episode_id, str) or not (1 <= len(self.episode_id) <= 128):
            raise ValueError("episode_id must be 1..128 chars")
        if not isinstance(self.truth_commitment, str) or not _HEX64_RE.match(self.truth_commitment):
            raise ValueError("truth_commitment must be a 64-char lowercase hex SHA-256")
        if self.salt_mode not in SALT_MODES:
            raise ValueError(f"salt_mode must be one of {SALT_MODES}")
        if not self.created_before_policy:
            raise ValueError("commitment must be created before policy execution (REQ-SEAL-010)")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "truth_commitment": self.truth_commitment,
            "created_before_policy": self.created_before_policy,
        }


@dataclass(frozen=True)
class RevealResult:
    """Outcome of post-episode commit-reveal verification (REQ-SEAL-011)."""

    verified: bool
    expected_commitment: str
    recomputed_commitment: str | None
    truth_count: int
    salt_mode: str
    errors: tuple[str, ...]
    integrity_scope_note: str = COMMITMENT_INTEGRITY_NOTE

    def to_dict(self) -> dict[str, Any]:
        return {
            "verified": self.verified,
            "expected_commitment": self.expected_commitment,
            "recomputed_commitment": self.recomputed_commitment,
            "truth_count": self.truth_count,
            "salt_mode": self.salt_mode,
            "errors": list(self.errors),
            "integrity_scope_note": self.integrity_scope_note,
        }


def create_commitment_bundle(
    episode_id: str,
    truths: Sequence[dict[str, Any] | TruthFinding],
    *,
    salt_hex: str | None = None,
    salt_mode: str = "PRODUCTION_SECRET",
) -> tuple[CommitmentBundle, str]:
    """Create a pre-episode commitment bundle and return ``(bundle, secret_salt_hex)``."""
    if salt_mode not in SALT_MODES:
        raise ValueError(f"salt_mode must be one of {SALT_MODES}")
    actual_salt = salt_hex if salt_hex is not None else generate_secret_salt(32)
    commitment = compute_commitment(truths, actual_salt)
    bundle = CommitmentBundle(
        episode_id=episode_id,
        truth_commitment=commitment,
        salt_mode=salt_mode,
        created_before_policy=True,
    )
    return bundle, actual_salt


def verify_reveal(
    expected_commitment: str,
    truths: Sequence[dict[str, Any] | TruthFinding],
    salt_hex: str,
    *,
    salt_mode: str = "PRODUCTION_SECRET",
) -> RevealResult:
    """Verify post-episode truth reveal against published commitment (REQ-SEAL-011)."""
    errors: list[str] = []
    if not isinstance(expected_commitment, str) or not _HEX64_RE.match(expected_commitment):
        errors.append("expected_commitment is not a valid 64-char lowercase hex SHA-256")
    if salt_mode not in SALT_MODES:
        errors.append(f"invalid salt_mode: {salt_mode!r}")
    if not isinstance(salt_hex, str) or not _SALT_HEX_RE.match(salt_hex):
        errors.append("salt_hex is not a valid 32..256 lowercase hex string")
    if not isinstance(truths, (list, tuple)):
        return RevealResult(
            verified=False,
            expected_commitment=str(expected_commitment),
            recomputed_commitment=None,
            truth_count=0,
            salt_mode=str(salt_mode),
            errors=(*errors, "truths must be a sequence"),
        )

    items, item_errors = _normalize_truth_items(truths)
    errors.extend(item_errors)
    if errors:
        return RevealResult(
            verified=False,
            expected_commitment=str(expected_commitment),
            recomputed_commitment=None,
            truth_count=len(items),
            salt_mode=str(salt_mode),
            errors=tuple(errors),
        )

    recomputed = canonical_sha256({"salt": salt_hex, "truths": items})
    matched = hmac.compare_digest(expected_commitment, recomputed)
    if not matched:
        errors.append("recomputed truth commitment does not match published commitment")

    return RevealResult(
        verified=matched,
        expected_commitment=expected_commitment,
        recomputed_commitment=recomputed,
        truth_count=len(items),
        salt_mode=salt_mode,
        errors=tuple(errors),
    )


def verify_episode_commitment_from_disk(
    episode_dir: Path | str,
    *,
    salt_mode: str = "TEST_FIXTURE",
) -> RevealResult:
    """Verify ``manifest.json`` commitment against ``sealed/truth.json`` and ``sealed/provenance.json``."""
    ep_path = Path(episode_dir)
    manifest_path = ep_path / "manifest.json"
    truth_path = ep_path / "sealed" / "truth.json"
    prov_path = ep_path / "sealed" / "provenance.json"

    if not manifest_path.is_file():
        return RevealResult(
            verified=False,
            expected_commitment="",
            recomputed_commitment=None,
            truth_count=0,
            salt_mode=salt_mode,
            errors=("missing manifest.json",),
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return RevealResult(
            verified=False,
            expected_commitment="",
            recomputed_commitment=None,
            truth_count=0,
            salt_mode=salt_mode,
            errors=("malformed manifest.json",),
        )
    expected = str(manifest.get("truth_commitment", ""))
    if not truth_path.is_file() or not prov_path.is_file():
        return RevealResult(
            verified=False,
            expected_commitment=expected,
            recomputed_commitment=None,
            truth_count=0,
            salt_mode=salt_mode,
            errors=("missing sealed truth.json or provenance.json",),
        )
    try:
        truths = json.loads(truth_path.read_text(encoding="utf-8"))
        prov = json.loads(prov_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return RevealResult(
            verified=False,
            expected_commitment=expected,
            recomputed_commitment=None,
            truth_count=0,
            salt_mode=salt_mode,
            errors=("malformed sealed JSON",),
        )
    salt_hex = prov.get("commitment_salt_hex", "")
    return verify_reveal(expected, truths, salt_hex, salt_mode=salt_mode)


__all__ = [
    "COMMITMENT_INTEGRITY_NOTE",
    "SALT_MODES",
    "CommitmentBundle",
    "RevealResult",
    "compute_commitment",
    "create_commitment_bundle",
    "deterministic_fixture_salt",
    "generate_secret_salt",
    "verify_episode_commitment_from_disk",
    "verify_reveal",
]
