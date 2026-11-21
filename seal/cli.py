"""Offline CLI for verifying TwinLedger commitments, hash chains, and receipts.

Usage:
  python3 -m seal.cli verify-receipt --receipt <receipt.json> [--manifest <manifest.json>]
      [--trajectory <trajectory_events.json>] [--truth <truth.json>] [--salt <salt_hex>]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from contracts.canonical import canonical_json
from seal.receipt import verify_receipt_offline


def _load_trajectory_events(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        events: list[dict[str, Any]] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            obj = json.loads(line)
            if isinstance(obj, dict) and "trajectory_event" in obj:
                events.append(obj["trajectory_event"])
            elif isinstance(obj, dict):
                events.append(obj)
        return events
    data = json.loads(text)
    if isinstance(data, dict) and "events" in data:
        return list(data["events"])
    if isinstance(data, list):
        return data
    raise ValueError(f"unsupported trajectory format in {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TwinLedger offline receipt verifier")
    sub = parser.add_subparsers(dest="cmd", required=True)

    vr = sub.add_parser("verify-receipt", help="Verify an episode receipt offline")
    vr.add_argument("--receipt", required=True, help="Path to receipt.json")
    vr.add_argument("--manifest", default=None, help="Optional path to manifest.json")
    vr.add_argument("--trajectory", default=None, help="Optional path to trajectory JSON/JSONL")
    vr.add_argument("--truth", default=None, help="Optional path to revealed truth.json")
    vr.add_argument("--salt", default=None, help="Optional revealed hex salt")
    vr.add_argument("--merkle-root", default=None, help="Optional expected batch Merkle root")

    args = parser.parse_args(argv)
    receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8")) if args.manifest else None
    traj_events = _load_trajectory_events(Path(args.trajectory)) if args.trajectory else None
    truths = json.loads(Path(args.truth).read_text(encoding="utf-8")) if args.truth else None

    res = verify_receipt_offline(
        receipt,
        manifest=manifest,
        trajectory_events=traj_events,
        revealed_truths=truths,
        revealed_salt_hex=args.salt,
        expected_merkle_root=args.merkle_root,
    )
    sys.stdout.write(canonical_json(res.to_dict()) + "\n")
    return 0 if res.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
