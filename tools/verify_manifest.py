#!/usr/bin/env python3
"""Manifest verifier CLI (REQ-DATA-021). Checks schema and public file SHA-256 hashes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gen.serialize import verify_episode_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify episode manifest hashes (REQ-DATA-021)")
    parser.add_argument("episode", help="Episode directory containing manifest.json and public/")
    args = parser.parse_args(argv)

    errors = verify_episode_manifest(Path(args.episode))
    if errors:
        print(f"verify_manifest: FAIL ({len(errors)} errors):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(f"verify_manifest: PASS ({args.episode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
