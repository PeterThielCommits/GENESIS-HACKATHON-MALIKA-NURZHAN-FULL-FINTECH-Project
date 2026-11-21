"""Versioned JSONL stdio server for TwinLedgerEnv (REQ-ARC-006).

Usage:
  python3 -m env.jsonl_server <public_dir>

Reads one JSONL ``tool_request`` per line on stdin and writes one frozen
``tool_response`` JSON line per turn on stdout. Never accesses private paths.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TextIO

from env.environment import EnvConfig, TwinLedgerEnv


def serve_stream(
    public_dir: Path | str,
    stdin: TextIO,
    stdout: TextIO,
    *,
    config: EnvConfig | None = None,
) -> int:
    """Serve JSONL tool requests until EOF or episode termination."""
    env = TwinLedgerEnv(config=config)
    init_obs = env.reset(public_dir)
    stdout.write(json.dumps({"event": "ready", "observation": init_obs}, ensure_ascii=False, sort_keys=True) + "\n")
    stdout.flush()

    for line in stdin:
        stripped = line.strip()
        if not stripped:
            continue
        resp = env.step(stripped)
        stdout.write(json.dumps(resp, ensure_ascii=False, sort_keys=True) + "\n")
        stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TwinLedger public-only JSONL environment server")
    parser.add_argument("public_dir", help="Path to episode public/ directory")
    args = parser.parse_args(argv)
    return serve_stream(Path(args.public_dir), sys.stdin, sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
