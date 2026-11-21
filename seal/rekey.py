"""Production CSPRNG salt re-keying for sealed episodes (Phase 9/16 — REQ-SEAL-012).

Checked-in ``dev``/``train`` episodes use deterministic ``TEST_FIXTURE`` salts
for reproducible git checkouts (REQ-SEAL-013). Before running a true hidden/sealed
``CLOSED_EVAL`` benchmark, :func:`rekey_episode_with_production_salt` draws a
fresh 256-bit CSPRNG salt via :func:`secrets.token_hex`, recomputes
``truth_commitment``, updates ``manifest.json`` and ``sealed/provenance.json``
with ``salt_mode = "PRODUCTION_SECRET"``, and verifies reveal in constant time.

Zone 2 rule: imports ONLY ``contracts``, ``seal.*``, and Python 3.11 stdlib.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from contracts.canonical import canonical_json
from contracts.loader import validate_instance
from seal.commitment import (
    compute_commitment,
    generate_secret_salt,
    verify_reveal,
)


@dataclass(frozen=True)
class ProductionRekeyResult:
    episode_id: str
    old_commitment: str
    new_commitment: str
    salt_mode: str
    verified: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "old_commitment": self.old_commitment,
            "new_commitment": self.new_commitment,
            "salt_mode": self.salt_mode,
            "verified": self.verified,
        }


def rekey_episode_with_production_salt(
    episode_dir: Path | str,
    *,
    num_bytes: int = 32,
) -> ProductionRekeyResult:
    """Replace ``TEST_FIXTURE`` salt on ``episode_dir`` with a fresh CSPRNG ``PRODUCTION_SECRET`` salt."""
    ep = Path(episode_dir).resolve()
    manifest_path = ep / "manifest.json"
    truth_path = ep / "sealed" / "truth.json"
    prov_path = ep / "sealed" / "provenance.json"

    if not manifest_path.is_file() or not truth_path.is_file() or not prov_path.is_file():
        raise FileNotFoundError(f"episode missing manifest.json or sealed truth/provenance: {ep}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    truths = json.loads(truth_path.read_text(encoding="utf-8"))
    prov = json.loads(prov_path.read_text(encoding="utf-8"))

    old_commitment = str(manifest["truth_commitment"])
    secret_salt = generate_secret_salt(num_bytes)
    new_commitment = compute_commitment(truths, secret_salt)

    reveal_check = verify_reveal(
        new_commitment,
        truths,
        secret_salt,
        salt_mode="PRODUCTION_SECRET",
    )
    if not reveal_check.verified:
        raise RuntimeError(f"production rekey verification failed: {reveal_check.errors}")

    manifest["truth_commitment"] = new_commitment
    m_errs = validate_instance("episode_manifest", manifest)
    if m_errs:
        raise ValueError(f"updated manifest failed schema validation: {m_errs}")

    prov["commitment_salt_hex"] = secret_salt
    prov["salt_mode"] = "PRODUCTION_SECRET"

    manifest_path.write_text(canonical_json(manifest) + "\n", encoding="utf-8")
    prov_path.write_text(canonical_json(prov) + "\n", encoding="utf-8")

    return ProductionRekeyResult(
        episode_id=str(manifest["episode_id"]),
        old_commitment=old_commitment,
        new_commitment=new_commitment,
        salt_mode="PRODUCTION_SECRET",
        verified=True,
    )


__all__ = [
    "ProductionRekeyResult",
    "rekey_episode_with_production_salt",
]
