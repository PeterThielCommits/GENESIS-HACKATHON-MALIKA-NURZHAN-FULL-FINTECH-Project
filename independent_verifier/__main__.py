"""CLI for the independent re-derivation verifier.

Usage:
  python3 -m independent_verifier <episode_public_dir> [--out report.json] [--check-against committed.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from independent_verifier.runner import compare_to_committed, run_episode


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="TwinLedger independent re-derivation verifier (second implementation)"
    )
    parser.add_argument("public_dir", help="Path to an episode public/ directory")
    parser.add_argument("--out", default=None, help="Write the report JSON here")
    parser.add_argument(
        "--check-against",
        default=None,
        help="Compare signatures against a committed verifier_report.json",
    )
    args = parser.parse_args(argv)

    result = run_episode(args.public_dir)
    text = json.dumps(result.report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    if args.check_against:
        diff = compare_to_committed(result.report, args.check_against)
        sys.stdout.write(json.dumps(diff, indent=2, sort_keys=True) + "\n")
        if diff["only_committed"] or diff["only_independent"]:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
