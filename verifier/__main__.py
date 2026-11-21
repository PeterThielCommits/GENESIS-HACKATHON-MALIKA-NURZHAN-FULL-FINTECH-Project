"""CLI entry point for Stage-1 public-only verifier discovery.

Usage:
  python3 -m verifier <public_dir> [--out verifier_report.json] [--proof-graph proof_graph.json] [--no-ablation]

Accepts ONLY a public episode directory. Never reads private directories.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from verifier.discover import discover
from verifier.result import VerifierConfig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="TwinLedger independent public-only verifier (Stage 1)"
    )
    parser.add_argument("public_dir", help="Path to the episode public/ directory")
    parser.add_argument(
        "--out",
        default=None,
        help="Optional output path for verifier_report.json",
    )
    parser.add_argument(
        "--proof-graph",
        default=None,
        help="Optional output path for private ProofGraph DAG JSON",
    )
    parser.add_argument(
        "--no-ablation",
        action="store_true",
        help="Skip minimal-evidence ablation re-runs",
    )
    args = parser.parse_args(argv)

    config = VerifierConfig(run_ablation=not args.no_ablation)
    output = discover(Path(args.public_dir), verifier_config=config)
    report_text = json.dumps(output.report.to_dict(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_text, encoding="utf-8")
    else:
        sys.stdout.write(report_text)

    if args.proof_graph:
        pg_path = Path(args.proof_graph)
        pg_path.parent.mkdir(parents=True, exist_ok=True)
        pg_text = (
            json.dumps(output.proof_graph.to_dict(), indent=2, ensure_ascii=False, sort_keys=True)
            + "\n"
        )
        pg_path.write_text(pg_text, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
