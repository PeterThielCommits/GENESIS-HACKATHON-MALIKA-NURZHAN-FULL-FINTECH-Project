"""Versioned JSONL stdio server for TwinLedgerEnv (REQ-ARC-006, REQ-SEAL-005).

Usage:
  python3 -m env.jsonl_server <public_dir> [--config <env_config.json>] [--cursor-seed <seed>]

Reads one JSONL ``tool_request`` per line on stdin and writes one canonical
frozen ``tool_response`` JSON line per turn on stdout. Never accesses private
paths and never leaks internal Python tracebacks on unexpected errors.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import TextIO

from contracts.canonical import canonical_json
from contracts.version import PROTOCOL_VERSION
from env.environment import EnvConfig, TwinLedgerEnv


def _bounded_internal_error() -> dict[str, object]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": "internal-error",
        "ok": False,
        "result": None,
        "error": {
            "code": "INTERNAL",
            "message": "bounded internal environment error",
        },
    }


def serve_stream(
    public_dir: Path | str,
    stdin: TextIO,
    stdout: TextIO,
    *,
    config: EnvConfig | None = None,
    cursor_seed: str = "episode",
) -> int:
    """Serve JSONL tool requests until EOF."""
    env = TwinLedgerEnv(config=config)
    init_obs = env.reset(public_dir, cursor_seed=cursor_seed)
    stdout.write(canonical_json({"event": "ready", "observation": init_obs}) + "\n")
    stdout.flush()

    for line in stdin:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            resp = env.step(stripped)
        except Exception:
            resp = _bounded_internal_error()
        stdout.write(canonical_json(resp) + "\n")
        stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TwinLedger public-only JSONL environment server")
    parser.add_argument("public_dir", help="Path to episode public/ directory")
    parser.add_argument("--config", default=None, help="Optional path to environment config JSON")
    parser.add_argument("--cursor-seed", default="episode", help="Deterministic cursor key label")
    args = parser.parse_args(argv)
    cfg = EnvConfig.from_file(args.config) if args.config else None
    return serve_stream(
        Path(args.public_dir),
        sys.stdin,
        sys.stdout,
        config=cfg,
        cursor_seed=args.cursor_seed,
    )


if __name__ == "__main__":
    raise SystemExit(main())
