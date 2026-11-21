"""Deterministic episode serialisation with public/sealed separation (8.6, 10.2 G17).

Layout written for each episode:

    <root>/<episode_id>/
        public/            exactly Book.public_files() — nothing else
        sealed/            truth.json, provenance.json, verifier_crosscheck.json, reject_log.json
        manifest.json      public manifest (no finding counts, no operator names)
        verifier_report.json  generator-side validation summary (public-safe)

Writes are staged then moved into place so a reader never observes a partial
episode. ``publish=False`` is used by tools that want the file map without I/O.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from contracts.canonical import canonical_json, sha256_hex
from contracts.errors import ContractError
from gen.build_episodes import EpisodePackage

FORBIDDEN_PUBLIC_NAMES = ("truth", "provenance", "sealed", "reject", "canary")


@dataclass(frozen=True)
class WrittenEpisode:
    episode_id: str
    root: Path
    public_dir: Path
    sealed_dir: Path
    manifest_path: Path
    file_hashes: Mapping[str, str]
    public_digest: str


def write_episode(episode: EpisodePackage, root: str | Path) -> WrittenEpisode:
    """Atomically write one episode to ``root/<episode_id>``."""
    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)
    target = root_path / episode.episode_id
    if target.exists():
        # Re-building the same seed must produce the same bytes; refuse silent
        # overwrites of a different package instead of mixing two episodes.
        existing_manifest = target / "manifest.json"
        if existing_manifest.exists():
            current = json.loads(existing_manifest.read_text(encoding="utf-8"))
            if current.get("public_digest") != episode.public_digest:
                raise ContractError(
                    "episode directory already exists with a different digest",
                    episode_id=episode.episode_id,
                )
            return _describe(target, episode)

    staging = Path(tempfile.mkdtemp(prefix=f".staging-{episode.episode_id}-", dir=root_path))
    try:
        public_dir = staging / "public"
        sealed_dir = staging / "sealed"
        public_dir.mkdir()
        sealed_dir.mkdir()

        hashes: dict[str, str] = {}
        for name, text in episode.public_files.items():
            _assert_public_name(name)
            path = public_dir / name
            path.write_text(text, encoding="utf-8", newline="\n")
            hashes[name] = sha256_hex(text.encode("utf-8"))

        for name, text in episode.sealed_files().items():
            (sealed_dir / name).write_text(text, encoding="utf-8", newline="\n")

        (staging / "manifest.json").write_text(
            canonical_json(episode.manifest) + "\n", encoding="utf-8", newline="\n"
        )
        (staging / "verifier_report.json").write_text(
            canonical_json(
                {
                    "report_version": "1.0.0",
                    "episode_id": episode.episode_id,
                    "mode": episode.mode,
                    "generator_invariants": "PASS",
                    "signature_decisions": [
                        decision.to_dict() for decision in episode.signature_decisions
                    ],
                    "diff_summary": episode.diff.summary(),
                    "notes": [
                        "Generator-side validation only. Independent verifier cross-check is Phase 8.",
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )

        staging.rename(target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return _describe(target, episode)


def _describe(target: Path, episode: EpisodePackage) -> WrittenEpisode:
    hashes = {
        item["name"]: str(item["sha256"]) for item in episode.manifest["public_files"]
    }
    return WrittenEpisode(
        episode_id=episode.episode_id,
        root=target,
        public_dir=target / "public",
        sealed_dir=target / "sealed",
        manifest_path=target / "manifest.json",
        file_hashes=hashes,
        public_digest=episode.public_digest,
    )


def _assert_public_name(name: str) -> None:
    lowered = name.lower()
    for forbidden in FORBIDDEN_PUBLIC_NAMES:
        if forbidden in lowered:
            raise ContractError(
                "forbidden public file name (sealed data could leak)", name=name
            )


def read_public_episode(root: str | Path) -> dict[str, Any]:
    """Load only ``public/`` + ``manifest.json`` — the policy-visible projection.

    This function is what an environment loader may use: it never touches
    ``sealed/``. It is used by the security tests to prove the separation.
    """
    root_path = Path(root)
    manifest_path = root_path / "manifest.json"
    if not manifest_path.exists():
        raise ContractError("episode manifest missing", root=str(root_path))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    public_dir = root_path / "public"
    files: dict[str, str] = {}
    for item in manifest["public_files"]:
        name = str(item["name"])
        _assert_public_name(name)
        path = public_dir / name
        if not path.is_file():
            raise ContractError("public file missing", episode_id=manifest["episode_id"], name=name)
        files[name] = path.read_text(encoding="utf-8")
    return {"manifest": manifest, "files": files}


def verify_written_episode(root: str | Path) -> dict[str, Any]:
    """Re-read an episode from disk and re-derive its hashes (REQ-DATA-021)."""
    root_path = Path(root)
    manifest = json.loads((root_path / "manifest.json").read_text(encoding="utf-8"))
    expected = {str(item["name"]): str(item["sha256"]) for item in manifest["public_files"]}
    problems: list[str] = []
    missing: list[str] = []
    mismatches: list[str] = []
    for name, digest in expected.items():
        path = root_path / "public" / name
        if not path.exists():
            missing.append(name)
            problems.append(f"missing: {name}")
            continue
        if sha256_hex(path.read_bytes()) != digest:
            mismatches.append(name)
            problems.append(f"hash mismatch: {name}")
    stray = sorted(
        path.name for path in (root_path / "public").iterdir() if path.name not in expected
    )
    if stray:
        problems.append(f"unexpected public files: {stray}")
    sealed_present = sorted(path.name for path in (root_path / "sealed").iterdir()) \
        if (root_path / "sealed").is_dir() else []
    return {
        "episode_id": manifest["episode_id"],
        "ok": not problems,
        "problems": problems,
        "public_digest": manifest["public_digest"],
        "public_file_count": len(expected) - len(missing),
        "missing_public_files": missing,
        "digest_mismatches": mismatches,
        "stray_public_files": stray,
        "sealed_files": sealed_present,
    }
