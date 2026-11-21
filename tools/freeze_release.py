#!/usr/bin/env python3
"""Post-Release Evidence Freeze & Contract Immutability Verifier (Phase 17 — TZ §26.17).

Computes and verifies cryptographic SHA-256 digests over all frozen benchmark
surfaces:
  - ``contracts/*.json`` and ``contracts/*.py``
  - ``configs/**/*.json``
  - ``judge/rubric_map.json``
  - ``docs/reference/TwinLedger_v3_Master_TZ_AI_Agents.txt``

Modes:
  - ``python3 tools/freeze_release.py --write``  : write ``configs/release_freeze.json``
  - ``python3 tools/freeze_release.py --verify`` : verify zero drift against ``configs/release_freeze.json``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from contracts.canonical import canonical_json

DEFAULT_FREEZE_MANIFEST = REPO_ROOT / "configs" / "release_freeze.json"


def _collect_frozen_paths() -> list[Path]:
    paths: list[Path] = []
    for p in sorted((REPO_ROOT / "contracts").rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix in (".json", ".py"):
            paths.append(p)
    for p in sorted((REPO_ROOT / "configs").rglob("*.json")):
        if p.is_file() and p.resolve() != DEFAULT_FREEZE_MANIFEST.resolve():
            paths.append(p)
    rubric = REPO_ROOT / "judge" / "rubric_map.json"
    if rubric.is_file():
        paths.append(rubric)
    tz_ref = REPO_ROOT / "docs" / "reference" / "TwinLedger_v3_Master_TZ_AI_Agents.txt"
    if tz_ref.is_file():
        paths.append(tz_ref)
    return paths


def compute_freeze_manifest() -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for p in _collect_frozen_paths():
        raw = p.read_bytes()
        entries.append(
            {
                "path": p.relative_to(REPO_ROOT).as_posix(),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    tree_hash = hashlib.sha256(canonical_json(entries).encode("utf-8")).hexdigest()
    return {
        "schema_version": "1.0.0",
        "release_version": "twinledger@1.0.0",
        "frozen_file_count": len(entries),
        "aggregate_sha256": tree_hash,
        "files": entries,
    }


def verify_freeze_manifest(manifest_path: Path = DEFAULT_FREEZE_MANIFEST) -> tuple[bool, list[str]]:
    if not manifest_path.is_file():
        return False, [f"missing freeze manifest: {manifest_path}"]
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    current = compute_freeze_manifest()

    errors: list[str] = []
    exp_map = {e["path"]: e["sha256"] for e in expected.get("files", [])}
    cur_map = {e["path"]: e["sha256"] for e in current.get("files", [])}

    for path_key in sorted(set(exp_map) | set(cur_map)):
        if path_key not in exp_map:
            errors.append(f"untracked new file in frozen surface: {path_key}")
        elif path_key not in cur_map:
            errors.append(f"missing frozen file: {path_key}")
        elif exp_map[path_key] != cur_map[path_key]:
            errors.append(f"SHA-256 drift in frozen file {path_key}: expected {exp_map[path_key]}, got {cur_map[path_key]}")

    if expected.get("aggregate_sha256") != current.get("aggregate_sha256"):
        errors.append("aggregate_sha256 mismatch")
    return len(errors) == 0, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TwinLedger post-release freeze manifest tool")
    parser.add_argument("--write", action="store_true", help="Write/update configs/release_freeze.json")
    parser.add_argument("--verify", action="store_true", help="Verify zero drift against configs/release_freeze.json")
    args = parser.parse_args(argv)

    if args.write:
        doc = compute_freeze_manifest()
        DEFAULT_FREEZE_MANIFEST.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(
            f"[PASS] freeze_release --write: {doc['frozen_file_count']} files frozen "
            f"(aggregate_sha256={doc['aggregate_sha256'][:16]}...) -> {DEFAULT_FREEZE_MANIFEST}"
        )
        return 0

    ok, errs = verify_freeze_manifest()
    if ok:
        doc = json.loads(DEFAULT_FREEZE_MANIFEST.read_text(encoding="utf-8"))
        print(
            f"[PASS] freeze_release --verify: {doc['frozen_file_count']} frozen files intact "
            f"(aggregate_sha256={doc['aggregate_sha256'][:16]}...)"
        )
        return 0
    print(f"[FAIL] freeze_release --verify ({len(errs)} errors):", file=sys.stderr)
    for e in errs:
        print(f"  - {e}", file=sys.stderr)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
